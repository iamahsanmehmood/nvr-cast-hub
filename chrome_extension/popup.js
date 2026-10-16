const serverInput = document.getElementById("serverUrl");
const modeTxt = document.getElementById("modeTxt");
const titleTxt = document.getElementById("titleTxt");
const connBadge = document.getElementById("connBadge");

chrome.storage.local.get(["hubUrl"], (res) => {
  if (res.hubUrl) serverInput.value = res.hubUrl;
  refreshStatus();
});

serverInput.addEventListener("change", () => {
  chrome.storage.local.set({ hubUrl: serverInput.value.trim() });
  refreshStatus();
});

function getHub() {
  return serverInput.value.trim().replace(/\/+$/, "");
}

async function refreshStatus() {
  try {
    const r = await fetch(`${getHub()}/api/status`);
    const d = await r.json();
    modeTxt.textContent = d.mode;
    titleTxt.textContent = d.title;
    connBadge.textContent = "ONLINE";
    connBadge.style.background = "#22c55e";
  } catch (e) {
    connBadge.textContent = "OFFLINE";
    connBadge.style.background = "#ef4444";
    titleTxt.textContent = "Launch NVR Cast Hub on PC";
  }
}

document.getElementById("btnCastCurrentTab").addEventListener("click", async () => {
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

document.getElementById("btnShareMeeting").addEventListener("click", () => {
  chrome.tabs.create({ url: `http://localhost:8090/?autoshare=1` });
});

async function mirrorMonitors(monitors) {
  await fetch(`${getHub()}/api/screen`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ monitors }),
  });
  setTimeout(refreshStatus, 600);
}

document.getElementById("btnMon1").addEventListener("click", () => mirrorMonitors([1]));
document.getElementById("btnMon2").addEventListener("click", () => mirrorMonitors([2]));
document.getElementById("btnMonAll").addEventListener("click", () => mirrorMonitors([1, 2]));

document.getElementById("btnCastCustom").addEventListener("click", async () => {
  const q = document.getElementById("customQuery").value.trim();
  if (!q) return;
  await fetch(`${getHub()}/api/youtube`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url: q, start_sec: 0 }),
  });
  document.getElementById("customQuery").value = "";
  setTimeout(refreshStatus, 600);
});

document.getElementById("btnStop").addEventListener("click", async () => {
  await fetch(`${getHub()}/api/standby`, { method: "POST" });
  setTimeout(refreshStatus, 600);
});
