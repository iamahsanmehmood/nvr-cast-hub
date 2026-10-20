const serverInput = document.getElementById("serverUrl");
const btnSaveUrl = document.getElementById("btnSaveUrl");
const modeTxt = document.getElementById("modeTxt");
const sourceTxt = document.getElementById("sourceTxt");
const titleTxt = document.getElementById("titleTxt");
const posTxt = document.getElementById("posTxt");
const connBadge = document.getElementById("connBadge");
const chkLoop = document.getElementById("chkLoop");
const pauseBtnLabel = document.getElementById("pauseBtnLabel");
const toastMsg = document.getElementById("toastMsg");

let toastTimer = null;
let cachedActiveTab = null;

function showToast(text, isError = false) {
  if (!toastMsg) return;
  toastMsg.textContent = text;
  toastMsg.style.display = "block";
  if (isError) {
    toastMsg.style.background = "#fef2f2";
    toastMsg.style.color = "#b91c1c";
    toastMsg.style.borderColor = "#fecaca";
  } else {
    toastMsg.style.background = "#eff6ff";
    toastMsg.style.color = "#1d4ed8";
    toastMsg.style.borderColor = "#bfdbfe";
  }
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    toastMsg.style.display = "none";
  }, 3200);
}

function getActiveTabSafe(cb) {
  try {
    chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
      void chrome.runtime.lastError;
      const t = tabs && tabs[0] ? tabs[0] : null;
      if (t) cachedActiveTab = t;
      cb(t);
    });
  } catch (_) {
    cb(cachedActiveTab);
  }
}

// Pre-cache active tab on popup open so user click gestures can execute immediately without async delay
getActiveTabSafe(() => {});

chrome.storage.local.get(["hubUrl"], (res) => {
  void chrome.runtime.lastError;
  if (res && res.hubUrl && serverInput) {
    serverInput.value = res.hubUrl;
  }
  refreshStatus();
  loadPopupTvCatalog();
});

function saveHubUrl() {
  if (!serverInput) return;
  const val = serverInput.value.trim() || "http://127.0.0.1:8090";
  chrome.storage.local.set({ hubUrl: val }, () => {
    void chrome.runtime.lastError;
    showToast("Saved Hub URL: " + val);
    refreshStatus();
  });
}

if (serverInput) serverInput.addEventListener("change", saveHubUrl);
if (btnSaveUrl) btnSaveUrl.addEventListener("click", saveHubUrl);

function getHub() {
  const raw = serverInput && serverInput.value ? serverInput.value.trim() : "http://127.0.0.1:8090";
  return (raw || "http://127.0.0.1:8090").replace(/\/+$/, "");
}

/**
 * Safe API helper that routes through background.js and NEVER throws uncaught Promise rejections.
 */
async function hubRequest(path, method = "GET", body = null) {
  return new Promise((resolve) => {
    try {
      chrome.runtime.sendMessage(
        { action: "hubApi", path, method, body },
        (resp) => {
          void chrome.runtime.lastError;
          if (resp && resp.ok) {
            resolve(resp);
          } else {
            resolve({ ok: false, error: (resp && resp.error) || "Hub offline" });
          }
        }
      );
    } catch (err) {
      resolve({ ok: false, error: String(err) });
    }
  });
}

/**
 * Safely sends a message to an active http/https tab. If the tab was opened BEFORE the extension
 * was loaded, automatically injects content_youtube.js into all frames and retries once.
 */
function sendToTabSafe(tab, payload, callback) {
  if (!tab || !tab.id || !tab.url || (!tab.url.startsWith("http://") && !tab.url.startsWith("https://"))) {
    if (callback) callback({ ok: false, restricted: true });
    return;
  }

  try {
    chrome.tabs.sendMessage(tab.id, payload, (resp) => {
      const err = chrome.runtime.lastError;
      if (!err && resp && resp.ok) {
        if (callback) callback(resp);
        return;
      }
      // Inject content_youtube.js into all frames of the already-open tab and retry once
      try {
        chrome.scripting.executeScript(
          { target: { tabId: tab.id, allFrames: true }, files: ["content_youtube.js"] },
          () => {
            void chrome.runtime.lastError;
            try {
              chrome.tabs.sendMessage(tab.id, payload, (resp2) => {
                void chrome.runtime.lastError;
                if (callback) callback(resp2 || { ok: false });
              });
            } catch (_) {
              if (callback) callback({ ok: false });
            }
          }
        );
      } catch (_) {
        if (callback) callback({ ok: false });
      }
    });
  } catch (_) {
    if (callback) callback({ ok: false });
  }
}

