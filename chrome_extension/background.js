function getCandidateUrls(cb) {
  chrome.storage.local.get(["hubUrl"], (res) => {
    void chrome.runtime.lastError;
    const saved = res && res.hubUrl ? res.hubUrl.trim().replace(/\/+$/, "") : "";
    const candidates = [];
    if (saved) candidates.push(saved);
    if (!candidates.includes("http://127.0.0.1:8090")) candidates.push("http://127.0.0.1:8090");
    if (!candidates.includes("http://localhost:8090")) candidates.push("http://localhost:8090");
    cb(candidates);
  });
}

async function fetchFromHub(path, options = {}) {
  return new Promise((resolve) => {
    getCandidateUrls(async (candidates) => {
      let lastErr = "Hub unreachable";
      for (const base of candidates) {
        try {
          const controller = new AbortController();
          const timer = setTimeout(() => controller.abort(), 4500);
          const resp = await fetch(`${base}${path}`, {
            ...options,
            signal: controller.signal,
          });
          clearTimeout(timer);
          let data = {};
          try {
            data = await resp.json();
          } catch (_) {}
          resolve({ ok: resp.ok, status: data, baseUrl: base });
          return;
        } catch (err) {
          lastErr = err && err.message ? err.message : String(err);
        }
      }
      resolve({ ok: false, error: lastErr });
    });
  });
}

async function ensureOffscreenDocument() {
  try {
    if (chrome.offscreen && chrome.offscreen.hasDocument) {
      const exists = await chrome.offscreen.hasDocument();
      if (exists) return true;
    }
    await chrome.offscreen.createDocument({
      url: "offscreen.html",
      reasons: ["USER_MEDIA", "AUDIO_PLAYBACK"],
      justification: "Keep active video tab rendering smoothly when switching tabs while casting to NVR.",
    });
    return true;
  } catch (err) {
    if (String(err).includes("Only a single offscreen")) return true;
    return false;
  }
}

function injectVisibilityKeepAlive(tabId) {
  if (!tabId) return;
  try {
    chrome.scripting.executeScript(
      {
        target: { tabId },
        world: "MAIN",
        func: () => {
          if (window.__nvrVisibilityPatched) return;
          window.__nvrVisibilityPatched = true;
          try {
            Object.defineProperty(document, "hidden", {
              configurable: true,
              get: () => false,
            });
            Object.defineProperty(document, "visibilityState", {
              configurable: true,
              get: () => "visible",
            });
            Object.defineProperty(document, "webkitHidden", {
              configurable: true,
              get: () => false,
            });
            window.addEventListener(
              "visibilitychange",
              (e) => {
                e.stopImmediatePropagation();
              },
              true
            );
          } catch (_) {}
        },
      },
      () => {
        void chrome.runtime.lastError;
      }
    );
  } catch (_) {}
}

async function startTabCaptureLock(tabId, sessionId, hubUrl, pumpTabFrames = false) {
  if (!tabId || !chrome.tabCapture || !chrome.tabCapture.getMediaStreamId) {
    return { ok: false };
  }
  return new Promise((resolve) => {
    try {
      chrome.tabCapture.getMediaStreamId({ targetTabId: tabId }, async (streamId) => {
        const err = chrome.runtime.lastError;
        if (err || !streamId) {
          resolve({ ok: false, error: err ? err.message : "No streamId" });
          return;
        }
        const okDoc = await ensureOffscreenDocument();
        if (!okDoc) {
          resolve({ ok: false, error: "Offscreen unavailable" });
          return;
        }
        chrome.runtime.sendMessage(
          {
            offscreenAction: "startTabLock",
            streamId,
            sessionId,
            hubUrl: hubUrl || "http://127.0.0.1:8090",
            pumpTabFrames: Boolean(pumpTabFrames),
          },
          (resp) => {
            void chrome.runtime.lastError;
            resolve(resp || { ok: true });
          }
        );
      });
    } catch (e) {
      resolve({ ok: false, error: String(e) });
    }
  });
}

