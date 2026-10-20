# 🛠️ Technical Architecture & Engineering Deep-Dive (`v0.1.0-beta`)

## 1. Three-Pillar Ecosystem Architecture

**NVR Cast Hub** is a complete multi-component software suite consisting of three integrated modules:

1. **Native Desktop Application, Hardware Player & Universal RTSP Engine ([`desktop_app/`](../desktop_app/))**
   - [`desktop_app/engine.py`](../desktop_app/engine.py): Manages the MediaMTX RTSP server (`:554`), 2-stage pre-buffered MPEG-TS ring-buffer pipeline (`75 MB`), dual-stream FFmpeg encoding pipeline (`/main` and `/sub`), 3-way output routing (`preview_only`, `both`, `nvr_only`), `yt-dlp` stream & playlist extraction, `WinSta0\Default` multi-monitor screen capture (`mss`), and WASAPI PC Speaker Audio Loopback (`pyaudiowpatch`).
   - [`desktop_app/local_player.py`](../desktop_app/local_player.py): Embedded **libVLC Hardware-Accelerated PC Player** (`DXVA2` / `D3D11VA`) with native Win32 `HWND` window reparenting (`SetParent` / `MoveWindow`) across the Main Studio Canvas, Floating Always-On-Top Picture-in-Picture (PiP) Mini-Player, and 100% Full-Screen TV Mode without interrupting playback.
   - [`desktop_app/sports_channels.py`](../desktop_app/sports_channels.py): Curated catalog of 24+ built-in Pakistani Live TV & Cricket channels, live GitHub M3U IPTV repository fetcher (`iptv-org` Pakistan, Sports, Cricket), custom M3U parser, and persistent configuration manager (`config/nvr_cast_config.json` & `config/NVR_Cast_Hub_Channels_VLC.m3u`).
   - [`desktop_app/gui.py`](../desktop_app/gui.py): Modern Dark Broadcast Studio Control Center providing a live stage player, transparent stream health diagnostics (`PROBING` → `BUFFERING` → `LIVE` → `OFFLINE/ERROR`), 3-way output routing selector, PiP & Full-Screen toggles, Pakistani TV / Cricket channel grid, and config import/export.
2. **Browser Web Cast Studio & Mobile Remote ([`web_studio/`](../web_studio/))**
   - [`web_studio/server.py`](../web_studio/server.py): Embedded multithreaded HTTP & WebM chunk streaming server (`http://localhost:8090` and `http://<LAN-IP>:8090`).
   - Enables **Google-Meet-style Browser Tab / Window / Screen sharing with audio** via `navigator.mediaDevices.getDisplayMedia()` + `MediaRecorder` (`video/webm;codecs=vp8,opus`), piping media chunks directly into FFmpeg's `pipe:0` stdin.
   - Includes a dedicated **🏏 Live Sports, Cricket & Pakistani TV Tab**, **YouTube Playlist Queue Auto-Advance**, and **Channel Configuration Import/Export**.
   - Doubles as a **Mobile Phone Remote** on your home/office Wi-Fi.
3. **Browser Extension ([`chrome_extension/`](../chrome_extension/))**
   - [`chrome_extension/content_youtube.js`](../chrome_extension/content_youtube.js): Injects a native **`📺 Cast to NVR`** button into YouTube and web video players, supporting both real-time playback sync and direct HTML5 `<video>.captureStream()` background tab streaming (using a background Web Audio oscillator to prevent Chrome background-tab throttling).
   - [`chrome_extension/popup.html`](../chrome_extension/popup.html) & [`popup.js`](../chrome_extension/popup.js): Toolbar remote for casting any open tab's live video feed, starting Meeting Share, or switching between Monitor 1, Monitor 2, and All Monitors.

---

## 2. How We Solved Core NVR Hardware, Firmware & PC Streaming Roadblocks

### Roadblock #1: The Hikvision Firmware Malformed RTSP URI Bug (`rtsp:192.168.x.x/main`)
When adding a Custom RTSP camera to many Hikvision NVRs, the NVR firmware omits the double slash `//` in its RTSP handshake:
```http
DESCRIBE rtsp:192.168.100.49:554/main RTSP/1.0
```
Standard RTSP servers fail to parse `rtsp:192.168.100.49:554/main` as a standard URL and treat `rtsp:192.168.100.49:554/main` as the **path name**, rejecting it because `:` is forbidden by default path regexes (`^[0-9a-zA-Z_\-/\.]+$`).
- **Our Solution:** [`ensure_mediamtx()`](../desktop_app/engine.py) automatically applies a 20-byte binary patch to `mediamtx.exe` (`^[0-9a-zA-Z_\-/\.]+$` $\rightarrow$ `^[0-9a-zA-Z_\-/.:]+$`) and configures wildcard `sourceOnDemand` rules in `mediamtx.yml` so both standard RTSP clients (Dahua, Uniview, Reolink, VLC) and quirky Hikvision firmware connect instantaneously.