function triggerTabPipImmediate(tab) {
  if (!tab || !tab.id || !tab.url || (!tab.url.startsWith("http://") && !tab.url.startsWith("https://"))) {
    return;
  }
  try {
    chrome.scripting.executeScript(
      {
        target: { tabId: tab.id, allFrames: true },
        world: "MAIN",
        func: () => {
          const vids = Array.from(document.querySelectorAll("video"));
          if (!vids.length) return false;
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
          if (best && best.readyState >= 1) {
            try {
              best.removeAttribute("disablePictureInPicture");
              best.disablePictureInPicture = false;
              if (document.pictureInPictureElement !== best && typeof best.requestPictureInPicture === "function") {
                best.requestPictureInPicture().catch(() => {});
                return true;
              }
            } catch (_) {}
          }
          return false;
        },
      },
      () => {
        void chrome.runtime.lastError;
      }
    );
  } catch (_) {}
}

async function refreshStatus() {
  const res = await hubRequest("/api/status", "GET");
  if (!res.ok || !res.status) {
    if (modeTxt) {
      modeTxt.textContent = "OFFLINE";
      modeTxt.style.background = "#fee2e2";
      modeTxt.style.color = "#b91c1c";
    }
    if (sourceTxt) sourceTxt.textContent = "-";
    if (titleTxt) titleTxt.textContent = "Start NVR Cast Hub on your PC";
    if (posTxt) posTxt.textContent = "Waiting for http://127.0.0.1:8090";
    if (connBadge) {
      connBadge.textContent = "OFFLINE";
      connBadge.style.background = "#fee2e2";
      connBadge.style.color = "#b91c1c";
      connBadge.style.borderColor = "#fecaca";
    }
    return;
  }

  const d = res.status;
  if (modeTxt) {
    modeTxt.textContent = (d.mode || "ONLINE") + (d.is_paused ? " • PAUSED" : "");
    if (d.is_paused) {
      modeTxt.style.background = "#fef3c7";
      modeTxt.style.color = "#b45309";
    } else {
      modeTxt.style.background = "#dcfce7";
      modeTxt.style.color = "#15803d";
    }
  }
  if (pauseBtnLabel) {
    pauseBtnLabel.textContent = d.is_paused ? "Resume" : "Pause";
  }
  if (sourceTxt) sourceTxt.textContent = d.active_source || "System";
  if (titleTxt) titleTxt.textContent = d.title || "Ready";
  if (chkLoop && typeof d.loop_video === "boolean") {
    chkLoop.checked = d.loop_video;
  }
  if (posTxt) {
    if (d.mode === "YOUTUBE" || d.mode === "FILE" || (d.mode === "BROWSER" && (d.playback_sec > 0 || d.duration_sec > 0))) {
      const m = Math.floor((d.playback_sec || 0) / 60);
      const s = String((d.playback_sec || 0) % 60).padStart(2, "0");
      let durStr = "";
      if (d.duration_sec > 0) {
        const dm = Math.floor(d.duration_sec / 60);
        const ds = String(d.duration_sec % 60).padStart(2, "0");
        durStr = ` / ${dm}:${ds}`;
      }
      posTxt.textContent = `Position: ${m}:${s}${durStr}${d.loop_video ? "  •  Loop Enabled" : ""}`;
    } else if (d.mode === "GALLERY" && d.gallery) {
      posTxt.textContent = `Slide ${d.gallery.index + 1} of ${d.gallery.count} (${d.gallery.interval}s timer${d.gallery.shuffle ? ", Shuffle" : ""})`;
    } else {
      posTxt.textContent = `RTSP: ${d.rtsp_main || "Active"}`;
    }
  }
  if (connBadge) {
    connBadge.textContent = "ONLINE";
    connBadge.style.background = "#dcfce7";
    connBadge.style.color = "#15803d";
    connBadge.style.borderColor = "#bbf7d0";
  }
}

setInterval(refreshStatus, 1600);

