import os
import sys
import time
import json
import queue
import random
import ctypes
from ctypes import wintypes
import socket
import shutil
import urllib.request
import zipfile
import threading
import subprocess

import yt_dlp

try:
    import mss
except ImportError:
    mss = None

try:
    import pyaudiowpatch as pyaudio
except ImportError:
    pyaudio = None

try:
    from PIL import Image, ImageDraw, ImageFont, ImageOps
except ImportError:
    Image = None

APP_VERSION = "0.1.0-beta"

# Support both running from source and PyInstaller --onefile executable
IS_FROZEN = getattr(sys, "frozen", False)
BUNDLE_DIR = getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
APP_DIR = os.path.dirname(sys.executable) if IS_FROZEN else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

BIN_DIR = os.path.join(APP_DIR, "bin")
EXT_DIR = os.path.join(APP_DIR, "chrome_extension")
MEDIAMTX_EXE = os.path.join(BIN_DIR, "mediamtx.exe")
MEDIAMTX_YML = os.path.join(BIN_DIR, "mediamtx.yml")

SUPPORTED_IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".bmp", ".webp", ".gif")
SUPPORTED_VIDEO_EXTS = (".mp4", ".mkv", ".avi", ".mov", ".ts", ".webm", ".m4v")


def attach_thread_to_default_desktop() -> bool:
    """Attach the calling thread to WinSta0\\Default so screen capture works from any Windows session."""
    if os.name != "nt":
        return False
    try:
        u32 = ctypes.windll.user32
        hdesk = u32.OpenDesktopW("Default", 0, True, 0x01FF)
        if hdesk:
            u32.SetThreadDesktop(hdesk)
            return True
    except Exception:
        pass
    return False