### Roadblock #2: NVR Hardware Decoder Rejects ("No Network Video")
Hardware ASIC decoders inside NVRs reject high-profile H.264 streams containing B-frames (`-bf > 0`), 4:4:4 chroma subsampling, or long keyframe intervals, and require a low-resolution **Sub-Stream** for multi-camera grid views.
- **Our Solution:** [`_build_dual_output_args()`](../desktop_app/engine.py) uses an FFmpeg `split=2` filter graph to simultaneously push `/main` (1080p/720p HD) and `/sub` (`640x360` SD) using `libx264 -profile:v baseline -level 3.1 -pix_fmt yuv420p -bf 0 -g 50 -fps_mode cfr`.

### Roadblock #3: Getting Live Audio Out of the NVR Monitor Speakers
Most CCTV NVRs ignore high-bitrate stereo AAC audio tracks over RTSP and strictly expect **ITU-T G.711** telephony/CCTV audio.
- **Our Solution:** Default NVR audio encoding uses **`G.711 ulaw` (`pcm_mulaw`, 8000 Hz, mono)**, with instant switching in the GUI/Web Studio to `G.711 alaw` (`pcm_alaw`), `AAC 16kHz Mono`, or `AAC 44.1kHz Stereo`.

### Roadblock #4: Jitter-Free PC & NVR Streaming for Unstable HLS / IPTV / YouTube Feeds
Raw `.m3u8` IPTV streams and YouTube HLS segments deliver data in bursts (`2s–6s` chunks). Piping them directly into a real-time `-re` encoder causes periodic freeze/fast-forward cycles, and decoding MJPEG frames on the Python Tkinter UI thread causes severe CPU spikes and frame drops at 1080p.
- **Our Solution (Single-Download MPEG-TS Ring Buffer + Embedded `libVLC` Tee):**
  1. **Stage 1 Upstream Prefetcher (`75 MB` Ring Buffer):** A dedicated upstream FFmpeg process downloads the source stream (with automatic reconnect and multi-connection HLS pre-fetching), copies video (`-c:v copy`) + encodes clean stereo AAC (`-c:a aac -ar 44100 -ac 2`), and writes continuous **MPEG-TS (`mpegts`)** chunks into a `75 MB` Python memory ring buffer (`ts_q`).
  2. **Local HTTP MPEG-TS Tee (`http://127.0.0.1:<port>/live.ts`):** When watching on PC (`Preview Only` or `Both`), the prefetcher simultaneously broadcasts the exact same MPEG-TS byte stream over a lightweight localhost HTTP server (`_start_pc_feed_server`).
  3. **Embedded Hardware-Accelerated `libVLC` Player ([`local_player.py`](../desktop_app/local_player.py)):** Connects to `http://127.0.0.1:<port>/live.ts` and decodes H.264/HEVC video + stereo audio directly on the GPU (`DXVA2`/`D3D11VA`) inside a native Win32 child window (`HWND`) at full **25–60 fps** with **0% Python GIL overhead**.
  4. **Zero-Interruption Win32 Reparenting:** Switching between **Main Studio View**, **Floating Always-On-Top PiP Mini-Player**, and **100% Full-Screen TV Mode (`F11` / `Esc`)** calls Win32 `user32.SetParent(child_hwnd, target_hwnd)` + `user32.MoveWindow(...)`—moving the live hardware surface instantly without restarting or re-buffering the stream.

### Roadblock #5: Multi-Monitor Desktop Capture & Continuous WASAPI Loopback Audio
- **Our Solution:** [`start_screen_cast()`](../desktop_app/engine.py) binds worker threads to the active interactive Windows desktop (`OpenDesktopW("Default")` + `SetThreadDesktop`), dynamically computes bounding boxes for any combination of monitors (including mixed Landscape `1920x1080` + Portrait `1080x1920`), overlays a high-contrast cursor, and streams WASAPI loopback audio with automatic `40ms` zero-byte silence padding so FFmpeg never stalls when PC speakers are silent.