// 1. Active Session Transport Controls
const btnTogglePause = document.getElementById("btnTogglePause");
if (btnTogglePause) {
  btnTogglePause.addEventListener("click", async () => {
    const r = await hubRequest("/api/player_sync", "POST", {
      event: "toggle_pause",
      source: "Chrome Extension",
    });
    if (!r.ok) showToast("NVR Cast Hub is not running on port 8090", true);
    refreshStatus();
  });
}

async function sendSeekDelta(deltaSec) {
  const r = await hubRequest("/api/player_sync", "POST", {
    event: "seek",
    delta_sec: deltaSec,
    source: "Chrome Extension",
  });
  if (!r.ok) showToast("NVR Cast Hub is not running on port 8090", true);
  refreshStatus();
}

const btnSeekBack = document.getElementById("btnSeekBack");
if (btnSeekBack) btnSeekBack.addEventListener("click", () => sendSeekDelta(-10));

const btnSeekFwd = document.getElementById("btnSeekFwd");
if (btnSeekFwd) btnSeekFwd.addEventListener("click", () => sendSeekDelta(10));

function castLiveTabStream(activatePip = true) {
  // Trigger Picture-in-Picture synchronously on the cached tab while user activation is active
  if (activatePip && cachedActiveTab) {
    triggerTabPipImmediate(cachedActiveTab);
  }

  getActiveTabSafe((tab) => {
    if (!tab || !tab.url || (!tab.url.startsWith("http://") && !tab.url.startsWith("https://"))) {
      showToast("Open a web video tab first to cast it.", true);
      return;
    }

    if (activatePip && (!cachedActiveTab || cachedActiveTab.id !== tab.id)) {
      triggerTabPipImmediate(tab);
    }

    const loop = chkLoop ? chkLoop.checked : false;
    const sessionId = `chrome_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`;
    const cleanTitle = (tab.title || "Live Chrome Video Stream")
      .replace(/^\(\d+\)\s*/, "")
      .replace(/\s*-\s*YouTube$/i, "")
      .trim();

    showToast(activatePip ? "Starting PiP Video Stream to NVR..." : "Starting live Chrome video stream to NVR...");

    // Start the NVR Cast Hub session + offscreen tabCapture lock (with automatic hybrid frame pumping)
    chrome.runtime.sendMessage(
      {
        action: "startLiveVideoStream",
        tabId: tab.id,
        session_id: sessionId,
        label: cleanTitle || "Live Chrome Video Stream",
        url: tab.url,
        loop,
        acquireTabLock: true,
        pumpTabFrames: true,
        source: activatePip ? "Chrome Extension (PiP Stream)" : "Chrome Extension (Live Tab)",
      },
      (bgRes) => {
        void chrome.runtime.lastError;
        if (!bgRes || !bgRes.ok) {
          showToast("Could not connect to NVR Cast Hub on port 8090. Ensure the app is running.", true);
          return;
        }

        // Also attach in-page <video> frame + timeline sync using the exact same sessionId
        sendToTabSafe(
          tab,
          {
            action: "startDirectLiveCast",
            activatePip,
            loop,
            hubAlreadyStarted: true,
            session_id: sessionId,
          },
          () => {
            showToast(
              activatePip
                ? "PiP Video Stream active! Continues across tab switches."
                : "Live Chrome stream active! Continues across tab switches."
            );
            setTimeout(refreshStatus, 350);
          }
        );
      }
    );
  });
}

// 2. Cast Current Tab Video (Direct Live Stream from Chrome Player)
const btnCastCurrentTab = document.getElementById("btnCastCurrentTab");
if (btnCastCurrentTab) {
  btnCastCurrentTab.addEventListener("click", () => castLiveTabStream(false));
}

// 3. PiP-Style Live Video Player Stream
const btnPipMirror = document.getElementById("btnPipMirror");
if (btnPipMirror) {
  btnPipMirror.addEventListener("click", () => castLiveTabStream(true));
}

const btnShareMeeting = document.getElementById("btnShareMeeting");
if (btnShareMeeting) {
  btnShareMeeting.addEventListener("click", () => {
    chrome.tabs.create({ url: `${getHub()}/?autoshare=1` });
  });
}

async function mirrorMonitors(monitors) {
  showToast("Switching NVR to PC Monitor Mirror...");
  const r = await hubRequest("/api/screen", "POST", {
    monitors,
    source: "Chrome Extension",
  });
  if (!r.ok) showToast("NVR Cast Hub is offline.", true);
  refreshStatus();
}

