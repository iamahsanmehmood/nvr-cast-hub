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

from desktop_app.engine import NVRCastEngine, APP_VERSION
from web_studio.server import WebRemoteHandler


class NVRCastDesktopApp:
    """
    NVR Cast Hub v0.1.0-beta — Professional 2-Column Broadcast Studio Desktop GUI.
      - Left Column:
          • Live 16:9 Stream Preview Monitor (5 FPS MJPEG from FFmpeg) with Pause/Stop Preview toggle
          • Real-Time Stream Health & Failure Diagnostic Banner (PROBING / BUFFERING / LIVE / STALLED / OFFLINE ERROR)
          • Master Transport Deck (Prev/Next Channel or Track, Seek -10s/+10s, Pause/Resume, Standby)
      - Right Column (Categorized Studio Workspace Tabs):
          1. 🏏 Live TV & Cricket (Pakistan Cricket, Official Cricket YouTube, PK News/TV, Global Sports, GitHub M3U Repos, Search, Test Link)
          2. ▶ YouTube & Video (YouTube URL/Search/Playlist/Channel, Active Queue Browser, Local Video File Caster, 24/7 Loop)
          3. 🖼 Photo Gallery (Folder or Multi-Photo Picker, Timer, Shuffle, Crossfade, Prev/Next Slide)
          4. 🖥 PC Monitors & Share (Multi-Monitor Desktop Mirroring + WASAPI Audio, Browser Tab/Window Share, Chrome Extension Sync)
          5. ⚙ Settings & Logs (Resolution, Aspect Fit, FPS, Bitrate, NVR Audio Codec, System & RTSP Activity Log)
    """

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(
            f"NVR Cast Hub v{APP_VERSION} — Universal RTSP Broadcast Studio (Live TV, YouTube, Gallery & Multi-Monitor)"
        )
        self.root.geometry("1240x830")
        self.root.minsize(1060, 720)
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
        self._tv_status_cache = {}  # url -> status string

        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        threading.Thread(target=self._init_services, daemon=True).start()
        self.root.after(220, self._preview_and_telemetry_tick)

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
            rowheight=28,
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
                    p = filedialog.askdirectory(title="Select Picture Folder for NVR Slideshow")
                elif kind == "pictures":
                    files = filedialog.askopenfilenames(
                        title="Select Picture(s) for NVR Slideshow",
                        filetypes=[("Image Files", "*.jpg *.jpeg *.png *.bmp *.webp *.gif"), ("All Files", "*.*")],
                    )
                    p = ";".join(files) if files else ""
                else:
                    p = filedialog.askopenfilename(
                        title="Select Video File to Stream to NVR",
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
                f"Web Cast Studio active at http://localhost:{self.engine.web_port} "
                f"(and http://{self.engine.lan_ip}:{self.engine.web_port})"
            )
            httpd.serve_forever()
        except Exception as e:
            self.engine.log(f"Web Remote port warning: {e}")

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
    # MASTER UI LAYOUT (TOP BAR + 2-COLUMN STUDIO WORKSPACE + FOOTER TICKER)
    # =========================================================================
    def _build_ui(self):
        # 1. Top Studio Header & RTSP Endpoints Bar
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

        # Studio Vector Badge
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
            text="Universal RTSP Broadcast Studio  •  Hikvision / Dahua / Uniview / Reolink / ONVIF",
            font=("Segoe UI", 8),
            bg="#ffffff",
            fg="#64748b",
        ).pack(anchor="w")

        # Right side of top header: Web Studio Button + Endpoint Pills
        self._make_btn(
            top_row,
            text="🌐 Open Web Studio (:8090) ↗",
            variant="accent",
            padx=12,
            pady=5,
            command=lambda: os.startfile(f"http://localhost:{self.engine.web_port}"),
        ).pack(side=tk.RIGHT, padx=(8, 0))

        self.main_rtsp_var = tk.StringVar(value=f"rtsp://{self.engine.lan_ip}:{self.engine.rtsp_port}/main")
        self.sub_rtsp_var = tk.StringVar(value=f"rtsp://{self.engine.lan_ip}:{self.engine.rtsp_port}/sub")
        self.web_remote_var = tk.StringVar(value=f"http://localhost:{self.engine.web_port}")

        ep_bar = tk.Frame(top_row, bg="#ffffff")
        ep_bar.pack(side=tk.RIGHT, padx=(8, 4))
        self._add_endpoint_pill(ep_bar, "MAIN (HD):", self.main_rtsp_var)
        self._add_endpoint_pill(ep_bar, "SUB (Grid):", self.sub_rtsp_var)

        # 2. Main 2-Column Workspace Container
        workspace = tk.Frame(self.root, bg="#f1f5f9")
        workspace.pack(fill=tk.BOTH, expand=True, padx=14, pady=(0, 6))
        workspace.columnconfigure(0, weight=0, minsize=508)
        workspace.columnconfigure(1, weight=1)
        workspace.rowconfigure(0, weight=1)

        # ---------------------------------------------------------------------
        # LEFT COLUMN: LIVE PREVIEW MONITOR + HEALTH DIAGNOSTICS + TRANSPORT
        # ---------------------------------------------------------------------
        left_col = tk.Frame(
            workspace,
            bg="#ffffff",
            highlightbackground="#cbd5e1",
            highlightthickness=1,
            padx=14,
            pady=12,
            width=508,
        )
        left_col.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        left_col.grid_propagate(False)

        self._build_left_monitor_deck(left_col)

        # ---------------------------------------------------------------------
        # RIGHT COLUMN: CATEGORIZED STUDIO WORKSPACE (5 TABS)
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
            text="⚡ LATEST EVENT:",
            font=("Segoe UI", 8, "bold"),
            bg="#ffffff",
            fg="#2563eb",
        ).pack(side=tk.LEFT, padx=(0, 6))

        self.latest_log_var = tk.StringVar(value="Initializing Universal RTSP Server & MediaMTX...")
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
            text="View Full Log →",
            font=("Segoe UI", 8, "bold"),
            bg="#f8fafc",
            fg="#475569",
            relief=tk.FLAT,
            cursor="hand2",
            command=lambda: self._switch_tab("settings"),
        ).pack(side=tk.RIGHT)

    def _add_endpoint_pill(self, parent, label_text: str, text_var: tk.StringVar):
        box = tk.Frame(parent, bg="#f8fafc", highlightbackground="#cbd5e1", highlightthickness=1, padx=7, pady=3)
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
            font=("Consolas", 9, "bold"),
            width=25,
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
            padx=6,
            cursor="hand2",
            command=lambda: self.copy_to_clipboard(text_var.get()),
        ).pack(side=tk.LEFT, padx=(5, 0))

    # =========================================================================
    # LEFT COLUMN: LIVE MONITOR, DIAGNOSTIC BANNER & TRANSPORT CONTROLS
    # =========================================================================
    def _build_left_monitor_deck(self, parent: tk.Frame):
        # Monitor Top Header Bar
        mon_hdr = tk.Frame(parent, bg="#ffffff")
        mon_hdr.pack(fill=tk.X, pady=(0, 6))

        self.preview_dot = tk.Label(
            mon_hdr,
            text="●",
            font=("Segoe UI", 11, "bold"),
            bg="#ffffff",
            fg="#10b981",
        )
        self.preview_dot.pack(side=tk.LEFT, padx=(0, 4))

        tk.Label(
            mon_hdr,
            text="LIVE NVR STREAM PREVIEW MONITOR",
            font=("Segoe UI", 9, "bold"),
            bg="#ffffff",
            fg="#0f172a",
        ).pack(side=tk.LEFT)

        self.preview_toggle_btn = self._make_btn(
            mon_hdr,
            text="⏸ Stop Preview",
            variant="secondary",
            padx=9,
            pady=2,
            font_size=8,
            command=self.on_toggle_preview,
        )
        self.preview_toggle_btn.pack(side=tk.RIGHT)

        # 16:9 Video Preview Canvas (480x270)
        canvas_wrap = tk.Frame(
            parent,
            bg="#0f172a",
            highlightbackground="#334155",
            highlightthickness=1,
            width=480,
            height=270,
        )
        canvas_wrap.pack( pady=(0, 8))
        canvas_wrap.pack_propagate(False)

        self.preview_canvas = tk.Canvas(
            canvas_wrap,
            width=480,
            height=270,
            bg="#0f172a",
            highlightthickness=0,
        )
        self.preview_canvas.pack(fill=tk.BOTH, expand=True)
        self._draw_initial_preview_canvas()

        # Stream Health & Diagnostic Alert Banner
        self.health_frame = tk.Frame(
            parent,
            bg="#ecfdf5",
            highlightbackground="#6ee7b7",
            highlightthickness=1,
            padx=10,
            pady=7,
        )
        self.health_frame.pack(fill=tk.X, pady=(0, 8))

        health_top = tk.Frame(self.health_frame, bg="#ecfdf5")
        health_top.pack(fill=tk.X)
        self.health_top = health_top

        self.health_badge = tk.Label(
            health_top,
            text=" ● STANDBY READY ",
            font=("Segoe UI", 8, "bold"),
            bg="#059669",
            fg="#ffffff",
            padx=6,
            pady=1,
        )
        self.health_badge.pack(side=tk.LEFT, padx=(0, 8))

        self.health_title_lbl = tk.Label(
            health_top,
            text="RTSP Server Online • Waiting for Stream",
            font=("Segoe UI", 9, "bold"),
            bg="#ecfdf5",
            fg="#065f46",
            anchor="w",
        )
        self.health_title_lbl.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.health_detail_lbl = tk.Label(
            self.health_frame,
            text="Select any Live TV channel, YouTube video, Photo Gallery, or PC Monitor on the right.",
            font=("Segoe UI", 8),
            bg="#ecfdf5",
            fg="#047857",
            anchor="w",
            justify=tk.LEFT,
            wraplength=455,
        )
        self.health_detail_lbl.pack(fill=tk.X, pady=(4, 0))

        # Now Playing Card
        now_card = tk.Frame(
            parent,
            bg="#f8fafc",
            highlightbackground="#e2e8f0",
            highlightthickness=1,
            padx=10,
            pady=8,
        )
        now_card.pack(fill=tk.X, pady=(0, 8))

        np_row1 = tk.Frame(now_card, bg="#f8fafc")
        np_row1.pack(fill=tk.X, pady=(0, 4))

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
            text="Source: System Standby",
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
            text="Standby Screen (Ready to Cast)",
            font=("Segoe UI", 10, "bold"),
            bg="#f8fafc",
            fg="#0f172a",
            anchor="w",
            justify=tk.LEFT,
            wraplength=455,
        )
        self.title_label.pack(fill=tk.X)

        # Master Transport Controls Deck
        transport_card = tk.Frame(
            parent,
            bg="#ffffff",
            highlightbackground="#e2e8f0",
            highlightthickness=1,
            padx=8,
            pady=8,
        )
        transport_card.pack(fill=tk.X, pady=(0, 8))

        tk.Label(
            transport_card,
            text="MASTER TRANSPORT & CHANNEL ZAPPING",
            font=("Segoe UI", 8, "bold"),
            bg="#ffffff",
            fg="#64748b",
        ).pack(anchor="w", pady=(0, 6))

        t_row1 = tk.Frame(transport_card, bg="#ffffff")
        t_row1.pack(fill=tk.X, pady=(0, 6))

        self._make_btn(
            t_row1,
            "⏮ Prev Ch / Track",
            lambda: self.engine.step_gallery_slide(-1),
            "secondary",
            padx=9,
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
            "Next Ch / Track ⏭",
            lambda: self.engine.step_gallery_slide(1),
            "secondary",
            padx=9,
            pady=5,
        ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 0))

        t_row2 = tk.Frame(transport_card, bg="#ffffff")
        t_row2.pack(fill=tk.X)

        self._make_btn(
            t_row2,
            "◁ Seek -10s",
            lambda: self.engine.seek_stream(delta_sec=-10, source="Desktop App"),
            "secondary",
            padx=8,
            pady=4,
            font_size=8,
        ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))

        self._make_btn(
            t_row2,
            "Seek +10s ▷",
            lambda: self.engine.seek_stream(delta_sec=10, source="Desktop App"),
            "secondary",
            padx=8,
            pady=4,
            font_size=8,
        ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)

        self._make_btn(
            t_row2,
            "■ Stop / Standby",
            lambda: threading.Thread(
                target=self.engine.start_standby_stream, args=("Desktop App",), daemon=True
            ).start(),
            "danger",
            padx=10,
            pady=4,
            font_size=8,
        ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 0))

        # Quick Telemetry Summary Footer inside Left Deck
        telemetry_row = tk.Frame(parent, bg="#ffffff")
        telemetry_row.pack(fill=tk.X, side=tk.BOTTOM, pady=(4, 0))

        self.telemetry_lbl = tk.Label(
            telemetry_row,
            text="Output: 1280x720 @ 25fps (H.264 Baseline) + 640x360 Sub  •  Audio: G.711u",
            font=("Segoe UI", 8),
            bg="#ffffff",
            fg="#64748b",
            anchor="w",
        )
        self.telemetry_lbl.pack(side=tk.LEFT)

    def _draw_initial_preview_canvas(self):
        self.preview_canvas.delete("all")
        self.preview_canvas.create_rectangle(0, 0, 480, 270, fill="#0f172a", outline="")
        self.preview_canvas.create_rectangle(16, 16, 464, 254, fill="#1e293b", outline="#334155")
        self.preview_canvas.create_text(
            240,
            115,
            text="NVR CAST HUB — LIVE PREVIEW MONITOR",
            fill="#f8fafc",
            font=("Segoe UI", 11, "bold"),
        )
        self.preview_canvas.create_text(
            240,
            148,
            text="Starting RTSP Server & Standby Stream...",
            fill="#38bdf8",
            font=("Segoe UI", 9),
        )

    def on_toggle_preview(self):
        self.engine.preview_enabled = not self.engine.preview_enabled
        if self.engine.preview_enabled:
            self.preview_toggle_btn.configure(text="⏸ Stop Preview", bg="#f8fafc", fg="#0f172a")
            self.preview_dot.configure(fg="#10b981")
            self._last_preview_bytes = None
        else:
            self.preview_toggle_btn.configure(text="▶ Resume Preview", bg="#eff6ff", fg="#1d4ed8")
            self.preview_dot.configure(fg="#94a3b8")
            self.preview_canvas.delete("all")
            self.preview_canvas.create_rectangle(0, 0, 480, 270, fill="#0f172a", outline="")
            self.preview_canvas.create_rectangle(24, 24, 456, 246, fill="#1e293b", outline="#334155")
            self.preview_canvas.create_text(
                240,
                110,
                text="⏸  LIVE PREVIEW PAUSED BY USER",
                fill="#f8fafc",
                font=("Segoe UI", 12, "bold"),
            )
            self.preview_canvas.create_text(
                240,
                142,
                text="NVR RTSP Broadcast (/main & /sub) continues running at full 25 FPS.",
                fill="#93c5fd",
                font=("Segoe UI", 9),
            )
            self.preview_canvas.create_text(
                240,
                168,
                text="Click '▶ Resume Preview' above anytime to view live video.",
                fill="#94a3b8",
                font=("Segoe UI", 8),
            )

    # =========================================================================
    # RIGHT COLUMN: CATEGORIZED 5-TAB STUDIO WORKSPACE
    # =========================================================================
    def _build_right_tabbed_workspace(self, parent: tk.Frame):
        # Custom Tab Navigation Bar
        nav_bar = tk.Frame(parent, bg="#f1f5f9", padx=4, pady=4)
        nav_bar.pack(fill=tk.X, pady=(0, 12))

        tabs_spec = [
            ("tv", "🏏  Live TV & Cricket"),
            ("youtube", "▶  YouTube & Video"),
            ("gallery", "🖼  Photo Gallery"),
            ("monitors", "🖥  PC Monitors & Share"),
            ("settings", "⚙  Settings & Logs"),
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
                padx=12,
                pady=7,
                cursor="hand2",
                command=lambda tid=tab_id: self._switch_tab(tid),
            )
            btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)
            self._tab_buttons[tab_id] = btn

        # Tab Content Host Container
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
    # TAB 1: LIVE TV, PAKISTAN CRICKET & GITHUB M3U IPTV STUDIO
    # -------------------------------------------------------------------------
    def _build_tab_live_tv(self, parent: tk.Frame):
        hdr = tk.Frame(parent, bg="#ffffff")
        hdr.pack(fill=tk.X, pady=(0, 8))

        tk.Label(
            hdr,
            text="LIVE SPORTS, PAKISTAN CRICKET & GITHUB M3U IPTV DIRECTORY",
            font=("Segoe UI", 10, "bold"),
            bg="#ffffff",
            fg="#0f172a",
        ).pack(side=tk.LEFT)

        self.auto_skip_var = tk.BooleanVar(value=True)
        tk.Checkbutton(
            hdr,
            text="Auto-Skip Offline Channels",
            variable=self.auto_skip_var,
            font=("Segoe UI", 8, "bold"),
            bg="#ffffff",
            fg="#059669",
            selectcolor="#ffffff",
            activebackground="#ffffff",
            command=self.on_toggle_auto_skip,
        ).pack(side=tk.RIGHT)

        # Quick Category Pills Row
        pills_row = tk.Frame(parent, bg="#ffffff")
        pills_row.pack(fill=tk.X, pady=(0, 8))

        quick_cats = [
            ("cricket_pk", "🇵🇰 PK Cricket & Sports"),
            ("youtube_cricket", "▶ Official Cricket YT"),
            ("pakistan_tv", "📺 Pakistan News & TV"),
            ("global_sports", "🌍 Global Sports"),
            ("iptv_sports", "📦 GitHub Sports M3U"),
            ("iptv_pk", "📦 GitHub Pakistan M3U"),
        ]
        for cat_id, cat_label in quick_cats:
            self._make_btn(
                pills_row,
                cat_label,
                lambda cid=cat_id: self.on_quick_select_tv_cat(cid),
                variant="accent" if cat_id == "cricket_pk" else "secondary",
                padx=8,
                pady=3,
                font_size=8,
            ).pack(side=tk.LEFT, padx=(0, 5))

        # Source Selector + Filter / Custom M3U Input Row
        filter_row = tk.Frame(parent, bg="#f8fafc", highlightbackground="#e2e8f0", highlightthickness=1, padx=8, pady=7)
        filter_row.pack(fill=tk.X, pady=(0, 8))

        tk.Label(filter_row, text="Source:", font=("Segoe UI", 8, "bold"), bg="#f8fafc", fg="#475569").pack(side=tk.LEFT)

        self.tv_source_options = [
            ("cricket_pk", "Pakistan Cricket & Live Sports TV (Geo Super, Willow, Ten, Star, DD)"),
            ("youtube_cricket", "Official Cricket YouTube Channels (PCB, Sports Central, PSL, ACC)"),
            ("pakistan_tv", "Pakistan News & Entertainment Live TV (24 News, Dunya, Capital, Bol, 8XM)"),
            ("global_sports", "Global Live Sports TV (ESPN, ESPN2, ESPNU, Tennis Channel)"),
            ("all_builtin", "All Built-in Sports & Pakistan Channels Combined"),
            ("iptv_sports", "GitHub Repo: iptv-org Sports (480+ Global Sports Channels)"),
            ("iptv_pk", "GitHub Repo: iptv-org Pakistan (PK Channels M3U)"),
            ("curated_pk_in", "GitHub Repo: Curated Pakistan & South Asia IPTV"),
            ("freetv_global", "GitHub Repo: Free-TV Open-Source Global IPTV"),
        ]
        self.tv_source_combo = ttk.Combobox(
            filter_row,
            values=[label for _, label in self.tv_source_options],
            width=36,
            state="readonly",
        )
        self.tv_source_combo.current(0)
        self.tv_source_combo.pack(side=tk.LEFT, padx=(5, 10))
        self.tv_source_combo.bind("<<ComboboxSelected>>", lambda e: self.on_load_tv_source(auto_play=False))

        tk.Label(filter_row, text="Search / .M3U URL:", font=("Segoe UI", 8, "bold"), bg="#f8fafc", fg="#475569").pack(
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
        self.tv_filter_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=3, padx=(5, 6))
        self.tv_filter_entry.bind("<Return>", lambda e: self.on_load_tv_source(auto_play=False))

        self._make_btn(
            filter_row,
            "🔍 Filter / Load M3U",
            lambda: self.on_load_tv_source(auto_play=False),
            "secondary",
            padx=9,
            pady=3,
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
        self.tv_tree.heading("title", text="Channel Name (Double-Click to Stream)")
        self.tv_tree.heading("group", text="Category / Network")
        self.tv_tree.heading("status", text="Stream Health / Type")

        self.tv_tree.column("num", width=44, anchor="center", stretch=False)
        self.tv_tree.column("title", width=270, anchor="w")
        self.tv_tree.column("group", width=165, anchor="w")
        self.tv_tree.column("status", width=165, anchor="w")

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
            "▶  Stream Selected Channel to NVR",
            self.on_play_selected_tv_channel,
            "primary",
            padx=16,
            pady=6,
        ).pack(side=tk.LEFT, padx=(0, 8))

        self._make_btn(
            act_row,
            "⚡ Test Selected Channel Link",
            self.on_test_selected_tv_channel,
            "accent",
            padx=12,
            pady=6,
        ).pack(side=tk.LEFT, padx=(0, 8))

        self._make_btn(
            act_row,
            "⏮ Prev Channel",
            lambda: self.engine.step_gallery_slide(-1),
            "secondary",
            padx=10,
            pady=6,
        ).pack(side=tk.LEFT, padx=(0, 4))

        self._make_btn(
            act_row,
            "Next Channel ⏭",
            lambda: self.engine.step_gallery_slide(1),
            "secondary",
            padx=10,
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
    # TAB 2: YOUTUBE, PLAYLISTS, WEB STREAMS & LOCAL VIDEO CASTER
    # -------------------------------------------------------------------------
    def _build_tab_youtube(self, parent: tk.Frame):
        tk.Label(
            parent,
            text="YOUTUBE VIDEO, PLAYLIST / CHANNEL QUEUE & LOCAL MOVIE CASTER",
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
        self._make_btn(row1, "▶ Stream URL / Playlist", self.on_stream_youtube, "primary", padx=14, pady=5).pack(
            side=tk.LEFT
        )

        row2 = tk.Frame(yt_box, bg="#f8fafc")
        row2.pack(fill=tk.X)

        self.loop_video_var = tk.BooleanVar(value=False)
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
            "📂 Browse & Stream Local Video File (.mp4, .mkv, .avi, .mov)...",
            self.on_stream_file,
            "accent",
            padx=12,
            pady=4,
        ).pack(side=tk.LEFT)

        # Active Playlist / Queue Browser Table
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
    # TAB 3: PHOTO GALLERY & SLIDESHOW STUDIO
    # -------------------------------------------------------------------------
    def _build_tab_gallery(self, parent: tk.Frame):
        tk.Label(
            parent,
            text="PICTURE & PHOTO GALLERY SLIDESHOW STUDIO",
            font=("Segoe UI", 10, "bold"),
            bg="#ffffff",
            fg="#0f172a",
        ).pack(anchor="w", pady=(0, 4))

        tk.Label(
            parent,
            text="Broadcast a single static picture or an entire photo folder to your NVR with custom timer, shuffle, and smooth crossfades.",
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

        self.gal_folder_var = tk.StringVar(value="")
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
        self.gal_timer_spin.insert(0, "5")
        self.gal_timer_spin.pack(side=tk.LEFT, ipady=2, padx=(6, 16))

        self.gal_shuffle_var = tk.BooleanVar(value=False)
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

        self.gal_transition_var = tk.BooleanVar(value=True)
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
            "▶  Start Photo Slideshow Broadcast",
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
    # TAB 4: PC MONITORS, BROWSER SHARE & CHROME EXTENSION
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

        self.pc_audio_var = tk.BooleanVar(value=True)
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

        self.cursor_var = tk.BooleanVar(value=True)
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
            "▶  Mirror Selected Monitor(s) to NVR Now",
            self.on_start_desktop_mirror,
            "primary",
            padx=16,
            pady=6,
        ).pack(anchor="w")

        # Browser & Chrome Extension Card
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
            text="• Click below to share a specific browser tab or application window (Meeting Mode), or use the NVR Cast Hub Chrome Extension on any HTML5 video player.",
            font=("Segoe UI", 8),
            bg="#f8fafc",
            fg="#475569",
            justify=tk.LEFT,
            wraplength=600,
        ).pack(anchor="w", pady=(0, 8))

        self._make_btn(
            web_box,
            "🌐 Share Browser Tab / Window + Audio (Meeting Mode) ↗",
            lambda: os.startfile(f"http://localhost:{self.engine.web_port}/?autoshare=1"),
            "accent",
            padx=14,
            pady=6,
        ).pack(anchor="w")

    # -------------------------------------------------------------------------
    # TAB 5: STREAM QUALITY SETTINGS & ACTIVITY LOG
    # -------------------------------------------------------------------------
    def _build_tab_settings(self, parent: tk.Frame):
        tk.Label(
            parent,
            text="RTSP VIDEO / AUDIO ENCODING & SYSTEM ACTIVITY LOG",
            font=("Segoe UI", 10, "bold"),
            bg="#ffffff",
            fg="#0f172a",
        ).pack(anchor="w", pady=(0, 8))

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
        self.res_combo.set("1280x720")
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
        self.fps_combo.set("25")
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
        self.bitrate_combo.set("1800k")
        self.bitrate_combo.pack(side=tk.LEFT, padx=(6, 16))
        self.bitrate_combo.bind("<<ComboboxSelected>>", self.on_settings_change)

        tk.Label(r2, text="NVR Audio Codec:", font=("Segoe UI", 9, "bold"), bg="#f8fafc", fg="#334155").pack(side=tk.LEFT)
        self.audio_combo = ttk.Combobox(
            r2,
            values=[
                "pcm_mulaw (G.711u CCTV)",
                "pcm_alaw (G.711a CCTV)",
                "aac (16kHz Mono)",
                "aac_hq (44.1kHz Stereo)",
                "none (Mute)",
            ],
            width=23,
            state="readonly",
        )
        self.audio_combo.set("pcm_mulaw (G.711u CCTV)")
        self.audio_combo.pack(side=tk.LEFT, padx=(6, 0))
        self.audio_combo.bind("<<ComboboxSelected>>", self.on_settings_change)

        # System Activity Log Header & Box
        log_hdr = tk.Frame(parent, bg="#ffffff")
        log_hdr.pack(fill=tk.X, pady=(0, 4))

        tk.Label(
            log_hdr,
            text="REAL-TIME SYSTEM, FFMPEG & RTSP DIAGNOSTIC LOG",
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
    # REAL-TIME PREVIEW RENDERER & STREAM HEALTH DIAGNOSTIC ENGINE (220ms TICK)
    # =========================================================================
    def _preview_and_telemetry_tick(self):
        try:
            # 1. Update Live 16:9 Preview Canvas if preview_enabled
            if self.engine.preview_enabled and Image is not None and ImageTk is not None:
                jpg_bytes = self.engine.get_preview_jpeg()
                if jpg_bytes and jpg_bytes is not self._last_preview_bytes:
                    self._last_preview_bytes = jpg_bytes
                    with Image.open(io.BytesIO(jpg_bytes)) as im:
                        if im.size != (480, 270):
                            im = im.resize((480, 270), Image.Resampling.BILINEAR)
                        self._preview_photo = ImageTk.PhotoImage(im)
                    self.preview_canvas.delete("all")
                    self.preview_canvas.create_image(0, 0, anchor=tk.NW, image=self._preview_photo)

            # 2. Update Stream Health & Failure Diagnostic Banner
            d = self.engine.get_status_dict()
            h = d.get("health", {})
            h_state = h.get("state", "STANDBY")
            h_diag = h.get("diag", "")
            h_err = h.get("error_msg", "")
            frames = h.get("decoded_frames", 0)

            if h_state == "ERROR":
                self._style_health_banner(
                    bg="#fef2f2",
                    border="#fca5a5",
                    badge_bg="#dc2626",
                    badge_txt=" ✖ STREAM FAILED / OFFLINE ",
                    title_fg="#991b1b",
                    title_txt=f"Stream Failed: {d.get('title', '').replace('✖ FAILED: ', '').replace('✖ OFFLINE: ', '')[:46]}",
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
                    detail_txt=f"Target: {d.get('current_url', '')[:75]}",
                )
            elif h_state == "CONNECTING":
                self._style_health_banner(
                    bg="#fffbeb",
                    border="#fcd34d",
                    badge_bg="#d97706",
                    badge_txt=" ◔ BUFFERING VIDEO ",
                    title_fg="#92400e",
                    title_txt=h_diag or "Connected to server — waiting for first video frame...",
                    detail_fg="#b45309",
                    detail_txt="FFmpeg is negotiating media segments (8.5s auto-timeout protection active).",
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
                    title_txt=h_diag or "Stream Paused (NVR RTSP Hold Screen Active)",
                    detail_fg="#b45309",
                    detail_txt="Click '▶ Resume' in Transport Controls to continue broadcasting.",
                )
            elif h_state == "LIVE":
                self._style_health_banner(
                    bg="#ecfdf5",
                    border="#6ee7b7",
                    badge_bg="#059669",
                    badge_txt=" ● LIVE ON NVR ",
                    title_fg="#065f46",
                    title_txt=h_diag or f"Broadcasting Live • {d['settings']['fps']} FPS • Frame #{frames}",
                    detail_fg="#047857",
                    detail_txt=f"Streaming smoothly to rtsp://{d['lan_ip']}:{self.engine.rtsp_port}/main (and /sub)",
                )
            else:
                self._style_health_banner(
                    bg="#f0fdf4",
                    border="#bbf7d0",
                    badge_bg="#16a34a",
                    badge_txt=" ● STANDBY READY ",
                    title_fg="#166534",
                    title_txt="RTSP Server Online • Standby Screen Active on NVR",
                    detail_fg="#15803d",
                    detail_txt="Select any Live TV channel, YouTube video, Photo Gallery, or PC Monitor on the right.",
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

            # Update telemetry summary
            st = d.get("settings", {})
            self.telemetry_lbl.configure(
                text=f"Output: {st.get('main_res')} @ {st.get('fps')}fps ({st.get('video_bitrate')}) + 640x360 Sub  •  Audio: {st.get('audio_codec')}"
            )

            # Refresh playlist queue table if count changed
            self._sync_playlist_tree_if_needed()
        except Exception:
            pass

        self.root.after(240, self._preview_and_telemetry_tick)

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
    # LIVE TV & CRICKET TAB HANDLERS
    # =========================================================================
    def on_toggle_auto_skip(self):
        self.engine.auto_skip_offline = bool(self.auto_skip_var.get())
        self.engine.log(f"Auto-Skip Offline Channels set to: {self.engine.auto_skip_offline}")

    def on_quick_select_tv_cat(self, cat_id: str):
        for idx, (cid, _) in enumerate(self.tv_source_options):
            if cid == cat_id:
                self.tv_source_combo.current(idx)
                break
        self.tv_filter_entry.delete(0, tk.END)
        self.on_load_tv_source(auto_play=False)

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
                st_txt = "▶ YouTube Auto-Play"
            elif ".m3u8" in low_u:
                st_txt = "● HLS Live Stream"
            else:
                st_txt = "● MPEG-TS Live"

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

        self.tv_count_lbl.configure(text=f"{len(chs)} Channels Loaded")

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
            title="Select Video File to Stream to NVR",
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
        folder = filedialog.askdirectory(title="Select Picture Folder for NVR Slideshow")
        if folder:
            self.gal_folder_var.set(folder)
            self.on_start_gallery_slideshow()

    def on_pick_gallery_files(self):
        files = filedialog.askopenfilenames(
            title="Select Picture(s) for NVR Slideshow",
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
            folder = filedialog.askdirectory(title="Select Picture Folder for NVR Slideshow")
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
        self.engine.log(
            f"Settings updated: Res={self.engine.main_res}, Aspect={self.engine.aspect_mode}, "
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
