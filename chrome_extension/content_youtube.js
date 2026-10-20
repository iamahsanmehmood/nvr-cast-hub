(function () {
  // Clean up any previous content script instance in this frame so old listeners/timers never conflict
  if (typeof window.__nvrCastCleanup === "function") {
    try {
      window.__nvrCastCleanup();
    } catch (_) {}
  }

  let isCastingToNVR = false;
  let activeSessionId = "";
  let boundVideo = null;
  let pumpTimerId = null;
  let frameInFlight = false;
  let frameInFlightSince = 0;
  let canvasTainted = false;
  let captureCanvas = null;
  let captureCtx = null;
  let keepAliveAudioCtx = null;
  let uiPollTimer = null;

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
    let best = vids[0];
    let bestScore = -1;
    for (const v of vids) {
      const area = (v.videoWidth || v.clientWidth || 1) * (v.videoHeight || v.clientHeight || 1);
      const playingBonus = !v.paused && v.readyState >= 2 ? 10000000 : 0;
      const readyBonus = v.readyState >= 1 ? 100000 : 0;
      const score = area + playingBonus + readyBonus;
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

  function startBackgroundKeepAliveAudio() {
    try {
      if (keepAliveAudioCtx) return;
      const AC = window.AudioContext || window.webkitAudioContext;
      if (!AC) return;
      keepAliveAudioCtx = new AC();
      const osc = keepAliveAudioCtx.createOscillator();
      const gain = keepAliveAudioCtx.createGain();
      // Near-zero inaudible gain keeps Chrome's audio-tab exemption active so background tabs never throttle
      gain.gain.value = 0.00001;
      osc.connect(gain);
      gain.connect(keepAliveAudioCtx.destination);
      osc.start();
    } catch (_) {}
  }

  function stopBackgroundKeepAliveAudio() {
    if (keepAliveAudioCtx) {
      try {
        keepAliveAudioCtx.close();
      } catch (_) {}
      keepAliveAudioCtx = null;
    }
  }

  function tryEnterPip(v) {
    if (!v) return false;
    try {
      v.removeAttribute("disablePictureInPicture");
      v.disablePictureInPicture = false;
      if (document.pictureInPictureElement !== v && typeof v.requestPictureInPicture === "function") {
        v.requestPictureInPicture().catch(() => {});
        return true;
      }
    } catch (_) {}
    return false;
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
      } else if (cmd.event === "playlist_step") {
        const selector = cmd.step >= 0 ? ".ytp-next-button" : ".ytp-prev-button";
        const navBtn = document.querySelector(selector);
        if (navBtn) navBtn.click();
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
      const isPlaylist = window.location.search.includes("list=") || window.location.pathname.includes("/playlist");
      boundVideo.loop = isPlaylist ? false : res.loop;
    }
    if (res.cmd) {
      applyRemoteCommand(res.cmd);
    }
  }

  function pumpSingleFrame() {
    if (!isCastingToNVR) return;
    const now = Date.now();
    if (frameInFlight) {
      if (now - frameInFlightSince > 1500) {
        frameInFlight = false;
      } else {
        return;
      }
    }

    const v = boundVideo && document.contains(boundVideo) ? boundVideo : findBestVideoElement();
    if (!v) return;
    boundVideo = v;

    const curSec = Math.floor(v.currentTime || 0);
    const durSec = Number.isFinite(v.duration) ? Math.floor(v.duration) : 0;
    const isPaused = Boolean(v.paused);
    const cleanTitle = getCleanVideoTitle();

    // If the video is cross-origin tainted, offscreen tabCapture pumps the pixels while we sync timeline/commands
    if (canvasTainted) {
      frameInFlight = true;
      frameInFlightSince = now;
      safeSendRuntime(
        {
          action: "pushVideoFrame",
          frame: "",
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
      return;
    }

    if (v.readyState < 2 || !v.videoWidth || !v.videoHeight) return;

    if (!captureCanvas) {
      captureCanvas = document.createElement("canvas");
      captureCanvas.width = 1280;
      captureCanvas.height = 720;
      captureCtx = captureCanvas.getContext("2d", { alpha: false });
    }

    frameInFlight = true;
    frameInFlightSince = now;

    let dataUrl = "";
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
      dataUrl = captureCanvas.toDataURL("image/jpeg", 0.78);
    } catch (_) {
      // Cross-origin tainted video element: delegate pixel pumping to offscreen tabCapture
      canvasTainted = true;
      frameInFlight = false;
      safeSendRuntime({ action: "enableOffscreenPump" });
      return;
    }

    // Route through background.js service worker so page CSP (connect-src) and Chrome PNA never block frames
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

  function startFramePumpTimer() {
    if (pumpTimerId) {
      clearInterval(pumpTimerId);
      pumpTimerId = null;
    }
    pumpTimerId = setInterval(() => {
      if (!isCastingToNVR) {
        clearInterval(pumpTimerId);
        pumpTimerId = null;
        return;
      }
      pumpSingleFrame();
    }, 42);
  }

  function stopLocalCaptureOnly() {
    isCastingToNVR = false;
    activeSessionId = "";
    frameInFlight = false;
    canvasTainted = false;
    if (pumpTimerId) {
      clearInterval(pumpTimerId);
      pumpTimerId = null;
    }
    stopBackgroundKeepAliveAudio();
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
    canvasTainted = false;
    const sessionId =
      options.sessionId || `chrome_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`;
    activeSessionId = sessionId;

    // Activate Chrome Picture-in-Picture immediately while user gesture is active
    if (options.activatePip !== false) {
      tryEnterPip(v);
    }

    // Register MediaSession auto-PiP handler for Chrome 120+
    try {
      if (navigator.mediaSession && navigator.mediaSession.setActionHandler) {
        navigator.mediaSession.setActionHandler("enterpictureinpicture", () => {
          if (boundVideo) tryEnterPip(boundVideo);
        });
      }
    } catch (_) {}

    startBackgroundKeepAliveAudio();

    if (btn && btn.style) {
      btn.innerHTML = `${CAST_SVG}<span>Connecting...</span>`;
      btn.style.background = "#eff6ff";
      btn.style.color = "#1d4ed8";
    }

    // If popup.js already started the Hub session, start pumping frames immediately!
    if (options.hubAlreadyStarted) {
      isCastingToNVR = true;
      startFramePumpTimer();
      pumpSingleFrame();
      const curBtn = btn || document.getElementById("nvr-cast-yt-btn");
      if (curBtn) updateButtonUI(curBtn, null);
      return true;
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
        source: options.activatePip !== false ? "Chrome Extension (PiP Stream)" : "Chrome Extension (Live Player)",
      },
      (resp) => {
        if (resp && resp.ok) {
          isCastingToNVR = true;
          startFramePumpTimer();
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
        acquireTabLock: Boolean(msg.acquireTabLock),
        hubAlreadyStarted: Boolean(msg.hubAlreadyStarted),
        sessionId: msg.session_id || "",
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
