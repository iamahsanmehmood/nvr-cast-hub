import json
import threading
from http.server import BaseHTTPRequestHandler
from desktop_app.engine import NVRCastEngine, APP_VERSION


class WebRemoteHandler(BaseHTTPRequestHandler):
    """
    Browser Web Cast Studio & Mobile Remote (v0.1.0-beta).
    Provides:
      - Meeting-Style Browser Tab / Window / Screen Share with Audio (getDisplayMedia + WebM chunk streaming)
      - Direct YouTube, IPTV (.m3u8), Twitch, and Web Video URL Casting
      - Multi-Monitor PC Desktop Selection (Choose All or Specific Monitors)
      - Real-Time Stream Tuning (Resolution, Aspect Fit, FPS, Bitrate, Audio Codec)
      - Mobile Phone LAN Remote Control (http://<LAN-IP>:8090)
    """

    engine: NVRCastEngine = None
    ui_sync_callback = None

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
            payload = {
                "version": APP_VERSION,
                "mode": self.engine.current_mode,
                "title": self.engine.current_title,
                "rtsp_main": f"rtsp://{self.engine.lan_ip}:{self.engine.rtsp_port}/main",
                "rtsp_sub": f"rtsp://{self.engine.lan_ip}:{self.engine.rtsp_port}/sub",
                "lan_ip": self.engine.lan_ip,
                "web_port": self.engine.web_port,
                "monitors": self.engine.monitors_info,
                "selected_monitors": self.engine.selected_monitors,
                "settings": {
                    "main_res": self.engine.main_res,
                    "fps": self.engine.fps,
                    "video_bitrate": self.engine.video_bitrate,
                    "audio_codec": self.engine.audio_codec,
                    "aspect_mode": self.engine.aspect_mode,
                    "show_cursor": self.engine.show_cursor,
                    "capture_pc_audio": self.engine.capture_pc_audio,
                },
            }
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
  .container {{ max-width: 780px; margin: 0 auto; }}
  .card {{ background: #1e293b; border-radius: 14px; padding: 20px; box-shadow: 0 10px 25px rgba(0,0,0,0.4); border: 1px solid #334155; margin-bottom: 16px; }}
  h2 {{ margin: 0 0 6px 0; color: #38bdf8; font-size: 21px; }}
  h3 {{ margin: 0 0 10px 0; color: #f8fafc; font-size: 15.5px; display: flex; align-items: center; gap: 8px; }}
  p.sub {{ margin: 0 0 14px 0; color: #94a3b8; font-size: 13px; }}
  .status {{ background: #0f172a; padding: 13px; border-radius: 10px; margin-bottom: 14px; border-left: 4px solid #4ade80; font-size: 13.5px; line-height: 1.5; }}
  .row {{ display: flex; gap: 8px; margin-bottom: 10px; flex-wrap: wrap; }}
  input[type=text], input[type=number], select {{ padding: 10px 12px; border-radius: 8px; border: 1px solid #475569; background: #0f172a; color: #fff; font-size: 13.5px; }}
  input[type=text] {{ flex: 1; min-width: 220px; }}
  .btn {{ width: 100%; padding: 11px 14px; border: none; border-radius: 8px; font-weight: 700; font-size: 13.5px; cursor: pointer; margin-bottom: 8px; transition: opacity 0.15s; }}
  .btn:hover {{ opacity: 0.92; }}
  .btn-sm {{ width: auto; padding: 6px 12px; font-size: 12px; margin-bottom: 0; background: #334155; color: #e2e8f0; }}
  .btn-play {{ background: #ef4444; color: white; }}
  .btn-meet {{ background: #8b5cf6; color: white; }}
  .btn-screen {{ background: #2563eb; color: white; }}
  .btn-standby {{ background: #475569; color: white; }}
  .mon-list {{ display: flex; flex-direction: column; gap: 8px; margin: 10px 0 12px 0; }}
  .mon-pill {{ background: #0f172a; border: 1px solid #475569; padding: 10px 12px; border-radius: 8px; font-size: 13px; cursor: pointer; display: flex; align-items: center; gap: 8px; }}
  .settings-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 10px; margin-bottom: 12px; }}
  .settings-grid label {{ font-size: 12px; color: #94a3b8; display: flex; flex-direction: column; gap: 4px; }}
  video#previewVideo {{ width: 100%; max-height: 280px; background: #020617; border-radius: 8px; border: 1px solid #334155; display: none; margin-top: 10px; }}
  .code-box {{ background: #0f172a; padding: 12px; border-radius: 8px; font-family: Consolas, monospace; font-size: 12px; color: #fde047; line-height: 1.6; word-break: break-all; }}
</style>
</head>
<body>
<div class="container">
  <div class="card">
    <h2>📺 NVR Cast Studio v{APP_VERSION}</h2>
    <p class="sub">Universal RTSP Media & Screen Caster for Hikvision, Dahua, Uniview, Reolink & ONVIF NVRs.</p>

    <div class="status">
      <strong>Active Mode:</strong> <span id="modeTxt" style="color:#4ade80;font-weight:700;">{self.engine.current_mode}</span><br>
      <strong>Now Playing on NVR:</strong> <span id="titleTxt">{self.engine.current_title}</span>
    </div>

    <h3>🎬 1. Cast YouTube, Live TV, or Any Web Video URL</h3>
    <div class="row">
      <input type="text" id="ytInput" placeholder="Paste YouTube / Twitch / Facebook / .m3u8 URL or search query...">
      <input type="number" id="startSec" placeholder="Start (s)" style="width: 90px;" min="0" value="0" title="Start timestamp in seconds">
    </div>
    <button class="btn btn-play" onclick="castYT()">▶ Stream Video / YouTube to NVR</button>
  </div>

  <div class="card">
    <h3>🖥️ 2. Multi-Monitor PC Desktop Mirroring (Choose All or Specific Monitors)</h3>
    <div class="row">
      <button class="btn btn-sm" onclick="selectMonitors('all')">Select All Monitors</button>
      <button class="btn btn-sm" onclick="selectMonitors(1)">Monitor 1 Only</button>
      <button class="btn btn-sm" onclick="selectMonitors(2)">Monitor 2 Only</button>
    </div>
    <div class="mon-list" id="monList">
      {mon_checks_html}
    </div>
    <div class="row" style="gap: 16px; margin-bottom: 12px; font-size: 13px;">
      <label><input type="checkbox" id="chkAudio" checked> 🔊 Stream PC Speaker Audio (WASAPI Loopback)</label>
      <label><input type="checkbox" id="chkCursor" checked> 🖱️ Show Mouse Pointer</label>
    </div>
    <button class="btn btn-screen" onclick="castDesktop()">🖥️ Mirror Selected Monitor(s) to NVR</button>
  </div>

  <div class="card">
    <h3>💻 3. Meeting-Style Browser Tab / Window / Screen Share (with Audio)</h3>
    <p class="sub">Works like Google Meet / Zoom: pick a specific Chrome Tab (with tab audio), Application Window, or Screen.</p>
    <button class="btn btn-meet" onclick="startMeetingShare()">📹 Share Browser Tab / Window / Screen</button>
    <video id="previewVideo" autoplay muted playsinline></video>
  </div>

  <div class="card">
    <h3>⚙️ 4. Flexibility & Stream Tuning Settings</h3>
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

    <button class="btn btn-standby" onclick="stopCast()">⏹ Stop All Casting / Return to Standby Screen</button>
    <div class="code-box" style="margin-top: 10px;">
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
    selected_monitors: getCheckedMonitors()
  }};
  await fetch('/api/settings', {{
    method: 'POST',
    headers: {{ 'Content-Type': 'application/json' }},
    body: JSON.stringify(payload)
  }});
}}

async function castYT() {{
  const url = document.getElementById('ytInput').value.trim();
  const start_sec = parseInt(document.getElementById('startSec').value || '0', 10) || 0;
  if (!url) return alert('Paste a YouTube link, video URL, or search query first!');
  stopLocalMediaCapture();
  await applySettings();
  await fetch('/api/youtube', {{
    method: 'POST',
    headers: {{ 'Content-Type': 'application/json' }},
    body: JSON.stringify({{ url, start_sec }})
  }});
  document.getElementById('ytInput').value = '';
  setTimeout(refreshStatus, 800);
}}

async function castDesktop() {{
  stopLocalMediaCapture();
  await applySettings();
  const monitors = getCheckedMonitors();
  await fetch('/api/screen', {{
    method: 'POST',
    headers: {{ 'Content-Type': 'application/json' }},
    body: JSON.stringify({{ monitors }})
  }});
  setTimeout(refreshStatus, 800);
}}

async function stopCast() {{
  stopLocalMediaCapture();
  await fetch('/api/standby', {{ method: 'POST' }});
  setTimeout(refreshStatus, 800);
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
      body: JSON.stringify({{ label }})
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
    document.getElementById('modeTxt').textContent = d.mode;
    document.getElementById('titleTxt').textContent = d.title;
  }} catch (e) {{}}
}}

setInterval(refreshStatus, 2000);

window.addEventListener('DOMContentLoaded', () => {{
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
            if "selected_monitors" in data and isinstance(data["selected_monitors"], list):
                self.engine.selected_monitors = [int(x) for x in data["selected_monitors"]]
            if WebRemoteHandler.ui_sync_callback:
                WebRemoteHandler.ui_sync_callback()
        elif self.path == "/api/youtube":
            url = data.get("url", "")
            start_sec = int(data.get("start_sec", 0) or 0)
            if url:
                self.engine.start_youtube_stream(url, start_sec=start_sec)
        elif self.path == "/api/standby":
            threading.Thread(target=self.engine.start_standby_stream, daemon=True).start()
        elif self.path == "/api/screen":
            monitors = data.get("monitors")
            if isinstance(monitors, list) and monitors:
                self.engine.selected_monitors = [int(x) for x in monitors]
            self.engine.start_screen_cast(self.engine.selected_monitors)
        elif self.path == "/api/browser_cast/start":
            label = data.get("label", "Meeting Screen/Tab Share")
            self.engine.start_browser_cast(label=f"Tab/Screen: {label}")

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self._send_cors_headers()
        self.end_headers()
        self.wfile.write(b'{"ok": true}')
