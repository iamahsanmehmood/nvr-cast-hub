import io
import os
import queue
import threading
import time
from http.server import ThreadingHTTPServer
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

try:
    from PIL import Image, ImageTk
except ImportError:
    Image = None
    ImageTk = None

from desktop_app.engine import (
    NVRCastEngine,
    APP_VERSION,
    CONFIG_DIR,
    CONFIG_JSON_PATH,
    DEFAULT_VLC_M3U_PATH,
)
from web_studio.server import WebRemoteHandler


class NVRCastDesktopApp:
    """
    NVR Cast Hub v0.1.0-beta — Clean, Spacious Universal Media Player & NVR Broadcast Studio.
      - 3-Way Output Routing Selector:
          1. [ 🖥 Preview Only (Watch Here) ] — Watch & listen directly inside the app (no NVR needed)
          2. [ 📡 NVR Only (Cast to NVR) ]    — Stream to NVR RTSP (/main & /sub) with local preview off
          3. [ 🖥 + 📡 Both (App + NVR) ]     — Watch inside the app AND broadcast to NVR simultaneously
      - Left Deck:
          • Large 640x360 (16:9) Live Video Player & Preview Canvas + PC Speaker Audio toggle + Open in VLC
          • Transparent Stream Health & Diagnostic Banner (PROBING / BUFFERING / LIVE / OFFLINE ERROR)
          • Clean Transport & Channel Zapping Bar (Prev/Next Channel, Seek -10s/+10s, Pause/Resume, Stop)
      - Right Deck (5 Clean Tabs):
          1. 📺 Channels & Live TV (24+ Pakistani TV Channels, Live Cricket, Add/Remove Channel, Import/Export M3U & JSON, Open in VLC)
          2. ▶ YouTube & Local Video (YouTube URL/Search/Playlist, Active Queue, Local Video File Player/Caster)
          3. 🖼 Photo Slideshow (Picture Folder / Multi-Photo Picker, Timer, Shuffle, Smooth Crossfade)
          4. 🖥 Screen Share & Chrome (Multi-Monitor Desktop Cast, Browser Tab Share, Chrome Extension Sync)
          5. ⚙ Config, VLC & Settings (Default VLC .m3u & .json Config Manager, Import/Export, Stream Quality & Logs)
    """

    PREVIEW_W = 640
    PREVIEW_H = 360

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(
            f"NVR Cast Hub v{APP_VERSION} — Live TV Player, YouTube, Media & NVR Caster"
        )
        self.root.geometry("1380x880")
        self.root.minsize(1180, 760)
        self.root.configure(bg="#f1f5f9")

        self._configure_ttk_styles()

        self.engine = NVRCastEngine(
            log_callback=self.append_log_threadsafe,
            status_callback=self.update_status_threadsafe,
        )
        WebRemoteHandler.ui_sync_callback = lambda: self.root.after(0, self._sync_ui_from_engine)
        WebRemoteHandler.browse_dialog_callback = self._open_dialog_from_web_threadsafe

        self.mon_vars = {}
        self._preview_photo = None
        self._last_preview_bytes = None
        self._active_tab_id = "tv"
        self._tab_frames = {}
        self._tab_buttons = {}
        self._output_mode_btns = {}
        self._tv_status_cache = {}

        # In-App Floating Picture-in-Picture (PiP) & Full-Screen TV Player State
        self.pip_win = None
        self.pip_canvas = None
        self.pip_photo = None
        self.pip_title_lbl = None
        self.pip_pause_btn = None
        self.pip_audio_btn = None
        self.pip_pin_var = tk.BooleanVar(value=True)
        self._pip_last_size = (0, 0)

        self.fs_win = None
        self.fs_canvas = None
        self.fs_photo = None
        self.fs_title_lbl = None
        self.fs_pause_btn = None
        self.fs_audio_btn = None
        self._fs_last_size = (0, 0)

        self._build_ui()
        self.root.bind("<F11>", lambda e: self.on_toggle_fullscreen())
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        threading.Thread(target=self._init_services, daemon=True).start()
        self.root.after(200, self._preview_and_telemetry_tick)

    def _configure_ttk_styles(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass

        style.configure(
            "Studio.Treeview",
            background="#ffffff",
            foreground="#0f172a",
            fieldbackground="#ffffff",
            rowheight=30,
            font=("Segoe UI", 9),
            borderwidth=0,
        )
        style.configure(
            "Studio.Treeview.Heading",
            background="#f1f5f9",
            foreground="#334155",
            font=("Segoe UI", 9, "bold"),
            relief="flat",
            padding=(8, 6),
        )
        style.map(
            "Studio.Treeview",
            background=[("selected", "#dbeafe")],
            foreground=[("selected", "#1d4ed8")],
        )
        style.configure(
            "TCombobox",
            fieldbackground="#f8fafc",
            background="#ffffff",
            foreground="#0f172a",
            padding=4,
        )

    def _open_dialog_from_web_threadsafe(self, kind: str) -> str:
        res_q = queue.Queue()

        def _ask():
            try:
                if kind == "folder":
                    p = filedialog.askdirectory(title="Select Picture Folder for Slideshow")
                elif kind == "pictures":
                    files = filedialog.askopenfilenames(
                        title="Select Picture(s) for Slideshow",
                        filetypes=[("Image Files", "*.jpg *.jpeg *.png *.bmp *.webp *.gif"), ("All Files", "*.*")],
                    )
                    p = ";".join(files) if files else ""
                else:
                    p = filedialog.askopenfilename(
                        title="Select Video File",
                        filetypes=[("Video Files", "*.mp4 *.mkv *.avi *.mov *.ts *.webm"), ("All Files", "*.*")],
                    )
                res_q.put(p or "")
            except Exception:
                res_q.put("")

        self.root.after(0, _ask)
        try:
            return res_q.get(timeout=120)
        except Exception:
            return ""

    def _init_services(self):
        ok = self.engine.start_server()
        if ok:
            self.root.after(0, self._refresh_addresses)
        try:
            WebRemoteHandler.engine = self.engine
            httpd = ThreadingHTTPServer(("0.0.0.0", self.engine.web_port), WebRemoteHandler)
            self.engine.log(
                f"Web Studio active at http://localhost:{self.engine.web_port} "
                f"(and http://{self.engine.lan_ip}:{self.engine.web_port})"
            )
            httpd.serve_forever()
        except Exception as e:
            self.engine.log(f"Web Studio port warning: {e}")

    def _refresh_addresses(self):
        main_rtsp = f"rtsp://{self.engine.lan_ip}:{self.engine.rtsp_port}/main"
        sub_rtsp = f"rtsp://{self.engine.lan_ip}:{self.engine.rtsp_port}/sub"
        web_url = f"http://localhost:{self.engine.web_port}"

        self.main_rtsp_var.set(main_rtsp)
        self.sub_rtsp_var.set(sub_rtsp)
        self.web_remote_var.set(web_url)

    def _make_btn(self, parent, text, command, variant="secondary", padx=11, pady=5, font_size=9):
        palette = {
            "primary": ("#2563eb", "#ffffff", "#1d4ed8", "#1e40af"),
            "success": ("#059669", "#ffffff", "#047857", "#065f46"),
            "danger": ("#fef2f2", "#dc2626", "#fecaca", "#fee2e2"),
            "warning": ("#fffbeb", "#b45309", "#fde68a", "#fef3c7"),
            "accent": ("#eff6ff", "#1d4ed8", "#bfdbfe", "#dbeafe"),
            "dark": ("#1e293b", "#f8fafc", "#334155", "#0f172a"),
            "secondary": ("#f8fafc", "#0f172a", "#cbd5e1", "#e2e8f0"),
        }
        bg, fg, border, active_bg = palette.get(variant, palette["secondary"])

        btn = tk.Button(
            parent,
            text=text,
            font=("Segoe UI", font_size, "bold"),
            bg=bg,
            fg=fg,
            activebackground=active_bg,
            activeforeground=fg,
            highlightbackground=border,
            relief=tk.SOLID,
            bd=1,
            padx=padx,
            pady=pady,
            cursor="hand2",
            command=command,
        )
        return btn

    # =========================================================================
    # MASTER UI LAYOUT (TOP BAR + 2-COLUMN WORKSPACE + FOOTER STATUS BAR)
    # =========================================================================
    def _build_ui(self):
        # 1. Top Header Bar with Output Routing Mode Selector & RTSP / VLC Shortcuts
        header = tk.Frame(
            self.root,
            bg="#ffffff",
            highlightbackground="#cbd5e1",
            highlightthickness=1,
            padx=16,
            pady=9,
        )
        header.pack(fill=tk.X, padx=14, pady=(10, 8))

        top_row = tk.Frame(header, bg="#ffffff")
        top_row.pack(fill=tk.X)

        # Clean App Icon
        icon_cv = tk.Canvas(top_row, width=36, height=36, bg="#ffffff", highlightthickness=0)
        icon_cv.pack(side=tk.LEFT, padx=(0, 10))
        icon_cv.create_rectangle(2, 2, 34, 34, fill="#2563eb", outline="#1d4ed8", width=1)
        icon_cv.create_rectangle(8, 9, 28, 23, outline="#ffffff", width=2)
        icon_cv.create_polygon(15, 12, 15, 20, 22, 16, fill="#ffffff", outline="#ffffff")
        icon_cv.create_line(12, 27, 24, 27, fill="#93c5fd", width=2)

        brand_col = tk.Frame(top_row, bg="#ffffff")
        brand_col.pack(side=tk.LEFT, anchor="w")

        tk.Label(
            brand_col,
            text=f"NVR Cast Hub  v{APP_VERSION}",
            font=("Segoe UI", 13, "bold"),
            bg="#ffffff",
            fg="#0f172a",
        ).pack(anchor="w")

        tk.Label(
            brand_col,
            text="Live TV & Media Player  •  Watch Here in App, Open in VLC, or Broadcast to NVR",
            font=("Segoe UI", 8),
            bg="#ffffff",
            fg="#64748b",
        ).pack(anchor="w")

        # Right side: Web Studio + VLC Playlist Button + RTSP Copy Pills
        self._make_btn(
            top_row,
            text="🌐 Web Studio (:8090) ↗",
            variant="accent",
            padx=11,
            pady=5,
            command=lambda: os.startfile(f"http://localhost:{self.engine.web_port}"),
        ).pack(side=tk.RIGHT, padx=(6, 0))

        self._make_btn(
            top_row,
            text="🎬 Open Channels in VLC",
            variant="secondary",
            padx=11,
            pady=5,
            command=lambda: self.engine.open_in_vlc(),
        ).pack(side=tk.RIGHT, padx=(6, 0))

        self.main_rtsp_var = tk.StringVar(value=f"rtsp://{self.engine.lan_ip}:{self.engine.rtsp_port}/main")
        self.sub_rtsp_var = tk.StringVar(value=f"rtsp://{self.engine.lan_ip}:{self.engine.rtsp_port}/sub")
        self.web_remote_var = tk.StringVar(value=f"http://localhost:{self.engine.web_port}")

        ep_bar = tk.Frame(top_row, bg="#ffffff")
        ep_bar.pack(side=tk.RIGHT, padx=(6, 2))
        self._add_endpoint_pill(ep_bar, "RTSP MAIN:", self.main_rtsp_var)
        self._add_endpoint_pill(ep_bar, "RTSP SUB:", self.sub_rtsp_var)

        # 2. Main 2-Column Workspace Container
        workspace = tk.Frame(self.root, bg="#f1f5f9")
        workspace.pack(fill=tk.BOTH, expand=True, padx=14, pady=(0, 6))
        workspace.columnconfigure(0, weight=0, minsize=668)
        workspace.columnconfigure(1, weight=1)
        workspace.rowconfigure(0, weight=1)

        # ---------------------------------------------------------------------
        # LEFT COLUMN: 640x360 PLAYER + 3-WAY OUTPUT SELECTOR + TRANSPORT
        # ---------------------------------------------------------------------
        left_col = tk.Frame(
            workspace,
            bg="#ffffff",
            highlightbackground="#cbd5e1",
            highlightthickness=1,
            padx=14,
            pady=12,
            width=668,
        )
        left_col.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        left_col.grid_propagate(False)

        self._build_left_monitor_deck(left_col)

        # ---------------------------------------------------------------------
        # RIGHT COLUMN: CLEAN 5-TAB CONTROL & CHANNEL MANAGER WORKSPACE
        # ---------------------------------------------------------------------
        right_col = tk.Frame(
            workspace,
            bg="#ffffff",
            highlightbackground="#cbd5e1",
            highlightthickness=1,
            padx=14,
            pady=12,
        )
        right_col.grid(row=0, column=1, sticky="nsew")

        self._build_right_tabbed_workspace(right_col)

        # 3. Bottom Compact Live Log Status Bar
        footer = tk.Frame(
            self.root,
            bg="#ffffff",
            highlightbackground="#cbd5e1",
            highlightthickness=1,
            padx=12,
            pady=5,
        )
        footer.pack(fill=tk.X, padx=14, pady=(0, 10))

        tk.Label(
            footer,
            text="⚡ STATUS:",
            font=("Segoe UI", 8, "bold"),
            bg="#ffffff",
            fg="#2563eb",
        ).pack(side=tk.LEFT, padx=(0, 6))

        self.latest_log_var = tk.StringVar(value="Ready — Choose 'Preview Only (Watch Here)' or 'Both (App + NVR)' and click any channel.")
        tk.Label(
            footer,
            textvariable=self.latest_log_var,
            font=("Consolas", 9),
            bg="#ffffff",
            fg="#334155",
            anchor="w",
        ).pack(side=tk.LEFT, fill=tk.X, expand=True)

        tk.Button(
            footer,
            text="Config & Logs →",
            font=("Segoe UI", 8, "bold"),
            bg="#f8fafc",
            fg="#475569",
            relief=tk.FLAT,
            cursor="hand2",
            command=lambda: self._switch_tab("settings"),
        ).pack(side=tk.RIGHT)

    def _add_endpoint_pill(self, parent, label_text: str, text_var: tk.StringVar):
        box = tk.Frame(parent, bg="#f8fafc", highlightbackground="#cbd5e1", highlightthickness=1, padx=6, pady=3)
        box.pack(side=tk.LEFT, padx=(0, 6))

        tk.Label(
            box,
            text=label_text,
            font=("Segoe UI", 8, "bold"),
            bg="#f8fafc",
            fg="#64748b",
        ).pack(side=tk.LEFT, padx=(0, 4))

        entry = tk.Entry(
            box,
            textvariable=text_var,
            font=("Consolas", 8, "bold"),
            width=23,
            bg="#f8fafc",
            fg="#0f172a",
            readonlybackground="#f8fafc",
            relief=tk.FLAT,
            state="readonly",
        )
        entry.pack(side=tk.LEFT)

        tk.Button(
            box,
            text="Copy",
            font=("Segoe UI", 8, "bold"),
            bg="#ffffff",
            fg="#2563eb",
            relief=tk.SOLID,
            bd=1,
            padx=5,
            cursor="hand2",
            command=lambda: self.copy_to_clipboard(text_var.get()),
        ).pack(side=tk.LEFT, padx=(4, 0))

    # =========================================================================
    # LEFT COLUMN: 3-WAY OUTPUT MODE BAR + 640x360 PLAYER + TRANSPORT
    # =========================================================================
    def _build_left_monitor_deck(self, parent: tk.Frame):
        # 1. Prominent 3-Way Output Routing Selector Bar (Watch Here vs NVR Only vs Both)
        mode_card = tk.Frame(
            parent,
            bg="#f8fafc",
            highlightbackground="#cbd5e1",
            highlightthickness=1,
            padx=8,
            pady=6,
        )
        mode_card.pack(fill=tk.X, pady=(0, 8))

        mode_top = tk.Frame(mode_card, bg="#f8fafc")
        mode_top.pack(fill=tk.X, pady=(0, 5))

        tk.Label(
            mode_top,
            text="OUTPUT DESTINATION & VIEW MODE:",
            font=("Segoe UI", 8, "bold"),
            bg="#f8fafc",
            fg="#334155",
        ).pack(side=tk.LEFT)

        self.fs_btn = self._make_btn(
            mode_top,
            text="⛶ Full Screen (F11)",
            variant="dark",
            padx=9,
            pady=2,
            font_size=8,
            command=self.on_toggle_fullscreen,
        )
        self.fs_btn.pack(side=tk.RIGHT, padx=(4, 0))

        self.pip_btn = self._make_btn(
            mode_top,
            text="🗗 PiP Mini Player",
            variant="accent",
            padx=9,
            pady=2,
            font_size=8,
            command=self.on_toggle_pip,
        )
        self.pip_btn.pack(side=tk.RIGHT, padx=(4, 0))

        self.audio_mute_btn = self._make_btn(
            mode_top,
            text="🔊 App Audio: ON" if self.engine.local_audio_enabled else "🔇 App Audio: Muted",
            variant="success" if self.engine.local_audio_enabled else "secondary",
            padx=8,
            pady=2,
            font_size=8,
            command=self.on_toggle_local_audio,
        )
        self.audio_mute_btn.pack(side=tk.RIGHT, padx=(4, 0))

        self.preview_toggle_btn = self._make_btn(
            mode_top,
            text="⏸ Pause View",
            variant="secondary",
            padx=7,
            pady=2,
            font_size=8,
            command=self.on_toggle_preview,
        )
        self.preview_toggle_btn.pack(side=tk.RIGHT)

        mode_btns_row = tk.Frame(mode_card, bg="#f8fafc")
        mode_btns_row.pack(fill=tk.X)

        modes_spec = [
            ("local_only", "🖥  Preview Only (Watch Here — No NVR)"),
            ("both", "🖥 + 📡  Both (Watch Here + Cast to NVR)"),
            ("nvr_only", "📡  NVR Only (Cast to NVR)"),
        ]
        for m_id, m_label in modes_spec:
            btn = tk.Button(
                mode_btns_row,
                text=m_label,
                font=("Segoe UI", 9, "bold"),
                relief=tk.SOLID,
                bd=1,
                padx=8,
                pady=5,
                cursor="hand2",
                command=lambda mid=m_id: self.on_select_output_mode(mid),
            )
            btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)
            self._output_mode_btns[m_id] = btn

        self._refresh_output_mode_buttons()

        # 2. Large 16:9 Video Player Canvas (640x360) — Double-Click for Full Screen
        canvas_wrap = tk.Frame(
            parent,
            bg="#0f172a",
            highlightbackground="#334155",
            highlightthickness=1,
            width=self.PREVIEW_W,
            height=self.PREVIEW_H,
        )
        canvas_wrap.pack(pady=(0, 8))
        canvas_wrap.pack_propagate(False)

        self.preview_canvas = tk.Canvas(
            canvas_wrap,
            width=self.PREVIEW_W,
            height=self.PREVIEW_H,
            bg="#0f172a",
            highlightthickness=0,
            cursor="hand2",
        )
        self.preview_canvas.pack(fill=tk.BOTH, expand=True)
        self.preview_canvas.bind("<Double-1>", lambda e: self.on_toggle_fullscreen())
        self._draw_initial_preview_canvas()

        # 3. Stream Health & Diagnostic Banner
        self.health_frame = tk.Frame(
            parent,
            bg="#ecfdf5",
            highlightbackground="#6ee7b7",
            highlightthickness=1,
            padx=10,
            pady=6,
        )
        self.health_frame.pack(fill=tk.X, pady=(0, 8))

        health_top = tk.Frame(self.health_frame, bg="#ecfdf5")
        health_top.pack(fill=tk.X)
        self.health_top = health_top

        self.health_badge = tk.Label(
            health_top,
            text=" ● READY ",
            font=("Segoe UI", 8, "bold"),
            bg="#059669",
            fg="#ffffff",
            padx=6,
            pady=1,
        )
        self.health_badge.pack(side=tk.LEFT, padx=(0, 8))

        self.health_title_lbl = tk.Label(
            health_top,
            text="Player & Broadcast Engine Online",
            font=("Segoe UI", 9, "bold"),
            bg="#ecfdf5",
            fg="#065f46",
            anchor="w",
        )
        self.health_title_lbl.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.health_detail_lbl = tk.Label(
            self.health_frame,
            text="Double-click any channel on the right to watch right here or broadcast to NVR.",
            font=("Segoe UI", 8),
            bg="#ecfdf5",
            fg="#047857",
            anchor="w",
            justify=tk.LEFT,
            wraplength=615,
        )
        self.health_detail_lbl.pack(fill=tk.X, pady=(3, 0))

        # 4. Now Playing Bar
        now_card = tk.Frame(
            parent,
            bg="#f8fafc",
            highlightbackground="#e2e8f0",
            highlightthickness=1,
            padx=10,
            pady=7,
        )
        now_card.pack(fill=tk.X, pady=(0, 8))

        np_row1 = tk.Frame(now_card, bg="#f8fafc")
        np_row1.pack(fill=tk.X, pady=(0, 3))

        self.mode_badge = tk.Label(
            np_row1,
            text=" STANDBY ",
            font=("Segoe UI", 8, "bold"),
            bg="#dcfce7",
            fg="#15803d",
            padx=8,
            pady=2,
        )
        self.mode_badge.pack(side=tk.LEFT)

        self.source_label = tk.Label(
            np_row1,
            text="Source: Ready",
            font=("Segoe UI", 8, "bold"),
            bg="#f8fafc",
            fg="#64748b",
            padx=8,
        )
        self.source_label.pack(side=tk.LEFT)

        self.pos_label = tk.Label(
            np_row1,
            text="",
            font=("Consolas", 9, "bold"),
            bg="#f8fafc",
            fg="#2563eb",
        )
        self.pos_label.pack(side=tk.RIGHT)

        self.title_label = tk.Label(
            now_card,
            text="Standby Screen (Select any Channel, Video, or Screen Share)",
            font=("Segoe UI", 10, "bold"),
            bg="#f8fafc",
            fg="#0f172a",
            anchor="w",
            justify=tk.LEFT,
            wraplength=615,
        )
        self.title_label.pack(fill=tk.X)

        # 5. Player & Channel Transport Controls
        transport_card = tk.Frame(
            parent,
            bg="#ffffff",
            highlightbackground="#e2e8f0",
            highlightthickness=1,
            padx=8,
            pady=8,
        )
        transport_card.pack(fill=tk.X, pady=(0, 6))

        t_row1 = tk.Frame(transport_card, bg="#ffffff")
        t_row1.pack(fill=tk.X, pady=(0, 6))

        self._make_btn(
            t_row1,
            "⏮ Prev Channel / Track",
            lambda: self.engine.step_gallery_slide(-1),
            "secondary",
            padx=10,
            pady=5,
        ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))

        self.pause_btn = self._make_btn(
            t_row1,
            "❚❚ Pause",
            self.on_toggle_pause,
            "accent",
            padx=12,
            pady=5,
        )
        self.pause_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)

        self._make_btn(
            t_row1,
            "Next Channel / Track ⏭",
            lambda: self.engine.step_gallery_slide(1),
            "secondary",
            padx=10,
            pady=5,
        ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 0))

        t_row2 = tk.Frame(transport_card, bg="#ffffff")
        t_row2.pack(fill=tk.X)

        self._make_btn(
            t_row2,
            "◁ -10s",
            lambda: self.engine.seek_stream(delta_sec=-10, source="Desktop App"),
            "secondary",
            padx=7,
            pady=4,
            font_size=8,
        ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 3))

        self._make_btn(
            t_row2,
            "+10s ▷",
            lambda: self.engine.seek_stream(delta_sec=10, source="Desktop App"),
            "secondary",
            padx=7,
            pady=4,
            font_size=8,
        ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=3)

        self._make_btn(
            t_row2,
            "🗗 PiP Mini",
            self.on_toggle_pip,
            "accent",
            padx=8,
            pady=4,
            font_size=8,
        ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=3)

        self._make_btn(
            t_row2,
            "⛶ Full Screen",
            self.on_toggle_fullscreen,
            "dark",
            padx=8,
            pady=4,
            font_size=8,
        ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=3)

        self._make_btn(
            t_row2,
            "🎬 VLC",
            self.on_open_current_in_vlc,
            "secondary",
            padx=7,
            pady=4,
            font_size=8,
        ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=3)

        self._make_btn(
            t_row2,
            "■ Stop",
            lambda: threading.Thread(
                target=self.engine.start_standby_stream, args=("Desktop App",), daemon=True
            ).start(),
            "danger",
            padx=8,
            pady=4,
            font_size=8,
        ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(3, 0))

        # Telemetry Footer
        telemetry_row = tk.Frame(parent, bg="#ffffff")
        telemetry_row.pack(fill=tk.X, side=tk.BOTTOM, pady=(2, 0))

        self.telemetry_lbl = tk.Label(
            telemetry_row,
            text="Mode: Both (Watch in App + NVR RTSP)  •  1280x720 @ 25fps",
            font=("Segoe UI", 8),
            bg="#ffffff",
            fg="#64748b",
            anchor="w",
        )
        self.telemetry_lbl.pack(side=tk.LEFT)

    def _refresh_output_mode_buttons(self):
        cur = self.engine.output_mode
        for m_id, btn in self._output_mode_btns.items():
            if m_id == cur:
                if m_id == "local_only":
                    btn.configure(bg="#059669", fg="#ffffff", highlightbackground="#047857")
                elif m_id == "nvr_only":
                    btn.configure(bg="#4f46e5", fg="#ffffff", highlightbackground="#4338ca")
                else:
                    btn.configure(bg="#2563eb", fg="#ffffff", highlightbackground="#1d4ed8")
            else:
                btn.configure(bg="#ffffff", fg="#334155", highlightbackground="#cbd5e1")

        if hasattr(self, "audio_mute_btn"):
            if self.engine.local_audio_enabled:
                self.audio_mute_btn.configure(text="🔊 App Audio: ON", bg="#059669", fg="#ffffff")
            else:
                self.audio_mute_btn.configure(text="🔇 App Audio: Muted", bg="#f8fafc", fg="#475569")
        if self.pip_audio_btn and self.pip_win and self.pip_win.winfo_exists():
            self.pip_audio_btn.configure(
                text="🔊" if self.engine.local_audio_enabled else "🔇",
                bg="#059669" if self.engine.local_audio_enabled else "#334155",
            )
        if self.fs_audio_btn and self.fs_win and self.fs_win.winfo_exists():
            self.fs_audio_btn.configure(
                text="🔊 Audio: ON" if self.engine.local_audio_enabled else "🔇 Audio: Muted",
                bg="#059669" if self.engine.local_audio_enabled else "#334155",
            )

    def on_select_output_mode(self, mode: str):
        self.engine.set_output_mode(mode, source="Desktop App")
        self._refresh_output_mode_buttons()
        if not self.engine.preview_enabled:
            self._draw_paused_preview_canvas("📡  NVR ONLY MODE ACTIVE (Local Preview Off)")
        else:
            self._last_preview_bytes = None
            self.preview_toggle_btn.configure(text="⏸ Pause View", bg="#f8fafc", fg="#0f172a")

    def on_toggle_local_audio(self):
        self.engine.toggle_local_audio()
        self._refresh_output_mode_buttons()

    def on_open_current_in_vlc(self):
        target = self.engine.current_url or self.engine.current_filepath or DEFAULT_VLC_M3U_PATH
        self.engine.open_in_vlc(target)

    # =========================================================================
    # IN-APP PICTURE-IN-PICTURE (PiP) FLOATING PLAYER & FULL-SCREEN TV MODE
    # =========================================================================
    def _ensure_preview_active_for_player(self):
        if self.engine.output_mode == "nvr_only":
            self.on_select_output_mode("both")
        elif not self.engine.preview_enabled:
            self.on_toggle_preview()

    def on_toggle_pip(self):
        """Toggles the Always-On-Top Floating Picture-in-Picture (PiP) Mini Player."""
        if self.pip_win is not None and self.pip_win.winfo_exists():
            self.on_close_pip(restore_studio=True)
            return

        if self.fs_win is not None and self.fs_win.winfo_exists():
            self.on_close_fullscreen(restore_studio=False)

        self._ensure_preview_active_for_player()

        pip = tk.Toplevel(self.root)
        pip.title(f"PiP Player — {self.engine.current_title}")
        pip.configure(bg="#0f172a")
        pip.attributes("-topmost", True)
        pip.minsize(320, 220)

        # Position in bottom-right corner of the primary screen
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        pw, ph = 480, 315
        px = max(20, sw - pw - 36)
        py = max(20, sh - ph - 86)
        pip.geometry(f"{pw}x{ph}+{px}+{py}")

        self.pip_win = pip
        self._pip_last_size = (0, 0)

        # Top slim title & status bar inside PiP
        top_bar = tk.Frame(pip, bg="#1e293b", padx=8, pady=4)
        top_bar.pack(fill=tk.X, side=tk.TOP)

        tk.Label(
            top_bar,
            text="🗗 PiP",
            font=("Segoe UI", 8, "bold"),
            bg="#2563eb",
            fg="#ffffff",
            padx=5,
            pady=1,
        ).pack(side=tk.LEFT, padx=(0, 6))

        self.pip_title_lbl = tk.Label(
            top_bar,
            text=self.engine.current_title,
            font=("Segoe UI", 8, "bold"),
            bg="#1e293b",
            fg="#f8fafc",
            anchor="w",
        )
        self.pip_title_lbl.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # Bottom compact control bar inside PiP
        ctl_bar = tk.Frame(pip, bg="#1e293b", padx=6, pady=5)
        ctl_bar.pack(fill=tk.X, side=tk.BOTTOM)

        def _pip_btn(txt, cmd, bg="#334155", fg="#f8fafc"):
            b = tk.Button(
                ctl_bar,
                text=txt,
                font=("Segoe UI", 8, "bold"),
                bg=bg,
                fg=fg,
                activebackground="#475569",
                activeforeground="#ffffff",
                relief=tk.FLAT,
                bd=0,
                padx=7,
                pady=3,
                cursor="hand2",
                command=cmd,
            )
            b.pack(side=tk.LEFT, padx=2)
            return b

        _pip_btn("⏮ Prev", lambda: self.engine.step_gallery_slide(-1))
        self.pip_pause_btn = _pip_btn(
            "▶" if self.engine.is_paused else "❚❚",
            self.on_toggle_pause,
            bg="#2563eb",
        )
        _pip_btn("Next ⏭", lambda: self.engine.step_gallery_slide(1))
        _pip_btn("-10s", lambda: self.engine.seek_stream(delta_sec=-10, source="PiP Player"))
        _pip_btn("+10s", lambda: self.engine.seek_stream(delta_sec=10, source="PiP Player"))

        self.pip_audio_btn = _pip_btn(
            "🔊" if self.engine.local_audio_enabled else "🔇",
            self.on_toggle_local_audio,
            bg="#059669" if self.engine.local_audio_enabled else "#334155",
        )

        # Right-aligned PiP window actions: Full Screen & Restore Studio
        tk.Button(
            ctl_bar,
            text="🗖 Studio",
            font=("Segoe UI", 8, "bold"),
            bg="#059669",
            fg="#ffffff",
            relief=tk.FLAT,
            padx=8,
            pady=3,
            cursor="hand2",
            command=lambda: self.on_close_pip(restore_studio=True),
        ).pack(side=tk.RIGHT, padx=2)

        tk.Button(
            ctl_bar,
            text="⛶ Full",
            font=("Segoe UI", 8, "bold"),
            bg="#4f46e5",
            fg="#ffffff",
            relief=tk.FLAT,
            padx=8,
            pady=3,
            cursor="hand2",
            command=self.on_toggle_fullscreen,
        ).pack(side=tk.RIGHT, padx=2)

        # Resizable 16:9 Video Canvas in the center of PiP
        self.pip_canvas = tk.Canvas(pip, bg="#000000", highlightthickness=0, cursor="hand2")
        self.pip_canvas.pack(fill=tk.BOTH, expand=True)
        self.pip_canvas.bind("<Double-1>", lambda e: self.on_toggle_fullscreen())

        pip.protocol("WM_DELETE_WINDOW", lambda: self.on_close_pip(restore_studio=True))

        # Minimize main Studio window so the floating PiP stays clean over your desktop
        self.root.iconify()
        self._last_preview_bytes = None
        self.engine.log("Opened Floating Picture-in-Picture (PiP) Mini Player (Always-On-Top).")

    def on_close_pip(self, restore_studio: bool = True):
        if self.pip_win is not None:
            try:
                self.pip_win.destroy()
            except Exception:
                pass
        self.pip_win = None
        self.pip_canvas = None
        self.pip_photo = None
        if restore_studio:
            try:
                self.root.deiconify()
                self.root.lift()
                self.root.focus_force()
            except Exception:
                pass
        self._last_preview_bytes = None

    def on_toggle_fullscreen(self):
        """Toggles the 100% Full-Screen Borderless TV & Video Player (F11 / Double-Click / Esc)."""
        if self.fs_win is not None and self.fs_win.winfo_exists():
            self.on_close_fullscreen(restore_studio=True)
            return

        if self.pip_win is not None and self.pip_win.winfo_exists():
            self.on_close_pip(restore_studio=False)

        self._ensure_preview_active_for_player()

        fs = tk.Toplevel(self.root)
        fs.title(f"Full Screen Player — {self.engine.current_title}")
        fs.configure(bg="#000000")
        fs.attributes("-fullscreen", True)
        fs.attributes("-topmost", True)

        self.fs_win = fs
        self._fs_last_size = (0, 0)

        # Bottom Sleek Cinema HUD Control Bar
        hud = tk.Frame(fs, bg="#0f172a", highlightbackground="#334155", highlightthickness=1, padx=16, pady=8)
        hud.pack(fill=tk.X, side=tk.BOTTOM)

        tk.Label(
            hud,
            text=" ● LIVE TV / FULL SCREEN ",
            font=("Segoe UI", 9, "bold"),
            bg="#2563eb",
            fg="#ffffff",
            padx=8,
            pady=2,
        ).pack(side=tk.LEFT, padx=(0, 10))

        self.fs_title_lbl = tk.Label(
            hud,
            text=self.engine.current_title,
            font=("Segoe UI", 11, "bold"),
            bg="#0f172a",
            fg="#f8fafc",
            anchor="w",
        )
        self.fs_title_lbl.pack(side=tk.LEFT, fill=tk.X, expand=True)

        def _fs_btn(txt, cmd, bg="#1e293b", fg="#f8fafc"):
            b = tk.Button(
                hud,
                text=txt,
                font=("Segoe UI", 9, "bold"),
                bg=bg,
                fg=fg,
                activebackground="#334155",
                activeforeground="#ffffff",
                relief=tk.FLAT,
                bd=0,
                padx=11,
                pady=5,
                cursor="hand2",
                command=cmd,
            )
            b.pack(side=tk.LEFT, padx=3)
            return b

        _fs_btn("⏮ Prev Ch (↑)", lambda: self.engine.step_gallery_slide(-1))
        _fs_btn("◁ -10s (←)", lambda: self.engine.seek_stream(delta_sec=-10, source="Full Screen"))
        self.fs_pause_btn = _fs_btn(
            "▶ Resume" if self.engine.is_paused else "❚❚ Pause",
            self.on_toggle_pause,
            bg="#2563eb",
        )
        _fs_btn("+10s (→) ▷", lambda: self.engine.seek_stream(delta_sec=10, source="Full Screen"))
        _fs_btn("Next Ch (↓) ⏭", lambda: self.engine.step_gallery_slide(1))

        self.fs_audio_btn = _fs_btn(
            "🔊 Audio: ON" if self.engine.local_audio_enabled else "🔇 Audio: Muted",
            self.on_toggle_local_audio,
            bg="#059669" if self.engine.local_audio_enabled else "#334155",
        )

        _fs_btn("🗗 Switch to PiP", self.on_toggle_pip, bg="#4f46e5")
        _fs_btn("✕ Exit Full Screen (Esc)", lambda: self.on_close_fullscreen(restore_studio=True), bg="#dc2626")

        # Main Full-Screen Cinema Canvas
        self.fs_canvas = tk.Canvas(fs, bg="#000000", highlightthickness=0, cursor="hand2")
        self.fs_canvas.pack(fill=tk.BOTH, expand=True)
        self.fs_canvas.bind("<Double-1>", lambda e: self.on_close_fullscreen(restore_studio=True))

        # Keyboard shortcuts in Full Screen
        fs.bind("<Escape>", lambda e: self.on_close_fullscreen(restore_studio=True))
        fs.bind("<F11>", lambda e: self.on_close_fullscreen(restore_studio=True))
        fs.bind("<space>", lambda e: self.on_toggle_pause())
        fs.bind("<Left>", lambda e: self.engine.seek_stream(delta_sec=-10, source="Full Screen"))
        fs.bind("<Right>", lambda e: self.engine.seek_stream(delta_sec=10, source="Full Screen"))
        fs.bind("<Up>", lambda e: self.engine.step_gallery_slide(-1))
        fs.bind("<Down>", lambda e: self.engine.step_gallery_slide(1))
        fs.focus_force()

        self._last_preview_bytes = None
        self.engine.log("Entered Full-Screen TV Mode (Press Esc, F11, or Double-Click to exit).")

    def on_close_fullscreen(self, restore_studio: bool = True):
        if self.fs_win is not None:
            try:
                self.fs_win.destroy()
            except Exception:
                pass
        self.fs_win = None
        self.fs_canvas = None
        self.fs_photo = None
        if restore_studio:
            try:
                self.root.deiconify()
                self.root.lift()
                self.root.focus_force()
            except Exception:
                pass
        self._last_preview_bytes = None

    def _draw_initial_preview_canvas(self):
        w, h = self.PREVIEW_W, self.PREVIEW_H
        self.preview_canvas.delete("all")
        self.preview_canvas.create_rectangle(0, 0, w, h, fill="#0f172a", outline="")
        self.preview_canvas.create_rectangle(24, 24, w - 24, h - 24, fill="#1e293b", outline="#334155")
        self.preview_canvas.create_text(
            w // 2,
            h // 2 - 24,
            text="NVR CAST HUB — LIVE PLAYER & PREVIEW MONITOR",
            fill="#f8fafc",
            font=("Segoe UI", 12, "bold"),
        )
        self.preview_canvas.create_text(
            w // 2,
            h // 2 + 12,
            text="Select 'Preview Only (Watch Here)' or 'Both' above and click any channel!",
            fill="#38bdf8",
            font=("Segoe UI", 10),
        )

    def _draw_paused_preview_canvas(self, headline: str = "⏸  LIVE PREVIEW PAUSED BY USER"):
        w, h = self.PREVIEW_W, self.PREVIEW_H
        self.preview_canvas.delete("all")
        self.preview_canvas.create_rectangle(0, 0, w, h, fill="#0f172a", outline="")
        self.preview_canvas.create_rectangle(28, 28, w - 28, h - 28, fill="#1e293b", outline="#334155")
        self.preview_canvas.create_text(
            w // 2,
            h // 2 - 30,
            text=headline,
            fill="#f8fafc",
            font=("Segoe UI", 12, "bold"),
        )
        self.preview_canvas.create_text(
            w // 2,
            h // 2 + 6,
            text="NVR RTSP Broadcast (/main & /sub) continues running at full speed.",
            fill="#93c5fd",
            font=("Segoe UI", 10),
        )
        self.preview_canvas.create_text(
            w // 2,
            h // 2 + 36,
            text="Click 'Preview Only' or 'Both' above anytime to watch live video here.",
            fill="#94a3b8",
            font=("Segoe UI", 9),
        )

    def on_toggle_preview(self):
        self.engine.preview_enabled = not self.engine.preview_enabled
        if self.engine.preview_enabled:
            self.preview_toggle_btn.configure(text="⏸ Pause View", bg="#f8fafc", fg="#0f172a")
            self._last_preview_bytes = None
        else:
            self.preview_toggle_btn.configure(text="▶ Resume View", bg="#eff6ff", fg="#1d4ed8")
            self._draw_paused_preview_canvas()

    # =========================================================================
    # RIGHT COLUMN: 5-TAB CHANNEL MANAGER & MEDIA STUDIO WORKSPACE
    # =========================================================================
    def _build_right_tabbed_workspace(self, parent: tk.Frame):
        nav_bar = tk.Frame(parent, bg="#f1f5f9", padx=4, pady=4)
        nav_bar.pack(fill=tk.X, pady=(0, 10))

        tabs_spec = [
            ("tv", "📺  Channels & Live TV"),
            ("youtube", "▶  YouTube & Video"),
            ("gallery", "🖼  Photo Slideshow"),
            ("monitors", "🖥  Screen Share"),
            ("settings", "⚙  Config, VLC & Settings"),
        ]

        for tab_id, tab_title in tabs_spec:
            btn = tk.Button(
                nav_bar,
                text=tab_title,
                font=("Segoe UI", 9, "bold"),
                bg="#2563eb" if tab_id == self._active_tab_id else "#f1f5f9",
                fg="#ffffff" if tab_id == self._active_tab_id else "#334155",
                activebackground="#1d4ed8",
                activeforeground="#ffffff",
                relief=tk.FLAT,
                bd=0,
                padx=10,
                pady=7,
                cursor="hand2",
                command=lambda tid=tab_id: self._switch_tab(tid),
            )
            btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)
            self._tab_buttons[tab_id] = btn

        self.tab_host = tk.Frame(parent, bg="#ffffff")
        self.tab_host.pack(fill=tk.BOTH, expand=True)

        for tab_id, _ in tabs_spec:
            frame = tk.Frame(self.tab_host, bg="#ffffff")
            self._tab_frames[tab_id] = frame

        self._build_tab_live_tv(self._tab_frames["tv"])
        self._build_tab_youtube(self._tab_frames["youtube"])
        self._build_tab_gallery(self._tab_frames["gallery"])
        self._build_tab_monitors(self._tab_frames["monitors"])
        self._build_tab_settings(self._tab_frames["settings"])

        self._switch_tab("tv")

    def _switch_tab(self, tab_id: str):
        self._active_tab_id = tab_id
        for tid, frame in self._tab_frames.items():
            if tid == tab_id:
                frame.pack(fill=tk.BOTH, expand=True)
            else:
                frame.pack_forget()
        for tid, btn in self._tab_buttons.items():
            if tid == tab_id:
                btn.configure(bg="#2563eb", fg="#ffffff")
            else:
                btn.configure(bg="#f1f5f9", fg="#334155")

    # -------------------------------------------------------------------------
    # TAB 1: CHANNELS & LIVE TV (PAKISTAN TV, CRICKET, ADD/IMPORT/EXPORT/VLC)
    # -------------------------------------------------------------------------
    def _build_tab_live_tv(self, parent: tk.Frame):
        hdr = tk.Frame(parent, bg="#ffffff")
        hdr.pack(fill=tk.X, pady=(0, 6))

        tk.Label(
            hdr,
            text="PAKISTAN TV, LIVE CRICKET & CUSTOM CHANNEL DIRECTORY",
            font=("Segoe UI", 10, "bold"),
            bg="#ffffff",
            fg="#0f172a",
        ).pack(side=tk.LEFT)

        self.auto_skip_var = tk.BooleanVar(value=self.engine.auto_skip_offline)
        tk.Checkbutton(
            hdr,
            text="Auto-Skip Offline",
            variable=self.auto_skip_var,
            font=("Segoe UI", 8, "bold"),
            bg="#ffffff",
            fg="#059669",
            selectcolor="#ffffff",
            activebackground="#ffffff",
            command=self.on_toggle_auto_skip,
        ).pack(side=tk.RIGHT)

        # Quick Category Filter Buttons
        pills_row = tk.Frame(parent, bg="#ffffff")
        pills_row.pack(fill=tk.X, pady=(0, 6))

        quick_cats = [
            ("pakistan_tv", "🇵🇰 Pakistan TV (24+ Ch)"),
            ("cricket_pk", "🏏 Cricket & Sports"),
            ("youtube_cricket", "▶ YouTube Live TV"),
            ("global_sports", "🌍 Global Sports"),
            ("all_builtin", "📋 All Built-In"),
            ("iptv_pk", "📦 GitHub PK M3U"),
            ("iptv_sports", "📦 GitHub Sports M3U"),
        ]
        for cat_id, cat_label in quick_cats:
            self._make_btn(
                pills_row,
                cat_label,
                lambda cid=cat_id: self.on_quick_select_tv_cat(cid),
                variant="accent" if cat_id in ("pakistan_tv", "cricket_pk") else "secondary",
                padx=7,
                pady=3,
                font_size=8,
            ).pack(side=tk.LEFT, padx=(0, 4))

        # Source Selector + Search Filter Row
        filter_row = tk.Frame(parent, bg="#f8fafc", highlightbackground="#e2e8f0", highlightthickness=1, padx=8, pady=6)
        filter_row.pack(fill=tk.X, pady=(0, 6))

        tk.Label(filter_row, text="List:", font=("Segoe UI", 8, "bold"), bg="#f8fafc", fg="#475569").pack(side=tk.LEFT)

        self.tv_source_options = [
            ("cricket_pk", "Pakistan Cricket & Live Sports TV"),
            ("pakistan_tv", "Pakistan News, Entertainment, Music & Movies (24+ Channels)"),
            ("youtube_cricket", "Official Cricket & Pakistani News YouTube Live Channels"),
            ("global_sports", "Global Sports TV (ESPN, Eurosport, Tennis, RedBull)"),
            ("all_builtin", "All Built-in Pakistani & Sports Channels Combined"),
            ("custom_channels", "My Added & Imported Custom Channels"),
            ("iptv_pk", "GitHub Repo: iptv-org Pakistan Channels M3U"),
            ("iptv_sports", "GitHub Repo: iptv-org Global Sports M3U (480+ Ch)"),
            ("curated_pk_in", "GitHub Repo: South Asia & Pakistan Curated M3U"),
            ("freetv_global", "GitHub Repo: Free-TV Open-Source Global IPTV"),
        ]
        self.tv_source_combo = ttk.Combobox(
            filter_row,
            values=[label for _, label in self.tv_source_options],
            width=34,
            state="readonly",
        )
        self.tv_source_combo.current(0)
        self.tv_source_combo.pack(side=tk.LEFT, padx=(5, 8))
        self.tv_source_combo.bind("<<ComboboxSelected>>", lambda e: self.on_load_tv_source(auto_play=False))

        tk.Label(filter_row, text="Search / M3U:", font=("Segoe UI", 8, "bold"), bg="#f8fafc", fg="#475569").pack(
            side=tk.LEFT
        )
        self.tv_filter_entry = tk.Entry(
            filter_row,
            font=("Segoe UI", 9),
            bg="#ffffff",
            fg="#0f172a",
            relief=tk.SOLID,
            bd=1,
        )
        self.tv_filter_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=2, padx=(4, 6))
        self.tv_filter_entry.bind("<Return>", lambda e: self.on_load_tv_source(auto_play=False))

        self._make_btn(
            filter_row,
            "🔍 Filter / Load",
            lambda: self.on_load_tv_source(auto_play=False),
            "secondary",
            padx=8,
            pady=2,
            font_size=8,
        ).pack(side=tk.LEFT)

        # Inline Quick "Add Channel" + Import/Export Bar
        add_box = tk.Frame(parent, bg="#f8fafc", highlightbackground="#e2e8f0", highlightthickness=1, padx=8, pady=6)
        add_box.pack(fill=tk.X, pady=(0, 6))

        tk.Label(add_box, text="➕ Add Channel:", font=("Segoe UI", 8, "bold"), bg="#f8fafc", fg="#1d4ed8").pack(
            side=tk.LEFT, padx=(0, 4)
        )

        self.add_ch_title_entry = tk.Entry(
            add_box,
            font=("Segoe UI", 9),
            width=18,
            bg="#ffffff",
            fg="#0f172a",
            relief=tk.SOLID,
            bd=1,
        )
        self.add_ch_title_entry.insert(0, "Channel Name")
        self.add_ch_title_entry.bind(
            "<FocusIn>",
            lambda e: self.add_ch_title_entry.delete(0, tk.END)
            if self.add_ch_title_entry.get() == "Channel Name"
            else None,
        )
        self.add_ch_title_entry.pack(side=tk.LEFT, ipady=2, padx=(0, 4))

        self.add_ch_url_entry = tk.Entry(
            add_box,
            font=("Segoe UI", 9),
            bg="#ffffff",
            fg="#0f172a",
            relief=tk.SOLID,
            bd=1,
        )
        self.add_ch_url_entry.insert(0, "Stream URL (.m3u8, YouTube, RTSP, HTTP)")
        self.add_ch_url_entry.bind(
            "<FocusIn>",
            lambda e: self.add_ch_url_entry.delete(0, tk.END)
            if self.add_ch_url_entry.get().startswith("Stream URL")
            else None,
        )
        self.add_ch_url_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=2, padx=(0, 6))
        self.add_ch_url_entry.bind("<Return>", lambda e: self.on_add_custom_channel())

        self._make_btn(
            add_box,
            "➕ Add & Save",
            self.on_add_custom_channel,
            "primary",
            padx=9,
            pady=2,
            font_size=8,
        ).pack(side=tk.LEFT, padx=(0, 4))

        self._make_btn(
            add_box,
            "📥 Import .M3U/.JSON",
            self.on_import_channels_dialog,
            "accent",
            padx=8,
            pady=2,
            font_size=8,
        ).pack(side=tk.LEFT, padx=(0, 4))

        self._make_btn(
            add_box,
            "📤 Export VLC .M3U",
            self.on_export_vlc_m3u_dialog,
            "secondary",
            padx=8,
            pady=2,
            font_size=8,
        ).pack(side=tk.LEFT)

        # Scrollable Channel Table (Treeview)
        tree_wrap = tk.Frame(parent, bg="#ffffff", highlightbackground="#cbd5e1", highlightthickness=1)
        tree_wrap.pack(fill=tk.BOTH, expand=True, pady=(0, 8))

        cols = ("num", "title", "group", "status")
        self.tv_tree = ttk.Treeview(
            tree_wrap,
            columns=cols,
            show="headings",
            style="Studio.Treeview",
            selectmode="browse",
        )
        self.tv_tree.heading("num", text="#")
        self.tv_tree.heading("title", text="Channel Name (Double-Click to Watch / Cast)")
        self.tv_tree.heading("group", text="Category / Network")
        self.tv_tree.heading("status", text="Stream Type / Status")

        self.tv_tree.column("num", width=42, anchor="center", stretch=False)
        self.tv_tree.column("title", width=265, anchor="w")
        self.tv_tree.column("group", width=155, anchor="w")
        self.tv_tree.column("status", width=155, anchor="w")

        tv_scroll = ttk.Scrollbar(tree_wrap, orient=tk.VERTICAL, command=self.tv_tree.yview)
        self.tv_tree.configure(yscrollcommand=tv_scroll.set)
        self.tv_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tv_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self.tv_tree.bind("<Double-1>", lambda e: self.on_play_selected_tv_channel())

        # Bottom Action Row for Live TV Tab
        act_row = tk.Frame(parent, bg="#ffffff")
        act_row.pack(fill=tk.X)

        self._make_btn(
            act_row,
            "▶  Watch / Play Selected Channel",
            self.on_play_selected_tv_channel,
            "primary",
            padx=14,
            pady=6,
        ).pack(side=tk.LEFT, padx=(0, 6))

        self._make_btn(
            act_row,
            "🎬 Open in VLC",
            self.on_open_selected_tv_in_vlc,
            "secondary",
            padx=10,
            pady=6,
        ).pack(side=tk.LEFT, padx=(0, 6))

        self._make_btn(
            act_row,
            "⚡ Test Link",
            self.on_test_selected_tv_channel,
            "accent",
            padx=10,
            pady=6,
        ).pack(side=tk.LEFT, padx=(0, 6))

        self._make_btn(
            act_row,
            "🗑 Remove",
            self.on_remove_selected_tv_channel,
            "danger",
            padx=9,
            pady=6,
        ).pack(side=tk.LEFT)

        self.tv_count_lbl = tk.Label(
            act_row,
            text="",
            font=("Segoe UI", 8, "bold"),
            bg="#ffffff",
            fg="#64748b",
        )
        self.tv_count_lbl.pack(side=tk.RIGHT)

        self._refresh_tv_channel_tree()

    # -------------------------------------------------------------------------
    # TAB 2: YOUTUBE, PLAYLISTS, WEB STREAMS & LOCAL VIDEO PLAYER/CASTER
    # -------------------------------------------------------------------------
    def _build_tab_youtube(self, parent: tk.Frame):
        tk.Label(
            parent,
            text="YOUTUBE VIDEO, PLAYLIST / CHANNEL QUEUE & LOCAL VIDEO PLAYER",
            font=("Segoe UI", 10, "bold"),
            bg="#ffffff",
            fg="#0f172a",
        ).pack(anchor="w", pady=(0, 4))

        tk.Label(
            parent,
            text="Paste any YouTube Video URL, YouTube Playlist (?list=...), YouTube Channel (@...), direct .m3u8/.mp4 stream, or search query.",
            font=("Segoe UI", 8),
            bg="#ffffff",
            fg="#64748b",
        ).pack(anchor="w", pady=(0, 8))

        yt_box = tk.Frame(parent, bg="#f8fafc", highlightbackground="#e2e8f0", highlightthickness=1, padx=10, pady=10)
        yt_box.pack(fill=tk.X, pady=(0, 10))

        row1 = tk.Frame(yt_box, bg="#f8fafc")
        row1.pack(fill=tk.X, pady=(0, 8))

        self.yt_entry = tk.Entry(
            row1,
            font=("Segoe UI", 10),
            bg="#ffffff",
            fg="#0f172a",
            insertbackground="#0f172a",
            relief=tk.SOLID,
            bd=1,
        )
        self.yt_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=5, padx=(0, 6))
        self.yt_entry.bind("<Return>", lambda e: self.on_stream_youtube())

        self._make_btn(row1, "📋 Paste", self.paste_clipboard, "secondary", padx=10, pady=5).pack(side=tk.LEFT, padx=(0, 6))
        self._make_btn(row1, "▶ Play / Stream URL", self.on_stream_youtube, "primary", padx=14, pady=5).pack(
            side=tk.LEFT
        )

        row2 = tk.Frame(yt_box, bg="#f8fafc")
        row2.pack(fill=tk.X)

        self.loop_video_var = tk.BooleanVar(value=self.engine.loop_video)
        tk.Checkbutton(
            row2,
            text="⟲  Loop Video / Playlist 24/7",
            variable=self.loop_video_var,
            font=("Segoe UI", 9, "bold"),
            bg="#f8fafc",
            fg="#0f172a",
            selectcolor="#ffffff",
            activebackground="#f8fafc",
            command=self.on_settings_change,
        ).pack(side=tk.LEFT, padx=(0, 14))

        self._make_btn(
            row2,
            "📂 Browse Local Video File (.mp4, .mkv, .avi, .mov)...",
            self.on_stream_file,
            "accent",
            padx=12,
            pady=4,
        ).pack(side=tk.LEFT)

        pl_hdr = tk.Frame(parent, bg="#ffffff")
        pl_hdr.pack(fill=tk.X, pady=(2, 4))

        self.pl_title_lbl = tk.Label(
            pl_hdr,
            text="ACTIVE PLAYLIST / CHANNEL QUEUE (Double-click any item to jump)",
            font=("Segoe UI", 9, "bold"),
            bg="#ffffff",
            fg="#334155",
        )
        self.pl_title_lbl.pack(side=tk.LEFT)

        pl_wrap = tk.Frame(parent, bg="#ffffff", highlightbackground="#cbd5e1", highlightthickness=1)
        pl_wrap.pack(fill=tk.BOTH, expand=True, pady=(0, 6))

        self.pl_tree = ttk.Treeview(
            pl_wrap,
            columns=("idx", "title", "url"),
            show="headings",
            style="Studio.Treeview",
            selectmode="browse",
        )
        self.pl_tree.heading("idx", text="#")
        self.pl_tree.heading("title", text="Track / Video Title")
        self.pl_tree.heading("url", text="Stream URL")

        self.pl_tree.column("idx", width=50, anchor="center", stretch=False)
        self.pl_tree.column("title", width=340, anchor="w")
        self.pl_tree.column("url", width=240, anchor="w")

        pl_scroll = ttk.Scrollbar(pl_wrap, orient=tk.VERTICAL, command=self.pl_tree.yview)
        self.pl_tree.configure(yscrollcommand=pl_scroll.set)
        self.pl_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        pl_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self.pl_tree.bind("<Double-1>", lambda e: self.on_jump_playlist_item())

    # -------------------------------------------------------------------------
    # TAB 3: PHOTO GALLERY & SLIDESHOW
    # -------------------------------------------------------------------------
    def _build_tab_gallery(self, parent: tk.Frame):
        tk.Label(
            parent,
            text="PICTURE & PHOTO GALLERY SLIDESHOW",
            font=("Segoe UI", 10, "bold"),
            bg="#ffffff",
            fg="#0f172a",
        ).pack(anchor="w", pady=(0, 4))

        tk.Label(
            parent,
            text="Display a single static picture or an entire photo folder with custom timer, shuffle, and smooth crossfades.",
            font=("Segoe UI", 8),
            bg="#ffffff",
            fg="#64748b",
        ).pack(anchor="w", pady=(0, 10))

        gal_card = tk.Frame(parent, bg="#f8fafc", highlightbackground="#e2e8f0", highlightthickness=1, padx=12, pady=12)
        gal_card.pack(fill=tk.X, pady=(0, 12))

        tk.Label(
            gal_card,
            text="Selected Picture Folder or Image File(s):",
            font=("Segoe UI", 8, "bold"),
            bg="#f8fafc",
            fg="#475569",
        ).pack(anchor="w", pady=(0, 4))

        path_row = tk.Frame(gal_card, bg="#f8fafc")
        path_row.pack(fill=tk.X, pady=(0, 10))

        self.gal_folder_var = tk.StringVar(value=self.engine.gallery_folder)
        self.gal_entry = tk.Entry(
            path_row,
            textvariable=self.gal_folder_var,
            font=("Segoe UI", 9),
            bg="#ffffff",
            fg="#0f172a",
            relief=tk.SOLID,
            bd=1,
        )
        self.gal_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=4, padx=(0, 6))

        self._make_btn(path_row, "📁 Select Folder...", self.on_pick_gallery_folder, "secondary", padx=10, pady=4).pack(
            side=tk.LEFT, padx=(0, 6)
        )
        self._make_btn(path_row, "🖼 Select Picture(s)...", self.on_pick_gallery_files, "secondary", padx=10, pady=4).pack(
            side=tk.LEFT
        )

        opt_row = tk.Frame(gal_card, bg="#f8fafc")
        opt_row.pack(fill=tk.X, pady=(0, 10))

        tk.Label(
            opt_row,
            text="Slide Interval (Seconds):",
            font=("Segoe UI", 9, "bold"),
            bg="#f8fafc",
            fg="#334155",
        ).pack(side=tk.LEFT)

        self.gal_timer_spin = tk.Spinbox(
            opt_row,
            from_=1,
            to=3600,
            width=5,
            font=("Segoe UI", 9, "bold"),
            bg="#ffffff",
            fg="#0f172a",
            relief=tk.SOLID,
            bd=1,
        )
        self.gal_timer_spin.delete(0, tk.END)
        self.gal_timer_spin.insert(0, str(self.engine.gallery_interval))
        self.gal_timer_spin.pack(side=tk.LEFT, ipady=2, padx=(6, 16))

        self.gal_shuffle_var = tk.BooleanVar(value=self.engine.gallery_shuffle)
        tk.Checkbutton(
            opt_row,
            text="⇄  Shuffle Photos",
            variable=self.gal_shuffle_var,
            font=("Segoe UI", 9, "bold"),
            bg="#f8fafc",
            fg="#0f172a",
            selectcolor="#ffffff",
            activebackground="#f8fafc",
        ).pack(side=tk.LEFT, padx=(0, 14))

        self.gal_transition_var = tk.BooleanVar(value=self.engine.gallery_transition)
        tk.Checkbutton(
            opt_row,
            text="✨ Smooth Crossfade",
            variable=self.gal_transition_var,
            font=("Segoe UI", 9, "bold"),
            bg="#f8fafc",
            fg="#0f172a",
            selectcolor="#ffffff",
            activebackground="#f8fafc",
            command=self.on_gallery_options_change,
        ).pack(side=tk.LEFT)

        ctl_row = tk.Frame(gal_card, bg="#f8fafc")
        ctl_row.pack(fill=tk.X)

        self._make_btn(
            ctl_row,
            "▶  Start Photo Slideshow",
            self.on_start_gallery_slideshow,
            "primary",
            padx=16,
            pady=6,
        ).pack(side=tk.LEFT, padx=(0, 8))

        self._make_btn(
            ctl_row,
            "◁ Previous Slide",
            lambda: self.engine.step_gallery_slide(-1),
            "secondary",
            padx=12,
            pady=6,
        ).pack(side=tk.LEFT, padx=(0, 6))

        self._make_btn(
            ctl_row,
            "Next Slide ▷",
            lambda: self.engine.step_gallery_slide(1),
            "secondary",
            padx=12,
            pady=6,
        ).pack(side=tk.LEFT)

        self.gal_status_lbl = tk.Label(
            parent,
            text="No active slideshow. Select a folder or picture files above to begin.",
            font=("Segoe UI", 9, "bold"),
            bg="#ffffff",
            fg="#475569",
            anchor="w",
        )
        self.gal_status_lbl.pack(fill=tk.X, pady=(4, 0))

    # -------------------------------------------------------------------------
    # TAB 4: SCREEN SHARE & CHROME EXTENSION
    # -------------------------------------------------------------------------
    def _build_tab_monitors(self, parent: tk.Frame):
        tk.Label(
            parent,
            text="MULTI-MONITOR PC DESKTOP MIRRORING & BROWSER CASTING",
            font=("Segoe UI", 10, "bold"),
            bg="#ffffff",
            fg="#0f172a",
        ).pack(anchor="w", pady=(0, 4))

        tk.Label(
            parent,
            text="Mirror one or more physical PC monitors (with live speaker audio) or stream directly from Google Chrome.",
            font=("Segoe UI", 8),
            bg="#ffffff",
            fg="#64748b",
        ).pack(anchor="w", pady=(0, 10))

        mon_box = tk.Frame(parent, bg="#f8fafc", highlightbackground="#e2e8f0", highlightthickness=1, padx=12, pady=12)
        mon_box.pack(fill=tk.X, pady=(0, 12))

        tk.Label(
            mon_box,
            text="1. Select Physical Display(s) to Mirror:",
            font=("Segoe UI", 9, "bold"),
            bg="#f8fafc",
            fg="#0f172a",
        ).pack(anchor="w", pady=(0, 8))

        chk_row = tk.Frame(mon_box, bg="#f8fafc")
        chk_row.pack(fill=tk.X, pady=(0, 10))

        for m in self.engine.monitors_info:
            if m["index"] == 0:
                continue
            var = tk.BooleanVar(value=(m["index"] in self.engine.selected_monitors))
            self.mon_vars[m["index"]] = var
            cb = tk.Checkbutton(
                chk_row,
                text=m["label"],
                variable=var,
                font=("Segoe UI", 9, "bold"),
                bg="#ffffff",
                fg="#0f172a",
                selectcolor="#ffffff",
                activebackground="#f1f5f9",
                padx=10,
                pady=4,
                relief=tk.SOLID,
                bd=1,
                command=self.on_monitor_selection_change,
            )
            cb.pack(side=tk.LEFT, padx=(0, 8))

        self._make_btn(chk_row, "Select All Displays", self.select_all_monitors, "secondary", padx=10, pady=4).pack(
            side=tk.LEFT
        )

        opt_row = tk.Frame(mon_box, bg="#f8fafc")
        opt_row.pack(fill=tk.X, pady=(0, 10))

        self.pc_audio_var = tk.BooleanVar(value=self.engine.capture_pc_audio)
        tk.Checkbutton(
            opt_row,
            text="🔊 Stream PC Speaker Audio (WASAPI Loopback)",
            variable=self.pc_audio_var,
            font=("Segoe UI", 9, "bold"),
            bg="#f8fafc",
            fg="#334155",
            selectcolor="#ffffff",
            command=self.on_settings_change,
        ).pack(side=tk.LEFT, padx=(0, 16))

        self.cursor_var = tk.BooleanVar(value=self.engine.show_cursor)
        tk.Checkbutton(
            opt_row,
            text="🖱 Show Mouse Pointer",
            variable=self.cursor_var,
            font=("Segoe UI", 9, "bold"),
            bg="#f8fafc",
            fg="#334155",
            selectcolor="#ffffff",
            command=self.on_settings_change,
        ).pack(side=tk.LEFT)

        self._make_btn(
            mon_box,
            "▶  Start Desktop Screen Share",
            self.on_start_desktop_mirror,
            "primary",
            padx=16,
            pady=6,
        ).pack(anchor="w")

        web_box = tk.Frame(parent, bg="#f8fafc", highlightbackground="#e2e8f0", highlightthickness=1, padx=12, pady=12)
        web_box.pack(fill=tk.X)

        tk.Label(
            web_box,
            text="2. Browser Tab / Window Share & Chrome Extension Live Video Cast:",
            font=("Segoe UI", 9, "bold"),
            bg="#f8fafc",
            fg="#0f172a",
        ).pack(anchor="w", pady=(0, 6))

        tk.Label(
            web_box,
            text="• Share a browser tab or application window with audio, or use the Chrome Extension on any video player.",
            font=("Segoe UI", 8),
            bg="#f8fafc",
            fg="#475569",
            justify=tk.LEFT,
            wraplength=600,
        ).pack(anchor="w", pady=(0, 8))

        self._make_btn(
            web_box,
            "🌐 Share Browser Tab / Window + Audio ↗",
            lambda: os.startfile(f"http://localhost:{self.engine.web_port}/?autoshare=1"),
            "accent",
            padx=14,
            pady=6,
        ).pack(anchor="w")

    # -------------------------------------------------------------------------
    # TAB 5: CONFIG, VLC SETUP, IMPORT/EXPORT & STREAM QUALITY SETTINGS
    # -------------------------------------------------------------------------
    def _build_tab_settings(self, parent: tk.Frame):
        tk.Label(
            parent,
            text="CONFIGURATION FILES, VLC PLAYLIST SETUP & STREAM QUALITY",
            font=("Segoe UI", 10, "bold"),
            bg="#ffffff",
            fg="#0f172a",
        ).pack(anchor="w", pady=(0, 6))

        # 1. Default Config & VLC Playlist Manager Card
        cfg_card = tk.Frame(parent, bg="#f8fafc", highlightbackground="#cbd5e1", highlightthickness=1, padx=12, pady=10)
        cfg_card.pack(fill=tk.X, pady=(0, 10))

        tk.Label(
            cfg_card,
            text="DEFAULT VLC PLAYLIST (.M3U) & PERSISTENT CHANNEL CONFIGURATION (.JSON)",
            font=("Segoe UI", 9, "bold"),
            bg="#f8fafc",
            fg="#1d4ed8",
        ).pack(anchor="w", pady=(0, 4))

        tk.Label(
            cfg_card,
            text=f"• VLC M3U Playlist:  {DEFAULT_VLC_M3U_PATH}\n• App Config JSON:  {CONFIG_JSON_PATH}",
            font=("Consolas", 8),
            bg="#f8fafc",
            fg="#334155",
            justify=tk.LEFT,
        ).pack(anchor="w", pady=(0, 8))

        cfg_btns = tk.Frame(cfg_card, bg="#f8fafc")
        cfg_btns.pack(fill=tk.X)

        self._make_btn(
            cfg_btns,
            "🎬 Open Playlist in VLC",
            lambda: self.engine.open_in_vlc(DEFAULT_VLC_M3U_PATH),
            "primary",
            padx=10,
            pady=5,
            font_size=8,
        ).pack(side=tk.LEFT, padx=(0, 6))

        self._make_btn(
            cfg_btns,
            "📥 Import .M3U / .JSON",
            self.on_import_channels_dialog,
            "accent",
            padx=10,
            pady=5,
            font_size=8,
        ).pack(side=tk.LEFT, padx=(0, 6))

        self._make_btn(
            cfg_btns,
            "📤 Export VLC .M3U...",
            self.on_export_vlc_m3u_dialog,
            "secondary",
            padx=10,
            pady=5,
            font_size=8,
        ).pack(side=tk.LEFT, padx=(0, 6))

        self._make_btn(
            cfg_btns,
            "📤 Export Config .JSON...",
            self.on_export_config_json_dialog,
            "secondary",
            padx=10,
            pady=5,
            font_size=8,
        ).pack(side=tk.LEFT, padx=(0, 6))

        self._make_btn(
            cfg_btns,
            "📂 Open Config Folder",
            lambda: os.startfile(CONFIG_DIR),
            "secondary",
            padx=10,
            pady=5,
            font_size=8,
        ).pack(side=tk.LEFT, padx=(0, 6))

        self._make_btn(
            cfg_btns,
            "↺ Reset Defaults",
            self.on_reset_default_channels,
            "warning",
            padx=10,
            pady=5,
            font_size=8,
        ).pack(side=tk.LEFT)

        # 2. Stream Encoding Settings Card
        s_card = tk.Frame(parent, bg="#f8fafc", highlightbackground="#e2e8f0", highlightthickness=1, padx=12, pady=10)
        s_card.pack(fill=tk.X, pady=(0, 10))

        r1 = tk.Frame(s_card, bg="#f8fafc")
        r1.pack(fill=tk.X, pady=(0, 6))

        tk.Label(r1, text="Main Resolution:", font=("Segoe UI", 9, "bold"), bg="#f8fafc", fg="#334155").pack(side=tk.LEFT)
        self.res_combo = ttk.Combobox(
            r1,
            values=["1280x720", "1920x1080", "854x480"],
            width=11,
            state="readonly",
        )
        self.res_combo.set(self.engine.main_res)
        self.res_combo.pack(side=tk.LEFT, padx=(6, 16))
        self.res_combo.bind("<<ComboboxSelected>>", self.on_settings_change)

        tk.Label(r1, text="Aspect Fit:", font=("Segoe UI", 9, "bold"), bg="#f8fafc", fg="#334155").pack(side=tk.LEFT)
        self.aspect_combo = ttk.Combobox(
            r1,
            values=["fit (Letterbox)", "stretch (Fill 16:9)", "crop (Center 16:9)"],
            width=17,
            state="readonly",
        )
        self.aspect_combo.set("fit (Letterbox)")
        self.aspect_combo.pack(side=tk.LEFT, padx=(6, 16))
        self.aspect_combo.bind("<<ComboboxSelected>>", self.on_settings_change)

        tk.Label(r1, text="Frame Rate:", font=("Segoe UI", 9, "bold"), bg="#f8fafc", fg="#334155").pack(side=tk.LEFT)
        self.fps_combo = ttk.Combobox(
            r1,
            values=["25", "30", "15"],
            width=5,
            state="readonly",
        )
        self.fps_combo.set(str(self.engine.fps))
        self.fps_combo.pack(side=tk.LEFT, padx=(6, 0))
        self.fps_combo.bind("<<ComboboxSelected>>", self.on_settings_change)

        r2 = tk.Frame(s_card, bg="#f8fafc")
        r2.pack(fill=tk.X)

        tk.Label(r2, text="Video Bitrate:", font=("Segoe UI", 9, "bold"), bg="#f8fafc", fg="#334155").pack(side=tk.LEFT)
        self.bitrate_combo = ttk.Combobox(
            r2,
            values=["1000k", "1800k", "2500k", "4000k"],
            width=9,
            state="readonly",
        )
        self.bitrate_combo.set(self.engine.video_bitrate)
        self.bitrate_combo.pack(side=tk.LEFT, padx=(6, 16))
        self.bitrate_combo.bind("<<ComboboxSelected>>", self.on_settings_change)

        tk.Label(r2, text="RTSP Audio Format:", font=("Segoe UI", 9, "bold"), bg="#f8fafc", fg="#334155").pack(side=tk.LEFT)
        self.audio_combo = ttk.Combobox(
            r2,
            values=[
                "pcm_mulaw (G.711u Standard)",
                "pcm_alaw (G.711a Standard)",
                "aac (16kHz Mono)",
                "aac_hq (44.1kHz Stereo)",
                "none (Mute RTSP)",
            ],
            width=25,
            state="readonly",
        )
        self.audio_combo.set("pcm_mulaw (G.711u Standard)")
        self.audio_combo.pack(side=tk.LEFT, padx=(6, 0))
        self.audio_combo.bind("<<ComboboxSelected>>", self.on_settings_change)

        # 3. System Activity Log
        log_hdr = tk.Frame(parent, bg="#ffffff")
        log_hdr.pack(fill=tk.X, pady=(0, 4))

        tk.Label(
            log_hdr,
            text="SYSTEM & STREAM ACTIVITY LOG",
            font=("Segoe UI", 8, "bold"),
            bg="#ffffff",
            fg="#64748b",
        ).pack(side=tk.LEFT)

        self._make_btn(
            log_hdr,
            "Clear Log",
            self.on_clear_log,
            "secondary",
            padx=8,
            pady=2,
            font_size=8,
        ).pack(side=tk.RIGHT)

        self.log_text = tk.Text(
            parent,
            bg="#0f172a",
            fg="#e2e8f0",
            font=("Consolas", 9),
            relief=tk.SOLID,
            bd=1,
            padx=8,
            pady=6,
            state=tk.DISABLED,
        )
        self.log_text.pack(fill=tk.BOTH, expand=True)

    # =========================================================================
    # REAL-TIME PREVIEW RENDERER & STREAM HEALTH DIAGNOSTIC ENGINE (140ms TICK)
    # =========================================================================
    def _render_fitted_frame_on_canvas(self, canvas: tk.Canvas, pil_im, bg_hex: str = "#000000"):
        cw = max(64, canvas.winfo_width())
        ch = max(48, canvas.winfo_height())
        iw, ih = pil_im.size
        scale = min(cw / float(iw), ch / float(ih))
        tw = max(1, int(iw * scale))
        th = max(1, int(ih * scale))
        resized = pil_im.resize((tw, th), Image.Resampling.BILINEAR) if (tw, th) != (iw, ih) else pil_im
        photo = ImageTk.PhotoImage(resized)
        canvas.delete("all")
        ox = (cw - tw) // 2
        oy = (ch - th) // 2
        canvas.create_image(ox, oy, anchor=tk.NW, image=photo)
        return photo

    def _preview_and_telemetry_tick(self):
        try:
            pip_alive = self.pip_win is not None and self.pip_win.winfo_exists() and self.pip_canvas is not None
            fs_alive = self.fs_win is not None and self.fs_win.winfo_exists() and self.fs_canvas is not None

            # 1. Update Live 16:9 (640x360) Preview Canvas + Floating PiP + Full-Screen TV Player
            if self.engine.preview_enabled and Image is not None and ImageTk is not None:
                jpg_bytes = self.engine.get_preview_jpeg()
                pip_size = (self.pip_canvas.winfo_width(), self.pip_canvas.winfo_height()) if pip_alive else (0, 0)
                fs_size = (self.fs_canvas.winfo_width(), self.fs_canvas.winfo_height()) if fs_alive else (0, 0)
                need_redraw = (
                    (jpg_bytes and jpg_bytes is not self._last_preview_bytes)
                    or (pip_alive and pip_size != self._pip_last_size)
                    or (fs_alive and fs_size != self._fs_last_size)
                )
                if jpg_bytes and need_redraw:
                    self._last_preview_bytes = jpg_bytes
                    self._pip_last_size = pip_size
                    self._fs_last_size = fs_size
                    with Image.open(io.BytesIO(jpg_bytes)) as src_im:
                        im_rgb = src_im.convert("RGB")
                        # Main Studio 640x360 canvas
                        main_im = (
                            im_rgb.resize((self.PREVIEW_W, self.PREVIEW_H), Image.Resampling.BILINEAR)
                            if im_rgb.size != (self.PREVIEW_W, self.PREVIEW_H)
                            else im_rgb
                        )
                        self._preview_photo = ImageTk.PhotoImage(main_im)
                        self.preview_canvas.delete("all")
                        self.preview_canvas.create_image(0, 0, anchor=tk.NW, image=self._preview_photo)

                        # Floating PiP Mini-Player canvas
                        if pip_alive:
                            self.pip_photo = self._render_fitted_frame_on_canvas(self.pip_canvas, im_rgb)

                        # Full-Screen TV Player canvas
                        if fs_alive:
                            self.fs_photo = self._render_fitted_frame_on_canvas(self.fs_canvas, im_rgb)

            # Sync PiP & Full-Screen titles and pause buttons
            if pip_alive:
                if self.pip_title_lbl:
                    self.pip_title_lbl.configure(text=self.engine.current_title)
                if self.pip_pause_btn:
                    self.pip_pause_btn.configure(text="▶" if self.engine.is_paused else "❚❚")
            if fs_alive:
                if self.fs_title_lbl:
                    self.fs_title_lbl.configure(text=self.engine.current_title)
                if self.fs_pause_btn:
                    self.fs_pause_btn.configure(text="▶ Resume" if self.engine.is_paused else "❚❚ Pause")

            # 2. Update Stream Health & Failure Diagnostic Banner
            d = self.engine.get_status_dict()
            h = d.get("health", {})
            h_state = h.get("state", "STANDBY")
            h_diag = h.get("diag", "")
            h_err = h.get("error_msg", "")
            frames = h.get("decoded_frames", 0)
            out_mode = d.get("output_mode", "both")

            mode_desc = {
                "local_only": "Watch Here in App Only (No NVR)",
                "nvr_only": f"Casting to NVR Only (rtsp://{d['lan_ip']}:{self.engine.rtsp_port}/main)",
                "both": f"Watching in App + Casting to NVR (rtsp://{d['lan_ip']}:{self.engine.rtsp_port}/main)",
            }.get(out_mode, "Both")

            if h_state == "ERROR":
                self._style_health_banner(
                    bg="#fef2f2",
                    border="#fca5a5",
                    badge_bg="#dc2626",
                    badge_txt=" ✖ STREAM FAILED / OFFLINE ",
                    title_fg="#991b1b",
                    title_txt=f"Stream Failed: {d.get('title', '').replace('✖ FAILED: ', '').replace('✖ OFFLINE: ', '')[:52]}",
                    detail_fg="#b91c1c",
                    detail_txt=h_err or h_diag or "Channel or video link could not be decoded. Try another channel or click Test Link.",
                )
            elif h_state == "PROBING":
                self._style_health_banner(
                    bg="#eff6ff",
                    border="#93c5fd",
                    badge_bg="#2563eb",
                    badge_txt=" ◌ PROBING LINK ",
                    title_fg="#1e40af",
                    title_txt=h_diag or "Verifying server & resolving stream URL...",
                    detail_fg="#1d4ed8",
                    detail_txt=f"Target: {d.get('current_url', '')[:82]}",
                )
            elif h_state == "CONNECTING":
                self._style_health_banner(
                    bg="#fffbeb",
                    border="#fcd34d",
                    badge_bg="#d97706",
                    badge_txt=" ◔ BUFFERING VIDEO ",
                    title_fg="#92400e",
                    title_txt=h_diag or "Connected to server — decoding first video frame...",
                    detail_fg="#b45309",
                    detail_txt=f"Output Mode: {mode_desc}",
                )
            elif h_state == "STALLED":
                self._style_health_banner(
                    bg="#fffbeb",
                    border="#fbbf24",
                    badge_bg="#b45309",
                    badge_txt=" ⚠ STREAM STALLED ",
                    title_fg="#92400e",
                    title_txt=h_diag or "Stream waiting for new packets from remote server...",
                    detail_fg="#b45309",
                    detail_txt=f"Decoded {frames} frames so far. Reconnecting or switch to next channel.",
                )
            elif h_state == "PAUSED":
                self._style_health_banner(
                    bg="#fffbeb",
                    border="#fde68a",
                    badge_bg="#d97706",
                    badge_txt=" ❚❚ PAUSED ",
                    title_fg="#92400e",
                    title_txt=h_diag or "Stream Paused",
                    detail_fg="#b45309",
                    detail_txt="Click '▶ Resume' below to continue playing.",
                )
            elif h_state == "LIVE":
                badge_lbl = " ● PLAYING IN APP " if out_mode == "local_only" else " ● LIVE STREAMING "
                self._style_health_banner(
                    bg="#ecfdf5",
                    border="#6ee7b7",
                    badge_bg="#059669",
                    badge_txt=badge_lbl,
                    title_fg="#065f46",
                    title_txt=h_diag or f"Playing Live • Frame #{frames}",
                    detail_fg="#047857",
                    detail_txt=mode_desc,
                )
            else:
                self._style_health_banner(
                    bg="#f0fdf4",
                    border="#bbf7d0",
                    badge_bg="#16a34a",
                    badge_txt=" ● READY ",
                    title_fg="#166534",
                    title_txt=f"Ready • {mode_desc}",
                    detail_fg="#15803d",
                    detail_txt="Double-click any Pakistani TV channel, Cricket stream, YouTube video, or Photo Slideshow on the right.",
                )

            # 3. Update Elapsed Time / Playlist / Gallery Counter
            mode = d.get("mode", "STANDBY")
            pl = d.get("playlist", {})
            pl_tag = f"[{pl.get('index', 0) + 1}/{pl.get('count', 1)}] " if pl.get("count", 0) > 1 else ""

            if mode in ("YOUTUBE", "FILE", "BROWSER"):
                sec = d.get("playback_sec", 0)
                m, s = divmod(sec, 60)
                self.pos_label.configure(text=f"{pl_tag}{m:02d}:{s:02d}{' • LOOP' if d.get('loop_video') else ''}")
            elif mode == "GALLERY":
                gal = d.get("gallery", {})
                self.pos_label.configure(
                    text=f"Slide {gal.get('index', 0) + 1}/{gal.get('count', 1)} ({gal.get('interval', 5)}s)"
                )
                self.gal_status_lbl.configure(
                    text=f"● Active Gallery: Slide {gal.get('index', 0) + 1} of {gal.get('count', 1)}  •  {gal.get('current_file', '')}"
                )
            else:
                self.pos_label.configure(text=pl_tag)

            self.pause_btn.configure(text="▶ Resume" if d.get("is_paused") else "❚❚ Pause")
            self.source_label.configure(text=f"Source: {d.get('active_source', 'System')}")

            st = d.get("settings", {})
            self.telemetry_lbl.configure(
                text=f"Mode: {out_mode.upper()}  •  {st.get('main_res')} @ {st.get('fps')}fps ({st.get('video_bitrate')})  •  App Audio: {'ON' if d.get('local_audio_enabled') else 'Muted'}"
            )

            self._sync_playlist_tree_if_needed()
        except Exception:
            pass

        self.root.after(200, self._preview_and_telemetry_tick)

    def _style_health_banner(
        self,
        bg: str,
        border: str,
        badge_bg: str,
        badge_txt: str,
        title_fg: str,
        title_txt: str,
        detail_fg: str,
        detail_txt: str,
    ):
        self.health_frame.configure(bg=bg, highlightbackground=border)
        self.health_top.configure(bg=bg)
        self.health_badge.configure(bg=badge_bg, text=badge_txt)
        self.health_title_lbl.configure(bg=bg, fg=title_fg, text=title_txt)
        self.health_detail_lbl.configure(bg=bg, fg=detail_fg, text=detail_txt)

    # =========================================================================
    # CHANNELS, ADD/REMOVE, IMPORT/EXPORT & VLC HANDLERS
    # =========================================================================
    def on_toggle_auto_skip(self):
        self.engine.auto_skip_offline = bool(self.auto_skip_var.get())
        self.engine.save_persistent_config()
        self.engine.log(f"Auto-Skip Offline Channels set to: {self.engine.auto_skip_offline}")

    def on_quick_select_tv_cat(self, cat_id: str):
        for idx, (cid, _) in enumerate(self.tv_source_options):
            if cid == cat_id:
                self.tv_source_combo.current(idx)
                break
        self.tv_filter_entry.delete(0, tk.END)
        self.on_load_tv_source(auto_play=False)

    def on_add_custom_channel(self):
        title = self.add_ch_title_entry.get().strip()
        url = self.add_ch_url_entry.get().strip()
        if not url or url.startswith("Stream URL"):
            messagebox.showwarning("Channel URL Required", "Please enter or paste a valid stream URL (.m3u8, YouTube, RTSP, or HTTP).")
            return
        if not title or title == "Channel Name":
            title = url.split("/")[-1].split("?")[0] or "Custom Channel"

        sel_idx = self.tv_source_combo.current()
        cur_cat = self.tv_source_options[sel_idx][0] if 0 <= sel_idx < len(self.tv_source_options) else "pakistan_tv"
        target_cat = cur_cat if cur_cat in ("pakistan_tv", "cricket_pk", "youtube_cricket", "global_sports", "custom_channels") else "pakistan_tv"
        group_label = "Pakistan TV" if target_cat == "pakistan_tv" else "Custom Live TV"

        res = self.engine.add_channel(title=title, url=url, group=group_label, category=target_cat)
        if res.get("ok"):
            self.add_ch_title_entry.delete(0, tk.END)
            self.add_ch_title_entry.insert(0, "Channel Name")
            self.add_ch_url_entry.delete(0, tk.END)
            self.add_ch_url_entry.insert(0, "Stream URL (.m3u8, YouTube, RTSP, HTTP)")
            self._refresh_tv_channel_tree()

    def on_remove_selected_tv_channel(self):
        idx = self._get_selected_tv_index()
        chs = self.engine.tv_channels or []
        if not (0 <= idx < len(chs)):
            return
        ch = chs[idx]
        self.engine.remove_channel(index=idx, url=ch.get("url", ""))
        self._refresh_tv_channel_tree()

    def on_open_selected_tv_in_vlc(self):
        idx = self._get_selected_tv_index()
        chs = self.engine.tv_channels or []
        if 0 <= idx < len(chs):
            self.engine.open_in_vlc(chs[idx].get("url", ""))
        else:
            self.engine.open_in_vlc(DEFAULT_VLC_M3U_PATH)

    def on_import_channels_dialog(self):
        path = filedialog.askopenfilename(
            title="Import Channels or Configuration (.m3u, .m3u8, .json)",
            filetypes=[
                ("Playlist & Config Files", "*.m3u *.m3u8 *.json"),
                ("VLC M3U Playlists", "*.m3u *.m3u8"),
                ("JSON Configuration", "*.json"),
                ("All Files", "*.*"),
            ],
        )
        if not path:
            return
        res = self.engine.import_config_or_m3u(path, target_category="pakistan_tv")
        if res.get("ok"):
            self._refresh_tv_channel_tree()
            self._refresh_output_mode_buttons()
            messagebox.showinfo(
                "Import Successful",
                f"Imported {res.get('imported', 0)} item(s) from:\n{path}\n\n"
                f"Updated default VLC playlist:\n{DEFAULT_VLC_M3U_PATH}",
            )
        else:
            messagebox.showerror("Import Failed", res.get("message", "Could not import file."))

    def on_export_vlc_m3u_dialog(self):
        path = filedialog.asksaveasfilename(
            title="Export Channels as VLC Playlist (.m3u)",
            initialdir=CONFIG_DIR,
            initialfile="NVR_Cast_Hub_Channels_VLC.m3u",
            defaultextension=".m3u",
            filetypes=[("VLC M3U Playlist", "*.m3u"), ("All Files", "*.*")],
        )
        if not path:
            return
        out = self.engine.export_vlc_m3u(path)
        if out:
            messagebox.showinfo("Exported VLC Playlist", f"Saved VLC .m3u playlist to:\n{out}")

    def on_export_config_json_dialog(self):
        path = filedialog.asksaveasfilename(
            title="Export Full Configuration & Channels (.json)",
            initialdir=CONFIG_DIR,
            initialfile="nvr_cast_config.json",
            defaultextension=".json",
            filetypes=[("JSON Configuration", "*.json"), ("All Files", "*.*")],
        )
        if not path:
            return
        out = self.engine.save_persistent_config(path)
        if out:
            messagebox.showinfo("Exported Configuration", f"Saved JSON configuration to:\n{out}")

    def on_reset_default_channels(self):
        if messagebox.askyesno(
            "Reset Default Channels",
            "Restore all default Pakistani TV, Live Cricket, and Sports channels and regenerate the default VLC .m3u file?",
        ):
            self.engine.reset_default_channels()
            self._refresh_tv_channel_tree()

    def _refresh_tv_channel_tree(self):
        chs = self.engine.tv_channels or []
        for item in self.tv_tree.get_children():
            self.tv_tree.delete(item)

        for i, ch in enumerate(chs):
            url = ch.get("url", "")
            low_u = url.lower()
            cached_st = self._tv_status_cache.get(url)
            if cached_st:
                st_txt = cached_st
            elif "youtube.com" in low_u or "youtu.be" in low_u:
                st_txt = "▶ YouTube Live/Auto"
            elif ".m3u8" in low_u:
                st_txt = "● HLS Live Stream"
            else:
                st_txt = "● Direct Live Stream"

            iid = str(i)
            self.tv_tree.insert(
                "",
                tk.END,
                iid=iid,
                values=(i + 1, ch.get("title", f"Channel #{i + 1}"), ch.get("group", "Live TV"), st_txt),
            )

        if chs:
            active_idx = min(max(0, self.engine.tv_active_index), len(chs) - 1)
            sel_id = str(active_idx)
            if self.tv_tree.exists(sel_id):
                self.tv_tree.selection_set(sel_id)
                self.tv_tree.see(sel_id)

        self.tv_count_lbl.configure(text=f"{len(chs)} Channels")

    def on_load_tv_source(self, auto_play: bool = False):
        sel_idx = self.tv_source_combo.current()
        source_id = self.tv_source_options[sel_idx][0] if 0 <= sel_idx < len(self.tv_source_options) else "cricket_pk"
        raw_input = self.tv_filter_entry.get().strip()

        if raw_input.lower().startswith(("http://", "https://")) or raw_input.lower().endswith((".m3u", ".m3u8")):
            target = raw_input
            filter_kw = ""
        else:
            target = source_id
            filter_kw = raw_input

        def _bg():
            self.engine.load_tv_category_or_m3u(
                target,
                filter_keyword=filter_kw,
                auto_play=auto_play,
                source="Desktop App Live TV",
            )
            self.root.after(0, self._refresh_tv_channel_tree)

        threading.Thread(target=_bg, daemon=True).start()

    def _get_selected_tv_index(self) -> int:
        sel = self.tv_tree.selection()
        if sel:
            try:
                return int(sel[0])
            except Exception:
                pass
        return max(0, self.engine.tv_active_index)

    def on_play_selected_tv_channel(self):
        idx = self._get_selected_tv_index()
        self.engine.play_tv_channel(index=idx, source="Desktop App Live TV")

    def on_test_selected_tv_channel(self):
        idx = self._get_selected_tv_index()
        chs = self.engine.tv_channels or []
        if not (0 <= idx < len(chs)):
            return
        ch = chs[idx]
        url = ch.get("url", "")
        title = ch.get("title", "Channel")
        ref = ch.get("referrer", "")

        self._tv_status_cache[url] = "◌ Testing..."
        self._refresh_tv_channel_tree()

        def _test_bg():
            res = self.engine.test_channel_link(url=url, title=title, referrer=ref)
            if res.get("ok"):
                self._tv_status_cache[url] = f"✓ ONLINE ({res.get('latency_ms', 0)}ms)"
            else:
                self._tv_status_cache[url] = "✖ OFFLINE / TIMEOUT"
            self.root.after(0, self._refresh_tv_channel_tree)

        threading.Thread(target=_test_bg, daemon=True).start()

    # =========================================================================
    # YOUTUBE, PLAYLIST & LOCAL VIDEO HANDLERS
    # =========================================================================
    def _sync_playlist_tree_if_needed(self):
        items = self.engine.playlist_items or []
        cur_children = self.pl_tree.get_children()
        sig = (len(items), self.engine.playlist_title, items[0]["url"] if items else "")
        if getattr(self, "_last_pl_sig", None) != sig:
            self._last_pl_sig = sig
            for c in cur_children:
                self.pl_tree.delete(c)
            for i, it in enumerate(items):
                self.pl_tree.insert(
                    "",
                    tk.END,
                    iid=str(i),
                    values=(i + 1, it.get("title", f"Track #{i + 1}"), it.get("url", "")),
                )
            if items:
                self.pl_title_lbl.configure(
                    text=f"ACTIVE QUEUE: {self.engine.playlist_title} ({len(items)} items — Double-click to jump)"
                )
            else:
                self.pl_title_lbl.configure(
                    text="ACTIVE PLAYLIST / CHANNEL QUEUE (Load any YouTube Playlist or TV Category)"
                )

        if items and 0 <= self.engine.playlist_index < len(items):
            sid = str(self.engine.playlist_index)
            if self.pl_tree.exists(sid) and self.pl_tree.selection() != (sid,):
                self.pl_tree.selection_set(sid)
                self.pl_tree.see(sid)

    def on_jump_playlist_item(self):
        sel = self.pl_tree.selection()
        if not sel:
            return
        try:
            idx = int(sel[0])
        except Exception:
            return
        items = self.engine.playlist_items or []
        if 0 <= idx < len(items):
            self.engine.playlist_index = idx
            if len(items) == len(self.engine.tv_channels):
                self.engine.tv_active_index = idx
            target = items[idx]
            self.engine.start_youtube_stream(
                target["url"],
                start_sec=0,
                loop=self.engine.loop_video,
                source="Desktop App Queue",
                _from_playlist=True,
                custom_title=target.get("title", ""),
            )

    def on_stream_youtube(self):
        val = self.yt_entry.get().strip()
        if not val:
            messagebox.showwarning("Input Required", "Please paste a YouTube URL, playlist link, or search query.")
            return
        if os.path.isfile(val):
            self.engine.start_local_file_stream(val, loop=self.loop_video_var.get(), source="Desktop App")
        else:
            self.engine.start_youtube_stream(val, loop=self.loop_video_var.get(), source="Desktop App")

    def on_stream_file(self):
        filepath = filedialog.askopenfilename(
            title="Select Video File",
            filetypes=[("Video Files", "*.mp4 *.mkv *.avi *.mov *.ts *.webm"), ("All Files", "*.*")],
        )
        if filepath:
            self.yt_entry.delete(0, tk.END)
            self.yt_entry.insert(0, filepath)
            self.engine.start_local_file_stream(filepath, loop=self.loop_video_var.get(), source="Desktop App")

    # =========================================================================
    # PHOTO GALLERY & SLIDESHOW HANDLERS
    # =========================================================================
    def on_gallery_options_change(self):
        self.engine.gallery_transition = bool(self.gal_transition_var.get())

    def on_pick_gallery_folder(self):
        folder = filedialog.askdirectory(title="Select Picture Folder for Slideshow")
        if folder:
            self.gal_folder_var.set(folder)
            self.on_start_gallery_slideshow()

    def on_pick_gallery_files(self):
        files = filedialog.askopenfilenames(
            title="Select Picture(s) for Slideshow",
            filetypes=[("Image Files", "*.jpg *.jpeg *.png *.bmp *.webp *.gif"), ("All Files", "*.*")],
        )
        if files:
            file_list = list(files)
            self.gal_folder_var.set(";".join(file_list) if len(file_list) > 1 else file_list[0])
            try:
                timer_s = int(self.gal_timer_spin.get() or 5)
            except Exception:
                timer_s = 5
            self.engine.gallery_transition = bool(self.gal_transition_var.get())
            self.engine.start_gallery_slideshow(
                file_list,
                interval_sec=timer_s,
                shuffle=self.gal_shuffle_var.get(),
                source="Desktop App Gallery",
            )

    def on_start_gallery_slideshow(self):
        folder = self.gal_folder_var.get().strip()
        if not folder:
            folder = filedialog.askdirectory(title="Select Picture Folder for Slideshow")
            if not folder:
                return
            self.gal_folder_var.set(folder)
        try:
            timer_s = int(self.gal_timer_spin.get() or 5)
        except Exception:
            timer_s = 5
        self.engine.gallery_transition = bool(self.gal_transition_var.get())
        self.engine.start_gallery_slideshow(
            folder,
            interval_sec=timer_s,
            shuffle=self.gal_shuffle_var.get(),
            source="Desktop App Gallery",
        )

    # =========================================================================
    # PC MONITORS & SETTINGS HANDLERS
    # =========================================================================
    def select_all_monitors(self):
        for var in self.mon_vars.values():
            var.set(True)
        self.on_monitor_selection_change()

    def on_monitor_selection_change(self):
        chosen = [idx for idx, var in self.mon_vars.items() if var.get()]
        if not chosen:
            chosen = [1]
            if 1 in self.mon_vars:
                self.mon_vars[1].set(True)
        self.engine.selected_monitors = chosen
        _, _, w, h, desc = self.engine.compute_monitor_region(chosen)
        self.engine.log(f"Selected Monitor Target: {desc}")
        if self.engine.current_mode == "SCREEN":
            self.engine.start_screen_cast(chosen, source="Desktop App")

    def on_start_desktop_mirror(self):
        chosen = [idx for idx, var in self.mon_vars.items() if var.get()]
        if not chosen:
            chosen = [1]
        self.engine.start_screen_cast(chosen, source="Desktop App")

    def on_toggle_pause(self):
        self.engine.toggle_pause(source="Desktop App")

    def _sync_ui_from_engine(self):
        for idx, var in self.mon_vars.items():
            var.set(idx in self.engine.selected_monitors or 0 in self.engine.selected_monitors)
        self.res_combo.set(self.engine.main_res)
        self.fps_combo.set(str(self.engine.fps))
        self.bitrate_combo.set(self.engine.video_bitrate)
        self.pc_audio_var.set(self.engine.capture_pc_audio)
        self.cursor_var.set(self.engine.show_cursor)
        self.loop_video_var.set(self.engine.loop_video)
        self.auto_skip_var.set(self.engine.auto_skip_offline)
        if self.engine.gallery_folder:
            self.gal_folder_var.set(self.engine.gallery_folder)
        self._refresh_output_mode_buttons()
        self._refresh_tv_channel_tree()

    def copy_to_clipboard(self, text: str):
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.engine.log(f"Copied to clipboard: {text}")

    def paste_clipboard(self):
        try:
            clip = self.root.clipboard_get()
            self.yt_entry.delete(0, tk.END)
            self.yt_entry.insert(0, clip)
        except Exception:
            pass

    def on_settings_change(self, event=None):
        self.engine.main_res = self.res_combo.get()
        self.engine.aspect_mode = self.aspect_combo.get().split(" ")[0]
        self.engine.fps = int(self.fps_combo.get())
        self.engine.video_bitrate = self.bitrate_combo.get()
        self.engine.audio_codec = self.audio_combo.get().split(" ")[0]
        self.engine.capture_pc_audio = self.pc_audio_var.get()
        self.engine.show_cursor = self.cursor_var.get()
        self.engine.loop_video = self.loop_video_var.get()
        self.engine.save_persistent_config()
        self.engine.log(
            f"Settings saved: Res={self.engine.main_res}, Aspect={self.engine.aspect_mode}, "
            f"FPS={self.engine.fps}, Bitrate={self.engine.video_bitrate}, Loop={self.engine.loop_video}"
        )
        if self.engine.current_mode == "SCREEN":
            self.engine.start_screen_cast(self.engine.selected_monitors, source="Desktop App")

    def on_clear_log(self):
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.delete("1.0", tk.END)
        self.log_text.configure(state=tk.DISABLED)

    def append_log_threadsafe(self, msg: str):
        self.root.after(0, self._append_log, msg)

    def _append_log(self, msg: str):
        self.latest_log_var.set(msg)
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, msg + "\n")
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)

    def update_status_threadsafe(self, mode: str, title: str):
        self.root.after(0, self._update_status, mode, title)

    def _update_status(self, mode: str, title: str):
        colors = {
            "STANDBY": ("#dcfce7", "#15803d"),
            "LOADING": ("#fef3c7", "#b45309"),
            "YOUTUBE": ("#dbeafe", "#1d4ed8"),
            "FILE": ("#dbeafe", "#1d4ed8"),
            "GALLERY": ("#dcfce7", "#15803d"),
            "SCREEN": ("#e0e7ff", "#4338ca"),
            "BROWSER": ("#f3e8ff", "#6d28d9"),
            "ERROR": ("#fee2e2", "#dc2626"),
        }
        bg, fg = colors.get(mode, ("#f1f5f9", "#334155"))
        self.mode_badge.configure(text=f" {mode} ", bg=bg, fg=fg)
        self.title_label.configure(text=title)
        if mode in ("YOUTUBE", "ERROR") and self.engine.tv_channels:
            self._refresh_tv_channel_tree()

    def on_close(self):
        self.engine.shutdown()
        self.root.destroy()