def get_lan_ip() -> str:
    """Detect the primary local area network IPv4 address (prefers 192.168.x.x)."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(1.0)
        s.connect(("192.168.100.1", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "127.0.0.1"


def find_ffmpeg() -> str:
    """Locate ffmpeg executable in ./bin, on PATH, or standard WinGet installation directory."""
    local_ff = os.path.join(BIN_DIR, "ffmpeg.exe")
    if os.path.isfile(local_ff):
        return local_ff
    path = shutil.which("ffmpeg")
    if path:
        return path
    winget_glob = os.path.expandvars(
        r"%LOCALAPPDATA%\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe"
    )
    if os.path.isdir(winget_glob):
        for root, _, files in os.walk(winget_glob):
            if "ffmpeg.exe" in files:
                return os.path.join(root, "ffmpeg.exe")
    return "ffmpeg"


def is_port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("0.0.0.0", port))
            return True
        except OSError:
            return False


def draw_cursor_on_bgra(buf: bytearray, width: int, height: int, left: int, top: int):
    """Draws a visible high-contrast mouse pointer onto a raw BGRA frame buffer."""
    try:
        pt = wintypes.POINT()
        ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
        cx = pt.x - left
        cy = pt.y - top
        if not (0 <= cx < width - 16 and 0 <= cy < height - 16):
            return
        for dy in range(14):
            row_y = cy + dy
            if row_y >= height:
                break
            max_dx = max(1, 14 - dy)
            row_offset = row_y * width * 4
            for dx in range(max_dx):
                col_x = cx + dx
                if col_x >= width:
                    break
                idx = row_offset + col_x * 4
                if dx == 0 or dy == 0 or dx == max_dx - 1:
                    buf[idx : idx + 4] = b"\x00\x00\x00\xff"
                else:
                    buf[idx : idx + 4] = b"\xff\xff\xff\xff"
    except Exception:
        pass


class NVRCastEngine:
    """
    Universal NVR RTSP Casting Engine (v0.1.0-beta).
    Features:
      - Direct YouTube / Web Video Streaming with Real-Time Seek, Pause/Resume & Loop
      - Chrome Extension PiP-Style Live Video Player Mirroring (video.captureStream() + seek sync)
      - Rock-Solid Photo Gallery & Single-Picture Slideshow with Pre-Rendered Cache, Smooth Crossfade,
        Timer, Shuffle, Next/Prev Slide & Wall-Clock Paced Audio
      - Multi-Monitor PC Desktop Mirroring (Monitor 1, Monitor 2, All Combined) + WASAPI Speaker Audio
      - Meeting-Style Browser Tab / Window / Screen Share
      - Video Loop Mode (Infinite Loop for local videos or web streams)
      - Unified Active Session Tracking across Desktop App, Web Studio & Chrome Extension
    """

    def __init__(self, log_callback=None, status_callback=None):
        self.log_cb = log_callback or (lambda msg: print(msg))
        self.status_cb = status_callback or (lambda state, title: None)

        self.lan_ip = get_lan_ip()
        self.ffmpeg_exe = find_ffmpeg()
        self.rtsp_port = 554 if is_port_free(554) else 8554
        self.web_port = 8090

        self.mediamtx_proc = None
        self.ffmpeg_proc = None
        self.stream_lock = threading.Lock()
        self.running = False
        self.screen_stop_event = threading.Event()
        self.browser_chunk_queue = None

        # Active Session State (shared across Desktop GUI, Web Studio & Chrome Extension)
        self.current_mode = "STOPPED"
        self.current_title = "Idle"
        self.current_url = ""
        self.current_filepath = ""
        self.active_source = "System"
        self.is_paused = False
        self.loop_video = False
        self.stream_started_at = 0.0
        self.seek_offset_sec = 0

        # Gallery Slideshow State
        self.gallery_folder = ""
        self.gallery_images = []
        self.gallery_index = 0
        self.gallery_interval = 5        # seconds per slide
        self.gallery_shuffle = False
        self.gallery_transition = True   # smooth crossfade between slides
        self.gallery_force_step = 0      # +1 for next slide, -1 for prev slide

        # Flexible encoding & display settings
        self.main_res = "1280x720"       # 1280x720, 1920x1080, 854x480
        self.fps = 25                    # 15, 25, 30
        self.video_bitrate = "1800k"     # 1000k, 1800k, 2500k, 4000k
        self.audio_codec = "pcm_mulaw"   # pcm_mulaw (G.711u), pcm_alaw (G.711a), aac, aac_hq, none
        self.aspect_mode = "fit"         # fit (Letterbox), stretch (Fill 16:9), crop (Center Crop)
        self.show_cursor = True
        self.capture_pc_audio = True

        # Multi-monitor selection: list of 1-based monitor indices (e.g. [1], [2], [1, 2])
        self.monitors_info = self.detect_monitors()
        self.selected_monitors = [1] if len(self.monitors_info) > 1 else [0]

        self._extract_bundled_assets()

    def log(self, msg: str):
        timestamp = time.strftime("%H:%M:%S")
        self.log_cb(f"[{timestamp}] {msg}")

    def _attach_ffmpeg_log_drainer(self, proc: subprocess.Popen, tag: str = "FFmpeg"):
        """
        Continuously drains proc.stdout in a background daemon thread so the OS pipe buffer
        can NEVER fill up and deadlock rawvideo/stdin streaming.
        """
        if not proc or not proc.stdout:
            return

        def _drain():
            try:
                for raw_line in iter(proc.stdout.readline, b""):
                    if not raw_line:
                        break
                    if isinstance(raw_line, bytes):
                        line_str = raw_line.decode("utf-8", errors="ignore").strip()
                    else:
                        line_str = str(raw_line).strip()
                    if line_str and ("Error" in line_str or "error" in line_str or "Invalid" in line_str):
                        self.log(f"[{tag}] {line_str}")
            except Exception:
                pass

        threading.Thread(target=_drain, daemon=True).start()

    def get_current_playback_sec(self) -> int:
        if self.current_mode not in ("YOUTUBE", "FILE"):
            return 0
        if self.is_paused or self.stream_started_at <= 0:
            return int(self.seek_offset_sec)
        return int(self.seek_offset_sec + max(0.0, time.time() - self.stream_started_at))

    def get_status_dict(self) -> dict:
        return {
            "version": APP_VERSION,
            "mode": self.current_mode,
            "title": self.current_title,
            "active_source": self.active_source,
            "is_paused": self.is_paused,
            "loop_video": self.loop_video,
            "current_url": self.current_url,
            "current_filepath": self.current_filepath,
            "playback_sec": self.get_current_playback_sec(),
            "gallery": {
                "folder": self.gallery_folder,
                "count": len(self.gallery_images),
                "index": self.gallery_index,
                "interval": self.gallery_interval,
                "shuffle": self.gallery_shuffle,
                "current_file": (
                    os.path.basename(self.gallery_images[self.gallery_index])
                    if self.gallery_images and 0 <= self.gallery_index < len(self.gallery_images)
                    else ""
                ),
            },
            "rtsp_main": f"rtsp://{self.lan_ip}:{self.rtsp_port}/main",
            "rtsp_sub": f"rtsp://{self.lan_ip}:{self.rtsp_port}/sub",
            "lan_ip": self.lan_ip,
            "web_port": self.web_port,
            "monitors": self.monitors_info,
            "selected_monitors": self.selected_monitors,
            "settings": {
                "main_res": self.main_res,
                "fps": self.fps,
                "video_bitrate": self.video_bitrate,
                "audio_codec": self.audio_codec,
                "aspect_mode": self.aspect_mode,
                "show_cursor": self.show_cursor,
                "capture_pc_audio": self.capture_pc_audio,
            },
        }

    def _extract_bundled_assets(self):
        """If running from PyInstaller single-file .exe, unpack bundled mediamtx and chrome_extension."""
        try:
            os.makedirs(BIN_DIR, exist_ok=True)
            bundled_mtx = os.path.join(BUNDLE_DIR, "bin", "mediamtx.exe")
            if os.path.isfile(bundled_mtx) and not os.path.isfile(MEDIAMTX_EXE):
                shutil.copy2(bundled_mtx, MEDIAMTX_EXE)

            bundled_ext = os.path.join(BUNDLE_DIR, "chrome_extension")
            if os.path.isdir(bundled_ext) and os.path.abspath(bundled_ext) != os.path.abspath(EXT_DIR):
                shutil.copytree(bundled_ext, EXT_DIR, dirs_exist_ok=True)
        except Exception as e:
            self.log(f"Asset unpack note: {e}")

    def detect_monitors(self) -> list:
        """Return list of monitor dicts from MSS. Index 0 is All Combined; 1..N are physical displays."""
        attach_thread_to_default_desktop()
        if mss is None:
            return [{"index": 1, "label": "Primary Display (1920x1080)", "left": 0, "top": 0, "width": 1920, "height": 1080}]
        try:
            with mss.MSS() as sct:
                result = []
                for idx, m in enumerate(sct.monitors):
                    w, h = m["width"], m["height"]
                    if idx == 0:
                        label = f"All Monitors Combined ({w}x{h})"
                    else:
                        orient = "Landscape" if w >= h else "Vertical"
                        prim = " [Primary]" if m.get("is_primary") or idx == 1 else ""
                        label = f"Monitor {idx}: {w}x{h} ({orient}){prim}"
                    result.append({
                        "index": idx,
                        "label": label,
                        "left": m["left"],
                        "top": m["top"],
                        "width": w,
                        "height": h,
                    })
                return result
        except Exception:
            return [{"index": 1, "label": "Primary Display (1920x1080)", "left": 0, "top": 0, "width": 1920, "height": 1080}]

    def compute_monitor_region(self, selected_indices: list = None) -> tuple:
        self.monitors_info = self.detect_monitors()
        if not selected_indices:
            selected_indices = self.selected_monitors or [1]

        if 0 in selected_indices or len(self.monitors_info) <= 1:
            m0 = self.monitors_info[0]
            w = (m0["width"] // 2) * 2
            h = (m0["height"] // 2) * 2
            return (m0["left"], m0["top"], w, h, m0["label"])

        chosen = [m for m in self.monitors_info if m["index"] in selected_indices and m["index"] > 0]
        if not chosen:
            chosen = [self.monitors_info[1]]

        left = min(m["left"] for m in chosen)
        top = min(m["top"] for m in chosen)
        right = max(m["left"] + m["width"] for m in chosen)
        bottom = max(m["top"] + m["height"] for m in chosen)
        width = ((right - left) // 2) * 2
        height = ((bottom - top) // 2) * 2

        if len(chosen) == 1:
            desc = f"Monitor {chosen[0]['index']} ({width}x{height})"
        else:
            nums = "+".join(str(m["index"]) for m in chosen)
            desc = f"Monitors {nums} ({width}x{height})"

        return (left, top, width, height, desc)

    def ensure_mediamtx(self) -> bool:
        os.makedirs(BIN_DIR, exist_ok=True)
        if not os.path.isfile(MEDIAMTX_EXE):
            self.log("MediaMTX binary not found. Downloading latest release from GitHub...")
            try:
                req = urllib.request.Request(
                    "https://api.github.com/repos/bluenviron/mediamtx/releases/latest",
                    headers={"User-Agent": f"NVRCastHub/{APP_VERSION}"},
                )
                with urllib.request.urlopen(req, timeout=15) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                assets = data.get("assets", [])
                win_asset = next(
                    (a for a in assets if "windows_amd64.zip" in a.get("name", "")),
                    None,
                )
                if not win_asset:
                    self.log("ERROR: Could not find windows_amd64.zip in MediaMTX release.")
                    return False

                zip_path = os.path.join(BIN_DIR, "mediamtx.zip")
                urllib.request.urlretrieve(win_asset["browser_download_url"], zip_path)
                with zipfile.ZipFile(zip_path, "r") as zf:
                    zf.extractall(BIN_DIR)
                os.remove(zip_path)
                self.log("MediaMTX downloaded and extracted successfully!")
            except Exception as e:
                self.log(f"ERROR downloading MediaMTX: {e}")
                return False

        # Ensure Hikvision & legacy NVR colon-path compatibility patch is applied to mediamtx.exe
        try:
            with open(MEDIAMTX_EXE, "rb") as f:
                raw = f.read()
            old_pat = b"^[0-9a-zA-Z_\\-/\\.]+$"
            new_pat = b"^[0-9a-zA-Z_\\-/.:]+$"
            if old_pat in raw:
                raw = raw.replace(old_pat, new_pat)
                with open(MEDIAMTX_EXE, "wb") as f:
                    f.write(raw)
                self.log("Applied NVR RTSP colon-path compatibility patch to MediaMTX.")
        except Exception:
            pass

        return os.path.isfile(MEDIAMTX_EXE)

    def write_mediamtx_config(self):
        yml_content = f"""logLevel: info
