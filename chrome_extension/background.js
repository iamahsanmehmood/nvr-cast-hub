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

  if (msg.action === "castYoutube") {
    fetchFromHub("/api/youtube", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        url: msg.url,
        start_sec: msg.start_sec || 0,
        loop: Boolean(msg.loop),
        source: msg.source || "Chrome Extension (Video Sync)",
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
        source: msg.source || "Chrome Extension (Video Sync)",
      }),
    }).then(sendResponse);
    return true;
  }

  if (msg.action === "startLiveVideoStream") {
    fetchFromHub("/api/browser_cast/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        label: msg.label || "PiP Browser Video Player",
        source: "Chrome Extension (PiP Stream)",
      }),
    }).then(sendResponse);
    return true;
  }

  if (msg.action === "pushVideoChunk") {
    getCandidateUrls(async (candidates) => {
      const base = candidates[0] || "http://127.0.0.1:8090";
      try {
        const bytes = new Uint8Array(msg.chunk);
        const resp = await fetch(`${base}/api/browser_cast/chunk`, {
          method: "POST",
          body: bytes,
        });
        sendResponse({ ok: resp.ok });
      } catch (_) {
        sendResponse({ ok: false });
      }
    });
    return true;
  }

  if (msg.action === "stopCast") {
    fetchFromHub("/api/standby", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ source: "Chrome Extension" }),
    }).then(sendResponse);
    return true;
  }

  return false;
});
