function getBaseUrl(cb) {
  chrome.storage.local.get(["hubUrl"], (res) => {
    const base = (res && res.hubUrl ? res.hubUrl : "http://127.0.0.1:8090").replace(/\/+$/, "");
    cb(base);
  });
}

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (!msg || !msg.action) return false;

  if (msg.action === "getStatus") {
    getBaseUrl(async (base) => {
      try {
        const r = await fetch(`${base}/api/status`);
        const data = await r.json();
        sendResponse({ ok: true, status: data });
      } catch (err) {
        sendResponse({ ok: false, error: String(err) });
      }
    });
    return true;
  }

  if (msg.action === "castYoutube") {
    getBaseUrl(async (base) => {
      try {
        const resp = await fetch(`${base}/api/youtube`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            url: msg.url,
            start_sec: msg.start_sec || 0,
            loop: Boolean(msg.loop),
            source: msg.source || "Chrome Extension (Live Sync)",
          }),
        });
        const data = await resp.json().catch(() => ({}));
        sendResponse({ ok: resp.ok, status: data });
      } catch (err) {
        sendResponse({ ok: false, error: String(err) });
      }
    });
    return true;
  }

  if (msg.action === "playerSync") {
    getBaseUrl(async (base) => {
      try {
        const resp = await fetch(`${base}/api/player_sync`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            event: msg.event,
            time_sec: msg.time_sec,
            delta_sec: msg.delta_sec,
            source: msg.source || "Chrome Extension (Live Sync)",
          }),
        });
        const data = await resp.json().catch(() => ({}));
        sendResponse({ ok: resp.ok, status: data });
      } catch (err) {
        sendResponse({ ok: false, error: String(err) });
      }
    });
    return true;
  }

  if (msg.action === "startLiveVideoStream") {
    getBaseUrl(async (base) => {
      try {
        const resp = await fetch(`${base}/api/browser_cast/start`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            label: msg.label || "PiP Browser Video Player",
            source: "Chrome Extension (PiP Video Stream)",
          }),
        });
        sendResponse({ ok: resp.ok });
      } catch (err) {
        sendResponse({ ok: false, error: String(err) });
      }
    });
    return true;
  }

  if (msg.action === "pushVideoChunk") {
    getBaseUrl(async (base) => {
      try {
        const bytes = new Uint8Array(msg.chunk);
        const resp = await fetch(`${base}/api/browser_cast/chunk`, {
          method: "POST",
          body: bytes,
        });
        sendResponse({ ok: resp.ok });
      } catch (err) {
        sendResponse({ ok: false });
      }
    });
    return true;
  }

  if (msg.action === "stopCast") {
    getBaseUrl(async (base) => {
      try {
        const resp = await fetch(`${base}/api/standby`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ source: "Chrome Extension" }),
        });
        sendResponse({ ok: resp.ok });
      } catch (err) {
        sendResponse({ ok: false });
      }
    });
    return true;
  }

  return false;
});