logDestinations: [stdout, file]
logFile: mediamtx.log
rtsp: yes
rtspTransports: [tcp, udp, multicast]
rtspEncryption: "no"
rtspAddress: :{self.rtsp_port}
rtpAddress: :8002
rtcpAddress: :8003
rtmp: no
hls: no
webrtc: no
srt: no

paths:
  main:
    source: publisher
    overridePublisher: yes
  sub:
    source: publisher
    overridePublisher: yes
  "~^.*(sub|102|subtype=1|channel=2).*$":
    source: rtsp://127.0.0.1:{self.rtsp_port}/sub
    sourceOnDemand: yes
  all_others:
    source: rtsp://127.0.0.1:{self.rtsp_port}/main
    sourceOnDemand: yes
"""
        with open(MEDIAMTX_YML, "w", encoding="utf-8") as f:
            f.write(yml_content)

    def start_server(self) -> bool:
        if not self.ensure_mediamtx():
            return False

        if not is_port_free(self.rtsp_port):
            alt_port = 8554 if self.rtsp_port == 554 else 8555
            self.log(f"Port {self.rtsp_port} busy, switching RTSP server to port {alt_port}...")
            self.rtsp_port = alt_port

        self.write_mediamtx_config()

        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

        try:
            self.mediamtx_proc = subprocess.Popen(
                [MEDIAMTX_EXE, MEDIAMTX_YML],
                cwd=BIN_DIR,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                startupinfo=startupinfo,
            )
            time.sleep(0.8)
            if self.mediamtx_proc.poll() is not None:
                out = self.mediamtx_proc.stdout.read() if self.mediamtx_proc.stdout else ""
                self.log(f"MediaMTX failed on port {self.rtsp_port}: {out}")
                if self.rtsp_port == 554:
                    self.rtsp_port = 8554
                    self.write_mediamtx_config()
                    self.mediamtx_proc = subprocess.Popen(
                        [MEDIAMTX_EXE, MEDIAMTX_YML],
                        cwd=BIN_DIR,
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True,
                        startupinfo=startupinfo,
                    )
                    time.sleep(0.8)

            self.running = True
            threading.Thread(target=self._monitor_mediamtx_logs, daemon=True).start()
            self.log(f"RTSP Server ONLINE at rtsp://{self.lan_ip}:{self.rtsp_port}/main (and /sub)")
            self.start_standby_stream()
            return True
        except Exception as e:
            self.log(f"Failed to start MediaMTX: {e}")
            return False

    def _monitor_mediamtx_logs(self):
        if not self.mediamtx_proc or not self.mediamtx_proc.stdout:
            return
        for line in self.mediamtx_proc.stdout:
            s = line.strip()
            if not s:
                continue
            if "127.0.0.1" not in s and ("[RTSP]" in s or "ERR" in s or "WARN" in s):
                self.log(f"[RTSP-Server] {s}")

    def _stop_ffmpeg_locked(self):
        self.screen_stop_event.set()
        if self.browser_chunk_queue is not None:
            try:
                self.browser_chunk_queue.put_nowait(None)
            except Exception:
                pass
            self.browser_chunk_queue = None

        if self.ffmpeg_proc and self.ffmpeg_proc.poll() is None:
            try:
                if self.ffmpeg_proc.stdin:
                    try:
                        self.ffmpeg_proc.stdin.close()
                    except Exception:
                        pass
                self.ffmpeg_proc.terminate()
                self.ffmpeg_proc.wait(timeout=1.5)
            except Exception:
                try:
                    self.ffmpeg_proc.kill()
                except Exception:
                    pass
        self.ffmpeg_proc = None

    def _build_audio_args(self, stream_map: str) -> list:
        if self.audio_codec == "none":
            return ["-an"]
        elif self.audio_codec == "pcm_alaw":
            return ["-map", stream_map, "-c:a", "pcm_alaw", "-ar", "8000", "-ac", "1"]
        elif self.audio_codec == "pcm_mulaw":
            return ["-map", stream_map, "-c:a", "pcm_mulaw", "-ar", "8000", "-ac", "1"]
        elif self.audio_codec == "aac_hq":
            return ["-map", stream_map, "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-ac", "2"]
        else:
            return ["-map", stream_map, "-c:a", "aac", "-b:a", "64k", "-ar", "16000", "-ac", "1"]

    def _scale_expr(self, w: str, h: str) -> str:
        if self.aspect_mode == "stretch":
            return f"scale={w}:{h},setsar=1"
        elif self.aspect_mode == "crop":
            return f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},setsar=1"
        else:
            return (
                f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
                f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=#0f172a,setsar=1"
            )

    def _build_dual_output_args(self, audio_map: str) -> list:
        """Builds FFmpeg arguments to simultaneously push /main (HD) and /sub (SD) streams."""
        w, h = self.main_res.split("x")
        fps = int(self.fps)
        gop = fps * 2
        main_url = f"rtsp://127.0.0.1:{self.rtsp_port}/main"
        sub_url = f"rtsp://127.0.0.1:{self.rtsp_port}/sub"

        main_scale = self._scale_expr(w, h)
        sub_scale = self._scale_expr("640", "360")

        filter_complex = (
            f"[0:v]fps={fps},format=yuv420p,split=2[v1][v2];"
            f"[v1]{main_scale}[vmain];"
            f"[v2]{sub_scale}[vsub]"
        )

        v_main_enc = [
            "-map", "[vmain]",
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-tune", "zerolatency",
            "-profile:v", "baseline",
            "-level", "3.1",
            "-pix_fmt", "yuv420p",
            "-bf", "0",
            "-b:v", self.video_bitrate,
            "-maxrate", self.video_bitrate,
            "-bufsize", self.video_bitrate,
            "-g", str(gop),
            "-keyint_min", str(fps),
            "-sc_threshold", "0",
        ]

        v_sub_enc = [
            "-map", "[vsub]",
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-tune", "zerolatency",
            "-profile:v", "baseline",
            "-level", "3.1",
            "-pix_fmt", "yuv420p",
            "-bf", "0",
            "-b:v", "500k",
            "-maxrate", "500k",
            "-bufsize", "500k",
            "-g", str(gop),
            "-keyint_min", str(fps),
            "-sc_threshold", "0",
        ]

        a_args = self._build_audio_args(audio_map)

        return (
            ["-filter_complex", filter_complex]
            + v_main_enc
            + a_args
            + ["-f", "rtsp", "-rtsp_transport", "tcp", main_url]
            + v_sub_enc
            + a_args
            + ["-f", "rtsp", "-rtsp_transport", "tcp", sub_url]
        )

    def start_standby_stream(self, source: str = "System Standby"):
        """Broadcasts an always-on Standby feed so the NVR channel never shows 'Offline'."""
        with self.stream_lock:
            self._stop_ffmpeg_locked()
            self.current_mode = "STANDBY"
            self.current_title = "Standby Screen (Ready to Cast)"
            self.active_source = source
            self.is_paused = False
            self.status_cb(self.current_mode, self.current_title)

            font_spec = "fontfile='C\\:/Windows/Fonts/arial.ttf'"
            drawtext_filter = (
                f"color=c=#0f172a:s=1280x720:r={self.fps},"
                "drawbox=x=60:y=60:w=1160:h=600:color=#1e293b@0.90:t=fill,"
                "drawbox=x=60:y=60:w=1160:h=6:color=#2563eb:t=fill,"
                f"drawtext={font_spec}:text='NVR CAST HUB v{APP_VERSION} — UNIVERSAL RTSP CASTER':fontcolor=white:fontsize=33:x=(w-text_w)/2:y=140,"
                f"drawtext={font_spec}:text='STATUS\\: ONLINE & READY FOR STREAM (HIKVISION / DAHUA / ONVIF)':fontcolor=#4ade80:fontsize=25:x=(w-text_w)/2:y=220,"
                f"drawtext={font_spec}:text='Main RTSP\\: rtsp\\://{self.lan_ip}\\:{self.rtsp_port}/main':fontcolor=#93c5fd:fontsize=25:x=(w-text_w)/2:y=310,"
                f"drawtext={font_spec}:text='Web Studio / Phone Remote\\: http\\://{self.lan_ip}\\:{self.web_port}':fontcolor=#fde047:fontsize=25:x=(w-text_w)/2:y=370,"
                f"drawtext={font_spec}:text='Cast YouTube, Photo Gallery, Video Loops, or Selected PC Monitors':fontcolor=#cbd5e1:fontsize=22:x=(w-text_w)/2:y=460,"
                f"drawtext={font_spec}:text='%{{localtime}}':fontcolor=#94a3b8:fontsize=24:x=(w-text_w)/2:y=545"
            )

            cmd = [
                self.ffmpeg_exe,
                "-hide_banner",
                "-loglevel", "warning",
                "-re",
                "-f", "lavfi",
                "-i", drawtext_filter,
                "-f", "lavfi",
                "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
            ] + self._build_dual_output_args("1:a:0")

            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

            self.ffmpeg_proc = subprocess.Popen(
                cmd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                startupinfo=startupinfo,
            )
            self._attach_ffmpeg_log_drainer(self.ffmpeg_proc, "Standby")
            self.log("Standby feed active on /main and /sub (NVR channel stays online).")

    def _start_paused_hold_screen(self, held_title: str):
        """Broadcasts a clean PAUSED overlay screen so the NVR stays connected while a video is paused."""
        safe_title = (
            held_title[:48]
            .replace("'", "")
            .replace(":", "\\:")
            .replace("%", "")
            .replace("\\", "/")
        )
        font_spec = "fontfile='C\\:/Windows/Fonts/arial.ttf'"
        drawtext_filter = (
            f"color=c=#0f172a:s=1280x720:r={self.fps},"
            "drawbox=x=100:y=120:w=1080:h=480:color=#1e293b@0.90:t=fill,"
            "drawbox=x=100:y=120:w=1080:h=6:color=#f59e0b:t=fill,"
            f"drawtext={font_spec}:text='STREAM PAUSED':fontcolor=#f59e0b:fontsize=44:x=(w-text_w)/2:y=220,"
            f"drawtext={font_spec}:text='{safe_title}':fontcolor=white:fontsize=28:x=(w-text_w)/2:y=310,"
            f"drawtext={font_spec}:text='Position\\: {self.seek_offset_sec}s — Click Resume in App / Web / Extension':fontcolor=#93c5fd:fontsize=24:x=(w-text_w)/2:y=390,"
            f"drawtext={font_spec}:text='%{{localtime}}':fontcolor=#94a3b8:fontsize=22:x=(w-text_w)/2:y=480"
        )
        cmd = [
            self.ffmpeg_exe,
            "-hide_banner",
            "-loglevel", "warning",
            "-re",
            "-f", "lavfi",
            "-i", drawtext_filter,
            "-f", "lavfi",
            "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
        ] + self._build_dual_output_args("1:a:0")

        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        self.ffmpeg_proc = subprocess.Popen(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            startupinfo=startupinfo,
        )
        self._attach_ffmpeg_log_drainer(self.ffmpeg_proc, "PausedHold")

    def toggle_pause(self, force_state: bool = None, source: str = None) -> bool:
        """Pauses or resumes the active stream across all modes without dropping the NVR RTSP channel."""
        target_pause = (not self.is_paused) if force_state is None else bool(force_state)
        if self.current_mode in ("STANDBY", "STOPPED"):
            return False

        if self.current_mode in ("GALLERY", "SCREEN"):
            self.is_paused = target_pause
            state_txt = "PAUSED" if self.is_paused else "RESUMED"
            self.log(f"{self.current_mode} stream {state_txt} (by {source or 'User'}).")
            clean_t = self.current_title.replace("[PAUSED] ", "")
            self.current_title = f"{'[PAUSED] ' if self.is_paused else ''}{clean_t}"
            self.status_cb(self.current_mode, self.current_title)
            return self.is_paused

        if self.current_mode == "YOUTUBE":
            if target_pause and not self.is_paused:
                self.seek_offset_sec = self.get_current_playback_sec()
                self.is_paused = True
                with self.stream_lock:
                    self._stop_ffmpeg_locked()
                    self._start_paused_hold_screen(self.current_title)
                self.status_cb("YOUTUBE", f"[PAUSED @ {self.seek_offset_sec}s] {self.current_title}")
                self.log(f"Paused YouTube/Web stream at {self.seek_offset_sec}s.")
            elif not target_pause and self.is_paused:
                self.is_paused = False
                self.log(f"Resuming YouTube/Web stream from {self.seek_offset_sec}s...")
                self.start_youtube_stream(
                    self.current_url,
                    start_sec=self.seek_offset_sec,
                    loop=self.loop_video,
                    source=source or self.active_source,
                )
            return self.is_paused

        if self.current_mode == "FILE":
            if target_pause and not self.is_paused:
                self.seek_offset_sec = self.get_current_playback_sec()
                self.is_paused = True
                with self.stream_lock:
                    self._stop_ffmpeg_locked()
                    self._start_paused_hold_screen(self.current_title)
                self.status_cb("FILE", f"[PAUSED @ {self.seek_offset_sec}s] {self.current_title}")
                self.log(f"Paused local file stream at {self.seek_offset_sec}s.")
            elif not target_pause and self.is_paused:
                self.is_paused = False
                self.log(f"Resuming local file stream from {self.seek_offset_sec}s...")
                self.start_local_file_stream(
                    self.current_filepath,
                    start_sec=self.seek_offset_sec,
                    loop=self.loop_video,
                    source=source or self.active_source,
                )
            return self.is_paused

        return self.is_paused

    def seek_stream(self, target_sec: int = None, delta_sec: int = None, source: str = None):
        """Seeks an active YouTube/Web or Local Video stream to a specific timestamp or relative +/- seconds."""
        if self.current_mode == "GALLERY" and delta_sec is not None:
            self.step_gallery_slide(1 if delta_sec >= 0 else -1)
            return
        if self.current_mode not in ("YOUTUBE", "FILE"):
            return
        cur = self.get_current_playback_sec()
        new_sec = max(0, target_sec if target_sec is not None else (cur + (delta_sec or 0)))
        self.seek_offset_sec = new_sec
        self.is_paused = False
        self.log(f"Seeking {self.current_mode} stream to {new_sec}s (triggered by {source or 'User'})...")
        if self.current_mode == "YOUTUBE" and self.current_url:
            self.start_youtube_stream(
                self.current_url,
                start_sec=new_sec,
                loop=self.loop_video,
                source=source or self.active_source,
            )
        elif self.current_mode == "FILE" and self.current_filepath:
            self.start_local_file_stream(
                self.current_filepath,
                start_sec=new_sec,
                loop=self.loop_video,
                source=source or self.active_source,
            )

    def start_youtube_stream(
        self,
        query_or_url: str,
        start_sec: int = 0,
        loop: bool = None,
        source: str = "Desktop App",
    ):
        """Resolves any YouTube URL, search query, or web video link (.m3u8/.mp4/Twitch/FB) and streams to NVR."""
        query_or_url = query_or_url.strip()
        if not query_or_url:
            return
        if loop is not None:
            self.loop_video = bool(loop)

        def _worker():
            self.log(f"[{source}] Resolving video stream: {query_or_url} (start={start_sec}s, loop={self.loop_video})...")
            self.status_cb("LOADING", f"Loading: {query_or_url[:48]}...")

            lower_q = query_or_url.lower()
            is_direct_media = any(
                lower_q.endswith(ext) or f"{ext}?" in lower_q
                for ext in (".m3u8", ".mp4", ".ts", ".mkv", ".webm", ".mpd")
            ) or lower_q.startswith("rtsp://") or lower_q.startswith("rtmp://")

            if is_direct_media:
                title = query_or_url.split("/")[-1].split("?")[0] or "Direct Media Stream"
                is_live = ".m3u8" in lower_q or lower_q.startswith("rtsp://")
                video_url = query_or_url
                audio_url = None
            else:
                ydl_opts = {
                    "format": "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best",
                    "noplaylist": True,
                    "quiet": True,
                    "no_warnings": True,
                    "default_search": "ytsearch1",
                    "js_runtimes": {"node": {}},
                }

                try:
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        info = ydl.extract_info(query_or_url, download=False)
                        if "entries" in info and info["entries"]:
                            info = info["entries"][0]

                        title = info.get("title", "Web Video Stream")
                        is_live = info.get("is_live", False)

                        req_formats = info.get("requested_formats")
                        if req_formats and len(req_formats) >= 2:
                            video_url = req_formats[0]["url"]
                            audio_url = req_formats[1]["url"]
                        else:
                            video_url = info["url"]
                            audio_url = None
                except Exception as e:
                    self.log(f"ERROR resolving video link: {e}")
                    self.status_cb(self.current_mode, self.current_title)
                    return

            self.log(f"Matched Stream: '{title}' ({'LIVE' if is_live else 'VOD'})")

            reconnect_args = [
                "-reconnect", "1",
                "-reconnect_streamed", "1",
                "-reconnect_delay_max", "5",
            ]
            seek_args = ["-ss", str(start_sec)] if (start_sec > 0 and not is_live) else []

            if audio_url:
                input_args = (
                    ["-re"] + seek_args + reconnect_args + ["-i", video_url]
                    + seek_args + reconnect_args + ["-i", audio_url]
                )
                audio_map = "1:a:0?"
            else:
                input_args = (
                    ["-re"] + seek_args + reconnect_args + ["-i", video_url]
                    + ["-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100"]
                )
                audio_map = "0:a:0?"

            cmd = (
                [self.ffmpeg_exe, "-hide_banner", "-loglevel", "warning"]
                + input_args
                + self._build_dual_output_args(audio_map)
            )

            with self.stream_lock:
                self._stop_ffmpeg_locked()
                self.current_mode = "YOUTUBE"
                self.current_title = f"{'[LOOP] ' if self.loop_video else ''}{title}"
                self.current_url = query_or_url
                self.active_source = source
                self.is_paused = False
                self.seek_offset_sec = int(start_sec)
                self.stream_started_at = time.time()
                self.status_cb(self.current_mode, self.current_title)

                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

                self.ffmpeg_proc = subprocess.Popen(
                    cmd,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    startupinfo=startupinfo,
                )
                proc_ref = self.ffmpeg_proc
                self._attach_ffmpeg_log_drainer(proc_ref, "YouTube")

            self.log(f"NOW STREAMING TO NVR ({source}): {title}")

            proc_ref.wait()
            with self.stream_lock:
                if self.ffmpeg_proc == proc_ref and self.running and not self.is_paused:
                    if self.loop_video:
                        self.log(f"Looping YouTube/Web video '{title}' from beginning...")
                        threading.Thread(
                            target=self.start_youtube_stream,
                            args=(query_or_url, 0, True, source),
                            daemon=True,
                        ).start()
                    else:
                        self.log(f"Finished playing '{title}'. Returning to Standby feed...")
                        threading.Thread(target=self.start_standby_stream, daemon=True).start()

        threading.Thread(target=_worker, daemon=True).start()

    def start_local_file_stream(
        self,
        filepath: str,
        start_sec: int = 0,
        loop: bool = None,
        source: str = "Desktop App",
    ):
        if not os.path.isfile(filepath):
            self.log(f"File not found: {filepath}")
            return
        # If the user picked an image file via Local File, route to Gallery Slideshow automatically
        if filepath.lower().endswith(SUPPORTED_IMAGE_EXTS):
            self.start_gallery_slideshow([filepath], interval_sec=self.gallery_interval, shuffle=False, source=source)
            return

        if loop is not None:
            self.loop_video = bool(loop)

        def _worker():
            title = os.path.basename(filepath)
            loop_args = ["-stream_loop", "-1"] if self.loop_video else []
            seek_args = ["-ss", str(start_sec)] if start_sec > 0 else []
            cmd = (
                [
                    self.ffmpeg_exe,
                    "-hide_banner",
                    "-loglevel", "warning",
                    "-re",
                ]
                + loop_args
                + seek_args
                + ["-i", filepath]
                + self._build_dual_output_args("0:a:0?")
            )
            with self.stream_lock:
                self._stop_ffmpeg_locked()
                self.current_mode = "FILE"
                self.current_filepath = filepath
                self.current_title = f"{'[LOOP] ' if self.loop_video else ''}File: {title}"
                self.active_source = source
                self.is_paused = False
                self.seek_offset_sec = int(start_sec)
                self.stream_started_at = time.time()
                self.status_cb(self.current_mode, self.current_title)

                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                self.ffmpeg_proc = subprocess.Popen(
                    cmd,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    startupinfo=startupinfo,
                )
                proc_ref = self.ffmpeg_proc
                self._attach_ffmpeg_log_drainer(proc_ref, "File")

            self.log(f"Streaming local file to NVR ({source}, loop={self.loop_video}): {title}")
            proc_ref.wait()
            with self.stream_lock:
                if self.ffmpeg_proc == proc_ref and self.running and not self.is_paused:
                    self.log("Local file finished. Returning to Standby feed...")
                    threading.Thread(target=self.start_standby_stream, daemon=True).start()

        threading.Thread(target=_worker, daemon=True).start()

    def start_gallery_slideshow(
        self,
        folder_or_files,
        interval_sec: int = 5,
        shuffle: bool = False,
        source: str = "Photo Gallery",
    ):
        """
        Rock-solid Photo Gallery / Single Picture / Folder Slideshow broadcaster:
          - Background pre-loader & slide cache so image decoding NEVER stalls the 25fps FFmpeg pipe
          - Smooth 8-frame crossfade transitions between photos
          - Strict wall-clock frame pacing (time.perf_counter) + drained FFmpeg stdout pipe
          - Supports single static picture or multi-photo folder with timer, shuffle, and Next/Prev step
        """
        if Image is None:
            self.log("ERROR: 'Pillow' (PIL) is required for Photo Gallery Slideshow.")
            return

        images = []
        if isinstance(folder_or_files, str):
            raw_str = folder_or_files.strip()
            # Support semicolon-separated file list or a folder/single file path
            if ";" in raw_str and not os.path.isdir(raw_str):
                parts = [p.strip() for p in raw_str.split(";") if p.strip()]
                for p in parts:
                    if os.path.isfile(p) and p.lower().endswith(SUPPORTED_IMAGE_EXTS):
                        images.append(p)
                if images:
                    self.gallery_folder = os.path.dirname(images[0])
            elif os.path.isdir(raw_str):
                self.gallery_folder = raw_str
                for entry in sorted(os.listdir(raw_str)):
                    full = os.path.join(raw_str, entry)
                    if os.path.isfile(full) and entry.lower().endswith(SUPPORTED_IMAGE_EXTS):
                        images.append(full)
            elif os.path.isfile(raw_str) and raw_str.lower().endswith(SUPPORTED_IMAGE_EXTS):
                self.gallery_folder = os.path.dirname(raw_str)
                images.append(raw_str)
        elif isinstance(folder_or_files, list):
            for p in folder_or_files:
                if os.path.isfile(p) and p.lower().endswith(SUPPORTED_IMAGE_EXTS):
                    images.append(p)
            if images:
                self.gallery_folder = os.path.dirname(images[0])

        if not images:
            self.log("Gallery Slideshow: No supported pictures (.jpg, .png, .webp, .bmp, .gif) found!")
            return

        self.gallery_interval = max(1, int(interval_sec or 5))
        self.gallery_shuffle = bool(shuffle)
        if self.gallery_shuffle and len(images) > 1:
            random.shuffle(images)
        self.gallery_images = images
        self.gallery_index = 0
        self.gallery_force_step = 0

        slide_cache = {}
        cache_lock = threading.Lock()

        def _render_slide_pil(img_path: str, idx: int, total: int, out_w: int, out_h: int):
            """Renders a slide to a PIL RGBA image (with B and R swapped for direct BGRA bytes export)."""
            cache_key = (img_path, idx, total, out_w, out_h, self.aspect_mode, self.gallery_interval, self.gallery_shuffle)
            with cache_lock:
                if cache_key in slide_cache:
                    return slide_cache[cache_key]

            canvas = Image.new("RGB", (out_w, out_h), (15, 23, 42))
            try:
                with Image.open(img_path) as im:
                    im = ImageOps.exif_transpose(im).convert("RGB")
                    if self.aspect_mode == "stretch":
                        fitted = im.resize((out_w, out_h), Image.Resampling.BILINEAR)
                        canvas.paste(fitted, (0, 0))
                    elif self.aspect_mode == "crop":
                        fitted = ImageOps.fit(im, (out_w, out_h), Image.Resampling.BILINEAR)
                        canvas.paste(fitted, (0, 0))
                    else:
                        im.thumbnail((out_w, out_h), Image.Resampling.BILINEAR)
                        ox = (out_w - im.width) // 2
                        oy = (out_h - im.height) // 2
                        canvas.paste(im, (ox, oy))
            except Exception as e:
                self.log(f"Slide load warning ({os.path.basename(img_path)}): {e}")

            draw = ImageDraw.Draw(canvas)
            try:
                font = ImageFont.truetype(r"C:\Windows\Fonts\segoeuib.ttf", 16)
            except Exception:
                font = ImageFont.load_default()
            fname = os.path.basename(img_path)
            if len(fname) > 34:
                fname = fname[:31] + "..."
            mode_tag = "Single Picture" if total == 1 else f"{idx + 1} / {total}  •  {self.gallery_interval}s"
            if self.gallery_shuffle and total > 1:
                mode_tag += "  •  Shuffle"
            badge_txt = f"  {mode_tag}  |  {fname}  "
            bbox = draw.textbbox((0, 0), badge_txt, font=font)
            bw = bbox[2] - bbox[0]
            bh = bbox[3] - bbox[1] + 12
            bx = out_w - bw - 18
            by = out_h - bh - 14
            draw.rounded_rectangle([bx, by, bx + bw, by + bh], radius=7, fill=(15, 23, 42), outline=(51, 65, 85), width=1)
            draw.text((bx, by + 5), badge_txt, font=font, fill=(248, 250, 252))

            # Store as channel-swapped RGBA so .tobytes() is directly BGRA for FFmpeg
            r, g, b = canvas.split()
            a = Image.new("L", (out_w, out_h), 255)
            bgra_img = Image.merge("RGBA", (b, g, r, a))
            raw_bytes = bgra_img.tobytes()

            with cache_lock:
                if len(slide_cache) >= 24:
                    slide_cache.pop(next(iter(slide_cache)))
                slide_cache[cache_key] = (bgra_img, raw_bytes)
            return (bgra_img, raw_bytes)

        def _preload_slide_async(idx: int, total: int, out_w: int, out_h: int):
            if not self.gallery_images:
                return
            norm_idx = idx % total
            img_path = self.gallery_images[norm_idx]
            threading.Thread(
                target=_render_slide_pil,
                args=(img_path, norm_idx, total, out_w, out_h),
                daemon=True,
            ).start()

        def _worker():
            out_w, out_h = [int(x) for x in self.main_res.split("x")]
            total_imgs = len(self.gallery_images)
            folder_name = os.path.basename(self.gallery_folder) or "Selected Photos"

            # Pre-render the first slide BEFORE spawning FFmpeg so frame 0 is ready immediately
            cur_idx = 0
            self.gallery_index = 0
            first_file = self.gallery_images[0]
            cur_pil, cur_frame_bytes = _render_slide_pil(first_file, 0, total_imgs, out_w, out_h)
            if total_imgs > 1:
                _preload_slide_async(1, total_imgs, out_w, out_h)

            with self.stream_lock:
                self._stop_ffmpeg_locked()
                self.screen_stop_event.clear()
                stop_evt = self.screen_stop_event

                audio_info = self._start_wasapi_audio_tcp_feeder(stop_evt)
                if audio_info:
                    aport, arate, achan = audio_info
                    audio_input_args = [
                        "-thread_queue_size", "512",
                        "-f", "s16le",
                        "-ar", str(arate),
                        "-ac", str(achan),
                        "-i", f"tcp://127.0.0.1:{aport}",
                    ]
                else:
                    audio_input_args = [
                        "-f", "lavfi",
                        "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
                    ]

                cmd = (
                    [
                        self.ffmpeg_exe,
                        "-hide_banner",
                        "-loglevel", "warning",
                        "-thread_queue_size", "256",
                        "-f", "rawvideo",
                        "-pix_fmt", "bgra",
                        "-s", f"{out_w}x{out_h}",
                        "-r", str(self.fps),
                        "-i", "pipe:0",
                    ]
                    + audio_input_args
                    + self._build_dual_output_args("1:a:0")
                )

                self.current_mode = "GALLERY"
                self.active_source = source
                self.is_paused = False
                self.current_title = f"Gallery [1/{total_imgs}]: {os.path.basename(first_file)}"
                self.status_cb(self.current_mode, self.current_title)

                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                self.ffmpeg_proc = subprocess.Popen(
                    cmd,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    bufsize=out_w * out_h * 4 * 2,
                    startupinfo=startupinfo,
                )
                proc_ref = self.ffmpeg_proc
                self._attach_ffmpeg_log_drainer(proc_ref, "Gallery")

            self.log(
                f"Started Photo Gallery Slideshow ({total_imgs} photo(s) from '{folder_name}', "
                f"timer={self.gallery_interval}s, shuffle={self.gallery_shuffle})"
            )

            frame_interval = 1.0 / float(self.fps)
            next_frame_t = time.perf_counter()
            slide_deadline = time.perf_counter() + float(self.gallery_interval)
            transition_queue = []

            try:
                while not stop_evt.is_set() and proc_ref.poll() is None:
                    now_perf = time.perf_counter()

                    # Check if we should advance to another slide (only when >1 photo or forced step)
                    should_step = (self.gallery_force_step != 0) or (
                        total_imgs > 1 and not self.is_paused and now_perf >= slide_deadline
                    )
                    if should_step:
                        if self.gallery_force_step != 0:
                            step_dir = self.gallery_force_step
                            self.gallery_force_step = 0
                            next_idx = (cur_idx + step_dir) % total_imgs
                        else:
                            next_idx = (cur_idx + 1) % total_imgs
                            if next_idx == 0 and self.gallery_shuffle and total_imgs > 2:
                                random.shuffle(self.gallery_images)
                                slide_cache.clear()

                        next_file = self.gallery_images[next_idx]
                        next_pil, next_bytes = _render_slide_pil(next_file, next_idx, total_imgs, out_w, out_h)

                        # Build smooth 6-frame crossfade if multiple photos
                        if total_imgs > 1 and self.gallery_transition and cur_pil is not None:
                            transition_queue = [
                                Image.blend(cur_pil, next_pil, alpha / 6.0).tobytes()
                                for alpha in range(1, 6)
                            ]

                        cur_idx = next_idx
                        cur_pil = next_pil
                        cur_frame_bytes = next_bytes
                        self.gallery_index = cur_idx
                        slide_deadline = time.perf_counter() + float(self.gallery_interval)
                        self.current_title = (
                            f"{'[PAUSED] ' if self.is_paused else ''}"
                            f"Gallery [{cur_idx + 1}/{total_imgs}]: {os.path.basename(next_file)}"
                        )
                        self.status_cb(self.current_mode, self.current_title)

                        # Pre-render the upcoming slide in background
                        if total_imgs > 1:
                            _preload_slide_async((cur_idx + 1) % total_imgs, total_imgs, out_w, out_h)
                    elif self.is_paused:
                        # Keep pushing slide_deadline forward while paused
                        slide_deadline = now_perf + float(self.gallery_interval)

                    frame_to_send = transition_queue.pop(0) if transition_queue else cur_frame_bytes
                    proc_ref.stdin.write(frame_to_send)

                    next_frame_t += frame_interval
                    sleep_s = next_frame_t - time.perf_counter()
                    if sleep_s > 0:
                        time.sleep(sleep_s)
                    elif sleep_s < -0.5:
                        next_frame_t = time.perf_counter()
            except Exception as e:
                if not stop_evt.is_set():
                    self.log(f"Gallery slideshow ended: {e}")
            finally:
                stop_evt.set()
                with self.stream_lock:
                    if self.ffmpeg_proc == proc_ref and self.running and not stop_evt.is_set():
                        threading.Thread(target=self.start_standby_stream, daemon=True).start()

        threading.Thread(target=_worker, daemon=True).start()

    def step_gallery_slide(self, step: int = 1):
        if self.current_mode == "GALLERY":
            self.gallery_force_step = 1 if step >= 0 else -1

    def _start_wasapi_audio_tcp_feeder(self, stop_evt: threading.Event):
        """
        Captures live Windows PC speaker output via WASAPI loopback and feeds raw s16le PCM over
        a localhost TCP socket using a strict wall-clock pacer so FFmpeg NEVER starves when speakers are silent.
        """
        if not self.capture_pc_audio or pyaudio is None or self.audio_codec == "none":
            return None

        try:
            pa = pyaudio.PyAudio()
            wasapi_info = pa.get_host_api_info_by_type(pyaudio.paWASAPI)
            default_out = pa.get_device_info_by_index(wasapi_info["defaultOutputDevice"])
            loopback_dev = None
            for dev in pa.get_loopback_device_info_generator():
                if default_out["name"] in dev["name"]:
                    loopback_dev = dev
                    break
            if loopback_dev is None:
                for dev in pa.get_loopback_device_info_generator():
                    if dev.get("maxInputChannels", 0) > 0:
                        loopback_dev = dev
                        break
            if loopback_dev is None:
                pa.terminate()
                return None

            rate = int(loopback_dev.get("defaultSampleRate", 48000) or 48000)
            channels = min(2, max(1, int(loopback_dev.get("maxInputChannels", 2) or 2)))
            dev_idx = loopback_dev["index"]
            chunk_sec = 0.020
            frames_per_chunk = int(rate * chunk_sec)
            bytes_per_chunk = frames_per_chunk * channels * 2

            srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            srv.bind(("127.0.0.1", 0))
            srv.listen(1)
            srv.settimeout(5.0)
            port = srv.getsockname()[1]

            audio_q = queue.Queue(maxsize=100)

            def _pa_cb(in_data, frame_count, time_info, status):
                try:
                    audio_q.put_nowait(in_data)
                except queue.Full:
                    pass
                return (None, pyaudio.paContinue)

            stream = pa.open(
                format=pyaudio.paInt16,
                channels=channels,
                rate=rate,
                input=True,
                input_device_index=dev_idx,
                frames_per_buffer=frames_per_chunk,
                stream_callback=_pa_cb,
            )
            stream.start_stream()

            def _tcp_worker():
                conn = None
                silence_chunk = b"\x00" * bytes_per_chunk
                try:
                    conn, _ = srv.accept()
                    next_tick = time.perf_counter()
                    while not stop_evt.is_set():
                        # Drain any immediately available WASAPI chunks
                        sent_any = False
                        while not stop_evt.is_set():
                            try:
                                pcm = audio_q.get_nowait()
                                conn.sendall(pcm)
                                next_tick += chunk_sec
                                sent_any = True
                            except queue.Empty:
                                break

                        now_t = time.perf_counter()
                        # If speakers are silent and wall clock passed next_tick, inject exact silence chunk
                        while now_t >= next_tick and not stop_evt.is_set():
                            conn.sendall(silence_chunk)
                            next_tick += chunk_sec
                            sent_any = True

                        sleep_s = next_tick - time.perf_counter()
                        if sleep_s > 0.002:
                            time.sleep(min(0.015, sleep_s))
                        elif not sent_any:
                            time.sleep(0.003)
                except Exception:
                    pass
                finally:
                    try:
                        stream.stop_stream()
                        stream.close()
                    except Exception:
                        pass
                    try:
                        pa.terminate()
                    except Exception:
                        pass
                    try:
                        if conn:
                            conn.close()
                        srv.close()
                    except Exception:
                        pass

            threading.Thread(target=_tcp_worker, daemon=True).start()
            self.log(f"PC Speaker Audio Loopback active: {loopback_dev['name']} ({rate}Hz, {channels}ch)")
            return (port, rate, channels)
        except Exception as e:
            self.log(f"PC Audio Loopback fallback to silent track: {e}")
            return None

    def start_screen_cast(self, monitor_indices: list = None, source: str = "Desktop App"):
        if monitor_indices is not None:
            self.selected_monitors = monitor_indices

        def _worker():
            attach_thread_to_default_desktop()
            if mss is None:
                self.log("ERROR: 'mss' package is required for PC Desktop Mirroring.")
                return

            mon_left, mon_top, cap_w, cap_h, desc = self.compute_monitor_region(self.selected_monitors)
            capture_rect = {"left": mon_left, "top": mon_top, "width": cap_w, "height": cap_h}

            with self.stream_lock:
                self._stop_ffmpeg_locked()
                self.screen_stop_event.clear()
                stop_evt = self.screen_stop_event

                audio_info = self._start_wasapi_audio_tcp_feeder(stop_evt)
                if audio_info:
                    aport, arate, achan = audio_info
                    audio_input_args = [
                        "-thread_queue_size", "512",
                        "-f", "s16le",
                        "-ar", str(arate),
                        "-ac", str(achan),
                        "-i", f"tcp://127.0.0.1:{aport}",
                    ]
                else:
                    audio_input_args = [
                        "-f", "lavfi",
                        "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
                    ]

                cmd = (
                    [
                        self.ffmpeg_exe,
                        "-hide_banner",
                        "-loglevel", "warning",
                        "-thread_queue_size", "256",
                        "-f", "rawvideo",
                        "-pix_fmt", "bgra",
                        "-s", f"{cap_w}x{cap_h}",
                        "-r", str(self.fps),
                        "-i", "pipe:0",
                    ]
                    + audio_input_args
                    + self._build_dual_output_args("1:a:0")
                )

                self.current_mode = "SCREEN"
                self.current_title = f"PC Desktop: {desc}"
                self.active_source = source
                self.is_paused = False
                self.status_cb(self.current_mode, self.current_title)

                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                self.ffmpeg_proc = subprocess.Popen(
                    cmd,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    bufsize=cap_w * cap_h * 4 * 2,
                    startupinfo=startupinfo,
                )
                proc_ref = self.ffmpeg_proc
                self._attach_ffmpeg_log_drainer(proc_ref, "Screen")

            self.log(f"[{source}] Started Desktop Mirroring [{desc}] @ {self.fps}fps to NVR.")

            frame_interval = 1.0 / float(self.fps)
            next_frame_t = time.perf_counter()
            sct = None
            last_buf = None
            try:
                sct = mss.MSS()
                while not stop_evt.is_set() and proc_ref.poll() is None:
                    if not self.is_paused or last_buf is None:
                        shot = sct.grab(capture_rect)
                        buf = bytearray(shot.raw)
                        if self.show_cursor:
                            draw_cursor_on_bgra(buf, cap_w, cap_h, mon_left, mon_top)
                        last_buf = buf
                    proc_ref.stdin.write(last_buf)

                    next_frame_t += frame_interval
                    sleep_time = next_frame_t - time.perf_counter()
                    if sleep_time > 0:
                        time.sleep(sleep_time)
                    elif sleep_time < -0.5:
                        next_frame_t = time.perf_counter()
            except Exception as e:
                if not stop_evt.is_set():
                    self.log(f"Desktop capture ended: {e}")
            finally:
                stop_evt.set()
                try:
                    if sct:
                        sct.close()
                except Exception:
                    pass
                with self.stream_lock:
                    if self.ffmpeg_proc == proc_ref and self.running and not stop_evt.is_set():
                        threading.Thread(target=self.start_standby_stream, daemon=True).start()

        threading.Thread(target=_worker, daemon=True).start()

    def start_browser_cast(
        self,
        label: str = "Web Meeting Screen/Tab Share",
        source: str = "Web Studio / Chrome Extension",
    ):
        """
        Receives live WebM chunks from either:
          - Chrome Extension HTML5 <video>.captureStream() (PiP-style live player mirroring)
          - Web Cast Studio getDisplayMedia() (Meeting-style Tab / Window / Screen share)
        and pipes them to the NVR RTSP server.
        """
        with self.stream_lock:
            self._stop_ffmpeg_locked()
            self.browser_chunk_queue = queue.Queue(maxsize=300)
            q_ref = self.browser_chunk_queue
            self.current_mode = "BROWSER"
            self.current_title = label
            self.active_source = source
            self.is_paused = False
            self.status_cb(self.current_mode, self.current_title)

            cmd = (
                [
                    self.ffmpeg_exe,
                    "-hide_banner",
                    "-loglevel", "warning",
                    "-fflags", "+genpts+igndts+nobuffer",
                    "-i", "pipe:0",
                    "-f", "lavfi",
                    "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
                ]
                + self._build_dual_output_args("0:a:0?")
            )

            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            self.ffmpeg_proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                startupinfo=startupinfo,
            )
            proc_ref = self.ffmpeg_proc
            self._attach_ffmpeg_log_drainer(proc_ref, "BrowserCast")

        self.log(f"[{source}] Started Live Browser Cast: '{label}'")

        def _feeder():
            try:
                while proc_ref.poll() is None:
                    chunk = q_ref.get()
                    if chunk is None:
                        break
                    proc_ref.stdin.write(chunk)
                    proc_ref.stdin.flush()
            except Exception as e:
                self.log(f"Browser cast stream ended: {e}")
            finally:
                try:
                    if proc_ref.stdin:
                        proc_ref.stdin.close()
                except Exception:
                    pass
                proc_ref.wait()
                with self.stream_lock:
                    if self.ffmpeg_proc == proc_ref and self.running:
                        self.log("Browser cast stopped. Returning to Standby feed...")
                        threading.Thread(target=self.start_standby_stream, daemon=True).start()

        threading.Thread(target=_feeder, daemon=True).start()

    def push_browser_chunk(self, data: bytes) -> bool:
        q = self.browser_chunk_queue
        if q is None or self.current_mode != "BROWSER":
            return False
        try:
            q.put_nowait(data)
            return True
        except queue.Full:
            return False

    def shutdown(self):
        self.running = False
        with self.stream_lock:
            self._stop_ffmpeg_locked()
        if self.mediamtx_proc and self.mediamtx_proc.poll() is None:
            try:
                self.mediamtx_proc.terminate()
                self.mediamtx_proc.wait(timeout=2)
            except Exception:
                try:
                    self.mediamtx_proc.kill()
                except Exception:
                    pass
