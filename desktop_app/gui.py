import os
import queue
import threading
from http.server import ThreadingHTTPServer
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from desktop_app.engine import NVRCastEngine, APP_VERSION
from web_studio.server import WebRemoteHandler


class NVRCastDesktopApp:
    """
    Native Windows Desktop GUI Control Center (v0.1.0-beta).
    Clean Whitish / Light Studio Interface:
      - Universal RTSP Casting (Hikvision, Dahua, Uniview, Reolink, ONVIF)
      - Active Stream Session Bar (shows active source + Pause/Resume, Seek -10s/+10s, Stop)
      - Direct YouTube / Web Video / Local Movie Streaming with Infinite Loop
      - Rock-Solid Photo Gallery & Single Picture Slideshow Studio (Folder/Pictures picker, Timer, Shuffle, Next/Prev)
      - Multi-Monitor Desktop Mirroring + WASAPI Speaker Audio
      - Browser Web Cast Studio (:8090) & Chrome Extension Sync
    """

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(f"NVR Cast Hub v{APP_VERSION} — Universal RTSP Media, Live Cricket/IPTV, Slideshow & Multi-Monitor Caster")
        self.root.geometry("1000x920")
        self.root.configure(bg="#f1f5f9")

        style = ttk.Style()
        try:
            style.theme_use("vista")
        except Exception:
            pass

        self.engine = NVRCastEngine(
            log_callback=self.append_log_threadsafe,
            status_callback=self.update_status_threadsafe,
        )
        WebRemoteHandler.ui_sync_callback = lambda: self.root.after(0, self._sync_ui_from_engine)
        WebRemoteHandler.browse_dialog_callback = self._open_dialog_from_web_threadsafe

        self.mon_vars = {}
        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        threading.Thread(target=self._init_services, daemon=True).start()
        self.root.after(1000, self._periodic_status_tick)

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

    def _make_card(self, parent, pady=(0, 8), padx=16):
        card = tk.Frame(
            parent,
            bg="#ffffff",
            highlightbackground="#cbd5e1",
            highlightthickness=1,
            padx=14,
            pady=10,
        )
        card.pack(fill=tk.X, padx=padx, pady=pady)
        return card

    def _make_btn(self, parent, text, command, variant="secondary", padx=12, pady=4):
        if variant == "primary":
            bg, fg, border = "#2563eb", "#ffffff", "#1d4ed8"
        elif variant == "danger":
            bg, fg, border = "#fef2f2", "#dc2626", "#fecaca"
        elif variant == "accent":
            bg, fg, border = "#eff6ff", "#1d4ed8", "#bfdbfe"
        else:
            bg, fg, border = "#f8fafc", "#0f172a", "#cbd5e1"

        btn = tk.Button(
            parent,
            text=text,
            font=("Segoe UI", 9, "bold"),
            bg=bg,
            fg=fg,
            activebackground=border,
            activeforeground=fg,
            relief=tk.SOLID,
            bd=1,
            padx=padx,
            pady=pady,
            cursor="hand2",
            command=command,
        )
        return btn

    def _build_ui(self):
        # Top White Header Bar
        header = tk.Frame(
            self.root,
            bg="#ffffff",
            highlightbackground="#cbd5e1",
            highlightthickness=1,
            padx=18,
            pady=10,
        )
        header.pack(fill=tk.X, padx=16, pady=(12, 8))

        top_bar = tk.Frame(header, bg="#ffffff")
        top_bar.pack(fill=tk.X)

        # Custom Vector-Drawn Cast Icon on Canvas
        icon_cv = tk.Canvas(top_bar, width=32, height=32, bg="#ffffff", highlightthickness=0)
        icon_cv.pack(side=tk.LEFT, padx=(0, 10))
        icon_cv.create_rectangle(2, 2, 30, 30, fill="#2563eb", outline="#1d4ed8", width=1)
        icon_cv.create_rectangle(7, 8, 25, 21, outline="#ffffff", width=2)
        icon_cv.create_oval(7, 19, 11, 23, fill="#ffffff", outline="#ffffff")
        icon_cv.create_arc(3, 15, 15, 27, start=0, extent=90, style=tk.ARC, outline="#ffffff", width=2)

        title_col = tk.Frame(top_bar, bg="#ffffff")
        title_col.pack(side=tk.LEFT, anchor="w")

        tk.Label(
            title_col,
            text=f"NVR Cast Hub  v{APP_VERSION}",
            font=("Segoe UI", 13, "bold"),
            bg="#ffffff",
            fg="#0f172a",
        ).pack(anchor="w")

        tk.Label(
            title_col,
            text="Universal RTSP Video, Photo Slideshow & Multi-Monitor Caster  •  Hikvision / Dahua / Uniview / Reolink / ONVIF",
            font=("Segoe UI", 8),
            bg="#ffffff",
            fg="#64748b",
        ).pack(anchor="w")

        self._make_btn(
            top_bar,
            text="Open Web Cast Studio (:8090)  ↗",
            variant="accent",
            padx=14,
            pady=5,
            command=lambda: os.startfile(f"http://localhost:{self.engine.web_port}"),
        ).pack(side=tk.RIGHT)

        # Card 1: RTSP Endpoints & Active Session Bar
        session_card = self._make_card(self.root)

        rtsp_row = tk.Frame(session_card, bg="#ffffff")
        rtsp_row.pack(fill=tk.X, pady=(0, 8))

        self.main_rtsp_var = tk.StringVar(value=f"rtsp://{self.engine.lan_ip}:{self.engine.rtsp_port}/main")
        self.sub_rtsp_var = tk.StringVar(value=f"rtsp://{self.engine.lan_ip}:{self.engine.rtsp_port}/sub")
        self.web_remote_var = tk.StringVar(value=f"http://localhost:{self.engine.web_port}")

        self._add_endpoint_pill(rtsp_row, "Main Stream (HD):", self.main_rtsp_var)
        self._add_endpoint_pill(rtsp_row, "Sub Stream (Grid):", self.sub_rtsp_var)
        self._add_endpoint_pill(rtsp_row, "Web Studio:", self.web_remote_var)

        sep = tk.Frame(session_card, bg="#e2e8f0", height=1)
        sep.pack(fill=tk.X, pady=6)

        status_bar = tk.Frame(session_card, bg="#ffffff")
        status_bar.pack(fill=tk.X, pady=(2, 0))

        self.mode_badge = tk.Label(
            status_bar,
            text=" STARTING ",
            font=("Segoe UI", 9, "bold"),
            bg="#dcfce7",
            fg="#15803d",
            padx=10,
            pady=3,
        )
        self.mode_badge.pack(side=tk.LEFT)

        self.title_label = tk.Label(
            status_bar,
            text="Initializing Universal RTSP Server...",
            font=("Segoe UI", 10, "bold"),
            bg="#ffffff",
            fg="#0f172a",
            padx=10,
        )
        self.title_label.pack(side=tk.LEFT)

        self.pos_label = tk.Label(
            status_bar,
            text="",
            font=("Segoe UI", 9, "bold"),
            bg="#ffffff",
            fg="#2563eb",
            padx=4,
        )
        self.pos_label.pack(side=tk.LEFT)

        # Transport Controls on the Right
        self._make_btn(
            status_bar,
            text="■  Stop / Standby",
            variant="danger",
            padx=10,
            pady=3,
            command=lambda: threading.Thread(target=self.engine.start_standby_stream, args=("Desktop App",), daemon=True).start(),
        ).pack(side=tk.RIGHT, padx=(4, 0))

        self._make_btn(
            status_bar,
            text="+10s  ▷",
            variant="secondary",
            padx=9,
            pady=3,
            command=lambda: self.engine.seek_stream(delta_sec=10, source="Desktop App"),
        ).pack(side=tk.RIGHT, padx=2)

        self._make_btn(
            status_bar,
            text="◁  -10s",
            variant="secondary",
            padx=9,
            pady=3,
            command=lambda: self.engine.seek_stream(delta_sec=-10, source="Desktop App"),
        ).pack(side=tk.RIGHT, padx=2)

        self.pause_btn = self._make_btn(
            status_bar,
            text="❚❚  Pause / Resume",
            variant="secondary",
            padx=11,
            pady=3,
            command=self.on_toggle_pause,
        )
        self.pause_btn.pack(side=tk.RIGHT, padx=(0, 4))

        # Card 2: YouTube, Playlist, Web Video & Local Movie Caster
        yt_card = self._make_card(self.root)

        tk.Label(
            yt_card,
            text="1.  YOUTUBE VIDEO / PLAYLIST, WEB STREAM & LOCAL VIDEO CASTER  (AUTO-PLAYS PLAYLISTS & 24/7 LOOP)",
            font=("Segoe UI", 9, "bold"),
            bg="#ffffff",
            fg="#334155",
        ).pack(anchor="w", pady=(0, 6))

        yt_row = tk.Frame(yt_card, bg="#ffffff")
        yt_row.pack(fill=tk.X)

        self.yt_entry = tk.Entry(
            yt_row,
            font=("Segoe UI", 10),
            bg="#f8fafc",
            fg="#0f172a",
            insertbackground="#0f172a",
            relief=tk.SOLID,
            bd=1,
        )
        self.yt_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=4, padx=(0, 6))
        self.yt_entry.bind("<Return>", lambda e: self.on_stream_youtube())

        self._make_btn(yt_row, "Paste", self.paste_clipboard, "secondary", padx=10, pady=3).pack(side=tk.LEFT, padx=(0, 6))

        self.loop_video_var = tk.BooleanVar(value=False)
        tk.Checkbutton(
            yt_row,
            text="⟲  Loop",
            variable=self.loop_video_var,
            font=("Segoe UI", 9, "bold"),
            bg="#ffffff",
            fg="#0f172a",
            selectcolor="#ffffff",
            activebackground="#ffffff",
            command=self.on_settings_change,
        ).pack(side=tk.LEFT, padx=(0, 6))

        self._make_btn(
            yt_row,
            "◀ Prev",
            lambda: self.engine.step_gallery_slide(-1),
            "secondary",
            padx=8,
            pady=4,
        ).pack(side=tk.LEFT, padx=(0, 3))
        self._make_btn(
            yt_row,
            "Next ▶",
            lambda: self.engine.step_gallery_slide(1),
            "secondary",
            padx=8,
            pady=4,
        ).pack(side=tk.LEFT, padx=(0, 6))

        self._make_btn(yt_row, "▶  Stream Video / Playlist", self.on_stream_youtube, "primary", padx=14, pady=4).pack(
            side=tk.LEFT, padx=(0, 6)
        )
        self._make_btn(yt_row, "Browse Video File...", self.on_stream_file, "secondary", padx=11, pady=4).pack(side=tk.LEFT)

        # Card 2B: Live TV, Pakistan Cricket & GitHub Sports M3U Studio
        tv_card = self._make_card(self.root)

        tk.Label(
            tv_card,
            text="2.  LIVE SPORTS, PAKISTAN CRICKET & GITHUB M3U IPTV STUDIO  (NEXT / PREV CHANNEL ZAPPING)",
            font=("Segoe UI", 9, "bold"),
            bg="#ffffff",
            fg="#334155",
        ).pack(anchor="w", pady=(0, 6))

        tv_row1 = tk.Frame(tv_card, bg="#ffffff")
        tv_row1.pack(fill=tk.X, pady=(0, 6))

        tk.Label(tv_row1, text="Source / Repo:", font=("Segoe UI", 9, "bold"), bg="#ffffff", fg="#475569").pack(side=tk.LEFT)

        self.tv_source_options = [
            ("cricket_pk", "Pakistan Cricket & Live Sports TV (Geo Super, Willow, Ten, Star, DD)"),
            ("youtube_cricket", "Official Cricket YouTube Channels (PCB, Sports Central, PSL, ACC)"),
            ("pakistan_tv", "Pakistan News & Entertainment Live TV (24 News, Dunya, Hum, Bol, ARY, Geo)"),
            ("global_sports", "Global Live Sports TV (ESPN, Eurosport, RedBull, Tennis Channel)"),
            ("all_builtin", "All Built-in Sports & Pakistan Channels Combined"),
            ("iptv_sports", "GitHub Repo: iptv-org Sports (480+ Global Sports Channels)"),
            ("iptv_pk", "GitHub Repo: iptv-org Pakistan (100+ PK Channels)"),
            ("curated_pk_in", "GitHub Repo: Curated Working Pakistan & South Asia IPTV"),
            ("freetv_global", "GitHub Repo: Free-TV Open-Source Global IPTV"),
        ]
        self.tv_source_combo = ttk.Combobox(
            tv_row1,
            values=[label for _, label in self.tv_source_options],
            width=50,
            state="readonly",
        )
        self.tv_source_combo.current(0)
        self.tv_source_combo.pack(side=tk.LEFT, padx=(6, 10))
        self.tv_source_combo.bind("<<ComboboxSelected>>", lambda e: self.on_load_tv_source(auto_play=False))

        tk.Label(tv_row1, text="Filter / .M3U URL:", font=("Segoe UI", 9, "bold"), bg="#ffffff", fg="#475569").pack(side=tk.LEFT)
        self.tv_filter_entry = tk.Entry(
            tv_row1,
            font=("Segoe UI", 9),
            bg="#f8fafc",
            fg="#0f172a",
            relief=tk.SOLID,
            bd=1,
        )
        self.tv_filter_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=3, padx=(6, 6))
        self.tv_filter_entry.bind("<Return>", lambda e: self.on_load_tv_source(auto_play=False))

        self._make_btn(
            tv_row1,
            "Load / Filter",
            lambda: self.on_load_tv_source(auto_play=False),
            "secondary",
            padx=10,
            pady=3,
        ).pack(side=tk.LEFT)

        tv_row2 = tk.Frame(tv_card, bg="#ffffff")
        tv_row2.pack(fill=tk.X)

        tk.Label(tv_row2, text="Channel:", font=("Segoe UI", 9, "bold"), bg="#ffffff", fg="#475569").pack(side=tk.LEFT)
        self.tv_channel_combo = ttk.Combobox(
            tv_row2,
            values=[],
            state="readonly",
        )
        self.tv_channel_combo.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(6, 8))
        self.tv_channel_combo.bind("<<ComboboxSelected>>", lambda e: self.on_play_selected_tv_channel())

        self._make_btn(
            tv_row2,
            "◀ Prev Ch",
            lambda: self.engine.step_gallery_slide(-1),
            "secondary",
            padx=10,
            pady=4,
        ).pack(side=tk.LEFT, padx=(0, 4))

        self._make_btn(
            tv_row2,
            "Next Ch ▶",
            lambda: self.engine.step_gallery_slide(1),
            "secondary",
            padx=10,
            pady=4,
        ).pack(side=tk.LEFT, padx=(0, 6))

        self._make_btn(
            tv_row2,
            "▶  Stream Selected Channel",
            self.on_play_selected_tv_channel,
            "primary",
            padx=14,
            pady=4,
        ).pack(side=tk.LEFT)

        self._refresh_tv_channel_combo()

        # Card 3: Picture & Photo Gallery Slideshow Studio
        gal_card = self._make_card(self.root)

        tk.Label(
            gal_card,
            text="3.  PICTURE & PHOTO GALLERY SLIDESHOW STUDIO  (SINGLE PHOTO OR FOLDER WITH TIMER & SHUFFLE)",
            font=("Segoe UI", 9, "bold"),
            bg="#ffffff",
            fg="#334155",
        ).pack(anchor="w", pady=(0, 6))

        gal_row = tk.Frame(gal_card, bg="#ffffff")
        gal_row.pack(fill=tk.X)

        self.gal_folder_var = tk.StringVar(value="")
        self.gal_entry = tk.Entry(
            gal_row,
            textvariable=self.gal_folder_var,
            font=("Segoe UI", 9),
            bg="#f8fafc",
            fg="#0f172a",
            insertbackground="#0f172a",
            relief=tk.SOLID,
            bd=1,
        )
        self.gal_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=4, padx=(0, 6))

        self._make_btn(gal_row, "Select Folder...", self.on_pick_gallery_folder, "secondary", padx=10, pady=3).pack(
            side=tk.LEFT, padx=(0, 5)
        )
        self._make_btn(gal_row, "Select Picture(s)...", self.on_pick_gallery_files, "secondary", padx=10, pady=3).pack(
            side=tk.LEFT, padx=(0, 8)
        )

        tk.Label(gal_row, text="Timer (s):", font=("Segoe UI", 9, "bold"), bg="#ffffff", fg="#475569").pack(side=tk.LEFT)
        self.gal_timer_spin = tk.Spinbox(
            gal_row,
            from_=1,
            to=3600,
            width=4,
            font=("Segoe UI", 9, "bold"),
            bg="#f8fafc",
            fg="#0f172a",
            relief=tk.SOLID,
            bd=1,
        )
        self.gal_timer_spin.delete(0, tk.END)
        self.gal_timer_spin.insert(0, "5")
        self.gal_timer_spin.pack(side=tk.LEFT, ipady=2, padx=(4, 8))

        self.gal_shuffle_var = tk.BooleanVar(value=False)
        tk.Checkbutton(
            gal_row,
            text="⇄  Shuffle",
            variable=self.gal_shuffle_var,
            font=("Segoe UI", 9, "bold"),
            bg="#ffffff",
            fg="#0f172a",
            selectcolor="#ffffff",
            activebackground="#ffffff",
        ).pack(side=tk.LEFT, padx=(0, 6))

        self._make_btn(gal_row, "◁ Prev", lambda: self.engine.step_gallery_slide(-1), "secondary", padx=8, pady=3).pack(
            side=tk.LEFT, padx=(0, 4)
        )
        self._make_btn(gal_row, "Next ▷", lambda: self.engine.step_gallery_slide(1), "secondary", padx=8, pady=3).pack(
            side=tk.LEFT, padx=(0, 6)
        )
        self._make_btn(gal_row, "▶  Start Slideshow", self.on_start_gallery_slideshow, "primary", padx=13, pady=4).pack(
            side=tk.LEFT
        )

        # Card 4: Multi-Monitor Desktop Mirroring & Meeting Screen Share
        mon_card = self._make_card(self.root)

        tk.Label(
            mon_card,
            text="4.  MULTI-MONITOR PC DESKTOP MIRRORING & MEETING TAB/WINDOW SHARE",
            font=("Segoe UI", 9, "bold"),
            bg="#ffffff",
            fg="#334155",
        ).pack(anchor="w", pady=(0, 6))

        mon_top_row = tk.Frame(mon_card, bg="#ffffff")
        mon_top_row.pack(fill=tk.X, pady=(0, 6))

        tk.Label(
            mon_top_row,
            text="Displays:",
            font=("Segoe UI", 9, "bold"),
            bg="#ffffff",
            fg="#475569",
        ).pack(side=tk.LEFT, padx=(0, 8))

        for m in self.engine.monitors_info:
            if m["index"] == 0:
                continue
            var = tk.BooleanVar(value=(m["index"] in self.engine.selected_monitors))
            self.mon_vars[m["index"]] = var
            cb = tk.Checkbutton(
                mon_top_row,
                text=m["label"],
                variable=var,
                font=("Segoe UI", 9),
                bg="#f8fafc",
                fg="#0f172a",
                selectcolor="#ffffff",
                activebackground="#f1f5f9",
                padx=8,
                pady=2,
                relief=tk.SOLID,
                bd=1,
                command=self.on_monitor_selection_change,
            )
            cb.pack(side=tk.LEFT, padx=(0, 8))

        self._make_btn(mon_top_row, "Select All Displays", self.select_all_monitors, "secondary", padx=10, pady=2).pack(
            side=tk.LEFT
        )

        mon_action_row = tk.Frame(mon_card, bg="#ffffff")
        mon_action_row.pack(fill=tk.X)

        self._make_btn(
            mon_action_row,
            text="▶  Mirror Selected Monitor(s) to NVR",
            command=self.on_start_desktop_mirror,
            variant="primary",
            padx=14,
            pady=4,
        ).pack(side=tk.LEFT, padx=(0, 8))

        self._make_btn(
            mon_action_row,
            text="Share Browser Tab / Window + Audio (Meeting Mode)  ↗",
            command=lambda: os.startfile(f"http://localhost:{self.engine.web_port}/?autoshare=1"),
            variant="accent",
            padx=14,
            pady=4,
        ).pack(side=tk.LEFT, padx=(0, 12))

        self.pc_audio_var = tk.BooleanVar(value=True)
        tk.Checkbutton(
            mon_action_row,
            text="Stream PC Speaker Audio",
            variable=self.pc_audio_var,
            font=("Segoe UI", 9, "bold"),
            bg="#ffffff",
            fg="#334155",
            selectcolor="#ffffff",
            command=self.on_settings_change,
        ).pack(side=tk.LEFT, padx=(0, 8))

        self.cursor_var = tk.BooleanVar(value=True)
        tk.Checkbutton(
            mon_action_row,
            text="Show Mouse Pointer",
            variable=self.cursor_var,
            font=("Segoe UI", 9, "bold"),
            bg="#ffffff",
            fg="#334155",
            selectcolor="#ffffff",
            command=self.on_settings_change,
        ).pack(side=tk.LEFT)

        # Card 5: Stream Quality & Encoding Options
        settings_card = self._make_card(self.root)

        settings_row = tk.Frame(settings_card, bg="#ffffff")
        settings_row.pack(fill=tk.X)

        tk.Label(
            settings_row,
            text="5.  QUALITY & ENCODING:",
            font=("Segoe UI", 9, "bold"),
            bg="#ffffff",
            fg="#334155",
        ).pack(side=tk.LEFT, padx=(0, 12))

        tk.Label(settings_row, text="Resolution:", font=("Segoe UI", 9), bg="#ffffff", fg="#475569").pack(side=tk.LEFT)
        self.res_combo = ttk.Combobox(
            settings_row,
            values=["1280x720", "1920x1080", "854x480"],
            width=10,
            state="readonly",
        )
        self.res_combo.set("1280x720")
        self.res_combo.pack(side=tk.LEFT, padx=(4, 12))
        self.res_combo.bind("<<ComboboxSelected>>", self.on_settings_change)

        tk.Label(settings_row, text="Fit:", font=("Segoe UI", 9), bg="#ffffff", fg="#475569").pack(side=tk.LEFT)
        self.aspect_combo = ttk.Combobox(
            settings_row,
            values=["fit (Letterbox)", "stretch (Fill 16:9)", "crop (Center 16:9)"],
            width=15,
            state="readonly",
        )
        self.aspect_combo.set("fit (Letterbox)")
        self.aspect_combo.pack(side=tk.LEFT, padx=(4, 12))
        self.aspect_combo.bind("<<ComboboxSelected>>", self.on_settings_change)

        tk.Label(settings_row, text="FPS:", font=("Segoe UI", 9), bg="#ffffff", fg="#475569").pack(side=tk.LEFT)
        self.fps_combo = ttk.Combobox(
            settings_row,
            values=["25", "30", "15"],
            width=4,
            state="readonly",
        )
        self.fps_combo.set("25")
        self.fps_combo.pack(side=tk.LEFT, padx=(4, 12))
        self.fps_combo.bind("<<ComboboxSelected>>", self.on_settings_change)

        tk.Label(settings_row, text="Bitrate:", font=("Segoe UI", 9), bg="#ffffff", fg="#475569").pack(side=tk.LEFT)
        self.bitrate_combo = ttk.Combobox(
            settings_row,
            values=["1000k", "1800k", "2500k", "4000k"],
            width=7,
            state="readonly",
        )
        self.bitrate_combo.set("1800k")
        self.bitrate_combo.pack(side=tk.LEFT, padx=(4, 12))
        self.bitrate_combo.bind("<<ComboboxSelected>>", self.on_settings_change)

        tk.Label(settings_row, text="Audio:", font=("Segoe UI", 9), bg="#ffffff", fg="#475569").pack(side=tk.LEFT)
        self.audio_combo = ttk.Combobox(
            settings_row,
            values=[
                "pcm_mulaw (G.711u CCTV)",
                "pcm_alaw (G.711a CCTV)",
                "aac (16kHz Mono)",
                "aac_hq (44.1kHz Stereo)",
                "none (Mute)",
            ],
            width=21,
            state="readonly",
        )
        self.audio_combo.set("pcm_mulaw (G.711u CCTV)")
        self.audio_combo.pack(side=tk.LEFT, padx=(4, 0))
        self.audio_combo.bind("<<ComboboxSelected>>", self.on_settings_change)

        # Card 6: System Activity Logs
        log_card = tk.Frame(
            self.root,
            bg="#ffffff",
            highlightbackground="#cbd5e1",
            highlightthickness=1,
            padx=14,
            pady=8,
        )
        log_card.pack(fill=tk.BOTH, expand=True, padx=16, pady=(0, 12))

        tk.Label(
            log_card,
            text="SYSTEM & RTSP SERVER ACTIVITY LOG",
            font=("Segoe UI", 8, "bold"),
            bg="#ffffff",
            fg="#64748b",
        ).pack(anchor="w", pady=(0, 4))

        self.log_text = tk.Text(
            log_card,
            height=6,
            bg="#f8fafc",
            fg="#334155",
            font=("Consolas", 9),
            relief=tk.SOLID,
            bd=1,
            state=tk.DISABLED,
        )
        self.log_text.pack(fill=tk.BOTH, expand=True)

    def _add_endpoint_pill(self, parent, label_text: str, text_var: tk.StringVar):
        box = tk.Frame(parent, bg="#f8fafc", highlightbackground="#e2e8f0", highlightthickness=1, padx=8, pady=4)
        box.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))

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
            bg="#f8fafc",
            fg="#0f172a",
            readonlybackground="#f8fafc",
            relief=tk.FLAT,
            state="readonly",
        )
        entry.pack(side=tk.LEFT, fill=tk.X, expand=True)

        tk.Button(
            box,
            text="Copy",
            font=("Segoe UI", 8, "bold"),
            bg="#ffffff",
            fg="#2563eb",
            relief=tk.SOLID,
            bd=1,
            padx=7,
            cursor="hand2",
            command=lambda: self.copy_to_clipboard(text_var.get()),
        ).pack(side=tk.RIGHT, padx=(4, 0))

    def _periodic_status_tick(self):
        try:
            d = self.engine.get_status_dict()
            if d["mode"] in ("YOUTUBE", "FILE"):
                sec = d.get("playback_sec", 0)
                m, s = divmod(sec, 60)
                self.pos_label.configure(text=f"•  {m:02d}:{s:02d}{' (Loop)' if d.get('loop_video') else ''}")
            elif d["mode"] == "GALLERY":
                gal = d.get("gallery", {})
                self.pos_label.configure(
                    text=f"•  Slide {gal.get('index', 0) + 1}/{gal.get('count', 1)} ({gal.get('interval', 5)}s)"
                )
            else:
                self.pos_label.configure(text="")
            self.pause_btn.configure(text="▶  Resume" if d.get("is_paused") else "❚❚  Pause")
        except Exception:
            pass
        self.root.after(1000, self._periodic_status_tick)

    def on_toggle_pause(self):
        self.engine.toggle_pause(source="Desktop App")

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
        self.engine.start_gallery_slideshow(
            folder,
            interval_sec=timer_s,
            shuffle=self.gal_shuffle_var.get(),
            source="Desktop App Gallery",
        )

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

    def _refresh_tv_channel_combo(self):
        chs = self.engine.tv_channels or []
        labels = [
            f"[{i + 1}/{len(chs)}]  {ch.get('title', 'Channel')}  ({ch.get('group', 'Live TV')})"
            for i, ch in enumerate(chs)
        ]
        self.tv_channel_combo["values"] = labels
        if labels:
            idx = min(max(0, self.engine.tv_active_index), len(labels) - 1)
            self.tv_channel_combo.current(idx)
        else:
            self.tv_channel_combo.set("No matching channels found")

    def on_load_tv_source(self, auto_play: bool = False):
        sel_idx = self.tv_source_combo.current()
        source_id = self.tv_source_options[sel_idx][0] if 0 <= sel_idx < len(self.tv_source_options) else "cricket_pk"
        raw_input = self.tv_filter_entry.get().strip()

        # If the user pasted a custom .m3u/.m3u8 URL into the Filter/.M3U box, load that URL directly
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
            self.root.after(0, self._refresh_tv_channel_combo)

        threading.Thread(target=_bg, daemon=True).start()

    def on_play_selected_tv_channel(self):
        idx = self.tv_channel_combo.current()
        if idx < 0:
            idx = 0
        self.engine.play_tv_channel(index=idx, source="Desktop App Live TV")

    def _sync_ui_from_engine(self):
        for idx, var in self.mon_vars.items():
            var.set(idx in self.engine.selected_monitors or 0 in self.engine.selected_monitors)
        self.res_combo.set(self.engine.main_res)
        self.fps_combo.set(str(self.engine.fps))
        self.bitrate_combo.set(self.engine.video_bitrate)
        self.pc_audio_var.set(self.engine.capture_pc_audio)
        self.cursor_var.set(self.engine.show_cursor)
        self.loop_video_var.set(self.engine.loop_video)
        if self.engine.gallery_folder:
            self.gal_folder_var.set(self.engine.gallery_folder)
        self._refresh_tv_channel_combo()

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

    def on_stream_youtube(self):
        val = self.yt_entry.get().strip()
        if not val:
            messagebox.showwarning("Input Required", "Please paste a YouTube URL, video path, or enter a search query.")
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

    def append_log_threadsafe(self, msg: str):
        self.root.after(0, self._append_log, msg)

    def _append_log(self, msg: str):
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
        }
        bg, fg = colors.get(mode, ("#f1f5f9", "#334155"))
        self.mode_badge.configure(text=f" {mode} ", bg=bg, fg=fg)
        src = getattr(self.engine, "active_source", "")
        src_prefix = f"[{src}]  " if src and src not in ("System", "System Standby") else ""
        self.title_label.configure(text=f"{src_prefix}{title}")

    def on_close(self):
        self.engine.shutdown()
        self.root.destroy()
