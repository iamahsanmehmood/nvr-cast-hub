let activeStream = null;
let audioCtx = null;
let frameWorker = null;
let fallbackIntervalId = null;
let activeSessionId = "";
let activeHubUrl = "http://127.0.0.1:8090";
let pumpTabFrames = false;
let lastDirectContentFrameAt = 0;
let inFlight = false;

function stopTimerOnly() {
  if (frameWorker) {
    try {
      frameWorker.postMessage({ cmd: "stop" });
      frameWorker.terminate();
    } catch (_) {}
    frameWorker = null;
  }
  if (fallbackIntervalId) {
    clearInterval(fallbackIntervalId);
    fallbackIntervalId = null;
  }
}

function stopOffscreenCapture() {
  pumpTabFrames = false;
  activeSessionId = "";
  inFlight = false;
  stopTimerOnly();

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

function startFrameLoop(onTick) {
  stopTimerOnly();
  try {
    frameWorker = new Worker("worker_timer.js");
    frameWorker.onmessage = () => onTick();
    frameWorker.onerror = () => {
      if (!fallbackIntervalId) {
        fallbackIntervalId = setInterval(onTick, 42);
      }
    };
    frameWorker.postMessage({ cmd: "start", interval: 42 });
  } catch (_) {
    fallbackIntervalId = setInterval(onTick, 42);
  }
}

async function startOffscreenCapture(msg) {
  stopOffscreenCapture();
  const streamId = msg.streamId;
  activeSessionId = msg.sessionId || "";
  activeHubUrl = (msg.hubUrl || "http://127.0.0.1:8090").replace(/\/+$/, "");
  pumpTabFrames = Boolean(msg.pumpTabFrames);
  lastDirectContentFrameAt = Number(msg.lastDirectContentFrameAt) || 0;

  try {
    const videoConstraints = {
      mandatory: {
        chromeMediaSource: "tab",
        chromeMediaSourceId: streamId,
        minWidth: 1280,
        maxWidth: 1280,
        minHeight: 720,
        maxHeight: 720,
        minFrameRate: 24,
        maxFrameRate: 30,
      },
    };
    try {
      activeStream = await navigator.mediaDevices.getUserMedia({
        audio: {
          mandatory: {
            chromeMediaSource: "tab",
            chromeMediaSourceId: streamId,
          },
        },
        video: videoConstraints,
      });
    } catch (_) {
      // Fallback to video-only if tab has no audio stream
      activeStream = await navigator.mediaDevices.getUserMedia({
        audio: false,
        video: videoConstraints,
      });
    }

    // Route tab audio back to speakers so the user hears it AND WASAPI loopback captures it cleanly
    if (activeStream.getAudioTracks().length > 0) {
      try {
        audioCtx = new AudioContext();
        const source = audioCtx.createMediaStreamSource(activeStream);
        source.connect(audioCtx.destination);
      } catch (_) {}
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

    const canvas = document.getElementById("tabCanvas");
    const ctx = canvas ? canvas.getContext("2d", { alpha: false }) : null;

    if (vid && canvas && ctx) {
      startFrameLoop(() => {
        if (!activeStream || inFlight || vid.readyState < 2) return;
        // Pump tab frames whenever explicitly requested OR if the content script hasn't sent a direct <video> frame in >650ms
        const contentSilentMs = Date.now() - lastDirectContentFrameAt;
        if (!pumpTabFrames && contentSilentMs < 650) {
          return;
        }

        inFlight = true;
        try {
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
              if (!jpgBlob || !activeStream) {
                inFlight = false;
                return;
              }
              const controller = new AbortController();
              const timer = setTimeout(() => controller.abort(), 1500);
              fetch(`${activeHubUrl}/api/browser_cast/frame`, {
                method: "POST",
                headers: {
                  "X-Session-Id": activeSessionId,
                },
                body: jpgBlob,
                signal: controller.signal,
              })
                .then((r) => r.json())
                .then((res) => {
                  if (res && res.stop) {
                    stopOffscreenCapture();
                  }
                })
                .catch(() => {})
                .finally(() => {
                  clearTimeout(timer);
                  inFlight = false;
                });
            },
            "image/jpeg",
            0.82
          );
        } catch (_) {
          inFlight = false;
        }
      });
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
  if (msg.offscreenAction === "enablePump") {
    pumpTabFrames = true;
    sendResponse({ ok: true });
    return false;
  }
  if (msg.offscreenAction === "noteDirectFrame") {
    lastDirectContentFrameAt = Date.now();
    if (typeof msg.pumpTabFrames === "boolean") {
      pumpTabFrames = msg.pumpTabFrames;
    }
    sendResponse({ ok: true });
    return false;
  }
  if (msg.offscreenAction === "stopTabLock") {
    stopOffscreenCapture();
    sendResponse({ ok: true });
    return false;
  }
  return false;
});
