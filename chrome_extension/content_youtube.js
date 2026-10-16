(function () {
  let isSyncedWithNVR = false;
  let boundVideo = null;
  let lastSyncedUrl = "";
  let lastSeekSentAt = 0;
  let seekDebounceTimer = null;
  let pipRecorder = null;

  function updateButtonUI(btn, statusData) {
    if (!btn) return;
    if (isSyncedWithNVR) {
      btn.textContent = "🟢 NVR Synced (Stop)";
      btn.style.background = "#16a34a";
      btn.title = "Live Seek & Pause Sync is ACTIVE on NVR! Scrubbing forward/backward or pausing here updates the NVR. Click to stop.";
    } else if (statusData && statusData.mode && statusData.mode !== "STANDBY" && statusData.mode !== "STOPPED") {
      btn.textContent = `📺 Cast to NVR (${statusData.mode} Busy)`;
      btn.style.background = "#dc2626";
      btn.title = `Currently running on NVR: [${statusData.mode}] ${statusData.title} (by ${statusData.active_source || "Hub"}). Click to switch NVR to this video with Live Sync!`;
    } else {
      btn.textContent = "📺 Cast to NVR (Sync)";
      btn.style.background = "#ef4444";
      btn.title = "Cast this video to NVR with real-time Forward/Backward Seek & Pause Sync";
    }
  }

  function stopPipRecorder() {
    if (pipRecorder && pipRecorder.state !== "inactive") {
      try {
        pipRecorder.stop();
      } catch (e) {}
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
      chrome.runtime.sendMessage({
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
    chrome.runtime.sendMessage({
      action: "playerSync",
      event: "pause",
      time_sec: Math.floor(boundVideo.currentTime || 0),
      source: "Chrome Extension (Video Pause)",
    });
  }

  function onVideoPlay() {
    if (!isSyncedWithNVR || !boundVideo || pipRecorder) return;
    if (boundVideo.seeking) return;
    chrome.runtime.sendMessage({
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
    } catch (e) {}
    boundVideo = null;
  }

  function startPipCaptureStream(v, btn) {
    try {
      const stream = v.captureStream ? v.captureStream(25) : v.mozCaptureStream ? v.mozCaptureStream(25) : null;
      if (!stream) return false;

      chrome.runtime.sendMessage(
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
              chrome.runtime.sendMessage({
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
    } catch (e) {
      return false;
    }
  }

  function startSyncForCurrentVideo(btn, forcePipMode) {
    const v = document.querySelector("video");
    const startSec = v ? Math.floor(v.currentTime || 0) : 0;
    const isYouTube = window.location.hostname.includes("youtube.com");

    btn.textContent = "⏳ Connecting NVR...";
    btn.style.background = "#f59e0b";

    if (forcePipMode && v) {
      if (startPipCaptureStream(v, btn)) return;
    }

    lastSyncedUrl = window.location.href;
    lastSeekSentAt = Date.now();

    chrome.runtime.sendMessage(
      {
        action: "castYoutube",
        url: window.location.href,
        start_sec: startSec,
        source: isYouTube ? "Chrome Extension (YouTube Live Sync)" : "Chrome Extension (Web Video Sync)",
      },
      (resp) => {
        if (resp && resp.ok) {
          isSyncedWithNVR = true;
          if (v) attachVideoSyncListeners(v);
          updateButtonUI(btn, resp.status);
        } else {
          alert("Could not reach NVR Cast Hub on http://127.0.0.1:8090. Make sure NVR Cast Hub is running on your PC!");
          isSyncedWithNVR = false;
          updateButtonUI(btn, null);
        }
      }
    );
  }

  function stopSync(btn) {
    isSyncedWithNVR = false;
    stopPipRecorder();
    detachVideoSyncListeners();
    chrome.runtime.sendMessage({ action: "stopCast" }, () => {
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
        "width: auto !important; padding: 0 10px !important; font-weight: 700; font-size: 12px; color: #fff; background: #ef4444; border-radius: 4px; margin: 8px 6px; height: 28px; line-height: 28px; display: inline-flex; align-items: center; cursor: pointer; border: none;";
      btn.textContent = "📺 Cast to NVR (Sync)";

      btn.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        if (isSyncedWithNVR) {
          stopSync(btn);
        } else {
          startSyncForCurrentVideo(btn, false);
        }
      });

      rightControls.prepend(btn);
    }

    // If synced and user navigated to a new YouTube video, auto-cast the new video!
    if (isSyncedWithNVR && window.location.href !== lastSyncedUrl && window.location.pathname.startsWith("/watch")) {
      startSyncForCurrentVideo(btn, false);
    }

    // Re-attach video listener if YouTube swapped the <video> element
    if (isSyncedWithNVR) {
      const v = document.querySelector("video");
      if (v && v !== boundVideo) attachVideoSyncListeners(v);
    }
  }

  // Listen for commands from the Extension Popup (e.g., "Start PiP Video Capture")
  chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
    if (msg && msg.action === "triggerPageVideoSync") {
      const btn = document.getElementById("nvr-cast-yt-btn");
      startSyncForCurrentVideo(btn || {}, Boolean(msg.pipMode));
      sendResponse({ ok: true });
    } else if (msg && msg.action === "stopPageVideoSync") {
      const btn = document.getElementById("nvr-cast-yt-btn");
      stopSync(btn || {});
      sendResponse({ ok: true });
    }
  });

  // Periodic check to inject button on YouTube and poll NVR busy status
  setInterval(() => {
    if (window.location.hostname.includes("youtube.com")) {
      injectYouTubePlayerButton();
      const btn = document.getElementById("nvr-cast-yt-btn");
      if (btn && !isSyncedWithNVR) {
        chrome.runtime.sendMessage({ action: "getStatus" }, (res) => {
          if (res && res.ok) updateButtonUI(btn, res.status);
        });
      }
    }
  }, 2000);
})();