function stopTabCaptureLock() {
  try {
    chrome.runtime.sendMessage({ offscreenAction: "stopTabLock" }, () => {
      void chrome.runtime.lastError;
    });
  } catch (_) {}
}

function reinjectAllOpenTabs() {
  try {
    chrome.tabs.query({ url: ["http://*/*", "https://*/*"] }, (tabs) => {
      void chrome.runtime.lastError;
      if (!tabs) return;
      for (const t of tabs) {
        if (t && t.id) {
          try {
            chrome.scripting.executeScript(
              { target: { tabId: t.id }, files: ["content_youtube.js"] },
              () => {
                void chrome.runtime.lastError;
              }
            );
          } catch (_) {}
        }
      }
    });
  } catch (_) {}
}

chrome.runtime.onInstalled.addListener(() => {
  reinjectAllOpenTabs();
});

// Also clean up any legacy scripts in open tabs immediately when service worker wakes
reinjectAllOpenTabs();

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (!msg || !msg.action) return false;

  if (msg.action === "hubApi") {
    const opts = { method: msg.method || "GET" };
    if (msg.body !== undefined && msg.body !== null) {
      opts.headers = { "Content-Type": "application/json" };
      opts.body = JSON.stringify(msg.body);
    }
    fetchFromHub(msg.path || "/api/status", opts).then(sendResponse);
    return true;
  }

  if (msg.action === "getStatus") {
    fetchFromHub("/api/status", { method: "GET" }).then(sendResponse);
    return true;
  }

  if (msg.action === "startLiveVideoStream") {
    const targetTabId = msg.tabId || (sender && sender.tab ? sender.tab.id : null);
    const sessionId = msg.session_id || `chrome_${Date.now()}`;
    if (targetTabId) {
      injectVisibilityKeepAlive(targetTabId);
    }

    fetchFromHub("/api/browser_cast/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        label: msg.label || "Live Chrome Video Stream",
        source: msg.source || "Chrome Extension (Live Player)",
        session_id: sessionId,
        url: msg.url || "",
        loop: msg.loop,
      }),
    }).then(async (hubRes) => {
      let tabLockOk = false;
      if (hubRes && hubRes.ok && targetTabId && msg.acquireTabLock !== false) {
        const lockRes = await startTabCaptureLock(
          targetTabId,
          sessionId,
          hubRes.baseUrl || "http://127.0.0.1:8090",
          Boolean(msg.pumpTabFrames)
        );
        tabLockOk = Boolean(lockRes && lockRes.ok);
      }
      sendResponse({ ...hubRes, session_id: sessionId, tabLockOk });
    });
    return true;
  }

  if (msg.action === "pushVideoFrame") {
    getCandidateUrls(async (candidates) => {
      const base = candidates[0] || "http://127.0.0.1:8090";
      try {
        const resp = await fetch(`${base}/api/browser_cast/frame`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            frame: msg.frame,
            session_id: msg.session_id || "",
            time_sec: msg.time_sec,
            duration_sec: msg.duration_sec,
            paused: msg.paused,
            title: msg.title || "",
          }),
        });
        let data = {};
        try {
          data = await resp.json();
        } catch (_) {}
        sendResponse({ ok: resp.ok, ...data });
      } catch (_) {
        sendResponse({ ok: false });
      }
    });
    return true;
  }

  if (msg.action === "castYoutube") {
    fetchFromHub("/api/youtube", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        url: msg.url,
        start_sec: msg.start_sec || 0,
        loop: Boolean(msg.loop),
        source: msg.source || "Chrome Extension",
      }),
    }).then(sendResponse);
    return true;
  }

  if (msg.action === "playerSync") {
    fetchFromHub("/api/player_sync", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        event: msg.event,
        time_sec: msg.time_sec,
        delta_sec: msg.delta_sec,
        source: msg.source || "Chrome Extension",
      }),
    }).then(sendResponse);
    return true;
  }

  if (msg.action === "stopCast") {
    stopTabCaptureLock();
    fetchFromHub("/api/standby", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ source: "Chrome Extension" }),
    }).then(sendResponse);
    return true;
  }

  return false;
});
