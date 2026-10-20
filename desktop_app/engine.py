import os
import io
import sys
import time
import json
import queue
import base64
import random
import ctypes
import collections
from ctypes import wintypes
import socket
import shutil
import urllib.parse
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
CONFIG_DIR = os.path.join(APP_DIR, "config")
CONFIG_JSON_PATH = os.path.join(CONFIG_DIR, "nvr_cast_config.json")
DEFAULT_VLC_M3U_PATH = os.path.join(CONFIG_DIR, "NVR_Cast_Hub_Channels_VLC.m3u")
MEDIAMTX_EXE = os.path.join(BIN_DIR, "mediamtx.exe")
MEDIAMTX_YML = os.path.join(BIN_DIR, "mediamtx.yml")

SUPPORTED_IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".bmp", ".webp", ".gif")
SUPPORTED_VIDEO_EXTS = (".mp4", ".mkv", ".avi", ".mov", ".ts", ".webm", ".m4v")

BUILTIN_TV_CHANNELS = {
    "cricket_pk": [
        {
            "title": "Geo Super HD (1080p Live Cricket & Sports)",
            "group": "Pakistan Cricket",
            "url": "http://116.90.120.149:8000/play/a021/index.m3u8",
        },
        {
            "title": "Willow Cricket HD (720p Live Cricket)",
            "group": "Live Cricket",
            "url": "http://tvsen5.aynascope.net/willowhd/index.m3u8",
        },
        {
            "title": "Ten Cricket Live",
            "group": "Live Cricket",
            "url": "http://103.151.60.162:2122/play/a0fj/index.m3u8?hls",
        },
        {
            "title": "PK Sports HD (Pakistan 720p)",
            "group": "Pakistan Sports",
            "url": "https://lbgo.bozztv.com/ssh101/ssh101/pksportshd/playlist.m3u8",
        },
        {
            "title": "M Sports HD (Pakistan 1080p)",
            "group": "Pakistan Sports",
            "url": "https://cdn.rabta.stream/M-Sports/index.m3u8",
        },
        {
            "title": "Sony Sports Ten 5 Live",
            "group": "Live Cricket",
            "url": "http://103.151.60.162:2122/play/a028/index.m3u8?hls",
        },
        {
            "title": "Star Sports 2 Live",
            "group": "Live Cricket",
            "url": "http://103.151.60.162:2122/play/a00v/index.m3u8?hls",
        },
        {
            "title": "Star Sports Select 1 HD (1080p)",
            "group": "Live Sports",
            "url": "http://103.151.60.162:2122/play/a026/index.m3u8?hls",
        },
        {
            "title": "Star Sports Select 2 HD (1080p)",
            "group": "Live Sports",
            "url": "http://103.151.60.162:2122/play/a027/index.m3u8?hls",
        },
        {
            "title": "DD Sports HD (1080p)",
            "group": "Live Sports",
            "url": "https://d3qs3d2rkhfqrt.cloudfront.net/out/v1/b17adfe543354fdd8d189b110617cddd/index.m3u8",
        },
        {
            "title": "T Sports 7 Live",
            "group": "Live Cricket",
            "url": "https://live-us1.thaimomo.com/live-as/chtsport-1/playlist.m3u8",
        },
    ],
    "pakistan_tv": [
        {
            "title": "24 News HD (Pakistan Live)",
            "group": "Pakistan News",
            "url": "https://cdn4.mjunoon.tv:8087/streamtest/146M/chunks.m3u8",
        },
        {
            "title": "Dunya News HD (Pakistan Live)",
            "group": "Pakistan News",
            "url": "https://imob.dunyanews.tv/livehd/ngrp:dunyalivehd_2_all/playlist.m3u8",
        },
        {
            "title": "365 News HD (Pakistan Live)",
            "group": "Pakistan News",
            "url": "https://cdn4.mjunoon.tv:8087/streamtest/140M/chunks.m3u8",
        },
        {
            "title": "Capital TV News (Pakistan Live)",
            "group": "Pakistan News",
            "url": "https://cdn4.mjunoon.tv:8087/streamtest/111M/chunks.m3u8",
        },
        {
            "title": "Lahore News HD (Pakistan)",
            "group": "Pakistan News",
            "url": "https://vcdn.dunyanews.tv/lahorelive/ngrp:lnews_1_all/playlist.m3u8",
        },
        {
            "title": "M News HD (1080p Pakistan)",
            "group": "Pakistan News",
            "url": "https://cdn.rabta.stream/M-News/index.m3u8",
        },
        {
            "title": "Such TV News (Pakistan Live)",
            "group": "Pakistan News",
            "url": "https://video.primexsports.com/suchnews/live/playlist.m3u8",
        },
        {
            "title": "ABN Urdu (Pakistan Live)",
            "group": "Pakistan News",
            "url": "https://mediaserver.abnvideos.com/streams/abnurdu.m3u8",
        },
        {
            "title": "Bol Entertainment HD (Pakistan)",
            "group": "Pakistan Entertainment",
            "url": "https://vodzong.mjunoon.tv:8087/streamtest/Channel5-159-4/playlist.m3u8",
        },
        {
            "title": "aurLife HD (Pakistan Entertainment)",
            "group": "Pakistan Entertainment",
            "url": "http://124.109.47.101/hls/stream1.m3u8",
        },
        {
            "title": "8XM Music TV (Pakistan)",
            "group": "Pakistan Music",
            "url": "https://cdn4.mjunoon.tv:8087/streamtest/131M/chunks.m3u8",
        },
        {
            "title": "JooMusic HD (Pakistan 720p)",
            "group": "Pakistan Music",
            "url": "https://livecdn.live247stream.com/joomusic/tv/playlist.m3u8",
        },
        {
            "title": "Madani Channel HD (Pakistan 720p)",
            "group": "Pakistan Islamic",
            "url": "http://tvsen7.aynascope.net/MadaniTV/index.m3u8",
        },
        {
            "title": "BS Film (Pakistan Movies)",
            "group": "Pakistan Movies",
            "url": "https://lbgo.bozztv.com/ssh101/ssh101/bsfilm/playlist.m3u8",
        },
        {
            "title": "BSTV Pakistan",
            "group": "Pakistan TV",
            "url": "https://lbgo.bozztv.com/ssh101/ssh101/bstv/playlist.m3u8",
        },
        {
            "title": "Falak TV (Pakistan Live)",
            "group": "Pakistan TV",
            "url": "https://falak.rst.ae/index.m3u8",
        },
        {
            "title": "Fazal TV HD (1080p)",
            "group": "Pakistan TV",
            "url": "http://cdn9.live247stream.com/punjabitvcanada/tv/playlist.m3u8",
        },
        {
            "title": "Minimax Kids (Pakistan)",
            "group": "Pakistan Kids",
            "url": "https://vodzong.mjunoon.tv:8087/streamtest/disckids-157-1/playlist.m3u8",
        },
        {
            "title": "ARY News Official (YouTube Live)",
            "group": "Pakistan News (YT)",
            "url": "https://www.youtube.com/@ARYNewsTvofficial/streams",
        },
        {
            "title": "Geo News Official (YouTube Live)",
            "group": "Pakistan News (YT)",
            "url": "https://www.youtube.com/@geonews/streams",
        },
        {
            "title": "Hum News Official (YouTube Live)",
            "group": "Pakistan News (YT)",
            "url": "https://www.youtube.com/@HumNewsPakistan/streams",
        },
        {
            "title": "Samaa TV Official (YouTube Live)",
            "group": "Pakistan News (YT)",
            "url": "https://www.youtube.com/@SamaaTv/streams",
        },
        {
            "title": "Express News Official (YouTube Live)",
            "group": "Pakistan News (YT)",
            "url": "https://www.youtube.com/@ExpressNews/streams",
        },
        {
            "title": "Dawn News Official (YouTube Live)",
            "group": "Pakistan News (YT)",
            "url": "https://www.youtube.com/@dawnnews/streams",
        },
    ],
    "youtube_cricket": [
        {
            "title": "Pakistan Cricket (PCB Official — Matches & Highlights)",
            "group": "YouTube Cricket",
            "url": "https://www.youtube.com/@pakistancricket/videos",
        },
        {
            "title": "Pakistan Cricket LIVE (PCB Live Domestic & Series Streams)",
            "group": "YouTube Cricket",
            "url": "https://www.youtube.com/@pakistancricket/streams",
        },
        {
            "title": "Sports Central (Pakistan Matches & PSL Official Highlights)",
            "group": "YouTube Cricket",
            "url": "https://www.youtube.com/@SportsCentralOfficial/videos",
        },
        {
            "title": "Pakistan Super League (Official PSL Videos & Matches)",
            "group": "YouTube Cricket",
            "url": "https://www.youtube.com/@PakistanSuperLeagueOfficial/videos",
        },
        {
            "title": "A Sports HD Official (Pakistan Sports YouTube)",
            "group": "YouTube Cricket",
            "url": "https://www.youtube.com/@asportstvpk/videos",
        },
        {
            "title": "PTV Sports Official (Pakistan Sports YouTube)",
            "group": "YouTube Cricket",
            "url": "https://www.youtube.com/@ptvsportsofficial/videos",
        },
        {
            "title": "Asian Cricket Council (Asia Cup & Pakistan Classics)",
            "group": "YouTube Cricket",
            "url": "https://www.youtube.com/@AsianCricketCouncilTV/videos",
        },
        {
            "title": "ICC Official (World Cup & International Cricket)",
            "group": "YouTube Cricket",
            "url": "https://www.youtube.com/@ICC/videos",
        },
        {
            "title": "Willow Cricket Official YouTube (Match Highlights)",
            "group": "YouTube Cricket",
            "url": "https://www.youtube.com/@willow/videos",
        },
    ],
    "global_sports": [
        {
            "title": "ESPN HD (720p Live Sports)",
            "group": "Global Sports",
            "url": "http://85.237.89.160:9590/usa-s/ESPN-HD/index.m3u8",
        },
        {
            "title": "ESPN 2 HD (720p Live Sports)",
            "group": "Global Sports",
            "url": "http://85.237.89.160:9590/usa-s/ESPN-2-HD/index.m3u8",
        },
        {
            "title": "ESPNU HD (720p College & World Sports)",
            "group": "Global Sports",
            "url": "http://85.237.89.160:9590/usa-s/ESPN-U-HD/index.m3u8",
        },
        {
            "title": "Tennis Channel 2 HD (Live Tennis)",
            "group": "Global Sports",
            "url": "https://mumbai-edge.smartplaytv.in/Tennis2/index.m3u8",
        },
        {
            "title": "Unbeaten Sports Network (1080p 24/7 Sports)",
            "group": "Global Sports",
            "url": "https://d1t5afz6qed3xk.cloudfront.net/Unbeaten.m3u8",
        },
        {
            "title": "30A Golf Kingdom HD (720p Golf)",
            "group": "Global Sports",
            "url": "https://30a-tv.com/feeds/vidaa/golf.m3u8",
        },
    ],
    "custom_channels": [],
}

