"""
Embedded hardware-accelerated PC player for NVR Cast Hub (libVLC).

Why this exists:
  The old in-app preview piped FFmpeg -> MJPEG -> Python -> PIL -> Tkinter PhotoImage.
  Measured on this PC, Tkinter could only present ~20 fps in the Studio and ~10 fps in
  Full Screen (a 1920x1080 PhotoImage costs ~42 ms), with no A/V sync between the
  separate video queue and PyAudio sink. A real media player engine fixes all of that:
  hardware decoding, its own network cache, A/V clock sync, vsync, native frame rate.

The NVR RTSP path is unchanged (FFmpeg -> MediaMTX). This player only drives the PC view.
If VLC (64-bit) is not installed, `available` is False and the app falls back to the
legacy FFmpeg preview path automatically.
"""

import ctypes
import os
import sys
import threading
import time

try:
    import vlc  # python-vlc; locates libvlc.dll from the installed VLC
except Exception:  # pragma: no cover - VLC not installed / wrong bitness
    vlc = None

_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"


class EmbeddedPlayer:
    """Thin, thread-safe wrapper around one libVLC media player rendering into a Win32 HWND."""

    def __init__(self, log_cb=None):
        self.log = log_cb or (lambda m: None)
        self.available = False
        self.instance = None
        self.player = None
        self.media = None
        self.active = False          # True while a stream is loaded for PC playback
        self.title = ""
        self.started_at = 0.0
        self.error = ""
        self._lock = threading.RLock()
        self._fps_sample = (0.0, 0)  # (perf_counter, displayed_pictures)
        self.measured_fps = 0.0
        self.version = ""
        if vlc is None:
            return
        try:
            self.instance = vlc.Instance(
                "--quiet",
                "--no-video-title-show",
                "--no-snapshot-preview",
                "--no-osd",
                "--avcodec-hw=any",          # D3D11VA / DXVA2 hardware decoding when available
                "--network-caching=1500",    # ms of network buffer (HLS also pre-fetches segments)
                "--live-caching=1500",
                "--file-caching=600",
                "--clock-jitter=0",
                "--http-reconnect",
                "--adaptive-logic=highest",  # keep best HLS rendition, avoid quality flapping
            )
            self.player = self.instance.media_player_new()
            self.player.video_set_mouse_input(False)  # let Tk receive double-click etc.
            self.player.video_set_key_input(False)
            self.version = vlc.libvlc_get_version().decode(errors="ignore")
            self.available = True
            ev = self.player.event_manager()
            ev.event_attach(vlc.EventType.MediaPlayerEncounteredError, self._on_error)
        except Exception as e:
            self.log(f"Embedded PC player unavailable (VLC not found or incompatible): {e}")
            self.available = False

    # ------------------------------------------------------------------ surface
    def attach(self, hwnd: int):
        if not self.available:
            return
        with self._lock:
            self.player.set_hwnd(int(hwnd))

    # ------------------------------------------------------------------ playback
    def play(
        self,
        url: str,
        audio_url: str = None,
        start_sec: int = 0,
        referrer: str = "",
        is_live: bool = False,
        loop: bool = False,
        title: str = "",
        muted: bool = False,
    ):
        if not self.available or not url:
            return
        with self._lock:
            try:
                self.player.stop()
            except Exception:
                pass
            m = self.instance.media_new(url)
            if url.startswith(("http://", "https://")):
                m.add_option(f":http-user-agent={_UA}")
                if referrer:
                    m.add_option(f":http-referrer={referrer}")
            if audio_url:
                m.add_option(f":input-slave={audio_url}")
            if start_sec and start_sec > 0 and not is_live:
                m.add_option(f":start-time={int(start_sec)}")
            if loop and not is_live:
                m.add_option(":input-repeat=65535")
            if url.startswith("http://127.0.0.1"):
                m.add_option(":network-caching=1000")  # local tee feed: already buffered upstream
            elif is_live:
                m.add_option(":network-caching=2000")
            self.media = m
            self.player.set_media(m)
            self.player.audio_set_mute(bool(muted))
            self.player.play()
            self.active = True
            self.title = title
            self.error = ""
            self.started_at = time.perf_counter()
            self._fps_sample = (time.perf_counter(), 0)
            self.measured_fps = 0.0

    def stop(self):
        if not self.available:
            return
        with self._lock:
            self.active = False
            try:
                self.player.stop()
            except Exception:
                pass
            self.media = None

    def set_pause(self, paused: bool):
        if self.available and self.active:
            with self._lock:
                self.player.set_pause(1 if paused else 0)

    def set_muted(self, muted: bool):
        if self.available:
            with self._lock:
                self.player.audio_set_mute(bool(muted))

    # ------------------------------------------------------------------ telemetry
    def _on_error(self, event):
        self.error = "PC player could not open this stream"

    def state_name(self) -> str:
        if not self.available or not self.active:
            return "IDLE"
        try:
            st = self.player.get_state()
        except Exception:
            return "IDLE"
        return {
            vlc.State.Opening: "OPENING",
            vlc.State.Buffering: "BUFFERING",
            vlc.State.Playing: "PLAYING",
            vlc.State.Paused: "PAUSED",
            vlc.State.Stopped: "STOPPED",
            vlc.State.Ended: "ENDED",
            vlc.State.Error: "ERROR",
        }.get(st, "IDLE")

    def stats(self) -> dict:
        """Returns displayed/lost picture counters and a smoothed displayed-fps measurement."""
        out = {"displayed": 0, "lost": 0, "lost_audio": 0, "fps": self.measured_fps, "showing_video": False}
        if not self.available or not self.active or self.media is None:
            return out
        try:
            st = vlc.MediaStats()
            self.media.get_stats(st)
            now = time.perf_counter()
            t_prev, d_prev = self._fps_sample
            if now - t_prev >= 1.0:
                fps = (st.displayed_pictures - d_prev) / (now - t_prev)
                self.measured_fps = fps if self.measured_fps == 0 else (0.6 * fps + 0.4 * self.measured_fps)
                self._fps_sample = (now, st.displayed_pictures)
            out.update(
                displayed=st.displayed_pictures,
                lost=st.lost_pictures,
                lost_audio=st.lost_abuffers,
                fps=self.measured_fps,
                showing_video=st.displayed_pictures > 0,
            )
        except Exception:
            pass
        return out


# ---------------------------------------------------------------------- Win32 helpers
_u32 = ctypes.windll.user32 if os.name == "nt" else None


def reparent_window(child_hwnd: int, new_parent_hwnd: int, width: int, height: int):
    """Moves a native child window (the video surface) into another window and fills it."""
    if _u32 is None:
        return
    _u32.SetParent(int(child_hwnd), int(new_parent_hwnd))
    _u32.MoveWindow(int(child_hwnd), 0, 0, max(1, int(width)), max(1, int(height)), True)


def resize_window(hwnd: int, width: int, height: int):
    if _u32 is None:
        return
    _u32.MoveWindow(int(hwnd), 0, 0, max(1, int(width)), max(1, int(height)), True)
