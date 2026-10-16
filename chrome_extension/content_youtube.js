(function () {
  // Clean up any previous content script instance in this tab so old listeners/timers never conflict
  if (typeof window.__nvrCastCleanup === "function") {
    try {
      window.__nvrCastCleanup();
    } catch (_) {}
  }

  let isCastingToNVR = false;
  let activeSessionId = "";
  let boundVideo = null;
  let frameWorker = null;
  let frameInFlight = false;
  let captureCanvas = null;
  let captureCtx = null;
  let uiPollTimer = null;
  let directFetchBase = "http://127.0.0.1:8090";
  let useRuntimeFallback = false;

  const CAST_SVG = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" style="margin-right:6px;flex-shrink:0;"><path d="M2 16.1A5 5 0 0 1 5.9 20M2 12.05A9 9 0 0 1 9.95 20M2 8V6a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-6"/><line x1="2" y1="20" x2="2.01" y2="20"/></svg>`;

  function safeSendRuntime(payload, cb) {
    try {
      if (!chrome || !chrome.runtime || !chrome.runtime.id) {
        stopLocalCaptureOnly();
        return;
      }
      chrome.runtime.sendMessage(payload, (resp) => {
        void chrome.runtime.lastError;
        if (cb) cb(resp);
      });
    } catch (_) {
      stopLocalCaptureOnly();
    }
  }

  function findBestVideoElement() {
    const vids = Array.from(document.querySelectorAll("video"));
    if (!vids.length) return null;
    // Prefer a playing video or the largest video element on the page
    let best = vids[0];
    let bestScore = -1;
    for (const v of vids) {
      const area = (v.videoWidth || v.clientWidth || 1) * (v.videoHeight || v.clientHeight || 1);
      const playingBonus = !v.paused && v.readyState >= 2 ? 10000000 : 0;
      const score = area + playingBonus;
      if (score > bestScore) {
        bestScore = score;
        best = v;
      }
    }
    return best;
  }

  function getCleanVideoTitle() {
    let t = document.title || "Live Chrome Video";
    t = t.replace(/^\(\d+\)\s*/, "").replace(/\s*-\s*YouTube$/i, "").trim();
    return t || "Live Chrome Video";
  }

  function updateButtonUI(btn, statusData) {
    if (!btn || !btn.style) return;
    if (isCastingToNVR) {
      btn.innerHTML = `${CAST_SVG}<span>NVR Live (Stop)</span>`;
      btn.style.background = "#16a34a";
      btn.style.color = "#ffffff";
      btn.style.borderColor = "#15803d";
      btn.title = "Streaming live Chrome video directly to NVR (continues across tabs). Click to stop.";
    } else if (statusData && statusData.mode && statusData.mode !== "STANDBY" && statusData.mode !== "STOPPED") {
      btn.innerHTML = `${CAST_SVG}<span>Cast to NVR (${statusData.mode})</span>`;
      btn.style.background = "#ffffff";
      btn.style.color = "#0f172a";
      btn.style.borderColor = "#cbd5e1";
      btn.title = `Active on NVR: [${statusData.mode}] ${statusData.title}. Click to cast this video.`;
    } else {
      btn.innerHTML = `${CAST_SVG}<span>Cast to NVR</span>`;
      btn.style.background = "#ffffff";
      btn.style.color = "#0f172a";
      btn.style.borderColor = "#cbd5e1";
      btn.title = "Stream this live Chrome video player directly to NVR (with PiP & background tab continuity)";
    }
  }

  function applyRemoteCommand(cmd) {
    if (!cmd || !boundVideo) return;
    try {
      if (cmd.event === "pause") {
        boundVideo.pause();
      } else if (cmd.event === "play") {
        boundVideo.play().catch(() => {});
      } else if (cmd.event === "seek") {
        if (typeof cmd.target_sec === "number") {
          boundVideo.currentTime = Math.max(0, cmd.target_sec);
        } else if (typeof cmd.delta_sec === "number") {
          boundVideo.currentTime = Math.max(0, (boundVideo.currentTime || 0) + cmd.delta_sec);
        }
      }
    } catch (_) {}
  }

  function handleFrameResponse(res) {
    if (!res) return;
    if (res.stop) {
      stopLocalCaptureOnly();
      const btn = document.getElementById("nvr-cast-yt-btn");
      if (btn) updateButtonUI(btn, null);
      return;
    }
    if (boundVideo && typeof res.loop === "boolean") {
      boundVideo.loop = res.loop;
    }
    if (res.cmd) {
      applyRemoteCommand(res.cmd);
    }
  }

  function pumpSingleFrame() {
    if (!isCastingToNVR || frameInFlight) return;
    const v = boundVideo && document.contains(boundVideo) ? boundVideo : findBestVideoElement();
    if (!v) return;
    boundVideo = v;

    if (v.readyState < 2 || !v.videoWidth || !v.videoHeight) return;

    if (!captureCanvas) {
      captureCanvas = document.createElement("canvas");
      captureCanvas.width = 1280;
      captureCanvas.height = 720;
      captureCtx = captureCanvas.getContext("2d", { alpha: false });
    }

    frameInFlight = true;
    try {
      const vw = v.videoWidth;
      const vh = v.videoHeight;
      captureCtx.fillStyle = "#000000";
      captureCtx.fillRect(0, 0, 1280, 720);
      const scale = Math.min(1280 / vw, 720 / vh);
      const dw = Math.round(vw * scale);
      const dh = Math.round(vh * scale);
      const dx = Math.round((1280 - dw) / 2);
      const dy = Math.round((720 - dh) / 2);
      captureCtx.drawImage(v, dx, dy, dw, dh);
    } catch (_) {
      frameInFlight = false;
      return;
    }

    const curSec = Math.floor(v.currentTime || 0);
    const durSec = Number.isFinite(v.duration) ? Math.floor(v.duration) : 0;
    const isPaused = Boolean(v.paused);
    const cleanTitle = getCleanVideoTitle();

    if (!useRuntimeFallback) {
      captureCanvas.toBlob(
        (jpgBlob) => {
          if (!jpgBlob || !isCastingToNVR) {
            frameInFlight = false;
            return;
          }
          fetch(`${directFetchBase}/api/browser_cast/frame`, {
            method: "POST",
            headers: {
              "X-Session-Id": activeSessionId,
              "X-Video-Time": String(curSec),
              "X-Video-Duration": String(durSec),
              "X-Video-Paused": isPaused ? "1" : "0",
              "X-Video-Title": encodeURIComponent(cleanTitle),
            },
            body: jpgBlob,
          })
            .then((r) => r.json())
            .then((res) => {
              handleFrameResponse(res);
              frameInFlight = false;
            })
            .catch(() => {
              // Automatically switch to background.js runtime bridge if direct fetch is blocked
              useRuntimeFallback = true;
              frameInFlight = false;
            });
        },
        "image/jpeg",
        0.8
      );
    } else {
      let dataUrl = "";
      try {
        dataUrl = captureCanvas.toDataURL("image/jpeg", 0.78);
      } catch (_) {
        frameInFlight = false;
        return;
      }
      safeSendRuntime(
        {
          action: "pushVideoFrame",
          frame: dataUrl,
          session_id: activeSessionId,
          time_sec: curSec,
          duration_sec: durSec,
          paused: isPaused,
          title: cleanTitle,
        },
        (res) => {
          handleFrameResponse(res);
          frameInFlight = false;
        }
      );
    }
  }

  function startWorkerFramePump() {
    if (frameWorker) {
      try {
        frameWorker.terminate();
      } catch (_) {}
      frameWorker = null;
    }
    try {
      const blob = new Blob(["setInterval(() => postMessage(1), 45);"], {
        type: "application/javascript",
      });
      frameWorker = new Worker(URL.createObjectURL(blob));
      frameWorker.onmessage = pumpSingleFrame;
    } catch (_) {
      // Fallback if page CSP restricts blob Worker creation
      const id = setInterval(() => {
        if (!isCastingToNVR) {
          clearInterval(id);
          return;
        }
        pumpSingleFrame();
      }, 45);
      frameWorker = { terminate: () => clearInterval(id) };
    }
  }

  function stopLocalCaptureOnly() {
    isCastingToNVR = false;
    activeSessionId = "";
    frameInFlight = false;
    if (frameWorker) {
      try {
        frameWorker.terminate();
      } catch (_) {}
      frameWorker = null;
    }
    if (document.pictureInPictureElement && document.pictureInPictureElement === boundVideo) {
      try {
        document.exitPictureInPicture().catch(() => {});
      } catch (_) {}
    }
  }

  function startDirectLiveCast(btn, options = {}) {
    const v = findBestVideoElement();
    if (!v) {
      if (options.notifyUserOnError) {
        alert("No active HTML5 video player found on this page.");
      }
      return false;
    }

    boundVideo = v;
    const sessionId = `chrome_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`;
    activeSessionId = sessionId;

    // Activate Chrome Picture-in-Picture when requested or on direct user click gesture
    // so Chrome's hardware video decoder stays 100% active when switching tabs!
    if (options.activatePip !== false && !document.pictureInPictureElement) {
      try {
        if (v.requestPictureInPicture && !v.disablePictureInPicture) {
          v.requestPictureInPicture().catch(() => {});
        }
      } catch (_) {}
    }

    // Also register MediaSession auto-PiP handler for Chrome 120+
    try {
      if (navigator.mediaSession && navigator.mediaSession.setActionHandler) {
        navigator.mediaSession.setActionHandler("enterpictureinpicture", () => {
          if (boundVideo && boundVideo.requestPictureInPicture) {
            boundVideo.requestPictureInPicture().catch(() => {});
          }
        });
      }
    } catch (_) {}

    if (btn && btn.style) {
      btn.innerHTML = `${CAST_SVG}<span>Connecting...</span>`;
      btn.style.background = "#eff6ff";
      btn.style.color = "#1d4ed8";
    }

    const cleanTitle = getCleanVideoTitle();
    safeSendRuntime(
      {
        action: "startLiveVideoStream",
        label: cleanTitle,
        url: window.location.href,
        session_id: sessionId,
        loop: options.loop,
        acquireTabLock: Boolean(options.acquireTabLock),
        pumpTabFrames: false,
        source: "Chrome Extension (Live Player)",
      },
      (resp) => {
        if (resp && resp.ok) {
          if (resp.baseUrl) {
            directFetchBase = resp.baseUrl;
          }
          isCastingToNVR = true;
          startWorkerFramePump();
          pumpSingleFrame();
          const curBtn = btn || document.getElementById("nvr-cast-yt-btn");
          if (curBtn) updateButtonUI(curBtn, resp.status);
        } else {
          stopLocalCaptureOnly();
          const curBtn = btn || document.getElementById("nvr-cast-yt-btn");
          if (curBtn) updateButtonUI(curBtn, null);
          if (options.notifyUserOnError) {
            alert("Could not connect to NVR Cast Hub on port 8090. Please ensure NVR Cast Hub is running on your PC.");
          }
        }
      }
    );
    return true;
  }

  function stopDirectLiveCast(btn) {
    stopLocalCaptureOnly();
    safeSendRuntime({ action: "stopCast" }, () => {
      const curBtn = btn || document.getElementById("nvr-cast-yt-btn");
      if (curBtn) updateButtonUI(curBtn, null);
    });
  }

  function injectYouTubePlayerButton() {
    if (!window.location.hostname.includes("youtube.com")) return;
    const rightControls = document.querySelector(".ytp-right-controls");
    if (!rightControls) return;

    let btn = document.getElementById("nvr-cast-yt-btn");
    if (!btn) {
      btn = document.createElement("button");
      btn.id = "nvr-cast-yt-btn";
      btn.className = "ytp-button";
      btn.style.cssText =
        "width: auto !important; padding: 0 11px !important; font-family: 'Segoe UI', system-ui, sans-serif; font-weight: 600; font-size: 12px; color: #0f172a; background: #ffffff; border: 1px solid #cbd5e1; border-radius: 6px; margin: 8px 6px; height: 28px; line-height: 26px; display: inline-flex; align-items: center; cursor: pointer; box-shadow: 0 1px 2px rgba(0,0,0,0.12);";
      updateButtonUI(btn, null);

      btn.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        if (isCastingToNVR) {
          stopDirectLiveCast(btn);
        } else {
          startDirectLiveCast(btn, {
            activatePip: true,
            acquireTabLock: true,
            notifyUserOnError: true,
          });
        }
      });

      rightControls.prepend(btn);
    }
  }

  function onRuntimeMessage(msg, sender, sendResponse) {
    if (!msg || !msg.action) return false;

    if (msg.action === "startDirectLiveCast" || msg.action === "triggerPageVideoSync") {
      const btn = document.getElementById("nvr-cast-yt-btn");
      const v = findBestVideoElement();
      if (!v) {
        sendResponse({ ok: false, noVideo: true });
        return false;
      }
      startDirectLiveCast(btn, {
        activatePip: msg.activatePip !== false,
        acquireTabLock: true,
        loop: msg.loop,
        notifyUserOnError: false,
      });
      sendResponse({ ok: true, title: getCleanVideoTitle() });
      return false;
    }

    if (msg.action === "stopPageVideoSync") {
      const btn = document.getElementById("nvr-cast-yt-btn");
      stopDirectLiveCast(btn);
      sendResponse({ ok: true });
      return false;
    }

    return false;
  }

  chrome.runtime.onMessage.addListener(onRuntimeMessage);

  uiPollTimer = setInterval(() => {
    injectYouTubePlayerButton();
    const btn = document.getElementById("nvr-cast-yt-btn");
    if (!btn) return;
    safeSendRuntime({ action: "getStatus" }, (resp) => {
      if (resp && resp.ok && resp.status) {
        const st = resp.status;
        if (
          isCastingToNVR &&
          (st.mode !== "BROWSER" || (st.browser_session_id && st.browser_session_id !== activeSessionId))
        ) {
          stopLocalCaptureOnly();
        }
        updateButtonUI(btn, st);
      }
    });
  }, 2000);

  window.__nvrCastCleanup = function () {
    stopLocalCaptureOnly();
    if (uiPollTimer) {
      clearInterval(uiPollTimer);
      uiPollTimer = null;
    }
    try {
      chrome.runtime.onMessage.removeListener(onRuntimeMessage);
    } catch (_) {}
    const oldBtn = document.getElementById("nvr-cast-yt-btn");
    if (oldBtn && oldBtn.parentNode) {
      oldBtn.parentNode.removeChild(oldBtn);
    }
  };

  injectYouTubePlayerButton();
})();