GITHUB_M3U_REPOS = [
    {
        "id": "iptv_sports",
        "name": "iptv-org: Sports Category (480+ Global Sports Channels)",
        "url": "https://iptv-org.github.io/iptv/categories/sports.m3u",
    },
    {
        "id": "iptv_pk",
        "name": "iptv-org: Pakistan Channels (100+ PK TV & Sports Channels)",
        "url": "https://iptv-org.github.io/iptv/countries/pk.m3u",
    },
    {
        "id": "curated_pk_in",
        "name": "Curated Working IPTV: Pakistan & South Asia Sports/TV (Rayyan98)",
        "url": "https://raw.githubusercontent.com/Rayyan98/my-curated-iptv/refs/heads/main/real_data/main_working.m3u",
    },
    {
        "id": "freetv_global",
        "name": "Free-TV: Global Open-Source IPTV Master List",
        "url": "https://raw.githubusercontent.com/Free-TV/IPTV/master/playlist.m3u8",
    },
    {
        "id": "iptv_all",
        "name": "iptv-org: Full Global Master Index (10,000+ Channels)",
        "url": "https://iptv-org.github.io/iptv/index.m3u",
    },
]


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
        self.prefetch_proc = None
        self.stream_lock = threading.Lock()
        self.running = False
        self.screen_stop_event = threading.Event()
        self.browser_chunk_queue = None
        self.browser_session_id = ""
        self._browser_latest_frame = None
        self._browser_frame_lock = threading.Lock()
        self._browser_pending_cmds = []
        self.browser_duration_sec = 0
        self._browser_out_size = (1280, 720)

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
        self._yt_cache = {}
        self._cast_gen = 0
        self.playlist_items = []
        self.playlist_index = 0
        self.playlist_title = ""

        # Live TV, Pakistan Cricket & GitHub M3U IPTV State
        self.channel_catalog = {k: [dict(ch) for ch in v] for k, v in BUILTIN_TV_CHANNELS.items()}
        self.tv_category = "cricket_pk"
        self.tv_source_title = "Pakistan Cricket & Live Sports"
        self.tv_filter = ""
        self.tv_custom_m3u = ""
        self.tv_channels = list(self.channel_catalog["cricket_pk"])
        self.tv_active_index = 0
        self.auto_skip_offline = False

        # 3-Way Output Routing Mode:
        #   "local_only" -> Watch/Preview inside this App ONLY (no NVR needed, 15fps 640x360 + PC Speaker Audio)
        #   "nvr_only"   -> Cast to NVR RTSP (/main & /sub) ONLY (local preview off)
        #   "both"       -> Watch Here inside App + Cast to NVR simultaneously
        self.output_mode = "both"
        self.local_audio_enabled = False
        self.local_audio_stop_evt = threading.Event()

        # Embedded hardware PC player (libVLC) — set by the Desktop GUI when VLC is available.
        # When active, the PC view + PC audio come from the embedded player (smooth, A/V synced),
        # while FFmpeg only feeds the NVR (RTSP) plus a light 8 fps heartbeat for Web Studio & health.
        self.use_embedded_player = False
        self.local_player_hook = None

        # Live Preview & Transparent Stream Health Telemetry
        self.preview_enabled = True
        self._latest_preview_jpeg = b""
        self._latest_preview_pil = None
        self._preview_frame_queue = collections.deque(maxlen=36)
        self._preview_lock = threading.Lock()
        self.stream_health = "STANDBY"       # STANDBY, PROBING, CONNECTING, LIVE, STALLED, PAUSED, ERROR
        self.stream_diag = "RTSP Server Online — Ready to Cast"
        self.stream_error_msg = ""
        self._last_ffmpeg_err = ""
        self.decoded_frames = 0
        self.last_frame_ts = 0.0

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
        self._init_and_load_config()

    def log(self, msg: str):
        timestamp = time.strftime("%H:%M:%S")
        self.log_cb(f"[{timestamp}] {msg}")

    def _init_and_load_config(self):
        """
        Loads persistent configuration & channel catalog from config/nvr_cast_config.json if present,
        and always ensures both config/nvr_cast_config.json and config/NVR_Cast_Hub_Channels_VLC.m3u
        exist on disk by default for instant VLC & setup usage.
        """
        try:
            os.makedirs(CONFIG_DIR, exist_ok=True)
            if os.path.isfile(CONFIG_JSON_PATH):
                with open(CONFIG_JSON_PATH, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                settings = cfg.get("settings", {})
                self.output_mode = settings.get("output_mode", self.output_mode)
                if self.output_mode not in ("local_only", "nvr_only", "both"):
                    self.output_mode = "both"
                self.preview_enabled = (self.output_mode != "nvr_only")
                self.local_audio_enabled = bool(settings.get("local_audio_enabled", self.output_mode == "local_only"))
                self.main_res = settings.get("main_res", self.main_res)
                self.fps = int(settings.get("fps", self.fps))
                self.video_bitrate = settings.get("video_bitrate", self.video_bitrate)
                self.audio_codec = settings.get("audio_codec", self.audio_codec)
                self.aspect_mode = settings.get("aspect_mode", self.aspect_mode)
                self.show_cursor = bool(settings.get("show_cursor", self.show_cursor))
                self.capture_pc_audio = bool(settings.get("capture_pc_audio", self.capture_pc_audio))
                self.auto_skip_offline = bool(settings.get("auto_skip_offline", self.auto_skip_offline))
                self.gallery_interval = int(settings.get("gallery_interval", self.gallery_interval))
                self.gallery_shuffle = bool(settings.get("gallery_shuffle", self.gallery_shuffle))

                saved_cat = cfg.get("channel_catalog", {})
                if isinstance(saved_cat, dict):
                    for k, ch_list in saved_cat.items():
                        if isinstance(ch_list, list) and ch_list:
                            # Merge saved channels with any new built-in channels so updates are preserved
                            existing_urls = {c.get("url") for c in ch_list if isinstance(c, dict)}
                            merged = [dict(c) for c in ch_list if isinstance(c, dict) and c.get("url")]
                            for builtin_ch in BUILTIN_TV_CHANNELS.get(k, []):
                                if builtin_ch["url"] not in existing_urls:
                                    merged.append(dict(builtin_ch))
                            self.channel_catalog[k] = merged

            self.tv_channels = list(self.channel_catalog.get(self.tv_category, self.channel_catalog["cricket_pk"]))
            self.save_persistent_config()
            self.export_vlc_m3u(DEFAULT_VLC_M3U_PATH, only_current_list=False, quiet=True)
        except Exception as e:
            self.log(f"Config init note: {e}")

    def save_persistent_config(self, filepath: str = None) -> str:
        """Saves current settings and full channel catalog (including custom Pakistani/Sports channels) to JSON."""
        target = filepath or CONFIG_JSON_PATH
        try:
            os.makedirs(os.path.dirname(target), exist_ok=True)
            payload = {
                "app": "NVR Cast Hub",
                "version": APP_VERSION,
                "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "settings": {
                    "output_mode": self.output_mode,
                    "local_audio_enabled": self.local_audio_enabled,
                    "main_res": self.main_res,
                    "fps": self.fps,
                    "video_bitrate": self.video_bitrate,
                    "audio_codec": self.audio_codec,
                    "aspect_mode": self.aspect_mode,
                    "show_cursor": self.show_cursor,
                    "capture_pc_audio": self.capture_pc_audio,
                    "auto_skip_offline": self.auto_skip_offline,
                    "gallery_interval": self.gallery_interval,
                    "gallery_shuffle": self.gallery_shuffle,
                },
                "channel_catalog": self.channel_catalog,
            }
            with open(target, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, ensure_ascii=False)
            return target
        except Exception as e:
            self.log(f"Failed to save config '{target}': {e}")
            return ""

    def export_vlc_m3u(self, filepath: str = None, only_current_list: bool = False, quiet: bool = False) -> str:
        """Exports all channels (or current category) to a standard VLC Media Player .m3u playlist file."""
        target = filepath or DEFAULT_VLC_M3U_PATH
        try:
            os.makedirs(os.path.dirname(target), exist_ok=True)
            lines = ["#EXTM3U"]
            if only_current_list:
                ch_iter = self.tv_channels
            else:
                ch_iter = []
                for cat_key in ("cricket_pk", "pakistan_tv", "custom_channels", "global_sports", "youtube_cricket"):
                    ch_iter.extend(self.channel_catalog.get(cat_key, []))

            seen_urls = set()
            count = 0
            for ch in ch_iter:
                u = (ch.get("url") or "").strip()
                if not u or u in seen_urls:
                    continue
                seen_urls.add(u)
                t = (ch.get("title") or "Channel").replace(",", " -")
                g = (ch.get("group") or "Live TV").replace('"', "'")
                ref = (ch.get("referrer") or "").strip()
                lines.append(f'#EXTINF:-1 group-title="{g}",{t}')
                if ref:
                    lines.append(f"#EXTVLCOPT:http-referrer={ref}")
                lines.append(u)
                count += 1

            with open(target, "w", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")
            if not quiet:
                self.log(f"Exported {count} channels to VLC Playlist: {target}")
            return target
        except Exception as e:
            self.log(f"Failed to export VLC M3U '{target}': {e}")
            return ""

    def import_config_or_m3u(self, filepath: str) -> dict:
        """Imports either a .json configuration file or a .m3u/.m3u8 VLC playlist file and saves to persistent config."""
        if not filepath or not os.path.isfile(filepath):
            return {"ok": False, "message": f"File not found: {filepath}"}
        try:
            low = filepath.lower()
            if low.endswith(".json"):
                with open(filepath, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                saved_cat = cfg.get("channel_catalog", {})
                imported_count = 0
                if isinstance(saved_cat, dict):
                    for k, ch_list in saved_cat.items():
                        if isinstance(ch_list, list):
                            self.channel_catalog[k] = [dict(c) for c in ch_list if isinstance(c, dict) and c.get("url")]
                            imported_count += len(self.channel_catalog[k])
                elif isinstance(cfg.get("channels"), list):
                    ch_list = [dict(c) for c in cfg["channels"] if isinstance(c, dict) and c.get("url")]
                    self.channel_catalog["custom_channels"] = ch_list
                    self.tv_category = "custom_channels"
                    imported_count = len(ch_list)

                self.load_tv_category_or_m3u(self.tv_category, auto_play=False, source="Config Import")
                self.save_persistent_config()
                self.export_vlc_m3u(DEFAULT_VLC_M3U_PATH, quiet=True)
                msg = f"Imported JSON configuration ({imported_count} channels) from {os.path.basename(filepath)}"
                self.log(msg)
                return {"ok": True, "count": imported_count, "message": msg}
            else:
                with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                parsed = self.parse_m3u_content(content, default_group="Imported M3U")
                if not parsed:
                    return {"ok": False, "message": "No valid stream URLs found in M3U file."}
                existing = self.channel_catalog.get("custom_channels", [])
                existing_urls = {c.get("url") for c in existing}
                added = 0
                for ch in parsed:
                    if ch["url"] not in existing_urls:
                        existing.append(ch)
                        existing_urls.add(ch["url"])
                        added += 1
                self.channel_catalog["custom_channels"] = existing
                self.tv_category = "custom_channels"
                self.tv_source_title = f"Imported & Custom Channels ({len(existing)})"
                self.tv_channels = list(existing)
                self.tv_active_index = 0
                self.save_persistent_config()
                self.export_vlc_m3u(DEFAULT_VLC_M3U_PATH, quiet=True)
                msg = f"Imported {len(parsed)} channel(s) ({added} new) from {os.path.basename(filepath)}"
                self.log(msg)
                return {"ok": True, "count": len(parsed), "message": msg}
        except Exception as e:
            err = f"Import failed: {e}"
            self.log(err)
            return {"ok": False, "message": err}

    def add_channel(
        self,
        title: str,
        url: str,
        category: str = "pakistan_tv",
        group: str = "Pakistan TV",
        referrer: str = "",
    ) -> dict:
        """Adds a custom channel (e.g., Pakistani TV, Sports, M3U8, or YouTube) and saves to config & VLC M3U."""
        title = (title or "").strip()
        url = (url or "").strip()
        if not title or not url:
            return {"ok": False, "message": "Both Channel Name and Stream URL are required."}
        if category not in self.channel_catalog:
            category = "pakistan_tv"

        new_ch = {
            "title": title,
            "group": (group or "Pakistan TV").strip(),
            "url": url,
        }
        if referrer:
            new_ch["referrer"] = referrer.strip()

        cat_list = self.channel_catalog.setdefault(category, [])
        cat_list.insert(0, new_ch)
        self.tv_category = category
        self.load_tv_category_or_m3u(category, filter_keyword="", auto_play=False, source="Channel Manager")
        self.save_persistent_config()
        self.export_vlc_m3u(DEFAULT_VLC_M3U_PATH, quiet=True)
        self.log(f"Added channel '{title}' ({group}) to '{category}' and updated VLC M3U config.")
        return {"ok": True, "channel": new_ch, "count": len(self.tv_channels)}

    def remove_channel(self, index: int = None, url: str = "") -> dict:
        """Removes a channel from the active channel list and persistent catalog."""
        target_url = (url or "").strip()
        target_title = ""
        if index is not None and 0 <= int(index) < len(self.tv_channels):
            removed = self.tv_channels.pop(int(index))
            target_url = removed.get("url", "")
            target_title = removed.get("title", "")
        elif target_url:
            for i, ch in enumerate(self.tv_channels):
                if ch.get("url") == target_url:
                    target_title = ch.get("title", "")
                    self.tv_channels.pop(i)
                    break

        if target_url:
            for k in list(self.channel_catalog.keys()):
                self.channel_catalog[k] = [c for c in self.channel_catalog[k] if c.get("url") != target_url]
            self.save_persistent_config()
            self.export_vlc_m3u(DEFAULT_VLC_M3U_PATH, quiet=True)
            self.log(f"Removed channel '{target_title or target_url}' and updated config.")
            return {"ok": True, "count": len(self.tv_channels)}
        return {"ok": False, "message": "Channel not found."}

    def reset_default_channels(self) -> dict:
        """Restores all built-in Pakistani Cricket, Pakistan TV, YouTube Cricket & Global Sports channels."""
        self.channel_catalog = {k: [dict(ch) for ch in v] for k, v in BUILTIN_TV_CHANNELS.items()}
        self.load_tv_category_or_m3u("cricket_pk", filter_keyword="", auto_play=False, source="Reset Defaults")
        self.save_persistent_config()
        self.export_vlc_m3u(DEFAULT_VLC_M3U_PATH, quiet=True)
        self.log("Restored default Pakistani & Sports channel lineup and regenerated VLC M3U playlist.")
        return {"ok": True, "count": len(self.tv_channels)}

    def open_in_vlc(self, url_or_path: str = None) -> dict:
        """Opens a specific channel stream URL or the full VLC .m3u playlist in VLC Media Player."""
        target = (url_or_path or "").strip()
        if not target:
            self.export_vlc_m3u(DEFAULT_VLC_M3U_PATH, quiet=True)
            target = DEFAULT_VLC_M3U_PATH

        vlc_candidates = [
            r"C:\Program Files\VideoLAN\VLC\vlc.exe",
            r"C:\Program Files (x86)\VideoLAN\VLC\vlc.exe",
            shutil.which("vlc") or "",
        ]
        vlc_exe = next((p for p in vlc_candidates if p and os.path.isfile(p)), None)
        try:
            if vlc_exe:
                subprocess.Popen([vlc_exe, target])
                self.log(f"Opened in VLC Media Player: {target}")
                return {"ok": True, "player": "VLC", "target": target}
            else:
                os.startfile(target)
                self.log(f"Opened with system media handler: {target}")
                return {"ok": True, "player": "System Default", "target": target}
        except Exception as e:
            err = f"Could not launch VLC / Media Player: {e}"
            self.log(err)
            return {"ok": False, "message": err}

    def set_output_mode(self, mode: str, source: str = "User") -> str:
        """
        Switches output routing mode between:
          - 'local_only': Watch/Preview inside this App ONLY (no NVR needed, enables local PC audio)
          - 'nvr_only':   Cast to NVR RTSP (/main & /sub) ONLY (pauses local preview)
          - 'both':       Watch inside App + Cast to NVR simultaneously
        """
        mode = (mode or "both").strip().lower()
        if mode not in ("local_only", "nvr_only", "both"):
            mode = "both"
        old_mode = self.output_mode
        self.output_mode = mode
        if mode == "local_only":
            self.preview_enabled = True
            self.local_audio_enabled = True
        elif mode == "nvr_only":
            self.preview_enabled = False
            self.local_audio_enabled = False
        else:
            self.preview_enabled = True

        self.save_persistent_config()
        labels = {
            "local_only": "🖥 PREVIEW ONLY (Watch Here in App — No NVR Needed)",
            "nvr_only": "📡 NVR ONLY (Cast to NVR — Local Preview Off)",
            "both": "🖥 + 📡 BOTH (Watch Here in App + Cast to NVR)",
        }
        self.log(f"[{source}] Output Mode set to: {labels[mode]}")

        # If a stream is currently active and we switched between local_only and NVR modes, restart pipeline seamlessly
        if old_mode != mode and not self.is_paused:
            if self.current_mode == "YOUTUBE" and self.current_url:
                cur_pos = self.get_current_playback_sec()
                self.start_youtube_stream(
                    self.current_url,
                    start_sec=cur_pos,
                    loop=self.loop_video,
                    source=self.active_source,
                    _from_playlist=(len(self.playlist_items) > 1),
                    custom_title=self.current_title.replace("[LOOP] ", ""),
                )
            elif self.current_mode == "FILE" and self.current_filepath:
                cur_pos = self.get_current_playback_sec()
                self.start_local_file_stream(
                    self.current_filepath,
                    start_sec=cur_pos,
                    loop=self.loop_video,
                    source=self.active_source,
                )
            elif self.current_mode == "GALLERY" and self.gallery_images:
                self.start_gallery_slideshow(
                    self.gallery_images,
                    interval_sec=self.gallery_interval,
                    shuffle=self.gallery_shuffle,
                    source=self.active_source,
                )
            elif self.current_mode == "SCREEN":
                self.start_screen_cast(self.selected_monitors, source=self.active_source)
            elif self.current_mode == "STANDBY":
                self.start_standby_stream(source=self.active_source)
        return self.output_mode

    def toggle_local_audio(self, force_state: bool = None) -> bool:
        """Toggles local PC speaker audio playback when watching channels/videos inside the app."""
        self.local_audio_enabled = (not self.local_audio_enabled) if force_state is None else bool(force_state)
        self.save_persistent_config()
        self._pc_player_command("mute", {"muted": not self.local_audio_enabled})
        self.log(f"App Local Speaker Audio: {'ON (Playing on PC Speakers)' if self.local_audio_enabled else 'MUTED'}")
        return self.local_audio_enabled

    def _pc_player_enabled(self) -> bool:
        return bool(self.use_embedded_player and self.local_player_hook and self.output_mode in ("local_only", "both"))

    def _start_pc_feed_server(self, feed_q: "queue.Queue", gen: int) -> int:
        """
        Serves the prefetcher's muxed MPEG-TS (video + AAC audio) to the embedded PC player over
        http://127.0.0.1:<port>/live.ts. One network pull feeds both NVR and PC, and split
        YouTube video/audio playlists reach the PC player already muxed.
        """
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(("127.0.0.1", 0))
        srv.listen(2)
        srv.settimeout(0.5)
        port = srv.getsockname()[1]

        def _serve():
            finished = False
            try:
                while not finished and gen == self._cast_gen and self.running:
                    try:
                        conn, _ = srv.accept()
                    except socket.timeout:
                        continue
                    try:
                        conn.settimeout(5.0)
                        req = b""
                        while b"\r\n\r\n" not in req and len(req) < 8192:
                            part = conn.recv(1024)
                            if not part:
                                break
                            req += part
                        conn.sendall(
                            b"HTTP/1.0 200 OK\r\nContent-Type: video/mp2t\r\n"
                            b"Cache-Control: no-cache\r\nConnection: close\r\n\r\n"
                        )
                        conn.settimeout(10.0)
                        while gen == self._cast_gen and self.running:
                            try:
                                chunk = feed_q.get(timeout=0.5)
                            except queue.Empty:
                                continue
                            if chunk is None:
                                finished = True
                                break
                            conn.sendall(chunk)
                    except Exception:
                        pass  # player disconnected; allow it to reconnect
                    finally:
                        try:
                            conn.close()
                        except Exception:
                            pass
            finally:
                try:
                    srv.close()
                except Exception:
                    pass

        threading.Thread(target=_serve, daemon=True).start()
        return port

    def _pc_player_command(self, action: str, payload: dict = None):
        hook = self.local_player_hook
        if hook is None:
            return
        try:
            hook(action, payload or {})
        except Exception:
            pass

    def _set_diagnostic_preview_frame(
        self,
        badge: str,
        title: str,
        subtitle: str,
        accent_rgb: tuple = (37, 99, 235),
    ):
        """Renders a clean 640x360 diagnostic card into _latest_preview_jpeg during PROBING, CONNECTING, or ERROR."""
        if Image is None:
            return
        try:
            im = Image.new("RGB", (640, 360), (15, 23, 42))
            draw = ImageDraw.Draw(im)
            draw.rectangle([(32, 32), (608, 328)], fill=(30, 41, 59), outline=(51, 65, 85), width=1)
            draw.rectangle([(32, 32), (608, 40)], fill=accent_rgb)
            try:
                f_badge = ImageFont.truetype(r"C:\Windows\Fonts\segoeuib.ttf", 18)
                f_title = ImageFont.truetype(r"C:\Windows\Fonts\segoeuib.ttf", 21)
                f_sub = ImageFont.truetype(r"C:\Windows\Fonts\segoeui.ttf", 15)
            except Exception:
                f_badge = f_title = f_sub = ImageFont.load_default()

            draw.text((56, 68), badge[:52], fill=accent_rgb, font=f_badge)
            draw.text((56, 116), (title or "Stream")[:50], fill=(248, 250, 252), font=f_title)
            sub1 = (subtitle or "")[:66]
            sub2 = (subtitle or "")[66:132]
            draw.text((56, 168), sub1, fill=(148, 163, 184), font=f_sub)
            if sub2:
                draw.text((56, 194), sub2, fill=(148, 163, 184), font=f_sub)
            mode_tag = (
                "Mode: Preview Only (Local App Player)"
                if self.output_mode == "local_only"
                else f"RTSP Output: rtsp://{self.lan_ip}:{self.rtsp_port}/main"
            )
            draw.text((56, 276), mode_tag, fill=(100, 116, 139), font=f_sub)

            buf = io.BytesIO()
            im.save(buf, format="JPEG", quality=85)
            with self._preview_lock:
                self._latest_preview_jpeg = buf.getvalue()
                self._latest_preview_pil = im.copy()
                self._preview_frame_queue.clear()
                self._preview_frame_queue.append(self._latest_preview_pil)
        except Exception:
            pass

    def get_preview_jpeg(self) -> bytes:
        with self._preview_lock:
            return self._latest_preview_jpeg

    def get_next_preview_frame(self):
        """
        Returns (newest pre-decoded PIL.Image, is_new_frame) for the legacy (non-VLC) preview path.
        FFmpeg already paces frames at 1.0x via the realtime filter, so we always present the newest
        frame: queueing here made video drift up to ~1s behind audio whenever Tk ticked slower than 25 fps.
        """
        with self._preview_lock:
            if self._preview_frame_queue:
                newest = self._preview_frame_queue[-1]
                self._preview_frame_queue.clear()
                return (newest, True)
            return (self._latest_preview_pil, False)

    def _attach_ffmpeg_log_drainer(self, proc: subprocess.Popen, tag: str = "FFmpeg"):
        """
        Drains both:
          1. proc.stdout (pipe:1): High-FPS MJPEG preview frames emitted directly by FFmpeg,
             pre-decoded into PIL.Image off the UI thread and queued in a smooth jitter buffer.
          2. proc.stderr (pipe:2): FFmpeg error/diagnostic logs.
        Ensures OS pipes NEVER block and provides 100% accurate live frame telemetry.
        """
        if not proc:
            return
        proc_gen = self._cast_gen

        if proc.stdout:
            def _drain_stdout_mjpeg():
                buf = bytearray()
                try:
                    while True:
                        chunk = proc.stdout.read(32768)
                        if not chunk:
                            break
                        buf.extend(chunk)
                        while True:
                            soi = buf.find(b"\xff\xd8")
                            if soi < 0:
                                buf.clear()
                                break
                            eoi = buf.find(b"\xff\xd9", soi + 2)
                            if eoi < 0:
                                if soi > 0:
                                    del buf[:soi]
                                break
                            jpg = bytes(buf[soi : eoi + 2])
                            del buf[: eoi + 2]
                            # Ignore frames from a superseded process or when a newer cast generation has started
                            if proc != self.ffmpeg_proc or (tag != "Standby" and proc_gen != self._cast_gen):
                                continue

                            # Pre-decode JPEG into RGB PIL.Image off the Tkinter main thread
                            pil_frame = None
                            if Image is not None:
                                try:
                                    with Image.open(io.BytesIO(jpg)) as _im:
                                        pil_frame = _im.convert("RGB")
                                except Exception:
                                    pil_frame = None

                            if tag == "Standby":
                                if self.stream_health not in ("ERROR", "PROBING", "CONNECTING"):
                                    with self._preview_lock:
                                        self._latest_preview_jpeg = jpg
                                        if pil_frame is not None:
                                            self._latest_preview_pil = pil_frame
                                            self._preview_frame_queue.clear()
                                            self._preview_frame_queue.append(pil_frame)
                                    self.decoded_frames += 1
                                    self.last_frame_ts = time.time()
                                    self.stream_health = "STANDBY"
                                    self.stream_diag = "Standby Feed Ready • Waiting for Cast"
                            elif tag == "PausedHold":
                                with self._preview_lock:
                                    self._latest_preview_jpeg = jpg
                                    if pil_frame is not None:
                                        self._latest_preview_pil = pil_frame
                                        self._preview_frame_queue.clear()
                                        self._preview_frame_queue.append(pil_frame)
                                self.decoded_frames += 1
                                self.last_frame_ts = time.time()
                                self.stream_health = "PAUSED"
                            else:
                                with self._preview_lock:
                                    self._latest_preview_jpeg = jpg
                                    if pil_frame is not None:
                                        self._latest_preview_pil = pil_frame
                                        self._preview_frame_queue.append(pil_frame)
                                self.decoded_frames += 1
                                self.last_frame_ts = time.time()
                                self.stream_health = "LIVE"
                                self.stream_diag = (
                                    f"LIVE • {self.fps} FPS • Frame #{self.decoded_frames} (Buffered)"
                                )
                except Exception:
                    pass

            threading.Thread(target=_drain_stdout_mjpeg, daemon=True).start()

        err_pipe = proc.stderr
        if err_pipe:
            def _drain_stderr():
                try:
                    for raw_line in iter(err_pipe.readline, b""):
                        if not raw_line:
                            break
                        if isinstance(raw_line, bytes):
                            line_str = raw_line.decode("utf-8", errors="ignore").strip()
                        else:
                            line_str = str(raw_line).strip()
                        if not line_str:
                            continue
                        low = line_str.lower()
                        if any(
                            k in low
                            for k in (
                                "error",
                                "invalid",
                                "403 forbidden",
                                "404 not found",
                                "timed out",
                                "connection refused",
                                "server returned",
                            )
                        ):
                            # Ignore benign h264 reorder/mmco warnings on live MPEG-TS streams
                            if any(
                                benign in low
                                for benign in (
                                    "non-existing pps",
                                    "mmco: unref",
                                    "reference picture missing",
                                    "corrupt decoded frame",
                                    "packet corrupt",
                                    "corrupt input packet",
                                )
                            ):
                                continue
                            self._last_ffmpeg_err = line_str
                            self.log(f"[{tag}] {line_str}")
                except Exception:
                    pass

            threading.Thread(target=_drain_stderr, daemon=True).start()

    def test_channel_link(self, url: str, title: str = "", referrer: str = "") -> dict:
        """Tests whether a stream URL actually connects and decodes a video frame within 6 seconds."""
        url = (url or "").strip()
        if not url:
            return {"ok": False, "message": "Empty URL"}
        t0 = time.perf_counter()
        if "youtube.com" in url.lower() or "youtu.be" in url.lower():
            try:
                with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True, "extract_flat": "in_playlist", "playlistend": 3}) as ydl:
                    info = ydl.extract_info(url, download=False)
                ms = int((time.perf_counter() - t0) * 1000)
                t_found = (info or {}).get("title") or title or "YouTube Stream"
                return {"ok": True, "latency_ms": ms, "message": f"ONLINE ({ms}ms) — {t_found}"}
            except Exception as e:
                return {"ok": False, "latency_ms": 0, "message": f"OFFLINE: {str(e)[:80]}"}

        cmd = [
            self.ffmpeg_exe,
            "-hide_banner",
            "-loglevel", "error",
            "-user_agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/125.0.0.0",
            "-rw_timeout", "5000000",
        ]
        if referrer:
            cmd += ["-headers", f"Referer: {referrer}\r\n"]
        cmd += ["-i", url, "-frames:v", "1", "-f", "null", "-"]
        try:
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=6.5, startupinfo=startupinfo)
            ms = int((time.perf_counter() - t0) * 1000)
            if r.returncode == 0:
                msg = f"ONLINE & DECODING VIDEO ({ms}ms)"
                self.log(f"[Channel Test] {title or url}: {msg}")
                return {"ok": True, "latency_ms": ms, "message": msg}
            err_lines = r.stderr.decode("utf-8", errors="ignore").strip().splitlines()
            reason = err_lines[-1] if err_lines else "Stream failed to decode"
            self.log(f"[Channel Test] {title or url}: OFFLINE ({reason})")
            return {"ok": False, "latency_ms": ms, "message": f"OFFLINE: {reason[:90]}"}
        except Exception:
            self.log(f"[Channel Test] {title or url}: OFFLINE (Timed out >6.5s)")
            return {"ok": False, "latency_ms": 6500, "message": "OFFLINE: Server timed out (>6.5s)"}

    def get_current_playback_sec(self) -> int:
        if self.current_mode == "BROWSER":
            return int(self.seek_offset_sec)
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
            "duration_sec": int(self.browser_duration_sec),
            "browser_session_id": self.browser_session_id,
            "playlist": {
                "title": self.playlist_title,
                "count": len(self.playlist_items),
                "index": self.playlist_index,
            },
            "live_tv": {
                "category": self.tv_category,
                "source_title": self.tv_source_title,
                "filter": self.tv_filter,
                "custom_m3u": self.tv_custom_m3u,
                "count": len(self.tv_channels),
                "active_index": self.tv_active_index,
            },
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
            "pc_player": dict(getattr(self, "pc_player_stats", {}) or {}),
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
            "health": {
                "state": self.stream_health,
                "diag": self.stream_diag,
                "error_msg": self.stream_error_msg,
                "decoded_frames": self.decoded_frames,
                "preview_enabled": self.preview_enabled,
                "auto_skip_offline": self.auto_skip_offline,
                "output_mode": self.output_mode,
                "local_audio_enabled": self.local_audio_enabled,
            },
            "output_mode": self.output_mode,
            "local_audio_enabled": self.local_audio_enabled,
            "config_json_path": CONFIG_JSON_PATH,
            "vlc_m3u_path": DEFAULT_VLC_M3U_PATH,
        }

    def get_tv_catalog_dict(self) -> dict:
        """Returns the full Live TV, Cricket & Sports channel lineup + GitHub M3U repository presets."""
        cats = [
            {"id": "cricket_pk", "name": "Pakistan Cricket & Live Sports TV"},
            {"id": "pakistan_tv", "name": "Pakistan News & Entertainment Live TV (24+ Channels)"},
            {"id": "youtube_cricket", "name": "Official Cricket & Pakistan News YouTube Channels"},
            {"id": "global_sports", "name": "Global Sports TV (ESPN, Eurosport, Tennis, RedBull)"},
            {"id": "all_builtin", "name": "All Built-in Sports & Pakistan Channels Combined"},
        ]
        if self.channel_catalog.get("custom_channels"):
            cats.insert(0, {"id": "custom_channels", "name": f"My Custom & Imported Channels ({len(self.channel_catalog['custom_channels'])})"})
        return {
            "category": self.tv_category,
            "source_title": self.tv_source_title,
            "filter": self.tv_filter,
            "custom_m3u": self.tv_custom_m3u,
            "active_index": self.tv_active_index,
            "channels": self.tv_channels,
            "github_repos": GITHUB_M3U_REPOS,
            "builtin_categories": cats,
            "config_json_path": CONFIG_JSON_PATH,
            "vlc_m3u_path": DEFAULT_VLC_M3U_PATH,
        }

    def parse_m3u_content(self, text: str, filter_keyword: str = "", default_group: str = "IPTV") -> list:
        """Parses standard #EXTM3U / #EXTINF IPTV playlists and optionally filters by keyword."""
        kw = (filter_keyword or "").strip().lower()
        lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
        channels = []
        pending_title = ""
        pending_group = default_group
        pending_ref = ""

        for ln in lines:
            if ln.startswith("#EXTINF"):
                # Extract channel title after the last comma
                parts = ln.split(",", 1)
                pending_title = parts[1].strip() if len(parts) > 1 else "Live TV Channel"
                pending_group = default_group
                if 'group-title="' in ln:
                    try:
                        pending_group = ln.split('group-title="', 1)[1].split('"', 1)[0].strip() or default_group
                    except Exception:
                        pass
            elif ln.startswith("#EXTVLCOPT:http-referrer="):
                pending_ref = ln.split("=", 1)[1].strip()
            elif not ln.startswith("#"):
                if ln.startswith(("http://", "https://", "rtsp://", "rtmp://")):
                    ch_title = pending_title or ln.split("/")[-1].split("?")[0] or f"Channel #{len(channels) + 1}"
                    haystack = f"{ch_title} {pending_group}".lower()
                    if not kw or kw in haystack:
                        channels.append({
                            "title": ch_title,
                            "group": pending_group,
                            "url": ln,
                            "referrer": pending_ref,
                        })
                        if len(channels) >= 400:
                            break
                pending_title = ""
                pending_ref = ""

        return channels

    def load_tv_category_or_m3u(
        self,
        category_or_url: str,
        filter_keyword: str = "",
        auto_play: bool = False,
        source: str = "Live TV & Sports",
    ) -> list:
        """
        Loads either a built-in Sports/Pakistan TV category OR any remote/local GitHub .m3u/.m3u8 playlist,
        filters by keyword if provided, and optionally starts playing Channel #1 with Next/Prev channel support.
        """
        target = (category_or_url or "cricket_pk").strip()
        kw = (filter_keyword or "").strip().lower()
        self.tv_filter = filter_keyword.strip()

        cat_titles = {
            "custom_channels": "My Custom & Imported Channels",
            "cricket_pk": "Pakistan Cricket & Live Sports TV",
            "youtube_cricket": "Official Cricket & Pakistan News YouTube Channels",
            "pakistan_tv": "Pakistan News & Entertainment Live TV (24+ Channels)",
            "global_sports": "Global Sports TV Channels",
            "all_builtin": "All Built-in Sports & Pakistan Channels",
        }

        loaded = []
        if target in self.channel_catalog or target in BUILTIN_TV_CHANNELS or target == "all_builtin":
            self.tv_category = target
            self.tv_source_title = cat_titles.get(target, "Live Sports & TV")
            if target == "all_builtin":
                raw_list = []
                for k in ("custom_channels", "cricket_pk", "pakistan_tv", "youtube_cricket", "global_sports"):
                    raw_list.extend(self.channel_catalog.get(k, BUILTIN_TV_CHANNELS.get(k, [])))
            else:
                raw_list = list(self.channel_catalog.get(target, BUILTIN_TV_CHANNELS.get(target, [])))

            for ch in raw_list:
                if not kw or kw in f"{ch['title']} {ch.get('group', '')}".lower():
                    loaded.append(dict(ch))
        else:
            # Check if target matches a GitHub repo preset ID
            repo_match = next((r for r in GITHUB_M3U_REPOS if r["id"] == target or r["url"] == target), None)
            m3u_url = repo_match["url"] if repo_match else target
            self.tv_category = repo_match["id"] if repo_match else "custom_m3u"
            self.tv_custom_m3u = m3u_url
            self.tv_source_title = repo_match["name"] if repo_match else f"M3U Playlist ({os.path.basename(m3u_url)[:32]})"

            self.log(f"[{source}] Fetching M3U Playlist: {m3u_url} (filter='{kw or 'ALL'}')...")
            try:
                if os.path.isfile(m3u_url):
                    with open(m3u_url, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()
                else:
                    req = urllib.request.Request(
                        m3u_url,
                        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/125.0.0.0"},
                    )
                    with urllib.request.urlopen(req, timeout=12) as resp:
                        content = resp.read().decode("utf-8", errors="ignore")

                loaded = self.parse_m3u_content(content, filter_keyword=kw, default_group=self.tv_source_title)
                self.log(f"[{source}] Loaded {len(loaded)} channel(s) from '{self.tv_source_title}'.")
            except Exception as e:
                self.log(f"[{source}] Failed to load M3U playlist '{m3u_url}': {e}")

        if loaded:
            self.tv_channels = loaded
            self.tv_active_index = 0
            if auto_play:
                self.play_tv_channel(index=0, source=source)
        else:
            self.log(f"[{source}] No channels matched filter '{filter_keyword}'. Keeping previous channel list.")

        return self.tv_channels

    def play_tv_channel(
        self,
        index: int = None,
        url: str = "",
        title: str = "",
        source: str = "Live TV & Sports",
    ):
        """
        Streams a channel from the active Live TV / Sports / M3U channel list and populates
        playlist_items so Next/Prev buttons step seamlessly across channels.
        """
        chosen_idx = 0
        chosen_item = None

        if index is not None and 0 <= int(index) < len(self.tv_channels):
            chosen_idx = int(index)
            chosen_item = self.tv_channels[chosen_idx]
        elif url:
            for i, ch in enumerate(self.tv_channels):
                if ch.get("url") == url:
                    chosen_idx = i
                    chosen_item = ch
                    break
            if chosen_item is None:
                chosen_item = {"title": title or "Live TV Stream", "url": url, "group": "Custom Live TV"}
                self.tv_channels.insert(0, chosen_item)
                chosen_idx = 0

        if not chosen_item and self.tv_channels:
            chosen_idx = 0
            chosen_item = self.tv_channels[0]

        if not chosen_item:
            return

        self.tv_active_index = chosen_idx
        target_url = chosen_item["url"]
        target_title = title or chosen_item.get("title") or "Live TV Channel"

        # Check if this channel entry is a YouTube Channel URL (/@... or /playlist?list=...)
        # If so, let start_youtube_stream expand the YouTube channel's videos/streams into a playlist!
        lower_u = target_url.lower()
        is_yt_channel_or_pl = ("youtube.com/@" in lower_u) or ("youtube.com/playlist" in lower_u) or ("list=" in lower_u)

        if is_yt_channel_or_pl:
            self.start_youtube_stream(
                target_url,
                start_sec=0,
                loop=self.loop_video,
                source=source,
                _from_playlist=False,
                custom_title=target_title,
            )
        else:
            # Load the entire TV channel list into playlist_items so Prev/Next buttons switch channels!
            self.playlist_items = [
                {
                    "id": str(i),
                    "url": ch["url"],
                    "title": ch.get("title", f"Channel #{i + 1}"),
                    "referrer": ch.get("referrer", ""),
                }
                for i, ch in enumerate(self.tv_channels)
            ]
            self.playlist_index = chosen_idx
            self.playlist_title = self.tv_source_title or "Live TV Channels"
            self.start_youtube_stream(
                target_url,
                start_sec=0,
                loop=self.loop_video,
                source=source,
                _from_playlist=True,
                custom_title=target_title,
            )

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
        self._pc_player_command("stop")
        if self.browser_chunk_queue is not None:
            try:
                self.browser_chunk_queue.put_nowait(None)
            except Exception:
                pass
            self.browser_chunk_queue = None

        if self.prefetch_proc and self.prefetch_proc.poll() is None:
            try:
                self.prefetch_proc.terminate()
                self.prefetch_proc.wait(timeout=1.0)
            except Exception:
                try:
                    self.prefetch_proc.kill()
                except Exception:
                    pass
        self.prefetch_proc = None

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
        af_sync = ["-af", "aresample=async=1000"]
        if self.audio_codec == "none":
            return ["-an"]
        elif self.audio_codec == "pcm_alaw":
            return ["-map", stream_map] + af_sync + ["-c:a", "pcm_alaw", "-ar", "8000", "-ac", "1"]
        elif self.audio_codec == "pcm_mulaw":
            return ["-map", stream_map] + af_sync + ["-c:a", "pcm_mulaw", "-ar", "8000", "-ac", "1"]
        elif self.audio_codec == "aac_hq":
            return ["-map", stream_map] + af_sync + ["-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-ac", "2"]
        else:
            return ["-map", stream_map] + af_sync + ["-c:a", "aac", "-b:a", "64k", "-ar", "16000", "-ac", "1"]

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

    def _start_local_speaker_audio_sink(self, proc_Getter_or_stop_evt=None) -> int:
        """
        Starts a decoupled, pre-buffered localhost TCP listener that receives s16le 44.1kHz stereo PCM
        audio from FFmpeg into a non-blocking Audio Jitter Queue and plays it smoothly on the PC's
        default speakers when self.local_audio_enabled is True (and drains silently when muted so
        FFmpeg NEVER experiences backpressure). Returns the bound TCP port, or None if unavailable.
        """
        if pyaudio is None:
            return None
        try:
            srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            srv.bind(("127.0.0.1", 0))
            srv.listen(1)
            srv.settimeout(16.0)
            port = srv.getsockname()[1]

            audio_q = queue.Queue(maxsize=450)  # ~5 seconds max PCM buffer
            eof_evt = threading.Event()

            def _tcp_reader():
                conn = None
                try:
                    conn, _ = srv.accept()
                    while self.running:
                        data = conn.recv(8192)
                        if not data:
                            break
                        if self.local_audio_enabled and self.output_mode in ("local_only", "both") and not self.is_paused:
                            if audio_q.full():
                                try:
                                    audio_q.get_nowait()
                                except Exception:
                                    pass
                            try:
                                audio_q.put_nowait(data)
                            except Exception:
                                pass
                        else:
                            # Drain queue when muted so unmuting has fresh audio
                            while not audio_q.empty():
                                try:
                                    audio_q.get_nowait()
                                except Exception:
                                    break
                except Exception:
                    pass
                finally:
                    eof_evt.set()
                    try:
                        if conn:
                            conn.close()
                        srv.close()
                    except Exception:
                        pass

            def _speaker_writer():
                pa = None
                out_stream = None
                prebuffering = True
                try:
                    pa = pyaudio.PyAudio()
                    out_stream = pa.open(
                        format=pyaudio.paInt16,
                        channels=2,
                        rate=44100,
                        output=True,
                        frames_per_buffer=2048,
                    )
                    while self.running and (not eof_evt.is_set() or not audio_q.empty()):
                        if prebuffering:
                            # Pre-buffer ~0.25s of PCM before starting playback to prevent underrun clicks
                            if audio_q.qsize() < 6 and not eof_evt.is_set():
                                time.sleep(0.015)
                                continue
                            prebuffering = False
                        try:
                            chunk = audio_q.get(timeout=0.08)
                            if self.local_audio_enabled and self.output_mode in ("local_only", "both") and not self.is_paused:
                                out_stream.write(chunk)
                        except queue.Empty:
                            prebuffering = True
                        except Exception:
                            pass
                except Exception:
                    pass
                finally:
                    try:
                        if out_stream:
                            out_stream.stop_stream()
                            out_stream.close()
                    except Exception:
                        pass
                    try:
                        if pa:
                            pa.terminate()
                    except Exception:
                        pass

            threading.Thread(target=_tcp_reader, daemon=True).start()
            threading.Thread(target=_speaker_writer, daemon=True).start()
            return port
        except Exception:
            return None

    def _build_dual_output_args(
        self,
        audio_map: str,
        local_audio_port: int = None,
        pace_realtime: bool = False,
        pc_player: bool = False,
    ) -> list:
        """
        Builds FFmpeg output arguments according to self.output_mode:
          - 'local_only': 960x540 @ 24fps MJPEG preview on pipe:1 + buffered local speaker audio (NO NVR RTSP needed)
          - 'nvr_only':   /main (HD) + /sub (SD) RTSP + 1fps heartbeat on pipe:1
          - 'both':       /main (HD) + /sub (SD) RTSP + 854x480 @ 20fps MJPEG preview on pipe:1 + buffered local speaker audio
        When pace_realtime=True, paces decoded frames smoothly at 1.0x wall-clock speed via FFmpeg's realtime filter.
        When pc_player=True, the embedded libVLC player renders the PC view, so pipe:1 only carries a light
        8 fps 640x360 heartbeat (Web Studio preview + health telemetry) and no PCM audio is produced.
        """
        w, h = self.main_res.split("x")
        fps = int(self.fps)
        gop = fps * 2
        main_url = f"rtsp://127.0.0.1:{self.rtsp_port}/main"
        sub_url = f"rtsp://127.0.0.1:{self.rtsp_port}/sub"

        main_scale = self._scale_expr(w, h)
        sub_scale = self._scale_expr("640", "360")
        prev_scale = self._scale_expr("854", "480")
        rt_filter = ",realtime=limit=2.5" if pace_realtime else ""

        local_audio_args = []
        if local_audio_port and not pc_player:
            local_audio_args = [
                "-map", audio_map,
                "-af", "aresample=async=1000",
                "-c:a", "pcm_s16le",
                "-ar", "44100",
                "-ac", "2",
                "-f", "s16le",
                f"tcp://127.0.0.1:{local_audio_port}",
            ]

        if self.output_mode == "local_only" and pc_player:
            # Embedded PC player shows the real video; FFmpeg just keeps health + Web Studio preview alive.
            hb_scale = self._scale_expr("640", "360")
            filter_complex = f"[0:v]fps=8{rt_filter},{hb_scale},format=yuvj420p[vprev]"
            return [
                "-filter_complex", filter_complex,
                "-map", "[vprev]", "-c:v", "mjpeg", "-q:v", "6", "-f", "image2pipe", "pipe:1",
            ]

        if self.output_mode == "local_only":
            hd_prev_scale = self._scale_expr("960", "540")
            filter_complex = f"[0:v]fps=24{rt_filter},{hd_prev_scale},format=yuvj420p[vprev]"
            v_prev_enc = [
                "-map", "[vprev]",
                "-c:v", "mjpeg",
                "-q:v", "4",
                "-f", "image2pipe",
                "pipe:1",
            ]
            return ["-filter_complex", filter_complex] + v_prev_enc + local_audio_args

        if self.output_mode == "nvr_only":
            filter_complex = (
                f"[0:v]fps={fps}{rt_filter},format=yuv420p,split=3[v1][v2][v3];"
                f"[v1]{main_scale}[vmain];"
                f"[v2]{sub_scale}[vsub];"
                f"[v3]fps=1,{prev_scale},format=yuvj420p[vprev]"
            )
        elif pc_player:
            hb_scale = self._scale_expr("640", "360")
            filter_complex = (
                f"[0:v]fps={fps}{rt_filter},split=3[v1][v2][v3];"
                f"[v1]{main_scale},format=yuv420p[vmain];"
                f"[v2]{sub_scale},format=yuv420p[vsub];"
                f"[v3]fps=8,{hb_scale},format=yuvj420p[vprev]"
            )
        else:
            # In 'both' mode, share the single unified fps+realtime pipeline across all 3 branches
            # so there is zero secondary fps filter jitter between /main, /sub, and the PC preview!
            filter_complex = (
                f"[0:v]fps={fps}{rt_filter},split=3[v1][v2][v3];"
                f"[v1]{main_scale},format=yuv420p[vmain];"
                f"[v2]{sub_scale},format=yuv420p[vsub];"
                f"[v3]{prev_scale},format=yuvj420p[vprev]"
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

        v_prev_enc = [
            "-map", "[vprev]",
            "-c:v", "mjpeg",
            "-q:v", "5",
            "-f", "image2pipe",
            "pipe:1",
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
            + v_prev_enc
            + local_audio_args
        )

    def start_standby_stream(self, source: str = "System Standby", preserve_error: bool = False):
        """Broadcasts an always-on Standby feed so the NVR channel never shows 'Offline'."""
        with self.stream_lock:
            self._stop_ffmpeg_locked()
            if not preserve_error:
                self.current_mode = "STANDBY"
                self.current_title = "Standby Screen (Ready to Cast)"
                self.active_source = source
                self.is_paused = False
                self.stream_health = "STANDBY"
                self.stream_diag = "Standby Feed Ready • Waiting for Cast"
                self.stream_error_msg = ""
                self.decoded_frames = 0
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
                stderr=subprocess.PIPE,
                startupinfo=startupinfo,
            )
            self._attach_ffmpeg_log_drainer(self.ffmpeg_proc, "Standby")
            if not preserve_error:
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
            stderr=subprocess.PIPE,
            startupinfo=startupinfo,
        )
        self.stream_health = "PAUSED"
        self.stream_diag = f"Stream Paused @ {self.seek_offset_sec}s • {held_title[:40]}"
        self._attach_ffmpeg_log_drainer(self.ffmpeg_proc, "PausedHold")

    def toggle_pause(self, force_state: bool = None, source: str = None) -> bool:
        """Pauses or resumes the active stream across all modes without dropping the NVR RTSP channel."""
        # Ignore legacy automatic background tab pause events
        if source and "Video Pause" in source:
            return self.is_paused

        target_pause = (not self.is_paused) if force_state is None else bool(force_state)
        if self.current_mode in ("STANDBY", "STOPPED"):
            return False

        if self.current_mode == "BROWSER":
            self.is_paused = target_pause
            with self._browser_frame_lock:
                self._browser_pending_cmds.append({"event": "pause" if target_pause else "play"})
            state_txt = "PAUSED" if self.is_paused else "RESUMED"
            self.log(f"Live Chrome Video {state_txt} (by {source or 'User'}).")
            return self.is_paused

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
                    _from_playlist=(len(self.playlist_items) > 1),
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
        """Seeks an active Browser Video, YouTube/Web, or Local Video stream."""
        # Ignore legacy automatic background tab seek events when in BROWSER mode
        if self.current_mode == "BROWSER":
            if source and "Video Seek" in source:
                return
            with self._browser_frame_lock:
                self._browser_pending_cmds.append({
                    "event": "seek",
                    "target_sec": target_sec,
                    "delta_sec": delta_sec,
                })
            self.log(f"Live Chrome Video seek requested (delta={delta_sec}, target={target_sec}, by {source or 'User'}).")
            return

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
                _from_playlist=(len(self.playlist_items) > 1),
            )
        elif self.current_mode == "FILE" and self.current_filepath:
            self.start_local_file_stream(
                self.current_filepath,
                start_sec=new_sec,
                loop=self.loop_video,
                source=source or self.active_source,
            )

    def _prefetch_yt_url(self, target_url: str):
        """Pre-resolves the next playlist video's HLS stream URLs in the background so track transitions are instant."""
        if not target_url or target_url in self._yt_cache:
            return
        ydl_opts = {
            "format": (
                "best[height<=720][protocol^=m3u8][vcodec^=avc1]/"
                "best[height<=720][vcodec^=avc1]/"
                "bestvideo[height<=720][protocol^=m3u8][vcodec^=avc1]+bestaudio[protocol^=m3u8]/"
                "bestvideo[height<=1080][protocol^=m3u8][vcodec^=avc1]+bestaudio[protocol^=m3u8]/"
                "bestvideo[height<=720][vcodec^=avc1]+bestaudio[acodec^=mp4a]/"
                "bestvideo[height<=720][protocol^=m3u8]+bestaudio[protocol^=m3u8]/"
                "best[height<=720][protocol^=m3u8]/"
                "bestvideo[height<=720]+bestaudio/best[height<=720]/best"
            ),
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "js_runtimes": {"node": {}},
        }
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(target_url, download=False)
                if "entries" in info and info["entries"]:
                    info = info["entries"][0]
                title = info.get("title", "Web Video Stream")
                is_live = info.get("is_live", False)
                req_formats = info.get("requested_formats")
                if req_formats and len(req_formats) >= 2:
                    video_url = req_formats[0]["url"]
                    audio_url = req_formats[1]["url"]
                    proto = req_formats[0].get("protocol", "")
                else:
                    video_url = info["url"]
                    audio_url = None
                    proto = info.get("protocol", "")
                is_hls = ("m3u8" in proto) or (".m3u8" in video_url) or ("hls_playlist" in video_url)
                self._yt_cache[target_url] = {
                    "title": title,
                    "is_live": is_live,
                    "video_url": video_url,
                    "audio_url": audio_url,
                    "is_hls": is_hls,
                    "ts": time.time(),
                }
        except Exception:
            pass

    def start_youtube_stream(
        self,
        query_or_url: str,
        start_sec: int = 0,
        loop: bool = None,
        source: str = "Desktop App",
        _from_playlist: bool = False,
        custom_title: str = "",
    ):
        """
        Resolves any YouTube URL, YouTube Playlist / Channel (plays all videos one by one automatically),
        M3U / M3U8 Live TV / Cricket stream, search query, or web video link and streams to NVR.
        """
        query_or_url = query_or_url.strip()
        if not query_or_url:
            return
        if loop is not None:
            self.loop_video = bool(loop)

        self._cast_gen += 1
        my_gen = self._cast_gen

        def _worker():
            nonlocal query_or_url, start_sec, custom_title

            # 0. Check if the user pasted a multi-channel .m3u IPTV playlist URL or local .m3u file
            if not _from_playlist and (
                query_or_url.lower().endswith(".m3u")
                or ".m3u?" in query_or_url.lower()
                or "raw.githubusercontent.com" in query_or_url.lower()
                or "iptv-org.github.io" in query_or_url.lower()
            ):
                loaded_chs = self.load_tv_category_or_m3u(query_or_url, filter_keyword=self.tv_filter, auto_play=False, source=source)
                if loaded_chs:
                    self.play_tv_channel(index=0, source=source)
                    return

            # 1. Check if the user pasted a YouTube Playlist OR YouTube Channel URL
            if not _from_playlist:
                has_playlist_param = False
                is_yt_channel = False
                list_id = ""
                seed_vid_id = ""
                try:
                    parsed = urllib.parse.urlparse(query_or_url)
                    qs = urllib.parse.parse_qs(parsed.query)
                    if "list" in qs and qs["list"]:
                        list_id = qs["list"][0].strip()
                        has_playlist_param = bool(list_id)
                    if "v" in qs and qs["v"]:
                        seed_vid_id = qs["v"][0].strip()
                    p_low = (parsed.path or "").lower()
                    if "youtube.com" in (parsed.netloc or "").lower() and (
                        p_low.startswith("/@")
                        or p_low.startswith("/channel/")
                        or p_low.startswith("/c/")
                        or p_low.startswith("/user/")
                    ):
                        is_yt_channel = True
                except Exception:
                    pass

                if has_playlist_param or is_yt_channel:
                    self.status_cb("LOADING", "Loading YouTube Playlist / Channel...")
                    extract_target = (
                        query_or_url
                        if is_yt_channel or (list_id.startswith("RD") and seed_vid_id)
                        else f"https://www.youtube.com/playlist?list={list_id}"
                    )
                    self.log(f"[{source}] Expanding YouTube Playlist/Channel: {extract_target}...")
                    flat_opts = {
                        "extract_flat": "in_playlist",
                        "noplaylist": False,
                        "playlistend": 60,
                        "quiet": True,
                        "no_warnings": True,
                        "ignoreerrors": True,
                        "js_runtimes": {"node": {}},
                    }
                    try:
                        with yt_dlp.YoutubeDL(flat_opts) as ydl:
                            pl_info = ydl.extract_info(extract_target, download=False)
                        entries = (pl_info or {}).get("entries") or []
                        # Handle nested tab entries if a channel root URL was given
                        if entries and isinstance(entries[0], dict) and "entries" in entries[0]:
                            entries = entries[0].get("entries") or []
                        items = []
                        start_idx = 0
                        for entry in entries:
                            if not entry:
                                continue
                            vid_id = entry.get("id") or ""
                            e_title = (entry.get("title") or "").strip()
                            if e_title in ("[Deleted video]", "[Private video]"):
                                continue
                            raw_u = entry.get("url") or ""
                            if raw_u.startswith("http"):
                                v_url = raw_u
                            elif vid_id and len(vid_id) == 11:
                                v_url = f"https://www.youtube.com/watch?v={vid_id}"
                            else:
                                continue
                            if seed_vid_id and (vid_id == seed_vid_id or seed_vid_id in v_url):
                                start_idx = len(items)
                            items.append({
                                "id": vid_id,
                                "url": v_url,
                                "title": e_title or f"Playlist Video #{len(items) + 1}",
                            })

                        if len(items) >= 1:
                            self.playlist_items = items
                            self.playlist_index = start_idx
                            self.playlist_title = custom_title or (pl_info or {}).get("title") or "YouTube Playlist"
                            query_or_url = items[start_idx]["url"]
                            custom_title = items[start_idx]["title"]
                            self.log(
                                f"Loaded '{self.playlist_title}' ({len(items)} videos). "
                                f"Auto-playing from [{start_idx + 1}/{len(items)}]: {items[start_idx]['title']}"
                            )
                        else:
                            self.playlist_items = []
                            self.playlist_index = 0
                            self.playlist_title = ""
                    except Exception as e:
                        self.log(f"Playlist expansion note (falling back to single video): {e}")
                        self.playlist_items = []
                        self.playlist_index = 0
                        self.playlist_title = ""
                else:
                    self.playlist_items = []
                    self.playlist_index = 0
                    self.playlist_title = ""

            if my_gen != self._cast_gen:
                return

            in_playlist = len(self.playlist_items) > 1
            pl_item = (
                self.playlist_items[self.playlist_index]
                if in_playlist and 0 <= self.playlist_index < len(self.playlist_items)
                else None
            )
            if pl_item and not custom_title:
                custom_title = pl_item.get("title", "")
            item_referrer = pl_item.get("referrer", "") if pl_item else ""

            pl_badge = f"[{self.playlist_index + 1}/{len(self.playlist_items)}] " if in_playlist else ""

            self.log(f"[{source}] Starting {pl_badge}stream: {query_or_url} (start={start_sec}s, loop={self.loop_video})...")
            self.current_url = query_or_url
            self.active_source = source
            self.stream_health = "PROBING"
            self.stream_error_msg = ""
            self.decoded_frames = 0
            self._last_ffmpeg_err = ""
            probe_label = custom_title or query_or_url
            self.stream_diag = f"Probing & Verifying Stream: {probe_label[:48]}..."
            self._set_diagnostic_preview_frame(
                "CONNECTING TO STREAM...",
                probe_label[:54],
                "Checking server availability & negotiating media stream...",
                "#3b82f6",
            )

            lower_q = query_or_url.lower()
            is_direct_media = any(
                lower_q.endswith(ext) or f"{ext}?" in lower_q
                for ext in (".m3u8", ".mp4", ".ts", ".mkv", ".webm", ".mpd")
            ) or lower_q.startswith("rtsp://") or lower_q.startswith("rtmp://") or ":8000/play/" in lower_q or ":2122/play/" in lower_q or ":9590/" in lower_q or ":8080/" in lower_q

            cached = self._yt_cache.get(query_or_url)
            if cached and (time.time() - cached["ts"] < 1800):
                title = custom_title or cached["title"]
                is_live = cached["is_live"]
                video_url = cached["video_url"]
                audio_url = cached["audio_url"]
                is_hls = cached["is_hls"]
                self.log(f"Using cached stream URLs for instant play: '{title}'")
            elif is_direct_media:
                title = custom_title or query_or_url.split("/")[-1].split("?")[0] or "Live TV Stream"
                is_live = (".m3u8" in lower_q) or lower_q.startswith("rtsp://") or ("/play/" in lower_q)
                video_url = query_or_url
                audio_url = None
                is_hls = (".m3u8" in lower_q) or ("/play/" in lower_q)

                # Quick 3.8s HTTP probe on direct HTTP streams so dead links fail transparently and fast
                if video_url.startswith(("http://", "https://")):
                    try:
                        hdrs = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/125.0.0.0"}
                        if item_referrer:
                            hdrs["Referer"] = item_referrer
                        req = urllib.request.Request(video_url, headers=hdrs)
                        with urllib.request.urlopen(req, timeout=3.8) as r:
                            _ = r.read(128)
                    except Exception as probe_err:
                        err_short = str(probe_err)[:72]
                        self.stream_health = "ERROR"
                        self.stream_error_msg = f"Channel '{title}' is offline or unreachable ({err_short})"
                        self.stream_diag = self.stream_error_msg
                        self._set_diagnostic_preview_frame(
                            "STREAM FAILED / OFFLINE",
                            title,
                            f"Server error: {err_short}",
                            "#ef4444",
                        )
                        self.current_mode = "ERROR"
                        self.current_title = f"✖ OFFLINE: {title}"
                        self.status_cb(self.current_mode, self.current_title)
                        if in_playlist and self.auto_skip_offline and self.playlist_index + 1 < len(self.playlist_items):
                            self.log(f"Channel '{title}' is offline ({err_short}) — Auto-Skip advancing to next channel...")
                            time.sleep(0.8)
                            self.playlist_index += 1
                            nxt = self.playlist_items[self.playlist_index]
                            self.start_youtube_stream(
                                nxt["url"],
                                0,
                                self.loop_video,
                                source,
                                _from_playlist=True,
                                custom_title=nxt.get("title", ""),
                            )
                        else:
                            self.log(f"✖ Channel '{title}' failed: {err_short}")
                            threading.Thread(target=self.start_standby_stream, kwargs={"preserve_error": True}, daemon=True).start()
                        return
            else:
                self.status_cb("LOADING", f"Loading {pl_badge}: {(custom_title or query_or_url)[:40]}...")
                # Prefer single muxed H.264 stream first, then m3u8_native H.264 + AAC
                ydl_opts = {
                    "format": (
                        "best[height<=720][protocol^=m3u8][vcodec^=avc1]/"
                        "best[height<=720][vcodec^=avc1]/"
                        "bestvideo[height<=720][protocol^=m3u8][vcodec^=avc1]+bestaudio[protocol^=m3u8]/"
                        "bestvideo[height<=1080][protocol^=m3u8][vcodec^=avc1]+bestaudio[protocol^=m3u8]/"
                        "bestvideo[height<=720][vcodec^=avc1]+bestaudio[acodec^=mp4a]/"
                        "bestvideo[height<=720][protocol^=m3u8]+bestaudio[protocol^=m3u8]/"
                        "best[height<=720][protocol^=m3u8]/"
                        "bestvideo[height<=720]+bestaudio/best[height<=720]/best"
                    ),
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

                        title = custom_title or info.get("title", "Web Video Stream")
                        is_live = info.get("is_live", False)

                        req_formats = info.get("requested_formats")
                        if req_formats and len(req_formats) >= 2:
                            video_url = req_formats[0]["url"]
                            audio_url = req_formats[1]["url"]
                            proto = req_formats[0].get("protocol", "")
                        else:
                            video_url = info["url"]
                            audio_url = None
                            proto = info.get("protocol", "")

                        is_hls = ("m3u8" in proto) or (".m3u8" in video_url) or ("hls_playlist" in video_url)
                        self._yt_cache[query_or_url] = {
                            "title": title,
                            "is_live": is_live,
                            "video_url": video_url,
                            "audio_url": audio_url,
                            "is_hls": is_hls,
                            "ts": time.time(),
                        }
                except Exception as e:
                    err_short = str(e)[:80]
                    self.log(f"ERROR resolving video link: {err_short}")
                    self.stream_health = "ERROR"
                    self.stream_error_msg = f"Failed to resolve '{probe_label[:36]}': {err_short}"
                    self.stream_diag = self.stream_error_msg
                    self._set_diagnostic_preview_frame(
                        "VIDEO LINK FAILED",
                        probe_label[:54],
                        err_short,
                        "#ef4444",
                    )
                    self.current_mode = "ERROR"
                    self.current_title = f"✖ FAILED: {probe_label[:40]}"
                    self.status_cb(self.current_mode, self.current_title)
                    # If inside a playlist and auto_skip_offline is enabled, automatically skip unavailable/blocked track
                    if len(self.playlist_items) > 1 and self.auto_skip_offline and self.playlist_index + 1 < len(self.playlist_items):
                        time.sleep(0.8)
                        self.playlist_index += 1
                        nxt = self.playlist_items[self.playlist_index]
                        self.log(f"Skipping unavailable track — advancing to [{self.playlist_index + 1}/{len(self.playlist_items)}]: {nxt['title']}")
                        self.start_youtube_stream(
                            nxt["url"],
                            0,
                            self.loop_video,
                            source,
                            _from_playlist=True,
                            custom_title=nxt.get("title", ""),
                        )
                        return
                    threading.Thread(target=self.start_standby_stream, kwargs={"preserve_error": True}, daemon=True).start()
                    return

            if my_gen != self._cast_gen:
                return

            # Pre-resolve the upcoming playlist video in the background so track transition is instant
            if len(self.playlist_items) > 1:
                next_pl_idx = (self.playlist_index + 1) % len(self.playlist_items)
                next_pl_url = self.playlist_items[next_pl_idx]["url"]
                if "youtube.com" in next_pl_url or "youtu.be" in next_pl_url:
                    threading.Thread(target=self._prefetch_yt_url, args=(next_pl_url,), daemon=True).start()

            self.log(f"Matched Stream: '{title}' ({'LIVE' if is_live else 'VOD'}, {'HLS' if is_hls else 'HTTP'})")

            seek_args = ["-ss", str(start_sec)] if (start_sec > 0 and not is_live) else []
            http_net_args = []
            if video_url.startswith(("http://", "https://")):
                http_net_args = [
                    "-user_agent",
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
                    "-rw_timeout", "15000000",
                    "-reconnect", "1",
                    "-reconnect_streamed", "1",
                    "-reconnect_on_network_error", "1",
                    "-reconnect_on_http_error", "4xx,5xx",
                    "-reconnect_delay_max", "5",
                ]
                if item_referrer:
                    http_net_args += ["-headers", f"Referer: {item_referrer}\r\n"]
                if is_hls:
                    http_net_args += [
                        "-http_persistent", "1",
                        "-http_multiple", "1",
                        "-max_reload", "1000",
                        "-m3u8_hold_counters", "1000",
                    ]
                    if is_live:
                        http_net_args += ["-live_start_index", "-4"]

            if audio_url:
                dl_input_args = (
                    ["-thread_queue_size", "4096", "-rtbufsize", "64M"]
                    + seek_args + http_net_args + ["-i", video_url]
                    + ["-thread_queue_size", "4096", "-rtbufsize", "32M"]
                    + seek_args + http_net_args + ["-i", audio_url]
                    + ["-map", "0:v:0", "-map", "1:a:0?"]
                )
            else:
                dl_input_args = (
                    ["-thread_queue_size", "4096", "-rtbufsize", "64M"]
                    + seek_args + http_net_args + ["-i", video_url]
                    + ["-map", "0:v:0", "-map", "0:a:0?"]
                )

            if is_hls and not audio_url:
                dl_codec_args = ["-c", "copy", "-f", "mpegts", "pipe:1"]
            else:
                dl_codec_args = ["-c:v", "copy", "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-ac", "2", "-f", "mpegts", "pipe:1"]

            dl_cmd = [self.ffmpeg_exe, "-hide_banner", "-loglevel", "warning"] + dl_input_args + dl_codec_args

            pc_play = self._pc_player_enabled()
            local_aport = (
                self._start_local_speaker_audio_sink()
                if (self.output_mode in ("local_only", "both") and not pc_play)
                else None
            )
            cmd = (
                [
                    self.ffmpeg_exe,
                    "-hide_banner",
                    "-loglevel", "warning",
                    "-thread_queue_size", "4096",
                    "-fflags", "+genpts+igndts+discardcorrupt",
                    "-i", "pipe:0",
                ]
                + self._build_dual_output_args(
                    "0:a:0?", local_audio_port=local_aport, pace_realtime=True, pc_player=pc_play
                )
            )

            display_title = f"{'[LOOP] ' if self.loop_video else ''}{pl_badge}{title}"
            ts_q = queue.Queue(maxsize=2400)  # Up to ~75 MB in-memory MPEG-TS stream buffer
            pc_q = queue.Queue(maxsize=2400) if pc_play else None
            pc_feed_ok = [pc_play]
            pc_port = self._start_pc_feed_server(pc_q, my_gen) if pc_play else None

            with self.stream_lock:
                if my_gen != self._cast_gen:
                    return
                self._stop_ffmpeg_locked()
                self.current_mode = "YOUTUBE"
                self.current_title = display_title
                self.current_url = query_or_url
                self.active_source = source
                self.is_paused = False
                self.seek_offset_sec = int(start_sec)
                self.stream_started_at = time.time()
                self.decoded_frames = 0
                self.stream_health = "CONNECTING"
                self.stream_diag = f"Pre-Buffering Stream for Smooth Playback: {title[:40]}..."
                self._set_diagnostic_preview_frame(
                    "PRE-BUFFERING STREAM...",
                    title[:54],
                    "Filling high-speed stream buffer for jitter-free playback...",
                    "#f59e0b",
                )
                self.status_cb(self.current_mode, self.current_title)

                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

                self.prefetch_proc = subprocess.Popen(
                    dl_cmd,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    startupinfo=startupinfo,
                )
                dl_ref = self.prefetch_proc

                self.ffmpeg_proc = subprocess.Popen(
                    cmd,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    bufsize=65536,
                    startupinfo=startupinfo,
                )
                proc_ref = self.ffmpeg_proc
                self._attach_ffmpeg_log_drainer(proc_ref, "YouTube")
                if pc_play:
                    self._pc_player_command("play", {
                        "url": f"http://127.0.0.1:{pc_port}/live.ts",
                        "audio_url": None,
                        "start_sec": 0,       # prefetcher already applied the seek
                        "referrer": "",
                        "is_live": True,      # local feed: no VLC-side seeking
                        "loop": False,
                        "title": display_title,
                    })

            def _drain_dl_stderr(p_err):
                if not p_err:
                    return
                try:
                    for raw_line in iter(p_err.readline, b""):
                        if not raw_line:
                            break
                        s = raw_line.decode("utf-8", errors="ignore").strip()
                        if s:
                            self._last_ffmpeg_err = s
                except Exception:
                    pass

            threading.Thread(target=_drain_dl_stderr, args=(dl_ref.stderr,), daemon=True).start()

            def _pump_prefetch_to_queue():
                nonlocal dl_ref
                total_dl_bytes = 0
                live_retries = 0
                try:
                    while my_gen == self._cast_gen and not self.is_paused and proc_ref.poll() is None:
                        while my_gen == self._cast_gen and not self.is_paused and proc_ref.poll() is None:
                            chunk = dl_ref.stdout.read(32768) if dl_ref and dl_ref.stdout else b""
                            if not chunk:
                                break
                            total_dl_bytes += len(chunk)
                            while my_gen == self._cast_gen and not self.is_paused and proc_ref.poll() is None:
                                try:
                                    ts_q.put(chunk, timeout=0.4)
                                    break
                                except queue.Full:
                                    continue
                            if pc_feed_ok[0]:
                                try:
                                    pc_q.put(chunk, timeout=3.0)
                                except queue.Full:
                                    # PC player stalled for 3s+: stop teeing so the NVR feed is never held back
                                    pc_feed_ok[0] = False
                                    self.log("PC player feed stalled — NVR stream continues unaffected.")

                        # If live TV stream disconnected mid-broadcast after delivering data, reconnect seamlessly
                        if (
                            is_live
                            and total_dl_bytes > 0
                            and live_retries < 5
                            and my_gen == self._cast_gen
                            and not self.is_paused
                            and proc_ref.poll() is None
                        ):
                            live_retries += 1
                            self.log(f"Live stream buffer reconnecting ({live_retries}/5) for '{title}'...")
                            time.sleep(0.6)
                            try:
                                startupinfo_r = subprocess.STARTUPINFO()
                                startupinfo_r.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                                dl_ref = subprocess.Popen(
                                    dl_cmd,
                                    stdin=subprocess.DEVNULL,
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE,
                                    startupinfo=startupinfo_r,
                                )
                                self.prefetch_proc = dl_ref
                                threading.Thread(target=_drain_dl_stderr, args=(dl_ref.stderr,), daemon=True).start()
                                continue
                            except Exception:
                                break
                        break
                except Exception:
                    pass
                finally:
                    try:
                        ts_q.put_nowait(None)
                    except Exception:
                        pass
                    if pc_q is not None:
                        try:
                            pc_q.put(None, timeout=2.0)
                        except Exception:
                            pass

            def _pump_queue_to_decoder():
                try:
                    # Pre-buffer ~320KB (or up to 1.8s wait) so HLS segment transitions never starve the decoder
                    prebuf = []
                    prebuf_bytes = 0
                    target_prebuf = 384 * 1024 if is_live else 256 * 1024
                    t_pre_start = time.time()
                    eof_reached = False
                    while prebuf_bytes < target_prebuf and (time.time() - t_pre_start) < 2.0:
                        try:
                            item = ts_q.get(timeout=0.25)
                            if item is None:
                                eof_reached = True
                                break
                            prebuf.append(item)
                            prebuf_bytes += len(item)
                        except queue.Empty:
                            if prebuf_bytes > 64 * 1024 and (time.time() - t_pre_start) >= 1.2:
                                break
                            continue

                    for chunk in prebuf:
                        if proc_ref.poll() is not None or my_gen != self._cast_gen:
                            return
                        proc_ref.stdin.write(chunk)
                    if prebuf:
                        proc_ref.stdin.flush()
                    prebuf.clear()

                    if not eof_reached:
                        while proc_ref.poll() is None and my_gen == self._cast_gen and not self.is_paused:
                            try:
                                chunk = ts_q.get(timeout=0.5)
                            except queue.Empty:
                                continue
                            if chunk is None:
                                break
                            proc_ref.stdin.write(chunk)
                except Exception:
                    pass
                finally:
                    try:
                        if proc_ref.stdin:
                            proc_ref.stdin.close()
                    except Exception:
                        pass

            threading.Thread(target=_pump_prefetch_to_queue, daemon=True).start()
            threading.Thread(target=_pump_queue_to_decoder, daemon=True).start()

            # First-frame & stall watchdog so dead M3U8 segments never hang the app
            def _stream_watchdog():
                t_start = time.time()
                while proc_ref.poll() is None and my_gen == self._cast_gen and not self.is_paused:
                    time.sleep(0.3)
                    if self.decoded_frames == 0 and (time.time() - t_start) > 14.5:
                        self.log(f"✖ Watchdog: '{title}' delivered 0 video frames in 14.5s (Stream Offline / Dead Segments).")
                        self.stream_health = "ERROR"
                        self.stream_error_msg = f"Stream Offline / Timed Out: '{title}' sent no video frames (14.5s)."
                        self.stream_diag = self.stream_error_msg
                        self._set_diagnostic_preview_frame(
                            "STREAM OFFLINE / TIMED OUT",
                            title[:54],
                            "Server sent 0 video frames within 14.5 seconds.",
                            "#ef4444",
                        )
                        try:
                            if self.prefetch_proc:
                                self.prefetch_proc.terminate()
                        except Exception:
                            pass
                        try:
                            proc_ref.terminate()
                        except Exception:
                            pass
                        break
                    elif self.decoded_frames > 0 and (time.time() - self.last_frame_ts) > 12.0:
                        self.stream_health = "STALLED"
                        self.stream_diag = f"⚠ Stream Re-Buffering (Waiting for packets: {int(time.time() - self.last_frame_ts)}s)"

            threading.Thread(target=_stream_watchdog, daemon=True).start()
            self.log(f"Pre-buffering & streaming ({source}): {display_title}")

            proc_ref.wait()
            with self.stream_lock:
                if self.ffmpeg_proc == proc_ref and self.running and not self.is_paused and my_gen == self._cast_gen:
                    failed_before_first_frame = (self.decoded_frames == 0)
                    if failed_before_first_frame:
                        reason = self._last_ffmpeg_err or self.stream_error_msg or "Stream offline, geoblocked, or corrupt media segments."
                        self.stream_health = "ERROR"
                        self.stream_error_msg = f"Stream Failed ({title[:34]}): {reason[:80]}"
                        self.stream_diag = self.stream_error_msg
                        self._set_diagnostic_preview_frame(
                            "STREAM FAILED / OFFLINE",
                            title[:54],
                            reason[:78],
                            "#ef4444",
                        )
                        self.current_mode = "ERROR"
                        self.current_title = f"✖ FAILED: {title}"
                        self.status_cb(self.current_mode, self.current_title)
                        self.log(f"✖ Stream Failed ('{title}'): {reason[:90]}")

                        if len(self.playlist_items) > 1 and self.auto_skip_offline and self.playlist_index + 1 < len(self.playlist_items):
                            self.playlist_index += 1
                            nxt = self.playlist_items[self.playlist_index]
                            self.log(
                                f"Auto-Skip Offline enabled — advancing to [{self.playlist_index + 1}/{len(self.playlist_items)}]: {nxt['title']}"
                            )
                            threading.Thread(
                                target=self.start_youtube_stream,
                                args=(nxt["url"], 0, self.loop_video, source, True, nxt.get("title", "")),
                                daemon=True,
                            ).start()
                        else:
                            # Keep RTSP server alive for NVR while preserving the visible ERROR diagnostic in the GUI
                            threading.Thread(target=self.start_standby_stream, kwargs={"preserve_error": True}, daemon=True).start()
                    elif len(self.playlist_items) > 1:
                        if self.playlist_index + 1 < len(self.playlist_items):
                            self.playlist_index += 1
                            nxt = self.playlist_items[self.playlist_index]
                            self.log(
                                f"Playlist auto-advancing to [{self.playlist_index + 1}/{len(self.playlist_items)}]: {nxt['title']}"
                            )
                            threading.Thread(
                                target=self.start_youtube_stream,
                                args=(nxt["url"], 0, self.loop_video, source, True, nxt.get("title", "")),
                                daemon=True,
                            ).start()
                        elif self.loop_video:
                            self.playlist_index = 0
                            first = self.playlist_items[0]
                            self.log(
                                f"Playlist completed — Looping playlist from [1/{len(self.playlist_items)}]: {first['title']}"
                            )
                            threading.Thread(
                                target=self.start_youtube_stream,
                                args=(first["url"], 0, True, source, True, first.get("title", "")),
                                daemon=True,
                            ).start()
                        else:
                            self.playlist_items = []
                            self.log(f"Finished Playlist '{self.playlist_title}'. Returning to Standby feed...")
                            threading.Thread(target=self.start_standby_stream, daemon=True).start()
                    elif self.loop_video:
                        self.log(f"Looping YouTube/Web video '{title}' from beginning...")
                        threading.Thread(
                            target=self.start_youtube_stream,
                            args=(query_or_url, 0, True, source, False, custom_title),
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
            pc_play = self._pc_player_enabled()
            local_aport = (
                self._start_local_speaker_audio_sink()
                if (self.output_mode in ("local_only", "both") and not pc_play)
                else None
            )
            cmd = (
                [
                    self.ffmpeg_exe,
                    "-hide_banner",
                    "-loglevel", "warning",
                    "-re",
                    "-thread_queue_size", "4096",
                    "-fflags", "+genpts+discardcorrupt",
                ]
                + loop_args
                + seek_args
                + ["-i", filepath]
                + self._build_dual_output_args("0:a:0?", local_audio_port=local_aport, pc_player=pc_play)
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
                self.decoded_frames = 0
                self.stream_health = "CONNECTING"
                self.stream_error_msg = ""
                self.stream_diag = f"Loading Local Video: {title}"
                self.status_cb(self.current_mode, self.current_title)

                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                self.ffmpeg_proc = subprocess.Popen(
                    cmd,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    startupinfo=startupinfo,
                )
                proc_ref = self.ffmpeg_proc
                self._attach_ffmpeg_log_drainer(proc_ref, "File")
                if pc_play:
                    self._pc_player_command("play", {
                        "url": filepath,
                        "start_sec": int(start_sec or 0),
                        "loop": bool(self.loop_video),
                        "title": self.current_title,
                    })

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
                self.decoded_frames = 0
                self.stream_health = "LIVE"
                self.stream_error_msg = ""
                self.stream_diag = f"Photo Gallery Active • {total_imgs} slide(s)"
                self.current_title = f"Gallery [1/{total_imgs}]: {os.path.basename(first_file)}"
                self.status_cb(self.current_mode, self.current_title)

                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                self.ffmpeg_proc = subprocess.Popen(
                    cmd,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
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
        direction = 1 if step >= 0 else -1
        if self.current_mode == "GALLERY":
            self.gallery_force_step = direction
        elif len(self.playlist_items) > 1:
            self.playlist_index = (self.playlist_index + direction) % len(self.playlist_items)
            if len(self.playlist_items) == len(self.tv_channels):
                self.tv_active_index = self.playlist_index
            nxt = self.playlist_items[self.playlist_index]
            self.log(
                f"Switched to [{self.playlist_index + 1}/{len(self.playlist_items)}]: {nxt['title']}"
            )
            self.start_youtube_stream(
                nxt["url"],
                start_sec=0,
                loop=self.loop_video,
                source=self.active_source,
                _from_playlist=True,
                custom_title=nxt.get("title", ""),
            )
        elif self.current_mode == "BROWSER":
            with self._browser_frame_lock:
                self._browser_pending_cmds.append({"event": "playlist_step", "step": direction})
            self.log(f"Live Chrome Playlist skip requested ({'Next' if direction > 0 else 'Prev'} track).")
        elif len(self.tv_channels) > 1:
            self.tv_active_index = (self.tv_active_index + direction) % len(self.tv_channels)
            self.play_tv_channel(index=self.tv_active_index, source="Live TV Channel Step")

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
                self.decoded_frames = 0
                self.stream_health = "LIVE"
                self.stream_error_msg = ""
                self.stream_diag = f"Desktop Mirroring Active • {desc}"
                self.status_cb(self.current_mode, self.current_title)

                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                self.ffmpeg_proc = subprocess.Popen(
                    cmd,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
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
        label: str = "Live Chrome Video Stream",
        source: str = "Chrome Extension",
        session_id: str = "",
        url: str = "",
    ):
        """
        Streams the live HTML5 <video> player or tab/window capture directly from Chrome to the NVR
        using a continuous 25fps rawvideo RGB24 wall-clock frame repeater + WASAPI PC Audio Loopback.
        Never drops on pause, seek, ABR resolution change, or tab switching!
        """
        out_w, out_h = [int(x) for x in self.main_res.split("x")]
        self._browser_out_size = (out_w, out_h)

        # Build an initial dark studio connecting frame so FFmpeg starts streaming immediately
        if Image is not None:
            init_im = Image.new("RGB", (out_w, out_h), (15, 23, 42))
            try:
                draw = ImageDraw.Draw(init_im)
                font = ImageFont.truetype(r"C:\Windows\Fonts\segoeuib.ttf", 26)
                draw.text((out_w // 2 - 220, out_h // 2 - 20), f"Connecting Live Chrome Stream: {label[:36]}...", fill=(248, 250, 252), font=font)
            except Exception:
                pass
            init_bytes = init_im.tobytes()
        else:
            init_bytes = b"\x0f\x17\x2a" * (out_w * out_h)

        with self._browser_frame_lock:
            self._browser_latest_frame = init_bytes
            self._browser_pending_cmds.clear()

        self._cast_gen += 1
        my_gen = self._cast_gen
        resolved_session = session_id or f"cast_{int(time.time() * 1000)}"
        self.browser_session_id = resolved_session
        self.current_mode = "BROWSER"
        self.current_title = label
        if url:
            self.current_url = url
        self.active_source = source
        self.is_paused = False
        self.seek_offset_sec = 0
        self.browser_duration_sec = 0
        self.stream_started_at = time.time()
        self.status_cb(self.current_mode, self.current_title)

        def _worker():
            with self.stream_lock:
                if my_gen != self._cast_gen:
                    return
                self._stop_ffmpeg_locked()
                self.screen_stop_event.clear()
                stop_evt = self.screen_stop_event

                self.browser_session_id = resolved_session
                self.current_mode = "BROWSER"
                self.current_title = label
                if url:
                    self.current_url = url
                self.active_source = source
                self.decoded_frames = 0
                self.stream_health = "LIVE"
                self.stream_error_msg = ""
                self.stream_diag = f"Live Chrome Video • {label[:40]}"
                self.status_cb(self.current_mode, self.current_title)

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
                        "-pix_fmt", "rgb24",
                        "-s", f"{out_w}x{out_h}",
                        "-r", str(self.fps),
                        "-i", "pipe:0",
                    ]
                    + audio_input_args
                    + self._build_dual_output_args("1:a:0")
                )

                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                self.ffmpeg_proc = subprocess.Popen(
                    cmd,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    bufsize=out_w * out_h * 3 * 2,
                    startupinfo=startupinfo,
                )
                proc_ref = self.ffmpeg_proc
                self._attach_ffmpeg_log_drainer(proc_ref, "BrowserCast")

            self.log(f"[{source}] Started Live Chrome Video Stream: '{label}' (session={self.browser_session_id})")

            frame_interval = 1.0 / float(self.fps)
            next_frame_t = time.perf_counter()

            try:
                while not stop_evt.is_set() and proc_ref.poll() is None:
                    with self._browser_frame_lock:
                        frame_bytes = self._browser_latest_frame
                    if frame_bytes:
                        proc_ref.stdin.write(frame_bytes)

                    next_frame_t += frame_interval
                    sleep_s = next_frame_t - time.perf_counter()
                    if sleep_s > 0:
                        time.sleep(sleep_s)
                    elif sleep_s < -0.5:
                        next_frame_t = time.perf_counter()
            except Exception as e:
                if not stop_evt.is_set():
                    self.log(f"Browser live stream ended: {e}")
            finally:
                stop_evt.set()
                try:
                    if proc_ref.stdin:
                        proc_ref.stdin.close()
                except Exception:
                    pass
                with self.stream_lock:
                    if self.ffmpeg_proc == proc_ref and self.running and not stop_evt.is_set():
                        self.log("Browser cast finished. Returning to Standby feed...")
                        threading.Thread(target=self.start_standby_stream, daemon=True).start()

        threading.Thread(target=_worker, daemon=True).start()

    def push_browser_frame(self, jpeg_bytes: bytes, meta: dict = None) -> dict:
        """
        Receives a live JPEG frame from Chrome's <video> player or getDisplayMedia canvas,
        updates the 25fps rawvideo frame buffer, and returns any pending remote-control commands.
        """
        meta = meta or {}
        req_session = meta.get("session_id", "")

        if self.current_mode != "BROWSER":
            return {"ok": False, "stop": True, "reason": "not_in_browser_mode"}

        if req_session and self.browser_session_id and req_session != self.browser_session_id:
            return {"ok": False, "stop": True, "reason": "session_superseded", "active_session_id": self.browser_session_id}

        if "time_sec" in meta and meta["time_sec"] is not None:
            try:
                self.seek_offset_sec = int(float(meta["time_sec"]))
            except Exception:
                pass
        if "duration_sec" in meta and meta["duration_sec"] is not None:
            try:
                self.browser_duration_sec = int(float(meta["duration_sec"]))
            except Exception:
                pass
        if "paused" in meta and meta["paused"] is not None:
            self.is_paused = bool(meta["paused"])
        if meta.get("title"):
            clean_t = str(meta["title"]).strip()
            if clean_t:
                prefix = "[PAUSED] " if self.is_paused else ("[LOOP] " if self.loop_video else "")
                new_title = f"{prefix}{clean_t}"
                if new_title != self.current_title:
                    self.current_title = new_title
                    self.status_cb(self.current_mode, self.current_title)

        if jpeg_bytes and Image is not None:
            try:
                out_w, out_h = self._browser_out_size
                with Image.open(io.BytesIO(jpeg_bytes)) as im:
                    im_rgb = im.convert("RGB")
                    if im_rgb.size != (out_w, out_h):
                        im_rgb = im_rgb.resize((out_w, out_h), Image.Resampling.BILINEAR)
                    raw_rgb = im_rgb.tobytes()
                with self._browser_frame_lock:
                    self._browser_latest_frame = raw_rgb
            except Exception:
                pass

        cmd = None
        with self._browser_frame_lock:
            if self._browser_pending_cmds:
                cmd = self._browser_pending_cmds.pop(0)

        return {
            "ok": True,
            "session_id": self.browser_session_id,
            "loop": self.loop_video,
            "cmd": cmd,
        }

    def push_browser_chunk(self, data: bytes) -> bool:
        """Legacy endpoint compatibility: if JPEG bytes are posted to /api/browser_cast/chunk, decode as frame."""
        if data and data[:2] == b"\xff\xd8":
            res = self.push_browser_frame(data)
            return bool(res.get("ok"))
        return self.current_mode == "BROWSER"

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
