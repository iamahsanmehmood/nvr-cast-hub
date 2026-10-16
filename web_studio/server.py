import base64
import json
import os
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler
from desktop_app.engine import NVRCastEngine, APP_VERSION


class WebRemoteHandler(BaseHTTPRequestHandler):
    """
    Browser Web Cast Studio, Active Session Controller & Mobile Remote (v0.1.0-beta).
    Clean Whitish / Light Studio UI with crisp SVG vector icons.
    Provides:
      - Unified Active Session Bar (shows which app/extension is currently streaming + Pause/Resume/Seek/Stop)
      - Direct YouTube / Web Video Casting with Infinite Loop & Seek Sync
      - Rock-Solid Photo Gallery & Single-Picture Slideshow with Timer, Shuffle & Next/Prev Controls
      - Multi-Monitor PC Desktop Selection (Choose All or Specific Monitors)
      - Meeting-Style Browser Tab / Window / Screen Share with Audio
    """

    engine: NVRCastEngine = None
    ui_sync_callback = None
    browse_dialog_callback = None

    def log_message(self, format, *args):
        pass

    def _send_cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header(
            "Access-Control-Allow-Headers",
            "Content-Type, X-Session-Id, X-Video-Time, X-Video-Duration, X-Video-Paused, X-Video-Title",
        )
        self.send_header("Access-Control-Allow-Private-Network", "true")

    def do_OPTIONS(self):
        self.send_response(200)
        self._send_cors_headers()
        self.end_headers()

    def do_GET(self):
        if self.path.startswith("/api/status"):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self._send_cors_headers()
            self.end_headers()
            payload = self.engine.get_status_dict()
            self.wfile.write(json.dumps(payload).encode("utf-8"))
            return

        mon_checks_html = ""
        for m in self.engine.detect_monitors():
            if m["index"] == 0:
                continue
            checked = "checked" if (m["index"] in self.engine.selected_monitors or 0 in self.engine.selected_monitors) else ""
            mon_checks_html += (
                f'<label class="mon-pill">'
                f'<input type="checkbox" class="mon-cb" value="{m["index"]}" {checked}> '
                f'<span>{m["label"]}</span></label>'
            )

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>NVR Cast Studio v{APP_VERSION} — Universal RTSP Caster</title>
<style>
  * {{ box-sizing: border-box; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Inter, Roboto, sans-serif;
    background: #f8fafc;
    color: #0f172a;
    margin: 0;
    padding: 22px 18px 36px 18px;
    -webkit-font-smoothing: antialiased;
  }}
  .container {{ max-width: 1020px; margin: 0 auto; }}
  .topbar {{
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 14px;
    padding: 16px 22px;
    margin-bottom: 16px;
    box-shadow: 0 1px 3px rgba(15, 23, 42, 0.04);
    display: flex;
    justify-content: space-between;
    align-items: center;
    flex-wrap: wrap;
    gap: 12px;
  }}
  .brand {{ display: flex; align-items: center; gap: 12px; }}
  .brand-icon {{
    width: 38px;
    height: 38px;
    border-radius: 10px;
    background: #2563eb;
    color: #ffffff;
    display: flex;
    align-items: center;
    justify-content: center;
    box-shadow: 0 2px 6px rgba(37, 99, 235, 0.25);
  }}
  .brand h1 {{ margin: 0; font-size: 18px; font-weight: 700; color: #0f172a; }}
  .brand p {{ margin: 2px 0 0 0; font-size: 12.5px; color: #64748b; }}
  .rtsp-pills {{ display: flex; gap: 8px; flex-wrap: wrap; }}
  .rtsp-pill {{
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    padding: 6px 10px;
    font-size: 12px;
    color: #334155;
    display: flex;
    align-items: center;
    gap: 8px;
  }}
  .rtsp-pill code {{ font-family: Consolas, monospace; font-weight: 700; color: #0f172a; }}
  .session-bar {{
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 14px;
    padding: 16px 22px;
    margin-bottom: 16px;
    box-shadow: 0 1px 3px rgba(15, 23, 42, 0.04);
    display: flex;
    justify-content: space-between;
    align-items: center;
    flex-wrap: wrap;
    gap: 14px;
  }}
  .session-info {{ flex: 1; min-width: 260px; }}
  .session-meta {{ display: flex; align-items: center; gap: 10px; margin-bottom: 5px; font-size: 12px; color: #64748b; }}
  .mode-badge {{
    background: #dcfce7;
    color: #15803d;
    font-weight: 700;
    font-size: 11px;
    padding: 3px 9px;
    border-radius: 6px;
    letter-spacing: 0.3px;
  }}
  .session-title {{ font-size: 15px; font-weight: 700; color: #0f172a; margin-bottom: 2px; }}
  .session-pos {{ font-size: 12.5px; font-weight: 600; color: #2563eb; }}
  .session-controls {{ display: flex; gap: 6px; flex-wrap: wrap; align-items: center; }}
  .grid-2col {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(440px, 1fr));
    gap: 16px;
    margin-bottom: 16px;
  }}
  .card {{
    background: #ffffff;
    border-radius: 14px;
    padding: 20px 22px;
    border: 1px solid #e2e8f0;
    box-shadow: 0 1px 3px rgba(15, 23, 42, 0.04);
  }}
  .card-header {{
    display: flex;
    align-items: center;
    gap: 10px;
    margin-bottom: 6px;
  }}
  .card-icon {{
    width: 30px;
    height: 30px;
    border-radius: 8px;
    background: #eff6ff;
    color: #2563eb;
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
  }}
  .card h3 {{ margin: 0; font-size: 15px; font-weight: 700; color: #0f172a; }}
  p.sub {{ margin: 0 0 14px 0; color: #64748b; font-size: 12.5px; line-height: 1.45; }}
  .row {{ display: flex; gap: 8px; margin-bottom: 10px; flex-wrap: wrap; align-items: center; }}
  input[type=text], input[type=number], select {{
    padding: 8.5px 11px;
    border-radius: 8px;
    border: 1px solid #cbd5e1;
    background: #f8fafc;
    color: #0f172a;
    font-size: 13px;
    outline: none;
    transition: border-color 0.15s;
  }}
  input[type=text]:focus, input[type=number]:focus, select:focus {{
    border-color: #2563eb;
    background: #ffffff;
  }}
  input[type=text] {{ flex: 1; min-width: 190px; }}
  button {{
    font-family: inherit;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 6px;
    cursor: pointer;
    transition: all 0.15s ease;
  }}
  .btn-primary {{
    padding: 9.5px 16px;
    border-radius: 8px;
    border: 1px solid #1d4ed8;
    background: #2563eb;
    color: #ffffff;
    font-weight: 600;
    font-size: 13px;
    box-shadow: 0 1px 2px rgba(37, 99, 235, 0.18);
  }}
  .btn-primary:hover {{ background: #1d4ed8; }}
  .btn-secondary {{
    padding: 8.5px 13px;
    border-radius: 8px;
    border: 1px solid #cbd5e1;
    background: #ffffff;
    color: #0f172a;
    font-weight: 600;
    font-size: 12.5px;
  }}
  .btn-secondary:hover {{ background: #f1f5f9; border-color: #94a3b8; }}
  .btn-danger {{
    padding: 8.5px 13px;
    border-radius: 8px;
    border: 1px solid #fecaca;
    background: #fef2f2;
    color: #dc2626;
    font-weight: 600;
    font-size: 12.5px;
  }}
  .btn-danger:hover {{ background: #fee2e2; }}
  .check-pill {{
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-size: 12.5px;
    font-weight: 600;
    color: #334155;
    padding: 6px 10px;
    border-radius: 8px;
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    cursor: pointer;
    user-select: none;
  }}
  .mon-list {{ display: flex; flex-direction: column; gap: 7px; margin: 10px 0 12px 0; }}
  .mon-pill {{
    background: #f8fafc;
    border: 1px solid #cbd5e1;
    padding: 9px 12px;
    border-radius: 8px;
    font-size: 13px;
    font-weight: 500;
    color: #0f172a;
    cursor: pointer;
    display: flex;
    align-items: center;
    gap: 9px;
  }}
  .mon-pill:hover {{ background: #f1f5f9; }}
  .settings-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
    gap: 12px;
  }}
  .settings-grid label {{
    font-size: 12px;
    font-weight: 600;
    color: #475569;
    display: flex;
    flex-direction: column;
    gap: 5px;
  }}
  video#previewVideo {{
    width: 100%;
    max-height: 240px;
    background: #0f172a;
    border-radius: 10px;
    border: 1px solid #cbd5e1;
    display: none;
    margin-top: 12px;
  }}
  svg {{
    width: 15px;
    height: 15px;
    stroke: currentColor;
    stroke-width: 2;
    stroke-linecap: round;
    stroke-linejoin: round;
    fill: none;
    flex-shrink: 0;
  }}
</style>
</head>
<body>
<div class="container">
  <!-- Top Bar -->
  <div class="topbar">
    <div class="brand">
      <div class="brand-icon">
        <svg viewBox="0 0 24 24" style="width:20px;height:20px;"><path d="M2 16.1A5 5 0 0 1 5.9 20M2 12.05A9 9 0 0 1 9.95 20M2 8V6a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-6"/><line x1="2" y1="20" x2="2.01" y2="20"/></svg>
      </div>
      <div>
        <h1>NVR Cast Studio <span style="font-size:12px;font-weight:600;color:#2563eb;background:#eff6ff;padding:2px 8px;border-radius:99px;margin-left:4px;">v{APP_VERSION}</span></h1>
        <p>Universal RTSP Video, Photo Slideshow &amp; Multi-Monitor Caster for Hikvision, Dahua, Uniview, Reolink &amp; ONVIF NVRs</p>
      </div>
    </div>
    <div class="rtsp-pills">
      <div class="rtsp-pill">
        <span>Main HD:</span>
        <code id="mainRtspCode">rtsp://{self.engine.lan_ip}:{self.engine.rtsp_port}/main</code>
        <button class="btn-secondary" style="padding:3px 8px;font-size:11px;" onclick="copyText('rtsp://{self.engine.lan_ip}:{self.engine.rtsp_port}/main', this)">Copy</button>
      </div>
      <div class="rtsp-pill">
        <span>Sub Grid:</span>
        <code id="subRtspCode">rtsp://{self.engine.lan_ip}:{self.engine.rtsp_port}/sub</code>
        <button class="btn-secondary" style="padding:3px 8px;font-size:11px;" onclick="copyText('rtsp://{self.engine.lan_ip}:{self.engine.rtsp_port}/sub', this)">Copy</button>
      </div>
    </div>
  </div>

  <!-- Unified Active Session Bar -->
  <div class="session-bar">
    <div class="session-info">
      <div class="session-meta">
        <span class="mode-badge" id="modeTxt">{self.engine.current_mode}</span>
        <span>Started By: <strong id="sourceTxt" style="color:#0f172a;">{self.engine.active_source}</strong></span>
      </div>
      <div class="session-title" id="titleTxt">{self.engine.current_title}</div>
      <div class="session-pos" id="timeTxt">Stream active on NVR</div>
    </div>
    <div class="session-controls">
      <button class="btn-secondary" onclick="togglePause()" id="btnPauseResume">
        <svg viewBox="0 0 24 24"><polygon points="5 3 19 12 5 21 5 3"/></svg>
        <span id="pauseBtnText">Pause / Resume</span>
      </button>
      <button class="btn-secondary" onclick="seekDelta(-30)" title="Rewind 30s">-30s</button>
      <button class="btn-secondary" onclick="seekDelta(-10)" title="Rewind 10s">
        <svg viewBox="0 0 24 24"><polygon points="11 19 2 12 11 5 11 19"/><polygon points="22 19 13 12 22 5 22 19"/></svg>
        -10s
      </button>
      <button class="btn-secondary" onclick="seekDelta(10)" title="Forward 10s">
        +10s
        <svg viewBox="0 0 24 24"><polygon points="13 19 22 12 13 5 13 19"/><polygon points="2 19 11 12 2 5 2 19"/></svg>
      </button>
      <button class="btn-secondary" onclick="seekDelta(30)" title="Forward 30s">+30s</button>
      <button class="btn-danger" onclick="stopCast()">
        <svg viewBox="0 0 24 24"><rect x="4" y="4" width="16" height="16" rx="2"/></svg>
        Stop / Standby
      </button>
    </div>
  </div>

  <!-- Row 1: Video Streamer + Photo Gallery Slideshow -->
  <div class="grid-2col">
    <!-- Card 1: YouTube & Local Video -->
    <div class="card">
      <div class="card-header">
        <div class="card-icon">
          <svg viewBox="0 0 24 24"><rect x="2" y="4" width="20" height="16" rx="2"/><polygon points="10 9 15 12 10 15 10 9"/></svg>
        </div>
        <h3>1. YouTube, Web Stream &amp; Local Video Caster</h3>
      </div>
      <p class="sub">Stream any YouTube video, live stream URL, search query, or local movie with instant seeking and infinite 24/7 loop.</p>
      <div class="row">
        <input type="text" id="ytInput" placeholder="Paste YouTube URL, search phrase, or local file path...">
      </div>
      <div class="row" style="justify-content:space-between;">
        <div style="display:flex;gap:8px;align-items:center;">
          <label style="font-size:12.5px;font-weight:600;color:#475569;">Start (s):
            <input type="number" id="startSec" style="width:74px;margin-left:4px;" min="0" value="0">
          </label>
          <label class="check-pill">
            <input type="checkbox" id="chkLoopVideo" onchange="applySettings()">
            <span>Loop Video Continuously</span>
          </label>
        </div>
      </div>
      <div class="row" style="margin-top:12px;margin-bottom:0;">
        <button class="btn-primary" style="flex:1.6;" onclick="castYT()">
          <svg viewBox="0 0 24 24"><polygon points="5 3 19 12 5 21 5 3"/></svg>
          Stream Video to NVR
        </button>
        <button class="btn-secondary" style="flex:1;" onclick="pickHostFile('video')">
          <svg viewBox="0 0 24 24"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>
          Browse Video File...
        </button>
      </div>
    </div>

    <!-- Card 2: Photo Gallery & Single Picture Slideshow -->
    <div class="card">
      <div class="card-header">
        <div class="card-icon">
          <svg viewBox="0 0 24 24"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg>
        </div>
        <h3>2. Picture &amp; Gallery Slideshow Studio</h3>
      </div>
      <p class="sub">Display a single picture or run a smooth folder slideshow with configurable timer, random shuffle, and instant slide stepping.</p>
      <div class="row">
        <input type="text" id="galleryFolder" placeholder="Select a picture folder or individual image files..." value="{self.engine.gallery_folder}">
        <button class="btn-secondary" onclick="pickHostFile('folder')" title="Select a Folder of Pictures">
          <svg viewBox="0 0 24 24"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>
          Folder...
        </button>
        <button class="btn-secondary" onclick="pickHostFile('pictures')" title="Select One or Multiple Picture Files">
          <svg viewBox="0 0 24 24"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg>
          Pictures...
        </button>
      </div>
      <div class="row">
        <label style="font-size:12.5px;font-weight:600;color:#475569;">Timer (sec):
          <input type="number" id="galleryTimer" value="{self.engine.gallery_interval}" min="1" max="3600" style="width:70px;margin-left:4px;">
        </label>
        <label class="check-pill">
          <input type="checkbox" id="chkGalleryShuffle">
          <span>Shuffle Order</span>
        </label>
        <button class="btn-secondary" onclick="stepGallery(-1)">
          <svg viewBox="0 0 24 24"><polyline points="15 18 9 12 15 6"/></svg>
          Prev
        </button>
        <button class="btn-secondary" onclick="stepGallery(1)">
          Next
          <svg viewBox="0 0 24 24"><polyline points="9 18 15 12 9 6"/></svg>
        </button>
      </div>
      <div class="row" style="margin-top:12px;margin-bottom:0;">
        <button class="btn-primary" style="width:100%;" onclick="startGallery()">
          <svg viewBox="0 0 24 24"><polygon points="5 3 19 12 5 21 5 3"/></svg>
          Start Picture / Slideshow on NVR
        </button>
      </div>
    </div>
  </div>

  <!-- Row 2: Multi-Monitor Desktop Mirroring + Meeting Screen Share -->
  <div class="grid-2col">
    <!-- Card 3: Multi-Monitor Desktop Mirror -->
    <div class="card">
      <div class="card-header">
        <div class="card-icon">
          <svg viewBox="0 0 24 24"><rect x="2" y="3" width="20" height="14" rx="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/></svg>
        </div>
        <h3>3. Multi-Monitor PC Desktop Mirroring</h3>
      </div>
      <p class="sub">Mirror any individual monitor or all monitors combined directly to your NVR with live PC speaker audio.</p>
      <div class="row">
        <button class="btn-secondary" onclick="selectMonitors('all')">Select All Displays</button>
        <button class="btn-secondary" onclick="selectMonitors(1)">Monitor 1 Only</button>
        <button class="btn-secondary" onclick="selectMonitors(2)">Monitor 2 Only</button>
      </div>
      <div class="mon-list" id="monList">
        {mon_checks_html}
      </div>
      <div class="row" style="margin-bottom:12px;">
        <label class="check-pill">
          <input type="checkbox" id="chkAudio" checked onchange="applySettings()">
          <span>PC Speaker Audio</span>
        </label>
        <label class="check-pill">
          <input type="checkbox" id="chkCursor" checked onchange="applySettings()">
          <span>Show Mouse Pointer</span>
        </label>
      </div>
      <button class="btn-primary" style="width:100%;" onclick="castDesktop()">
        <svg viewBox="0 0 24 24"><rect x="2" y="3" width="20" height="14" rx="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/></svg>
        Mirror Selected Monitor(s) to NVR
      </button>
    </div>

    <!-- Card 4: Meeting-Style Tab / Window Share -->
    <div class="card">
      <div class="card-header">
        <div class="card-icon">
          <svg viewBox="0 0 24 24"><path d="M13 3H4a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-3"/><polyline points="8 21 12 17 16 21"/><line x1="12" y1="17" x2="12" y2="21"/></svg>
        </div>
        <h3>4. Meeting-Style Browser Tab / Window Share</h3>
      </div>
      <p class="sub">Works like Google Meet or Zoom: choose a single browser tab (with tab audio), an application window, or a display.</p>
      <button class="btn-primary" style="width:100%;" onclick="startMeetingShare()">
        <svg viewBox="0 0 24 24"><path d="M2 16.1A5 5 0 0 1 5.9 20M2 12.05A9 9 0 0 1 9.95 20M2 8V6a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-6"/><line x1="2" y1="20" x2="2.01" y2="20"/></svg>
        Choose Browser Tab / Window / Screen to Share
      </button>
      <video id="previewVideo" autoplay muted playsinline></video>
    </div>
  </div>

  <!-- Card 5: Stream Quality & Encoding Settings -->
  <div class="card">
    <div class="card-header" style="margin-bottom:12px;">
      <div class="card-icon">
        <svg viewBox="0 0 24 24"><line x1="4" y1="21" x2="4" y2="14"/><line x1="4" y1="10" x2="4" y2="3"/><line x1="12" y1="21" x2="12" y2="12"/><line x1="12" y1="8" x2="12" y2="3"/><line x1="20" y1="21" x2="20" y2="16"/><line x1="20" y1="12" x2="20" y2="3"/><line x1="1" y1="14" x2="7" y2="14"/><line x1="9" y1="8" x2="15" y2="8"/><line x1="17" y1="16" x2="23" y2="16"/></svg>
      </div>
      <h3>5. Stream Quality &amp; NVR Encoding Settings</h3>
    </div>
    <div class="settings-grid">
      <label>Main Stream Resolution
        <select id="selRes" onchange="applySettings()">
          <option value="1280x720">1280x720 (720p HD)</option>
          <option value="1920x1080">1920x1080 (1080p Full HD)</option>
          <option value="854x480">854x480 (480p Fast)</option>
        </select>
      </label>
      <label>Aspect Ratio Fit
        <select id="selAspect" onchange="applySettings()">
          <option value="fit">Fit / Letterbox (Keep Aspect)</option>
          <option value="stretch">Stretch to Fill Screen</option>
          <option value="crop">Center Crop to 16:9</option>
        </select>
      </label>
      <label>Frame Rate (FPS)
        <select id="selFps" onchange="applySettings()">
          <option value="25">25 FPS (PAL NVR Std)</option>
          <option value="30">30 FPS (Smooth)</option>
          <option value="15">15 FPS (Low CPU)</option>
        </select>
      </label>
      <label>Video Bitrate
        <select id="selBitrate" onchange="applySettings()">
          <option value="1800k">1800 kbps (Balanced)</option>
          <option value="1000k">1000 kbps (Light)</option>
          <option value="2500k">2500 kbps (High)</option>
          <option value="4000k">4000 kbps (Ultra)</option>
        </select>
      </label>
      <label>NVR Audio Codec
        <select id="selAudio" onchange="applySettings()">
          <option value="pcm_mulaw">G.711u (pcm_mulaw NVR)</option>
          <option value="pcm_alaw">G.711a (pcm_alaw NVR)</option>
          <option value="aac">AAC 16kHz Mono</option>
          <option value="aac_hq">AAC 44.1kHz Stereo</option>
          <option value="none">Mute (Video Only)</option>
        </select>
      </label>
    </div>
  </div>
</div>

<script>
let mediaRecorder = null;
let displayStream = null;
let sendChain = Promise.resolve();

function copyText(txt, btn) {{
  navigator.clipboard.writeText(txt).catch(() => {{}});
  if (btn) {{
    const orig = btn.textContent;
    btn.textContent = 'Copied!';
    setTimeout(() => {{ btn.textContent = orig; }}, 1200);
  }}
}}

function selectMonitors(target) {{
  const cbs = document.querySelectorAll('.mon-cb');
  cbs.forEach(cb => {{
    if (target === 'all') cb.checked = true;
    else cb.checked = (parseInt(cb.value, 10) === target);
  }});
}}

function getCheckedMonitors() {{
  const cbs = document.querySelectorAll('.mon-cb');
  const selected = [];
  cbs.forEach(cb => {{ if (cb.checked) selected.push(parseInt(cb.value, 10)); }});
  return selected.length ? selected : [1];
}}

async function applySettings() {{
  const payload = {{
    main_res: document.getElementById('selRes').value,
    aspect_mode: document.getElementById('selAspect').value,
    fps: parseInt(document.getElementById('selFps').value, 10),
    video_bitrate: document.getElementById('selBitrate').value,
    audio_codec: document.getElementById('selAudio').value,
    capture_pc_audio: document.getElementById('chkAudio').checked,
    show_cursor: document.getElementById('chkCursor').checked,
    loop_video: document.getElementById('chkLoopVideo').checked,
    selected_monitors: getCheckedMonitors()
  }};
  try {{
    await fetch('/api/settings', {{
      method: 'POST',
      headers: {{ 'Content-Type': 'application/json' }},
      body: JSON.stringify(payload)
    }});
  }} catch (_) {{}}
}}

async function togglePause() {{
  try {{
    await fetch('/api/player_sync', {{
      method: 'POST',
      headers: {{ 'Content-Type': 'application/json' }},
      body: JSON.stringify({{ event: 'toggle_pause', source: 'Web Studio' }})
    }});
    setTimeout(refreshStatus, 300);
  }} catch (_) {{}}
}}

async function seekDelta(delta) {{
  try {{
    await fetch('/api/player_sync', {{
      method: 'POST',
      headers: {{ 'Content-Type': 'application/json' }},
      body: JSON.stringify({{ event: 'seek', delta_sec: delta, source: 'Web Studio' }})
    }});
    setTimeout(refreshStatus, 350);
  }} catch (_) {{}}
}}

async function castYT() {{
  const url = document.getElementById('ytInput').value.trim();
  const start_sec = parseInt(document.getElementById('startSec').value || '0', 10) || 0;
  const loop = document.getElementById('chkLoopVideo').checked;
  if (!url) return alert('Please paste a YouTube URL, video link, local file path, or search query.');
  stopLocalMediaCapture();
  await applySettings();
  await fetch('/api/youtube', {{
    method: 'POST',
    headers: {{ 'Content-Type': 'application/json' }},
    body: JSON.stringify({{ url, start_sec, loop, source: 'Web Studio' }})
  }});
  setTimeout(refreshStatus, 500);
}}

async function pickHostFile(kind) {{
  try {{
    const r = await fetch('/api/browse_dialog', {{
      method: 'POST',
      headers: {{ 'Content-Type': 'application/json' }},
      body: JSON.stringify({{ kind }})
    }});
    const d = await r.json();
    if (d && d.path) {{
      if (kind === 'folder' || kind === 'pictures') {{
        document.getElementById('galleryFolder').value = d.path;
        startGallery();
      }} else if (kind === 'video') {{
        document.getElementById('ytInput').value = d.path;
        const loop = document.getElementById('chkLoopVideo').checked;
        await fetch('/api/file', {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify({{ filepath: d.path, loop, source: 'Web Studio' }})
        }});
        setTimeout(refreshStatus, 500);
      }}
    }}
  }} catch (_) {{}}
}}

async function startGallery() {{
  const folder = document.getElementById('galleryFolder').value.trim();
  const interval_sec = parseInt(document.getElementById('galleryTimer').value || '5', 10) || 5;
  const shuffle = document.getElementById('chkGalleryShuffle').checked;
  if (!folder) return alert('Select a picture folder or picture files first!');
  stopLocalMediaCapture();
  await applySettings();
  await fetch('/api/gallery', {{
    method: 'POST',
    headers: {{ 'Content-Type': 'application/json' }},
    body: JSON.stringify({{ action: 'start', folder, interval_sec, shuffle, source: 'Web Studio' }})
  }});
  setTimeout(refreshStatus, 400);
}}

async function stepGallery(step) {{
  await fetch('/api/gallery', {{
    method: 'POST',
    headers: {{ 'Content-Type': 'application/json' }},
    body: JSON.stringify({{ action: 'step', step }})
  }});
  setTimeout(refreshStatus, 250);
}}

async function castDesktop() {{
  stopLocalMediaCapture();
  await applySettings();
  const monitors = getCheckedMonitors();
  await fetch('/api/screen', {{
    method: 'POST',
    headers: {{ 'Content-Type': 'application/json' }},
    body: JSON.stringify({{ monitors, source: 'Web Studio' }})
  }});
  setTimeout(refreshStatus, 400);
}}

async function stopCast() {{
  stopLocalMediaCapture();
  await fetch('/api/standby', {{
    method: 'POST',
    headers: {{ 'Content-Type': 'application/json' }},
    body: JSON.stringify({{ source: 'Web Studio' }})
  }});
  setTimeout(refreshStatus, 400);
}}

function stopLocalMediaCapture() {{
  if (window.__meetingWorker) {{
    try {{ window.__meetingWorker.terminate(); }} catch (_) {{}}
    window.__meetingWorker = null;
  }}
  if (displayStream) {{
    displayStream.getTracks().forEach(t => t.stop());
    displayStream = null;
  }}
  const vid = document.getElementById('previewVideo');
  vid.style.display = 'none';
  vid.srcObject = null;
}}

async function startMeetingShare() {{
  if (!navigator.mediaDevices || !navigator.mediaDevices.getDisplayMedia) {{
    if (window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1') {{
      window.location.href = 'http://localhost:' + window.location.port + '/?autoshare=1';
      return;
    }}
    alert('Screen sharing requires http://localhost:8090 in Chrome or Edge.');
    return;
  }}

  try {{
    stopLocalMediaCapture();
    await applySettings();
    displayStream = await navigator.mediaDevices.getDisplayMedia({{
      video: {{ width: {{ ideal: 1280 }}, height: {{ ideal: 720 }}, frameRate: {{ ideal: 25, max: 30 }} }},
      audio: true
    }});

    const vid = document.getElementById('previewVideo');
    vid.srcObject = displayStream;
    vid.style.display = 'block';
    await vid.play().catch(() => {{}});

    const videoTrack = displayStream.getVideoTracks()[0];
    const label = videoTrack ? (videoTrack.label || 'Browser Screen Share') : 'Browser Screen Share';
    const sessionId = 'web_' + Date.now();

    await fetch('/api/browser_cast/start', {{
      method: 'POST',
      headers: {{ 'Content-Type': 'application/json' }},
      body: JSON.stringify({{ label, source: 'Web Studio (Meeting Share)', session_id: sessionId }})
    }});

    const canvas = document.createElement('canvas');
    canvas.width = 1280;
    canvas.height = 720;
    const ctx = canvas.getContext('2d');
    let inFlight = false;

    const blob = new Blob(['setInterval(() => postMessage(1), 45);'], {{ type: 'application/javascript' }});
    const worker = new Worker(URL.createObjectURL(blob));
    window.__meetingWorker = worker;

    worker.onmessage = () => {{
      if (inFlight || !displayStream || vid.readyState < 2) return;
      inFlight = true;
      const vw = vid.videoWidth || 1280;
      const vh = vid.videoHeight || 720;
      ctx.fillStyle = '#0f172a';
      ctx.fillRect(0, 0, 1280, 720);
      const scale = Math.min(1280 / vw, 720 / vh);
      const dw = Math.round(vw * scale);
      const dh = Math.round(vh * scale);
      const dx = Math.round((1280 - dw) / 2);
      const dy = Math.round((720 - dh) / 2);
      ctx.drawImage(vid, dx, dy, dw, dh);
      canvas.toBlob((jpgBlob) => {{
        if (!jpgBlob) {{ inFlight = false; return; }}
        fetch('/api/browser_cast/frame', {{
          method: 'POST',
          headers: {{ 'X-Session-Id': sessionId }},
          body: jpgBlob
        }})
          .then(r => r.json())
          .then(res => {{
            if (res && res.stop) stopLocalMediaCapture();
          }})
          .catch(() => {{}})
          .finally(() => {{ inFlight = false; }});
      }}, 'image/jpeg', 0.82);
    }};

    videoTrack.onended = () => {{
      stopCast();
    }};

    setTimeout(refreshStatus, 500);
  }} catch (err) {{
    console.error('Meeting share cancelled:', err);
  }}
}}

async function refreshStatus() {{
  try {{
    const r = await fetch('/api/status');
    const d = await r.json();
    const modeEl = document.getElementById('modeTxt');
    modeEl.textContent = d.mode + (d.is_paused ? ' • PAUSED' : '');
    if (d.is_paused) {{
      modeEl.style.background = '#fef3c7';
      modeEl.style.color = '#b45309';
    }} else {{
      modeEl.style.background = '#dcfce7';
      modeEl.style.color = '#15803d';
    }}
    const pauseTxt = document.getElementById('pauseBtnText');
    if (pauseTxt) pauseTxt.textContent = d.is_paused ? 'Resume Stream' : 'Pause Stream';
    document.getElementById('sourceTxt').textContent = d.active_source || 'System';
    document.getElementById('titleTxt').textContent = d.title;
    const tSpan = document.getElementById('timeTxt');
    if (d.mode === 'YOUTUBE' || d.mode === 'FILE' || (d.mode === 'BROWSER' && (d.playback_sec > 0 || d.duration_sec > 0))) {{
      const m = Math.floor((d.playback_sec || 0) / 60);
      const s = String((d.playback_sec || 0) % 60).padStart(2, '0');
      let durStr = '';
      if (d.duration_sec > 0) {{
        const dm = Math.floor(d.duration_sec / 60);
        const ds = String(d.duration_sec % 60).padStart(2, '0');
        durStr = ` / ${{dm}}:${{ds}}`;
      }}
      tSpan.textContent = `Playback Position: ${{m}}:${{s}}${{durStr}}${{d.loop_video ? '  •  Loop Active' : ''}}`;
    }} else if (d.mode === 'GALLERY' && d.gallery) {{
      tSpan.textContent = `Slide ${{d.gallery.index + 1}} of ${{d.gallery.count}}  •  Timer: ${{d.gallery.interval}}s${{d.gallery.shuffle ? '  •  Shuffle' : ''}}`;
    }} else {{
      tSpan.textContent = `Broadcasting live on ${{d.rtsp_main}}`;
    }}
  }} catch (_) {{}}
}}

setInterval(refreshStatus, 1400);

window.addEventListener('DOMContentLoaded', () => {{
  refreshStatus();
  const params = new URLSearchParams(window.location.search);
  if (params.get('autoshare') === '1') {{
    setTimeout(startMeetingShare, 400);
  }}
}});
</script>
</body>
</html>"""
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self._send_cors_headers()
        self.end_headers()
        self.wfile.write(html.encode("utf-8"))

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        raw_body = self.rfile.read(length) if length > 0 else b""

        if self.path == "/api/browser_cast/frame":
            ctype = self.headers.get("Content-Type", "")
            jpeg_bytes = b""
            meta = {}
            if "application/json" in ctype:
                try:
                    j = json.loads(raw_body.decode("utf-8")) if raw_body else {}
                    b64_str = j.get("frame", "")
                    if "," in b64_str:
                        b64_str = b64_str.split(",", 1)[1]
                    if b64_str:
                        jpeg_bytes = base64.b64decode(b64_str)
                    meta = {
                        "session_id": j.get("session_id", ""),
                        "time_sec": j.get("time_sec"),
                        "duration_sec": j.get("duration_sec"),
                        "paused": j.get("paused"),
                        "title": j.get("title", ""),
                    }
                except Exception:
                    pass
            else:
                jpeg_bytes = raw_body
                raw_title = self.headers.get("X-Video-Title", "")
                meta = {
                    "session_id": self.headers.get("X-Session-Id", ""),
                    "time_sec": self.headers.get("X-Video-Time"),
                    "duration_sec": self.headers.get("X-Video-Duration"),
                    "paused": (
                        self.headers.get("X-Video-Paused") == "1"
                        if self.headers.get("X-Video-Paused") is not None
                        else None
                    ),
                    "title": urllib.parse.unquote(raw_title) if raw_title else "",
                }

            res = self.engine.push_browser_frame(jpeg_bytes, meta)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self._send_cors_headers()
            self.end_headers()
            self.wfile.write(json.dumps(res).encode("utf-8"))
            return

        if self.path == "/api/browser_cast/chunk":
            ok = self.engine.push_browser_chunk(raw_body)
            self.send_response(200 if ok else 409)
            self.send_header("Content-Type", "application/json")
            self._send_cors_headers()
            self.end_headers()
            self.wfile.write(b'{"ok": true}' if ok else b'{"ok": false}')
            return

        try:
            data = json.loads(raw_body.decode("utf-8")) if raw_body else {}
        except Exception:
            data = {}

        if self.path == "/api/browse_dialog":
            kind = data.get("kind", "folder")
            chosen_path = ""
            if WebRemoteHandler.browse_dialog_callback:
                chosen_path = WebRemoteHandler.browse_dialog_callback(kind) or ""
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self._send_cors_headers()
            self.end_headers()
            self.wfile.write(json.dumps({"ok": bool(chosen_path), "path": chosen_path}).encode("utf-8"))
            return

        if self.path == "/api/settings":
            if "main_res" in data:
                self.engine.main_res = data["main_res"]
            if "aspect_mode" in data:
                self.engine.aspect_mode = data["aspect_mode"]
            if "fps" in data:
                self.engine.fps = int(data["fps"])
            if "video_bitrate" in data:
                self.engine.video_bitrate = data["video_bitrate"]
            if "audio_codec" in data:
                self.engine.audio_codec = data["audio_codec"]
            if "capture_pc_audio" in data:
                self.engine.capture_pc_audio = bool(data["capture_pc_audio"])
            if "show_cursor" in data:
                self.engine.show_cursor = bool(data["show_cursor"])
            if "loop_video" in data:
                self.engine.loop_video = bool(data["loop_video"])
            if "selected_monitors" in data and isinstance(data["selected_monitors"], list):
                self.engine.selected_monitors = [int(x) for x in data["selected_monitors"]]
            if WebRemoteHandler.ui_sync_callback:
                WebRemoteHandler.ui_sync_callback()

        elif self.path == "/api/youtube":
            url = data.get("url", "").strip()
            start_sec = int(data.get("start_sec", 0) or 0)
            loop = data.get("loop")
            source = data.get("source", "Web / Extension")
            if url:
                if os.path.isfile(url):
                    self.engine.start_local_file_stream(url, start_sec=start_sec, loop=loop, source=source)
                else:
                    self.engine.start_youtube_stream(url, start_sec=start_sec, loop=loop, source=source)
            if WebRemoteHandler.ui_sync_callback:
                WebRemoteHandler.ui_sync_callback()

        elif self.path == "/api/file":
            filepath = data.get("filepath", "").strip()
            start_sec = int(data.get("start_sec", 0) or 0)
            loop = data.get("loop")
            source = data.get("source", "Web Studio")
            if filepath:
                self.engine.start_local_file_stream(filepath, start_sec=start_sec, loop=loop, source=source)
            if WebRemoteHandler.ui_sync_callback:
                WebRemoteHandler.ui_sync_callback()

        elif self.path == "/api/player_sync":
            ev = data.get("event", "")
            source = data.get("source", "Chrome Extension")
            if ev == "seek":
                target_sec = data.get("time_sec")
                delta_sec = data.get("delta_sec")
                self.engine.seek_stream(
                    target_sec=int(target_sec) if target_sec is not None else None,
                    delta_sec=int(delta_sec) if delta_sec is not None else None,
                    source=source,
                )
            elif ev == "pause":
                self.engine.toggle_pause(force_state=True, source=source)
            elif ev in ("play", "resume"):
                self.engine.toggle_pause(force_state=False, source=source)
            elif ev == "toggle_pause":
                self.engine.toggle_pause(source=source)
            if WebRemoteHandler.ui_sync_callback:
                WebRemoteHandler.ui_sync_callback()

        elif self.path == "/api/gallery":
            action = data.get("action", "start")
            if action == "step":
                self.engine.step_gallery_slide(int(data.get("step", 1)))
            else:
                folder = data.get("folder", "")
                interval_sec = int(data.get("interval_sec", 5) or 5)
                shuffle = bool(data.get("shuffle", False))
                source = data.get("source", "Web Studio Gallery")
                self.engine.start_gallery_slideshow(
                    folder,
                    interval_sec=interval_sec,
                    shuffle=shuffle,
                    source=source,
                )
            if WebRemoteHandler.ui_sync_callback:
                WebRemoteHandler.ui_sync_callback()

        elif self.path == "/api/standby":
            source = data.get("source", "User Standby")
            threading.Thread(target=self.engine.start_standby_stream, args=(source,), daemon=True).start()

        elif self.path == "/api/screen":
            monitors = data.get("monitors")
            source = data.get("source", "Web / Extension")
            if isinstance(monitors, list) and monitors:
                self.engine.selected_monitors = [int(x) for x in monitors]
            self.engine.start_screen_cast(self.engine.selected_monitors, source=source)
            if WebRemoteHandler.ui_sync_callback:
                WebRemoteHandler.ui_sync_callback()

        elif self.path == "/api/browser_cast/start":
            label = data.get("label", "Live Chrome Video Stream")
            source = data.get("source", "Chrome Extension")
            session_id = data.get("session_id", "")
            url = data.get("url", "")
            if "loop" in data and data["loop"] is not None:
                self.engine.loop_video = bool(data["loop"])
            self.engine.start_browser_cast(label=label, source=source, session_id=session_id, url=url)
            if WebRemoteHandler.ui_sync_callback:
                WebRemoteHandler.ui_sync_callback()

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self._send_cors_headers()
        self.end_headers()
        self.wfile.write(json.dumps(self.engine.get_status_dict()).encode("utf-8"))
