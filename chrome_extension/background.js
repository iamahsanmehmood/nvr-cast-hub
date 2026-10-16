chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg && msg.action === "castYoutube") {
    chrome.storage.local.get(["hubUrl"], async (res) => {
      const base = (res && res.hubUrl ? res.hubUrl : "http://127.0.0.1:8090").replace(/\/+$/, "");
      try {
        const resp = await fetch(`${base}/api/youtube`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            url: msg.url,
            start_sec: msg.start_sec || 0,
          }),
        });
        sendResponse({ ok: resp.ok });
      } catch (err) {
        sendResponse({ ok: false, error: String(err) });
      }
    });
    return true; // keep message channel open for async response
  }
});
