# 🛠️ Technical Architecture & Engineering Deep-Dive (`v0.1.0-beta`)

## 1. Three-Pillar Ecosystem Architecture

**NVR Cast Hub** is a complete multi-component software suite consisting of three integrated modules:

1. **Native Desktop Application & Universal RTSP Engine ([`desktop_app/`](../desktop_app/))**
   - [`desktop_app/engine.py`](../desktop_app/engine.py): Manages the MediaMTX RTSP server (`:554`), dual-stream FFmpeg encoding pipeline (`/main` and `/sub`), `yt-dlp` stream extraction, `WinSta0\Default` multi-monitor screen capture (`mss`), and WASAPI PC Speaker Audio Loopback (`pyaudiowpatch`).
   - [`desktop_app/gui.py`](../desktop_app/gui.py): Native Windows Tkinter Control Center providing 1-click RTSP URL copying, monitor selection checkboxes, quality/codec tuning, and live server logs.
2. **Browser Web Cast Studio & Mobile Remote ([`web_studio/`](../web_studio/))**
   - [`web_studio/server.py`](../web_studio/server.py): Embedded multithreaded HTTP & WebM chunk streaming server (`http://localhost:8090` and `http://<LAN-IP>:8090`).
   - Enables **Google-Meet-style Browser Tab / Window / Screen sharing with audio** via `navigator.mediaDevices.getDisplayMedia()` + `MediaRecorder` (`video/webm;codecs=vp8,opus`), piping 200ms media chunks directly into FFmpeg's `pipe:0` stdin.
   - Doubles as a **Mobile Phone Remote** on your home/office Wi-Fi.
3. **Browser Extension ([`chrome_extension/`](../chrome_extension/))**
   - [`chrome_extension/content_youtube.js`](../chrome_extension/content_youtube.js): Injects a native **`📺 Cast to NVR`** button directly inside the YouTube video player bar, capturing the video URL and current playback timestamp (`currentTime`) to seamlessly transfer playback onto the NVR monitor.
   - [`chrome_extension/popup.html`](../chrome_extension/popup.html) & [`popup.js`](../chrome_extension/popup.js): Toolbar remote for casting any open tab's video, starting Meeting Share, or switching between Monitor 1, Monitor 2, and All Monitors.

---

## 2. How We Solved the 5 Core NVR Hardware & Firmware Roadblocks

### Roadblock #1: The Hikvision Firmware Malformed RTSP URI Bug (`rtsp:192.168.x.x/main`)
When adding a Custom RTSP camera to many Hikvision NVRs, the NVR firmware omits the double slash `//` in its RTSP handshake:
```http
DESCRIBE rtsp:192.168.100.49:554/main RTSP/1.0
```
Standard RTSP servers fail to parse `rtsp:192.168.100.49:554/main` as a standard URL and treat `rtsp:192.168.100.49:554/main` as the **path name**, rejecting it because `:` is forbidden by default path regexes (`^[0-9a-zA-Z_\-/\.]+$`).
- **Our Solution:** [`ensure_mediamtx()`](../desktop_app/engine.py) automatically applies a 20-byte binary patch to `mediamtx.exe` (`^[0-9a-zA-Z_\-/\.]+$` $\rightarrow$ `^[0-9a-zA-Z_\-/.:]+$`) and configures wildcard `sourceOnDemand` rules in `mediamtx.yml` so both standard RTSP clients (Dahua, Uniview, Reolink, VLC) and quirky Hikvision firmware connect instantaneously.

### Roadblock #2: NVR Hardware Decoder Rejects ("No Network Video")
Hardware ASIC decoders inside NVRs reject high-profile H.264 streams containing B-frames (`-bf > 0`), 4:4:4 chroma subsampling, or long keyframe intervals, and require a low-resolution **Sub-Stream** for multi-camera grid views.
- **Our Solution:** [`_build_dual_output_args()`](../desktop_app/engine.py) uses an FFmpeg `split=2` filter graph to simultaneously push `/main` (1080p/720p HD) and `/sub` (`640x360` SD) using `libx264 -profile:v baseline -level 3.1 -pix_fmt yuv420p -bf 0 -g 50`.

### Roadblock #3: Getting Live Audio Out of the NVR Monitor Speakers
Most CCTV NVRs ignore high-bitrate stereo AAC audio tracks over RTSP and strictly expect **ITU-T G.711** telephony/CCTV audio.
- **Our Solution:** Default audio encoding uses **`G.711 ulaw` (`pcm_mulaw`, 8000 Hz, mono)**, with instant switching in the GUI/Web Studio to `G.711 alaw` (`pcm_alaw`), `AAC 16kHz Mono`, or `AAC 44.1kHz Stereo`.

### Roadblock #4: Multi-Monitor Desktop Capture & Continuous WASAPI Loopback Audio
- **Our Solution:** [`start_screen_cast()`](../desktop_app/engine.py) binds worker threads to the active interactive Windows desktop (`OpenDesktopW("Default")` + `SetThreadDesktop`), dynamically computes bounding boxes for any combination of monitors (including mixed Landscape `1920x1080` + Portrait `1080x1920`), overlays a high-contrast cursor, and streams WASAPI loopback audio with automatic `40ms` zero-byte silence padding so FFmpeg never stalls when PC speakers are silent.