const btnMon1 = document.getElementById("btnMon1");
if (btnMon1) btnMon1.addEventListener("click", () => mirrorMonitors([1]));

const btnMon2 = document.getElementById("btnMon2");
if (btnMon2) btnMon2.addEventListener("click", () => mirrorMonitors([2]));

const btnMonAll = document.getElementById("btnMonAll");
if (btnMonAll) btnMonAll.addEventListener("click", () => mirrorMonitors([1, 2]));

const btnCastCustom = document.getElementById("btnCastCustom");
if (btnCastCustom) {
  btnCastCustom.addEventListener("click", async () => {
    const customInput = document.getElementById("customQuery");
    const q = customInput ? customInput.value.trim() : "";
    const loop = chkLoop ? chkLoop.checked : false;
    if (!q) {
      showToast("Enter a YouTube URL or search query first.", true);
      return;
    }
    showToast("Starting stream on NVR...");
    const r = await hubRequest("/api/youtube", "POST", {
      url: q,
      start_sec: 0,
      loop,
      source: "Chrome Extension",
    });
    if (r.ok && customInput) customInput.value = "";
    if (!r.ok) showToast("NVR Cast Hub is offline.", true);
    refreshStatus();
  });
}

const btnOpenStudio = document.getElementById("btnOpenStudio");
if (btnOpenStudio) {
  btnOpenStudio.addEventListener("click", () => {
    chrome.tabs.create({ url: `${getHub()}/` });
  });
}

async function stepGallery(step) {
  const r = await hubRequest("/api/gallery", "POST", { action: "step", step });
  if (!r.ok) showToast("NVR Cast Hub is offline.", true);
  refreshStatus();
}

const btnGalPrev = document.getElementById("btnGalPrev");
if (btnGalPrev) btnGalPrev.addEventListener("click", () => stepGallery(-1));

const btnGalNext = document.getElementById("btnGalNext");
if (btnGalNext) btnGalNext.addEventListener("click", () => stepGallery(1));

const btnStop = document.getElementById("btnStop");
if (btnStop) {
  btnStop.addEventListener("click", async () => {
    getActiveTabSafe((tab) => {
      if (tab) sendToTabSafe(tab, { action: "stopPageVideoSync" });
    });
    chrome.runtime.sendMessage({ action: "stopCast" }, () => {
      void chrome.runtime.lastError;
      showToast("Stopped cast — NVR returned to Standby.");
      refreshStatus();
    });
  });
}

// Live Sports, Pakistan Cricket & GitHub IPTV Controls
const selTvCat = document.getElementById("selTvCat");
const selTvChannel = document.getElementById("selTvChannel");
const btnPlayTvCh = document.getElementById("btnPlayTvCh");

function populatePopupTvChannels(catData) {
  if (!selTvChannel || !catData) return;
  const chs = catData.channels || [];
  selTvChannel.innerHTML = chs
    .map((ch, idx) => `<option value="${idx}">[${idx + 1}] ${ch.title}</option>`)
    .join("");
  if (typeof catData.active_index === "number" && catData.active_index < chs.length) {
    selTvChannel.value = String(catData.active_index);
  }
}

async function loadPopupTvCatalog() {
  const r = await hubRequest("/api/live_tv", "GET");
  if (r && r.ok && r.status) {
    if (selTvCat && r.status.category) selTvCat.value = r.status.category;
    populatePopupTvChannels(r.status);
  }
}

if (selTvCat) {
  selTvCat.addEventListener("change", async () => {
    showToast("Loading channels...");
    const r = await hubRequest("/api/live_tv", "POST", {
      action: "load",
      category: selTvCat.value,
      filter: "",
      auto_play: false,
      source: "Chrome Extension Live TV",
    });
    if (r && r.ok && r.status) {
      populatePopupTvChannels(r.status);
    }
  });
}

if (btnPlayTvCh) {
  btnPlayTvCh.addEventListener("click", async () => {
    const idx = selTvChannel ? parseInt(selTvChannel.value || "0", 10) : 0;
    showToast("Streaming selected channel to NVR...");
    await hubRequest("/api/live_tv", "POST", {
      action: "play",
      index: idx,
      source: "Chrome Extension Live TV",
    });
    setTimeout(refreshStatus, 400);
  });
}
