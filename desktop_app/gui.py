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
    Controls:
      - Universal RTSP Casting (Hikvision, Dahua, Uniview, Reolink, ONVIF)
      - Active Stream Session Bar (shows active source + Pause/Resume, Seek -10s/+10s, Stop)
      - Direct YouTube / Web Video / Local Movie Streaming with Infinite Loop
      - Photo Gallery / Folder Slideshow Gadget (Folder/Images picker, Timer in sec, Shuffle, Next/Prev)
      - Multi-Monitor Desktop Mirroring + WASAPI Speaker Audio
      - Browser Web Cast Studio (:8090) & Chrome Extension Sync
    """

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(f"NVR Cast Hub v{APP_VERSION} — Universal NVR & CCTV Caster (Desktop + Web + Extension)")
        self.root.geometry("950x840")
        self.root.configure(bg="#0f172a")

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

    def _open_dialog_from_web_threadsafe(self, kind: str) -> str:
        res_q = queue.Queue()

        def _ask():
            try:
                if kind == "folder":
                    p = filedialog.askdirectory(title="Select Picture Folder for NVR Slideshow")
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
                f"Web Cast Studio & Remote active at http://localhost:{self.engine.web_port} "
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

    def _build_ui(self):
        header = tk.Frame(self.root, bg="#1e293b", padx=18, pady=8)
        header.pack(fill=tk.X)

        top_bar = tk.Frame(header, bg="#1e293b")
        top_bar.pack(fill=tk.X)

        tk.Label(
            top_bar,
            text=f"📺 NVR Cast Hub v{APP_VERSION} — Universal RTSP Media, Gallery, Multi-Monitor & Web Caster",
            font=("Segoe UI", 12, "bold"),
            bg="#1e293b",
            fg="#38bdf8",
        ).pack(side=tk.LEFT, anchor="w")

        tk.Button(
            top_bar,
            text="🌐 Open Web Cast Studio (:8090)",
            font=("Segoe UI", 9, "bold"),
            bg="#0284c7",
            fg="#ffffff",
            relief=tk.FLAT,
            padx=12,
            pady=2,
            command=lambda: os.startfile(f"http://localhost:{self.engine.web_port}"),
        ).pack(side=tk.RIGHT)

        tk.Label(
            header,
            text="Works with Hikvision, Dahua, Uniview, Reolink & any ONVIF/RTSP NVR — Synchronized across Desktop App, Web Studio & Chrome Extension.",
            font=("Segoe UI", 8),
            bg="#1e293b",
            fg="#94a3b8",
        ).pack(anchor="w", pady=(2, 0))

        # 1. RTSP Connection Info
        conn_frame = tk.LabelFrame(
            self.root,
            text=" 1. Universal NVR RTSP Stream Addresses & Web Cast Studio ",
            font=("Segoe UI", 9, "bold"),
            bg="#0f172a",
            fg="#4ade80",
            padx=12,
            pady=4,
        )
        conn_frame.pack(fill=tk.X, padx=16, pady=(6, 3))

        self.main_rtsp_var = tk.StringVar(value=f"rtsp://{self.engine.lan_ip}:{self.engine.rtsp_port}/main")
        self.sub_rtsp_var = tk.StringVar(value=f"rtsp://{self.engine.lan_ip}:{self.engine.rtsp_port}/sub")
        self.web_remote_var = tk.StringVar(value=f"http://localhost:{self.engine.web_port}")

        self._add_copy_row(conn_frame, "Main Stream (HD):", self.main_rtsp_var, 0)
        self._add_copy_row(conn_frame, "Sub Stream (Grid 360p):", self.sub_rtsp_var, 1)
        self._add_copy_row(conn_frame, "Web Cast Studio URL:", self.web_remote_var, 2)

        # Active Session & Playback Control Bar
        status_frame = tk.Frame(self.root, bg="#1e293b", padx=12, pady=6)
        status_frame.pack(fill=tk.X, padx=16, pady=3)

        self.mode_badge = tk.Label(
            status_frame,
            text=" STARTING... ",
            font=("Segoe UI", 9, "bold"),
            bg="#f59e0b",
            fg="#0f172a",
            padx=8,
            pady=2,
        )
        self.mode_badge.pack(side=tk.LEFT)

        self.title_label = tk.Label(
            status_frame,
            text="Initializing Universal RTSP Server...",
            font=("Segoe UI", 9, "bold"),
            bg="#1e293b",
            fg="#f8fafc",
            padx=8,
        )
        self.title_label.pack(side=tk.LEFT)

        # Right-aligned playback controls inside Active Session bar
        tk.Button(
            status_frame,
            text="⏹ Stop / Standby",
            font=("Segoe UI", 8, "bold"),
            bg="#dc2626",
            fg="#ffffff",
            relief=tk.FLAT,
            padx=8,
            command=lambda: threading.Thread(target=self.engine.start_standby_stream, args=("Desktop App",), daemon=True).start(),
        ).pack(side=tk.RIGHT, padx=(4, 0))

        tk.Button(
            status_frame,
            text="⏩ +10s",
            font=("Segoe UI", 8, "bold"),
            bg="#334155",
            fg="#ffffff",
            relief=tk.FLAT,
            padx=7,
            command=lambda: self.engine.seek_stream(delta_sec=10, source="Desktop App"),
        ).pack(side=tk.RIGHT, padx=2)

        tk.Button(
            status_frame,
            text="⏪ -10s",
            font=("Segoe UI", 8, "bold"),
            bg="#334155",
            fg="#ffffff",
            relief=tk.FLAT,
            padx=7,
            command=lambda: self.engine.seek_stream(delta_sec=-10, source="Desktop App"),
        ).pack(side=tk.RIGHT, padx=2)

        self.pause_btn = tk.Button(
            status_frame,
            text="⏯ Pause / Resume",
            font=("Segoe UI", 8, "bold"),
            bg="#f59e0b",
            fg="#0f172a",
            relief=tk.FLAT,
            padx=9,
            command=self.on_toggle_pause,
        )
        self.pause_btn.pack(side=tk.RIGHT, padx=(0, 4))

        # 2. YouTube, Web Video & Local Video Loop
        yt_frame = tk.LabelFrame(
            self.root,
            text=" 2. Cast YouTube, Live TV, Web Video URL, or Local Movie (with Infinite Loop & Seek) ",
            font=("Segoe UI", 9, "bold"),
            bg="#0f172a",
            fg="#38bdf8",
            padx=12,
            pady=6,
        )
        yt_frame.pack(fill=tk.X, padx=16, pady=3)

        input_row = tk.Frame(yt_frame, bg="#0f172a")
        input_row.pack(fill=tk.X, pady=(2, 2))

        self.yt_entry = tk.Entry(
            input_row,
            font=("Segoe UI", 10),
            bg="#1e293b",
            fg="#ffffff",
            insertbackground="#ffffff",
            relief=tk.FLAT,
        )
        self.yt_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=4, padx=(0, 6))
        self.yt_entry.bind("<Return>", lambda e: self.on_stream_youtube())

        tk.Button(
            input_row,
            text="Paste",
            font=("Segoe UI", 8, "bold"),
            bg="#334155",
            fg="#ffffff",
            relief=tk.FLAT,
            padx=8,
            command=self.paste_clipboard,
        ).pack(side=tk.LEFT, ipady=3, padx=(0, 6))

        self.loop_video_var = tk.BooleanVar(value=False)
        tk.Checkbutton(
            input_row,
            text="🔁 Loop Video",
            variable=self.loop_video_var,
            font=("Segoe UI", 9, "bold"),
            bg="#0f172a",
            fg="#fde047",
            selectcolor="#1e293b",
            activebackground="#0f172a",
            activeforeground="#fde047",
            command=self.on_settings_change,
        ).pack(side=tk.LEFT, padx=(0, 6))

        tk.Button(
            input_row,
            text="▶ Stream Video to NVR",
            font=("Segoe UI", 9, "bold"),
            bg="#ef4444",
            fg="#ffffff",
            relief=tk.FLAT,
            padx=12,
            command=self.on_stream_youtube,
        ).pack(side=tk.LEFT, ipady=3, padx=(0, 6))

        tk.Button(
            input_row,
            text="📂 Local Video File...",
            font=("Segoe UI", 9, "bold"),
            bg="#0284c7",
            fg="#ffffff",
            relief=tk.FLAT,
            padx=10,
            command=self.on_stream_file,
        ).pack(side=tk.LEFT, ipady=3)

        # 3. Photo Gallery / Folder Slideshow Gadget
        gal_frame = tk.LabelFrame(
            self.root,
            text=" 3. Photo Gallery / Folder Slideshow Gadget (Set Timer, Shuffle Pictures & Cast to NVR) ",
            font=("Segoe UI", 9, "bold"),
            bg="#0f172a",
            fg="#10b981",
            padx=12,
            pady=6,
        )
        gal_frame.pack(fill=tk.X, padx=16, pady=3)

        gal_row = tk.Frame(gal_frame, bg="#0f172a")
        gal_row.pack(fill=tk.X, pady=(2, 2))

        self.gal_folder_var = tk.StringVar(value="")
        self.gal_entry = tk.Entry(
            gal_row,
            textvariable=self.gal_folder_var,
            font=("Segoe UI", 9),
            bg="#1e293b",
            fg="#ffffff",
            insertbackground="#ffffff",
            relief=tk.FLAT,
        )
        self.gal_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=4, padx=(0, 6))

        tk.Button(
            gal_row,
            text="📁 Folder...",
            font=("Segoe UI", 8, "bold"),
            bg="#334155",
            fg="#ffffff",
            relief=tk.FLAT,
            padx=8,
            command=self.on_pick_gallery_folder,
        ).pack(side=tk.LEFT, ipady=3, padx=(0, 4))

        tk.Button(
            gal_row,
            text="🖼️ Pictures...",
            font=("Segoe UI", 8, "bold"),
            bg="#334155",
            fg="#ffffff",
            relief=tk.FLAT,
            padx=8,
            command=self.on_pick_gallery_files,
        ).pack(side=tk.LEFT, ipady=3, padx=(0, 8))

        tk.Label(gal_row, text="Timer (s):", font=("Segoe UI", 9), bg="#0f172a", fg="#cbd5e1").pack(side=tk.LEFT)
        self.gal_timer_spin = tk.Spinbox(
            gal_row,
            from_=1,
            to=3600,
            width=4,
            font=("Segoe UI", 9, "bold"),
            bg="#1e293b",
            fg="#fde047",
            buttonbackground="#334155",
            relief=tk.FLAT,
        )
        self.gal_timer_spin.delete(0, tk.END)
        self.gal_timer_spin.insert(0, "5")
        self.gal_timer_spin.pack(side=tk.LEFT, ipady=2, padx=(4, 8))

        self.gal_shuffle_var = tk.BooleanVar(value=True)
        tk.Checkbutton(
            gal_row,
            text="🔀 Shuffle",
            variable=self.gal_shuffle_var,
            font=("Segoe UI", 9, "bold"),
            bg="#0f172a",
            fg="#a7f3d0",
            selectcolor="#1e293b",
            activebackground="#0f172a",
        ).pack(side=tk.LEFT, padx=(0, 6))

        tk.Button(
            gal_row,
            text="⏮",
            font=("Segoe UI", 8, "bold"),
            bg="#334155",
            fg="#ffffff",
            relief=tk.FLAT,
            padx=6,
            command=lambda: self.engine.step_gallery_slide(-1),
        ).pack(side=tk.LEFT, ipady=2, padx=(0, 3))

        tk.Button(
            gal_row,
            text="⏭",
            font=("Segoe UI", 8, "bold"),
            bg="#334155",
            fg="#ffffff",
            relief=tk.FLAT,
            padx=6,
            command=lambda: self.engine.step_gallery_slide(1),
        ).pack(side=tk.LEFT, ipady=2, padx=(0, 6))

        tk.Button(
            gal_row,
            text="▶ Start Slideshow",
            font=("Segoe UI", 9, "bold"),
            bg="#10b981",
            fg="#052e16",
            relief=tk.FLAT,
            padx=12,
            command=self.on_start_gallery_slideshow,
        ).pack(side=tk.LEFT, ipady=3)

        # 4. Multi-Monitor Desktop & Meeting Screen Share
        mon_frame = tk.LabelFrame(
            self.root,
            text=" 4. Multi-Monitor Desktop Mirroring (Choose All or Specific Monitors) & Meeting Share ",
            font=("Segoe UI", 9, "bold"),
            bg="#0f172a",
            fg="#a855f7",
            padx=12,
            pady=6,
        )
        mon_frame.pack(fill=tk.X, padx=16, pady=3)

        mon_top_row = tk.Frame(mon_frame, bg="#0f172a")
        mon_top_row.pack(fill=tk.X, pady=(0, 4))

        tk.Label(
            mon_top_row,
            text="Select Monitor(s):",
            font=("Segoe UI", 9, "bold"),
            bg="#0f172a",
            fg="#cbd5e1",
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
                bg="#1e293b",
                fg="#f8fafc",
                selectcolor="#0f172a",
                activebackground="#1e293b",
                activeforeground="#38bdf8",
                padx=8,
                pady=2,
                command=self.on_monitor_selection_change,
            )
            cb.pack(side=tk.LEFT, padx=(0, 8))

        tk.Button(
            mon_top_row,
            text="Select All",
            font=("Segoe UI", 8, "bold"),
            bg="#334155",
            fg="#ffffff",
            relief=tk.FLAT,
            padx=8,
            command=self.select_all_monitors,
        ).pack(side=tk.LEFT, padx=(4, 0))

        mon_action_row = tk.Frame(mon_frame, bg="#0f172a")
        mon_action_row.pack(fill=tk.X, pady=(2, 0))

        tk.Button(
            mon_action_row,
            text="🖥️ Mirror Selected Monitor(s) to NVR",
            font=("Segoe UI", 9, "bold"),
            bg="#2563eb",
            fg="#ffffff",
            relief=tk.FLAT,
            padx=14,
            pady=3,
            command=self.on_start_desktop_mirror,
        ).pack(side=tk.LEFT, padx=(0, 8))

        tk.Button(
            mon_action_row,
            text="💻 Share Tab / Window + Audio (Meeting Mode)",
            font=("Segoe UI", 9, "bold"),
            bg="#7c3aed",
            fg="#ffffff",
            relief=tk.FLAT,
            padx=14,
            pady=3,
            command=lambda: os.startfile(f"http://localhost:{self.engine.web_port}/?autoshare=1"),
        ).pack(side=tk.LEFT, padx=(0, 8))

        self.pc_audio_var = tk.BooleanVar(value=True)
        tk.Checkbutton(
            mon_action_row,
            text="🔊 PC Speaker Audio",
            variable=self.pc_audio_var,
            font=("Segoe UI", 9),
            bg="#0f172a",
            fg="#cbd5e1",
            selectcolor="#1e293b",
            command=self.on_settings_change,
        ).pack(side=tk.LEFT, padx=(4, 6))

        self.cursor_var = tk.BooleanVar(value=True)
        tk.Checkbutton(
            mon_action_row,
            text="🖱️ Cursor",
            variable=self.cursor_var,
            font=("Segoe UI", 9),
            bg="#0f172a",
            fg="#cbd5e1",
            selectcolor="#1e293b",
            command=self.on_settings_change,
        ).pack(side=tk.LEFT)

        # 5. Stream Flexibility & Quality Settings
        settings_frame = tk.LabelFrame(
            self.root,
            text=" 5. Flexibility & Stream Encoding Options ",
            font=("Segoe UI", 9, "bold"),
            bg="#0f172a",
            fg="#eab308",
            padx=12,
            pady=5,
        )
        settings_frame.pack(fill=tk.X, padx=16, pady=3)

        tk.Label(settings_frame, text="Resolution:", font=("Segoe UI", 9), bg="#0f172a", fg="#cbd5e1").pack(side=tk.LEFT)
        self.res_combo = ttk.Combobox(
            settings_frame,
            values=["1280x720", "1920x1080", "854x480"],
            width=10,
            state="readonly",
        )
        self.res_combo.set("1280x720")
        self.res_combo.pack(side=tk.LEFT, padx=(4, 12))
        self.res_combo.bind("<<ComboboxSelected>>", self.on_settings_change)

        tk.Label(settings_frame, text="Aspect Fit:", font=("Segoe UI", 9), bg="#0f172a", fg="#cbd5e1").pack(side=tk.LEFT)
        self.aspect_combo = ttk.Combobox(
            settings_frame,
            values=["fit (Letterbox)", "stretch (Fill 16:9)", "crop (Center 16:9)"],
            width=16,
            state="readonly",
        )
        self.aspect_combo.set("fit (Letterbox)")
        self.aspect_combo.pack(side=tk.LEFT, padx=(4, 12))
        self.aspect_combo.bind("<<ComboboxSelected>>", self.on_settings_change)

        tk.Label(settings_frame, text="FPS:", font=("Segoe UI", 9), bg="#0f172a", fg="#cbd5e1").pack(side=tk.LEFT)
        self.fps_combo = ttk.Combobox(
            settings_frame,
            values=["25", "30", "15"],
            width=4,
            state="readonly",
        )
        self.fps_combo.set("25")
        self.fps_combo.pack(side=tk.LEFT, padx=(4, 12))
        self.fps_combo.bind("<<ComboboxSelected>>", self.on_settings_change)

        tk.Label(settings_frame, text="Bitrate:", font=("Segoe UI", 9), bg="#0f172a", fg="#cbd5e1").pack(side=tk.LEFT)
        self.bitrate_combo = ttk.Combobox(
            settings_frame,
            values=["1000k", "1800k", "2500k", "4000k"],
            width=7,
            state="readonly",
        )
        self.bitrate_combo.set("1800k")
        self.bitrate_combo.pack(side=tk.LEFT, padx=(4, 12))
        self.bitrate_combo.bind("<<ComboboxSelected>>", self.on_settings_change)

        tk.Label(settings_frame, text="Audio:", font=("Segoe UI", 9), bg="#0f172a", fg="#cbd5e1").pack(side=tk.LEFT)
        self.audio_combo = ttk.Combobox(
            settings_frame,
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
        self.audio_combo.pack(side=tk.LEFT, padx=(4, 4))
        self.audio_combo.bind("<<ComboboxSelected>>", self.on_settings_change)

        # Log Console
        log_frame = tk.LabelFrame(
            self.root,
            text=" Live Stream & RTSP Server Logs ",
            font=("Segoe UI", 9, "bold"),
            bg="#0f172a",
            fg="#94a3b8",
            padx=10,
            pady=4,
        )
        log_frame.pack(fill=tk.BOTH, expand=True, padx=16, pady=(3, 10))

        self.log_text = tk.Text(
            log_frame,
            height=6,
            bg="#020617",
            fg="#38bdf8",
            font=("Consolas", 9),
            relief=tk.FLAT,
            state=tk.DISABLED,
        )
        self.log_text.pack(fill=tk.BOTH, expand=True)

    def _add_copy_row(self, parent, label_text: str, text_var: tk.StringVar, row: int):
        tk.Label(
            parent,
            text=label_text,
            font=("Segoe UI", 9, "bold"),
            bg="#0f172a",
            fg="#cbd5e1",
            width=22,
            anchor="w",
        ).grid(row=row, column=0, sticky="w", pady=1)

        entry = tk.Entry(
            parent,
            textvariable=text_var,
            font=("Consolas", 9, "bold"),
            bg="#1e293b",
            fg="#fde047",
            readonlybackground="#1e293b",
            relief=tk.FLAT,
            width=48,
            state="readonly",
        )
        entry.grid(row=row, column=1, sticky="ew", padx=8, pady=1, ipady=1)

        tk.Button(
            parent,
            text="Copy",
            font=("Segoe UI", 8, "bold"),
            bg="#334155",
            fg="#ffffff",
            relief=tk.FLAT,
            padx=10,
            command=lambda: self.copy_to_clipboard(text_var.get()),
        ).grid(row=row, column=2, pady=1)
        parent.grid_columnconfigure(1, weight=1)

    def on_toggle_pause(self):
        self.engine.toggle_pause(source="Desktop App")

    def on_pick_gallery_folder(self):
        folder = filedialog.askdirectory(title="Select Picture Folder for NVR Slideshow")
        if folder:
            self.gal_folder_var.set(folder)
            self.on_start_gallery_slideshow()

    def on_pick_gallery_files(self):
        files = filedialog.askopenfilenames(
            title="Select Pictures for NVR Slideshow",
            filetypes=[("Image Files", "*.jpg *.jpeg *.png *.bmp *.webp *.gif"), ("All Files", "*.*")],
        )
        if files:
            file_list = list(files)
            self.gal_folder_var.set(os.path.dirname(file_list[0]))
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
            "STANDBY": ("#22c55e", "#052e16"),
            "LOADING": ("#f59e0b", "#0f172a"),
            "YOUTUBE": ("#ef4444", "#ffffff"),
            "FILE": ("#3b82f6", "#ffffff"),
            "GALLERY": ("#10b981", "#052e16"),
            "SCREEN": ("#2563eb", "#ffffff"),
            "BROWSER": ("#8b5cf6", "#ffffff"),
        }
        bg, fg = colors.get(mode, ("#475569", "#ffffff"))
        self.mode_badge.configure(text=f" {mode} ", bg=bg, fg=fg)
        src = getattr(self.engine, "active_source", "")
        src_prefix = f"[{src}] " if src and src not in ("System", "System Standby") else ""
        self.title_label.configure(text=f"{src_prefix}{title}")

    def on_close(self):
        self.engine.shutdown()
        self.root.destroy()
