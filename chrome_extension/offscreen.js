let activeStream = null;
let audioCtx = null;
let frameWorker = null;
let activeSessionId = "";
let activeHubUrl = "http://127.0.0.1:8090";
let pumpTabFrames = false;

function stopOffscreenCapture() {
  pumpTabFrames = false;
  activeSessionId = "";
  if (frameWorker) {
    try {
      frameWorker.terminate();
    } catch (_) {}
    frameWorker = null;
  }
  if (audioCtx) {
    try {
      audioCtx.close();
    } catch (_) {}
    audioCtx = null;
  }
  if (activeStream) {
    try {
      activeStream.getTracks().forEach((t) => t.stop());
    } catch (_) {}
    activeStream = null;
  }
  const vid = document.getElementById("tabVideo");
  if (vid) vid.srcObject = null;
}

async function startOffscreenCapture(msg) {
  stopOffscreenCapture();
  const streamId = msg.streamId;
  activeSessionId = msg.sessionId || "";
  activeHubUrl = (msg.hubUrl || "http://127.0.0.1:8090").replace(/\/+$/, "");
  pumpTabFrames = Boolean(msg.pumpTabFrames);

  try {
    activeStream = await navigator.mediaDevices.getUserMedia({
      audio: {
        mandatory: {
          chromeMediaSource: "tab",
          chromeMediaSourceId: streamId,
        },
      },
      video: {
        mandatory: {
          chromeMediaSource: "tab",
          chromeMediaSourceId: streamId,
          minWidth: 1280,
          maxWidth: 1280,
          minHeight: 720,
          maxHeight: 720,
          minFrameRate: 25,
          maxFrameRate: 30,
        },
      },
    });

    // Route tab audio back to speakers so the user hears it AND WASAPI loopback captures it cleanly
    if (activeStream.getAudioTracks().length > 0) {
      audioCtx = new AudioContext();
      const source = audioCtx.createMediaStreamSource(activeStream);
      source.connect(audioCtx.destination);
    }

    const vid = document.getElementById("tabVideo");
    if (vid) {
      vid.srcObject = activeStream;
      await vid.play().catch(() => {});
    }

    const vTrack = activeStream.getVideoTracks()[0];
    if (vTrack) {
      vTrack.onended = () => {
        stopOffscreenCapture();
      };
    }

    if (pumpTabFrames && vid) {
      const canvas = document.getElementById("tabCanvas");
      const ctx = canvas.getContext("2d");
      let inFlight = false;

      const blob = new Blob(["setInterval(() => postMessage(1), 45);"], {
        type: "application/javascript",
      });
      frameWorker = new Worker(URL.createObjectURL(blob));
      frameWorker.onmessage = () => {
        if (!pumpTabFrames || inFlight || !activeStream || vid.readyState < 2) return;
        inFlight = true;
        const vw = vid.videoWidth || 1280;
        const vh = vid.videoHeight || 720;
        ctx.fillStyle = "#000000";
        ctx.fillRect(0, 0, 1280, 720);
        const scale = Math.min(1280 / vw, 720 / vh);
        const dw = Math.round(vw * scale);
        const dh = Math.round(vh * scale);
        const dx = Math.round((1280 - dw) / 2);
        const dy = Math.round((720 - dh) / 2);
        ctx.drawImage(vid, dx, dy, dw, dh);

        canvas.toBlob(
          (jpgBlob) => {
            if (!jpgBlob) {
              inFlight = false;
              return;
            }
            fetch(`${activeHubUrl}/api/browser_cast/frame`, {
              method: "POST",
              headers: {
                "X-Session-Id": activeSessionId,
              },
              body: jpgBlob,
            })
              .then((r) => r.json())
              .then((res) => {
                if (res && res.stop) {
                  stopOffscreenCapture();
                }
              })
              .catch(() => {})
              .finally(() => {
                inFlight = false;
              });
          },
          "image/jpeg",
          0.82
        );
      };
    }

    return { ok: true };
  } catch (err) {
    stopOffscreenCapture();
    return { ok: false, error: String(err) };
  }
}

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (!msg || !msg.offscreenAction) return false;
  if (msg.offscreenAction === "startTabLock") {
    startOffscreenCapture(msg).then(sendResponse);
    return true;
  }
  if (msg.offscreenAction === "stopTabLock") {
    stopOffscreenCapture();
    sendResponse({ ok: true });
    return false;
  }
  return false;
});
