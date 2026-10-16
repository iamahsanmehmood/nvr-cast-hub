const serverInput = document.getElementById("serverUrl");
const btnSaveUrl = document.getElementById("btnSaveUrl");
const modeTxt = document.getElementById("modeTxt");
const titleTxt = document.getElementById("titleTxt");
const connBadge = document.getElementById("connBadge");

chrome.storage.local.get(["hubUrl"], (res) => {
  if (res && res.hubUrl && serverInput) {
    serverInput.value = res.hubUrl;
  }
  refreshStatus();
});

function saveHubUrl() {
  if (!serverInput) return;
  const val = serverInput.value.trim() || "http://127.0.0.1:8090";
  chrome.storage.local.set({ hubUrl: val });
  refreshStatus();
}

if (serverInput) {
  serverInput.addEventListener("change", saveHubUrl);
}
if (btnSaveUrl) {
  btnSaveUrl.addEventListener("click", saveHubUrl);
}

function getHub() {
  const raw = serverInput && serverInput.value ? serverInput.value.trim() : "http://127.0.0.1:8090";
  return (raw || "http://127.0.0.1:8090").replace(/\/+$/, "");
}

async function refreshStatus() {
  try {
    const r = await fetch(`${getHub()}/api/status`);
    const d = await r.json();
    if (modeTxt) modeTxt.textContent = d.mode || "ONLINE";
    if (titleTxt) titleTxt.textContent = d.title || "Ready";
    if (connBadge) {
      connBadge.textContent = "ONLINE";
      connBadge.style.background = "#22c55e";
      connBadge.style.color = "#052e16";
    }
  } catch (e) {
    if (modeTxt) modeTxt.textContent = "OFFLINE";
    if (titleTxt) titleTxt.textContent = "Launch NVR Cast Hub on PC";
    if (connBadge) {
      connBadge.textContent = "OFFLINE";
      connBadge.style.background = "#ef4444";
      connBadge.style.color = "#ffffff";
    }
  }
}

const btnCastCurrentTab = document.getElementById("btnCastCurrentTab");
if (btnCastCurrentTab) {
  btnCastCurrentTab.addEventListener("click", async () => {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab || !tab.url) return;

    let startSec = 0;
    let detectedVideoSrc = null;

    try {
      const results = await chrome.scripting.executeScript({
        target: { tabId: tab.id },
        func: () => {
          const v = document.querySelector("video");
          if (!v) return { time: 0, src: null };
          const src = v.currentSrc || v.src || null;
          return {
            time: Math.floor(v.currentTime || 0),
            src: src && !src.startsWith("blob:") ? src : null,
          };
        },
      });
      if (results && results[0] && results[0].result) {
        startSec = results[0].result.time || 0;
        detectedVideoSrc = results[0].result.src || null;
      }
    } catch (e) {}

    const targetUrl = detectedVideoSrc || tab.url;
    await fetch(`${getHub()}/api/youtube`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url: targetUrl, start_sec: startSec }),
    });
    setTimeout(refreshStatus, 600);
  });
}

const btnShareMeeting = document.getElementById("btnShareMeeting");
if (btnShareMeeting) {
  btnShareMeeting.addEventListener("click", () => {
    chrome.tabs.create({ url: `${getHub()}/?autoshare=1` });
  });
}

async function mirrorMonitors(monitors) {
  await fetch(`${getHub()}/api/screen`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ monitors }),
  });
  setTimeout(refreshStatus, 600);
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
    if (!q) return;
    await fetch(`${getHub()}/api/youtube`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url: q, start_sec: 0 }),
    });
    if (customInput) customInput.value = "";
    setTimeout(refreshStatus, 600);
  });
}

const btnStop = document.getElementById("btnStop");
if (btnStop) {
  btnStop.addEventListener("click", async () => {
    await fetch(`${getHub()}/api/standby`, { method: "POST" });
    setTimeout(refreshStatus, 600);
  });
}
