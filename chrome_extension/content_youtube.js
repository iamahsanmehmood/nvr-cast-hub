(function () {
  if (window.__nvrCastContentInjected) return;
  window.__nvrCastContentInjected = true;

  let isSyncedWithNVR = false;
  let boundVideo = null;
  let lastSyncedUrl = "";
  let lastSeekSentAt = 0;
  let seekDebounceTimer = null;
  let pipRecorder = null;
  let pollIntervalId = null;

  const CAST_SVG = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" style="margin-right:6px;flex-shrink:0;"><path d="M2 16.1A5 5 0 0 1 5.9 20M2 12.05A9 9 0 0 1 9.95 20M2 8V6a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-6"/><line x1="2" y1="20" x2="2.01" y2="20"/></svg>`;

  function safeSendRuntime(payload, cb) {
    try {
      if (!chrome || !chrome.runtime || !chrome.runtime.id) {
        if (pollIntervalId) clearInterval(pollIntervalId);
        return;
      }
      chrome.runtime.sendMessage(payload, (resp) => {
        void chrome.runtime.lastError;
        if (cb) cb(resp);
      });
    } catch (_) {
      if (pollIntervalId) clearInterval(pollIntervalId);
    }
  }

  function updateButtonUI(btn, statusData) {
    if (!btn || !btn.style) return;
    if (isSyncedWithNVR) {
      btn.innerHTML = `${CAST_SVG}<span>NVR Synced (Stop)</span>`;
      btn.style.background = "#16a34a";
      btn.style.color = "#ffffff";
      btn.style.borderColor = "#15803d";
      btn.title = "Live Seek & Pause Sync is ACTIVE on NVR. Scrubbing or pausing updates the NVR. Click to stop.";
    } else if (statusData && statusData.mode && statusData.mode !== "STANDBY" && statusData.mode !== "STOPPED") {
      btn.innerHTML = `${CAST_SVG}<span>Cast to NVR (${statusData.mode})</span>`;
      btn.style.background = "#ffffff";
      btn.style.color = "#0f172a";
      btn.style.borderColor = "#cbd5e1";
      btn.title = `Active on NVR: [${statusData.mode}] ${statusData.title}. Click to switch NVR to this video.`;
    } else {
      btn.innerHTML = `${CAST_SVG}<span>Cast to NVR</span>`;
      btn.style.background = "#ffffff";
      btn.style.color = "#0f172a";
      btn.style.borderColor = "#cbd5e1";
      btn.title = "Cast this video to NVR with real-time Forward/Backward Seek & Pause Sync";
    }
  }

  function stopPipRecorder() {
    if (pipRecorder && pipRecorder.state !== "inactive") {
      try {
        pipRecorder.stop();
      } catch (_) {}
    }
    pipRecorder = null;
  }

  function onVideoSeeked() {
    if (!isSyncedWithNVR || !boundVideo || pipRecorder) return;
    const now = Date.now();
    if (now - lastSeekSentAt < 600) return;
    clearTimeout(seekDebounceTimer);
    seekDebounceTimer = setTimeout(() => {
      if (!isSyncedWithNVR || !boundVideo) return;
      lastSeekSentAt = Date.now();
      const targetSec = Math.floor(boundVideo.currentTime || 0);
      safeSendRuntime({
        action: "playerSync",
        event: "seek",
        time_sec: targetSec,
        source: "Chrome Extension (Video Seek)",
      });
    }, 350);
  }

  function onVideoPause() {
    if (!isSyncedWithNVR || !boundVideo || pipRecorder) return;
    if (boundVideo.seeking) return;
    safeSendRuntime({
      action: "playerSync",
      event: "pause",
      time_sec: Math.floor(boundVideo.currentTime || 0),
      source: "Chrome Extension (Video Pause)",
    });
  }

  function onVideoPlay() {
    if (!isSyncedWithNVR || !boundVideo || pipRecorder) return;
    if (boundVideo.seeking) return;
    safeSendRuntime({
      action: "playerSync",
      event: "play",
      time_sec: Math.floor(boundVideo.currentTime || 0),
      source: "Chrome Extension (Video Play)",
    });
  }

  function attachVideoSyncListeners(v) {
    if (boundVideo === v) return;
    detachVideoSyncListeners();
    boundVideo = v;
    if (!boundVideo) return;
    boundVideo.addEventListener("seeked", onVideoSeeked);
    boundVideo.addEventListener("pause", onVideoPause);
    boundVideo.addEventListener("play", onVideoPlay);
  }

  function detachVideoSyncListeners() {
    if (!boundVideo) return;
    try {
      boundVideo.removeEventListener("seeked", onVideoSeeked);
      boundVideo.removeEventListener("pause", onVideoPause);
      boundVideo.removeEventListener("play", onVideoPlay);
    } catch (_) {}
    boundVideo = null;
  }

  function startPipCaptureStream(v, btn) {
    try {
      const stream = v.captureStream ? v.captureStream(25) : v.mozCaptureStream ? v.mozCaptureStream(25) : null;
      if (!stream) return false;

      safeSendRuntime(
        {
          action: "startLiveVideoStream",
          label: document.title || "Browser Video Player",
        },
        (resp) => {
          if (!resp || !resp.ok) return;
          let mimeType = "video/webm;codecs=vp8,opus";
          if (!MediaRecorder.isTypeSupported(mimeType)) {
            mimeType = "video/webm";
          }
          pipRecorder = new MediaRecorder(stream, {
            mimeType,
            videoBitsPerSecond: 1800000,
          });
          pipRecorder.ondataavailable = async (ev) => {
            if (ev.data && ev.data.size > 0 && isSyncedWithNVR) {
              const buf = await ev.data.arrayBuffer();
              safeSendRuntime({
                action: "pushVideoChunk",
                chunk: Array.from(new Uint8Array(buf)),
              });
            }
          };
          pipRecorder.start(200);
          isSyncedWithNVR = true;
          updateButtonUI(btn, null);
        }
      );
      return true;
    } catch (_) {
      return false;
    }
  }

  function startSyncForCurrentVideo(btn, forcePipMode, notifyUserOnError) {
    const v = document.querySelector("video");
    const startSec = v ? Math.floor(v.currentTime || 0) : 0;
    const isYouTube = window.location.hostname.includes("youtube.com");

    if (btn && btn.style) {
      btn.innerHTML = `${CAST_SVG}<span>Connecting...</span>`;
      btn.style.background = "#eff6ff";
      btn.style.color = "#1d4ed8";
    }

    if (forcePipMode && v) {
      if (startPipCaptureStream(v, btn)) return;
    }

    lastSyncedUrl = window.location.href;
    lastSeekSentAt = Date.now();

    safeSendRuntime(
      {
        action: "castYoutube",
        url: window.location.href,
        start_sec: startSec,
        source: isYouTube ? "Chrome Extension (YouTube Sync)" : "Chrome Extension (Web Video Sync)",
      },
      (resp) => {
        if (resp && resp.ok) {
          isSyncedWithNVR = true;
          if (v) attachVideoSyncListeners(v);
          updateButtonUI(btn, resp.status);
        } else {
          isSyncedWithNVR = false;
          updateButtonUI(btn, null);
          if (notifyUserOnError) {
            alert("Could not connect to NVR Cast Hub on port 8090. Please ensure NVR Cast Hub is running on your PC.");
          }
        }
      }
    );
  }

  function stopSync(btn) {
    isSyncedWithNVR = false;
    stopPipRecorder();
    detachVideoSyncListeners();
    safeSendRuntime({ action: "stopCast" }, () => {
      updateButtonUI(btn, null);
    });
  }

  function injectYouTubePlayerButton() {
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
        if (isSyncedWithNVR) {
          stopSync(btn);
        } else {
          startSyncForCurrentVideo(btn, false, true);
        }
      });

      rightControls.prepend(btn);
    }

    if (isSyncedWithNVR && window.location.href !== lastSyncedUrl && window.location.pathname.startsWith("/watch")) {
      startSyncForCurrentVideo(btn, false, false);
    }

    if (isSyncedWithNVR) {
      const v = document.querySelector("video");
      if (v && v !== boundVideo) attachVideoSyncListeners(v);
    }
  }

  chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
    if (!msg || !msg.action) return false;
    if (msg.action === "attachSyncOnly") {
      const v = document.querySelector("video");
      isSyncedWithNVR = true;
      lastSyncedUrl = window.location.href;
      lastSeekSentAt = Date.now();
      if (v) attachVideoSyncListeners(v);
      const btn = document.getElementById("nvr-cast-yt-btn");
      updateButtonUI(btn, null);
      sendResponse({
        ok: true,
        time: v ? Math.floor(v.currentTime || 0) : 0,
        src: v && (v.currentSrc || v.src) && !(v.currentSrc || v.src).startsWith("blob:") ? v.currentSrc || v.src : null,
      });
      return false;
    }
    if (msg.action === "triggerPageVideoSync") {
      const btn = document.getElementById("nvr-cast-yt-btn");
      startSyncForCurrentVideo(btn, Boolean(msg.pipMode), false);
      sendResponse({ ok: true });
      return false;
    }
    if (msg.action === "stopPageVideoSync") {
      const btn = document.getElementById("nvr-cast-yt-btn");
      isSyncedWithNVR = false;
      stopPipRecorder();
      detachVideoSyncListeners();
      updateButtonUI(btn, null);
      sendResponse({ ok: true });
      return false;
    }
    return false;
  });

  pollIntervalId = setInterval(() => {
    if (window.location.hostname.includes("youtube.com")) {
      injectYouTubePlayerButton();
      const btn = document.getElementById("nvr-cast-yt-btn");
      if (btn && !isSyncedWithNVR) {
        safeSendRuntime({ action: "getStatus" }, (res) => {
          if (res && res.ok) updateButtonUI(btn, res.status);
        });
      }
    }
  }, 2000);
})();
