import json
import threading
from http.server import BaseHTTPRequestHandler
from desktop_app.engine import NVRCastEngine, APP_VERSION


class WebRemoteHandler(BaseHTTPRequestHandler):
    """
    Browser Web Cast Studio, Active Session Controller & Mobile Remote (v0.1.0-beta).
    Provides:
      - Unified Active Session Bar (shows which app/extension is currently streaming + Pause/Resume/Seek/Stop)
      - Direct YouTube / Web Video Casting with Infinite Loop & Seek Sync
      - Photo Gallery / Folder Slideshow with Timer, Shuffle & Next/Prev Controls
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
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

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

        # Build monitor checkboxes HTML dynamically
        mon_checks_html = ""
        for m in self.engine.detect_monitors():
            if m["index"] == 0:
                continue
            checked = "checked" if (m["index"] in self.engine.selected_monitors or 0 in self.engine.selected_monitors) else ""
            mon_checks_html += (
                f'<label class="mon-pill">'
                f'<input type="checkbox" class="mon-cb" value="{m["index"]}" {checked}> '
                f'{m["label"]}</label>'
            )

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>NVR Cast Studio v{APP_VERSION} — Universal NVR & CCTV Caster</title>
<style>
  * {{ box-sizing: border-box; }}
  body {{ font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; background: #0f172a; color: #f8fafc; margin: 0; padding: 18px; }}
  .container {{ max-width: 820px; margin: 0 auto; }}
  .card {{ background: #1e293b; border-radius: 14px; padding: 18px 20px; box-shadow: 0 10px 25px rgba(0,0,0,0.4); border: 1px solid #334155; margin-bottom: 16px; }}
  h2 {{ margin: 0 0 6px 0; color: #38bdf8; font-size: 21px; }}
  h3 {{ margin: 0 0 10px 0; color: #f8fafc; font-size: 15.5px; display: flex; align-items: center; gap: 8px; }}
  p.sub {{ margin: 0 0 12px 0; color: #94a3b8; font-size: 13px; }}
  .status {{ background: #0f172a; padding: 14px; border-radius: 10px; margin-bottom: 12px; border-left: 4px solid #4ade80; font-size: 13.5px; line-height: 1.6; }}
  .row {{ display: flex; gap: 8px; margin-bottom: 10px; flex-wrap: wrap; align-items: center; }}
  input[type=text], input[type=number], select {{ padding: 9px 12px; border-radius: 8px; border: 1px solid #475569; background: #0f172a; color: #fff; font-size: 13.5px; }}
  input[type=text] {{ flex: 1; min-width: 200px; }}
  .btn {{ width: 100%; padding: 11px 14px; border: none; border-radius: 8px; font-weight: 700; font-size: 13.5px; cursor: pointer; margin-bottom: 8px; transition: opacity 0.15s; }}
  .btn:hover {{ opacity: 0.92; }}
  .btn-sm {{ width: auto; padding: 7px 12px; font-size: 12.5px; margin-bottom: 0; background: #334155; color: #e2e8f0; border-radius: 7px; border: none; font-weight: 600; cursor: pointer; }}
  .btn-play {{ background: #ef4444; color: white; }}
  .btn-gallery {{ background: #10b981; color: white; }}
  .btn-meet {{ background: #8b5cf6; color: white; }}
  .btn-screen {{ background: #2563eb; color: white; }}
  .btn-standby {{ background: #475569; color: white; }}
  .btn-warn {{ background: #f59e0b; color: #0f172a; }}
  .mon-list {{ display: flex; flex-direction: column; gap: 8px; margin: 10px 0 12px 0; }}
  .mon-pill {{ background: #0f172a; border: 1px solid #475569; padding: 10px 12px; border-radius: 8px; font-size: 13px; cursor: pointer; display: flex; align-items: center; gap: 8px; }}
  .settings-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px; margin-bottom: 12px; }}
  .settings-grid label {{ font-size: 12px; color: #94a3b8; display: flex; flex-direction: column; gap: 4px; }}
  video#previewVideo {{ width: 100%; max-height: 280px; background: #020617; border-radius: 8px; border: 1px solid #334155; display: none; margin-top: 10px; }}
  .code-box {{ background: #0f172a; padding: 12px; border-radius: 8px; font-family: Consolas, monospace; font-size: 12px; color: #fde047; line-height: 1.6; word-break: break-all; }}
</style>
</head>
<body>
<div class="container">
  <div class="card">
    <h2>📺 NVR Cast Studio v{APP_VERSION}</h2>
    <p class="sub">Universal RTSP Media, Photo Gallery, Video Loop & Screen Caster for Hikvision, Dahua, Uniview, Reolink & ONVIF NVRs.</p>

    <div class="status" id="statusBanner">
      <strong>Active Mode:</strong> <span id="modeTxt" style="color:#4ade80;font-weight:700;">{self.engine.current_mode}</span>
      &nbsp;|&nbsp; <strong>Started By:</strong> <span id="sourceTxt" style="color:#38bdf8;font-weight:700;">{self.engine.active_source}</span><br>
      <strong>Now Playing on NVR:</strong> <span id="titleTxt">{self.engine.current_title}</span>
      &nbsp;<span id="timeTxt" style="color:#fde047;"></span>
    </div>

    <div class="row" style="margin-bottom: 4px;">
      <button class="btn-sm btn-warn" onclick="togglePause()" id="btnPauseResume">⏯ Pause / Resume Current Stream</button>
      <button class="btn-sm" onclick="seekDelta(-30)">⏪ -30s</button>
      <button class="btn-sm" onclick="seekDelta(-10)">⏪ -10s</button>
      <button class="btn-sm" onclick="seekDelta(10)">⏩ +10s</button>
      <button class="btn-sm" onclick="seekDelta(30)">⏩ +30s</button>
      <button class="btn-sm" style="background:#dc2626;color:#fff;" onclick="stopCast()">⏹ Stop / Standby</button>
    </div>
  </div>

  <div class="card">
    <h3>🎬 1. Cast YouTube, Web Video, or Local Video (with Infinite Loop & Seek)</h3>
    <div class="row">
      <input type="text" id="ytInput" placeholder="Paste YouTube / Web Video URL, search phrase, or local file path...">
      <input type="number" id="startSec" placeholder="Start (s)" style="width: 90px;" min="0" value="0" title="Start timestamp in seconds">
      <label style="font-size:13px;display:flex;align-items:center;gap:5px;cursor:pointer;">
        <input type="checkbox" id="chkLoopVideo"> 🔁 Loop Video
      </label>
    </div>
    <div class="row">
      <button class="btn btn-play" style="flex:2;margin-bottom:0;" onclick="castYT()">▶ Stream Video / YouTube to NVR</button>
      <button class="btn-sm" style="padding:11px 14px;" onclick="pickHostFile('video')">📂 Pick Video File on PC...</button>
    </div>
  </div>

  <div class="card">
    <h3>🖼️ 2. Photo Gallery / Folder Slideshow Gadget (Timer + Shuffle)</h3>
    <p class="sub">Select a folder of pictures on your PC to run an automatic slideshow on your NVR monitor with timer and shuffle.</p>
    <div class="row">
      <input type="text" id="galleryFolder" placeholder="Enter image folder path (e.g. C:\\Users\\Public\\Pictures) or click Browse..." value="{self.engine.gallery_folder}">
      <button class="btn-sm" onclick="pickHostFile('folder')">📁 Browse Folder...</button>
    </div>
    <div class="row">
      <label style="font-size:13px;">Slide Timer (sec):
        <input type="number" id="galleryTimer" value="{self.engine.gallery_interval}" min="1" max="3600" style="width:75px;margin-left:6px;">
      </label>
      <label style="font-size:13px;display:flex;align-items:center;gap:5px;cursor:pointer;margin-left:10px;">
        <input type="checkbox" id="chkGalleryShuffle"> 🔀 Shuffle Pictures
      </label>
      <button class="btn-sm" onclick="stepGallery(-1)">⏮ Prev Slide</button>
      <button class="btn-sm" onclick="stepGallery(1)">⏭ Next Slide</button>
    </div>
    <button class="btn btn-gallery" style="margin-bottom:0;" onclick="startGallery()">🖼️ Start Photo Gallery Slideshow on NVR</button>
  </div>

  <div class="card">
    <h3>🖥️ 3. Multi-Monitor PC Desktop Mirroring (Choose All or Specific Monitors)</h3>
    <div class="row">
      <button class="btn-sm" onclick="selectMonitors('all')">Select All Monitors</button>
      <button class="btn-sm" onclick="selectMonitors(1)">Monitor 1 Only</button>
      <button class="btn-sm" onclick="selectMonitors(2)">Monitor 2 Only</button>
    </div>
    <div class="mon-list" id="monList">
      {mon_checks_html}
    </div>
    <div class="row" style="gap: 16px; margin-bottom: 12px; font-size: 13px;">
      <label><input type="checkbox" id="chkAudio" checked> 🔊 Stream PC Speaker Audio (WASAPI Loopback)</label>
      <label><input type="checkbox" id="chkCursor" checked> 🖱️ Show Mouse Pointer</label>
    </div>
    <button class="btn btn-screen" style="margin-bottom:0;" onclick="castDesktop()">🖥️ Mirror Selected Monitor(s) to NVR</button>
  </div>

  <div class="card">
    <h3>💻 4. Meeting-Style Browser Tab / Window / Screen Share (with Audio)</h3>
    <p class="sub">Works like Google Meet / Zoom: pick a specific Chrome Tab (with tab audio), Application Window, or Screen.</p>
    <button class="btn btn-meet" style="margin-bottom:0;" onclick="startMeetingShare()">📹 Share Browser Tab / Window / Screen</button>
    <video id="previewVideo" autoplay muted playsinline></video>
  </div>

  <div class="card">
    <h3>⚙️ 5. Flexibility & Stream Tuning Settings</h3>
    <div class="settings-grid">
      <label>Main Resolution
        <select id="selRes" onchange="applySettings()">
          <option value="1280x720">1280x720 (720p HD)</option>
          <option value="1920x1080">1920x1080 (1080p FHD)</option>
          <option value="854x480">854x480 (480p Fast)</option>
        </select>
      </label>
      <label>Aspect Ratio Fit
        <select id="selAspect" onchange="applySettings()">
          <option value="fit">Fit / Letterbox (Keep Aspect)</option>
          <option value="stretch">Stretch to Fill NVR Screen</option>
          <option value="crop">Center Crop to 16:9</option>
        </select>
      </label>
      <label>Frame Rate (FPS)
        <select id="selFps" onchange="applySettings()">
          <option value="25">25 FPS (PAL CCTV Std)</option>
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
          <option value="pcm_mulaw">G.711u (pcm_mulaw CCTV)</option>
          <option value="pcm_alaw">G.711a (pcm_alaw CCTV)</option>
          <option value="aac">AAC 16kHz Mono (NVR)</option>
          <option value="aac_hq">AAC 44.1kHz Stereo (VLC)</option>
          <option value="none">Mute (Video Only)</option>
        </select>
      </label>
    </div>

    <div class="code-box" style="margin-top: 8px;">
      <strong>Main Stream:</strong> rtsp://{self.engine.lan_ip}:{self.engine.rtsp_port}/main<br>
      <strong>Sub Stream:</strong> rtsp://{self.engine.lan_ip}:{self.engine.rtsp_port}/sub
    </div>
  </div>
</div>

<script>
let mediaRecorder = null;
let displayStream = null;
let sendChain = Promise.resolve();

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
  await fetch('/api/settings', {{
    method: 'POST',
    headers: {{ 'Content-Type': 'application/json' }},
    body: JSON.stringify(payload)
  }});
}}

async function togglePause() {{
  await fetch('/api/player_sync', {{
    method: 'POST',
    headers: {{ 'Content-Type': 'application/json' }},
    body: JSON.stringify({{ event: 'toggle_pause', source: 'Web Studio' }})
  }});
  setTimeout(refreshStatus, 400);
}}

async function seekDelta(delta) {{
  await fetch('/api/player_sync', {{
    method: 'POST',
    headers: {{ 'Content-Type': 'application/json' }},
    body: JSON.stringify({{ event: 'seek', delta_sec: delta, source: 'Web Studio' }})
  }});
  setTimeout(refreshStatus, 500);
}}

async function castYT() {{
  const url = document.getElementById('ytInput').value.trim();
  const start_sec = parseInt(document.getElementById('startSec').value || '0', 10) || 0;
  const loop = document.getElementById('chkLoopVideo').checked;
  if (!url) return alert('Paste a YouTube link, video URL, local file path, or search query first!');
  stopLocalMediaCapture();
  await applySettings();
  await fetch('/api/youtube', {{
    method: 'POST',
    headers: {{ 'Content-Type': 'application/json' }},
    body: JSON.stringify({{ url, start_sec, loop, source: 'Web Studio' }})
  }});
  setTimeout(refreshStatus, 600);
}}

async function pickHostFile(kind) {{
  const r = await fetch('/api/browse_dialog', {{
    method: 'POST',
    headers: {{ 'Content-Type': 'application/json' }},
    body: JSON.stringify({{ kind }})
  }});
  const d = await r.json();
  if (d && d.path) {{
    if (kind === 'folder') {{
      document.getElementById('galleryFolder').value = d.path;
    }} else if (kind === 'video') {{
      document.getElementById('ytInput').value = d.path;
      const loop = document.getElementById('chkLoopVideo').checked;
      await fetch('/api/file', {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify({{ filepath: d.path, loop, source: 'Web Studio' }})
      }});
      setTimeout(refreshStatus, 600);
    }}
  }}
}}

async function startGallery() {{
  const folder = document.getElementById('galleryFolder').value.trim();
  const interval_sec = parseInt(document.getElementById('galleryTimer').value || '5', 10) || 5;
  const shuffle = document.getElementById('chkGalleryShuffle').checked;
  if (!folder) return alert('Select or enter a Picture Folder path first!');
  stopLocalMediaCapture();
  await applySettings();
  await fetch('/api/gallery', {{
    method: 'POST',
    headers: {{ 'Content-Type': 'application/json' }},
    body: JSON.stringify({{ action: 'start', folder, interval_sec, shuffle, source: 'Web Studio' }})
  }});
  setTimeout(refreshStatus, 600);
}}

async function stepGallery(step) {{
  await fetch('/api/gallery', {{
    method: 'POST',
    headers: {{ 'Content-Type': 'application/json' }},
    body: JSON.stringify({{ action: 'step', step }})
  }});
  setTimeout(refreshStatus, 300);
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
  setTimeout(refreshStatus, 600);
}}

async function stopCast() {{
  stopLocalMediaCapture();
  await fetch('/api/standby', {{
    method: 'POST',
    headers: {{ 'Content-Type': 'application/json' }},
    body: JSON.stringify({{ source: 'Web Studio' }})
  }});
  setTimeout(refreshStatus, 600);
}}

function stopLocalMediaCapture() {{
  if (mediaRecorder && mediaRecorder.state !== 'inactive') {{
    try {{ mediaRecorder.stop(); }} catch (e) {{}}
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
    alert('Screen sharing requires http://localhost:8090 or Chrome.');
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

    const videoTrack = displayStream.getVideoTracks()[0];
    const label = videoTrack ? (videoTrack.label || 'Browser Screen Share') : 'Browser Screen Share';

    await fetch('/api/browser_cast/start', {{
      method: 'POST',
      headers: {{ 'Content-Type': 'application/json' }},
      body: JSON.stringify({{ label, source: 'Web Studio (Meeting Share)' }})
    }});

    let mimeType = 'video/webm;codecs=vp8,opus';
    if (!MediaRecorder.isTypeSupported(mimeType)) {{
      mimeType = 'video/webm';
    }}

    mediaRecorder = new MediaRecorder(displayStream, {{
      mimeType,
      videoBitsPerSecond: 1800000
    }});

    mediaRecorder.ondataavailable = (e) => {{
      if (e.data && e.data.size > 0) {{
        sendChain = sendChain.then(() =>
          fetch('/api/browser_cast/chunk', {{
            method: 'POST',
            body: e.data
          }}).catch(() => {{}})
        );
      }}
    }};

    videoTrack.onended = () => {{
      stopCast();
    }};

    mediaRecorder.start(200);
    setTimeout(refreshStatus, 600);
  }} catch (err) {{
    console.error('Meeting share cancelled or failed:', err);
  }}
}}

async function refreshStatus() {{
  try {{
    const r = await fetch('/api/status');
    const d = await r.json();
    document.getElementById('modeTxt').textContent = d.mode + (d.is_paused ? ' (PAUSED)' : '');
    document.getElementById('sourceTxt').textContent = d.active_source || 'System';
    document.getElementById('titleTxt').textContent = d.title;
    const tSpan = document.getElementById('timeTxt');
    if (d.mode === 'YOUTUBE' || d.mode === 'FILE') {{
      const m = Math.floor((d.playback_sec || 0) / 60);
      const s = (d.playback_sec || 0) % 60;
      tSpan.textContent = `[Pos: ${{m}}m ${{s}}s${{d.loop_video ? ' • LOOP' : ''}}]`;
    }} else if (d.mode === 'GALLERY' && d.gallery) {{
      tSpan.textContent = `[Slide ${{d.gallery.index + 1}}/${{d.gallery.count}} • ${{d.gallery.interval}}s]`;
    }} else {{
      tSpan.textContent = '';
    }}
  }} catch (e) {{}}
}}

setInterval(refreshStatus, 1500);

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
                import os
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
            label = data.get("label", "Live Browser Video / Tab Share")
            source = data.get("source", "Chrome Extension / Web Studio")
            self.engine.start_browser_cast(label=label, source=source)
            if WebRemoteHandler.ui_sync_callback:
                WebRemoteHandler.ui_sync_callback()

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self._send_cors_headers()
        self.end_headers()
        self.wfile.write(json.dumps(self.engine.get_status_dict()).encode("utf-8"))
