const serverInput = document.getElementById("serverUrl");
const btnSaveUrl = document.getElementById("btnSaveUrl");
const modeTxt = document.getElementById("modeTxt");
const sourceTxt = document.getElementById("sourceTxt");
const titleTxt = document.getElementById("titleTxt");
const posTxt = document.getElementById("posTxt");
const connBadge = document.getElementById("connBadge");
const chkLoop = document.getElementById("chkLoop");

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

if (serverInput) serverInput.addEventListener("change", saveHubUrl);
if (btnSaveUrl) btnSaveUrl.addEventListener("click", saveHubUrl);

function getHub() {
  const raw = serverInput && serverInput.value ? serverInput.value.trim() : "http://127.0.0.1:8090";
  return (raw || "http://127.0.0.1:8090").replace(/\/+$/, "");
}

async function refreshStatus() {
  try {
    const r = await fetch(`${getHub()}/api/status`);
    const d = await r.json();
    if (modeTxt) modeTxt.textContent = (d.mode || "ONLINE") + (d.is_paused ? " (PAUSED)" : "");
    if (sourceTxt) sourceTxt.textContent = d.active_source || "System";
    if (titleTxt) titleTxt.textContent = d.title || "Ready";
    if (chkLoop && typeof d.loop_video === "boolean") {
      chkLoop.checked = d.loop_video;
    }
    if (posTxt) {
      if (d.mode === "YOUTUBE" || d.mode === "FILE") {
        const m = Math.floor((d.playback_sec || 0) / 60);
        const s = (d.playback_sec || 0) % 60;
        posTxt.textContent = `⏱ Position: ${m}m ${s}s ${d.loop_video ? "• 🔁 Loop Active" : ""}`;
      } else if (d.mode === "GALLERY" && d.gallery) {
        posTxt.textContent = `🖼️ Slide ${d.gallery.index + 1}/${d.gallery.count} (${d.gallery.interval}s timer)`;
      } else {
        posTxt.textContent = "";
      }
    }
    if (connBadge) {
      connBadge.textContent = "ONLINE";
      connBadge.style.background = "#22c55e";
      connBadge.style.color = "#052e16";
    }
  } catch (e) {
    if (modeTxt) modeTxt.textContent = "OFFLINE";
    if (sourceTxt) sourceTxt.textContent = "-";
    if (titleTxt) titleTxt.textContent = "Launch NVR Cast Hub on PC";
    if (posTxt) posTxt.textContent = "";
    if (connBadge) {
      connBadge.textContent = "OFFLINE";
      connBadge.style.background = "#ef4444";
      connBadge.style.color = "#ffffff";
    }
  }
}

setInterval(refreshStatus, 1500);

// Active Stream Controls: Pause/Resume & Seek -10s / +10s
const btnTogglePause = document.getElementById("btnTogglePause");
if (btnTogglePause) {
  btnTogglePause.addEventListener("click", async () => {
    await fetch(`${getHub()}/api/player_sync`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ event: "toggle_pause", source: "Chrome Extension" }),
    });
    setTimeout(refreshStatus, 300);
  });
}

async function sendSeekDelta(deltaSec) {
  await fetch(`${getHub()}/api/player_sync`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ event: "seek", delta_sec: deltaSec, source: "Chrome Extension" }),
  });
  setTimeout(refreshStatus, 400);
}

const btnSeekBack = document.getElementById("btnSeekBack");
if (btnSeekBack) btnSeekBack.addEventListener("click", () => sendSeekDelta(-10));

const btnSeekFwd = document.getElementById("btnSeekFwd");
if (btnSeekFwd) btnSeekFwd.addEventListener("click", () => sendSeekDelta(10));

// Cast Current Tab's Video with Live Seek/Pause Sync
const btnCastCurrentTab = document.getElementById("btnCastCurrentTab");
if (btnCastCurrentTab) {
  btnCastCurrentTab.addEventListener("click", async () => {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab || !tab.url) return;

    // Tell the content script on the tab to attach seek/pause sync listeners
    try {
      chrome.tabs.sendMessage(tab.id, { action: "triggerPageVideoSync", pipMode: false });
    } catch (e) {}

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
    const loop = chkLoop ? chkLoop.checked : false;
    await fetch(`${getHub()}/api/youtube`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        url: targetUrl,
        start_sec: startSec,
        loop,
        source: "Chrome Extension (Tab Video Sync)",
      }),
    });
    setTimeout(refreshStatus, 500);
  });
}

// PiP-Style Live HTML5 <video>.captureStream() Mirroring
const btnPipMirror = document.getElementById("btnPipMirror");
if (btnPipMirror) {
  btnPipMirror.addEventListener("click", async () => {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab || !tab.id) return;
    chrome.tabs.sendMessage(tab.id, { action: "triggerPageVideoSync", pipMode: true }, () => {
      setTimeout(refreshStatus, 600);
    });
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
    body: JSON.stringify({ monitors, source: "Chrome Extension" }),
  });
  setTimeout(refreshStatus, 500);
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
    if (!q) return;
    await fetch(`${getHub()}/api/youtube`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url: q, start_sec: 0, loop, source: "Chrome Extension" }),
    });
    if (customInput) customInput.value = "";
    setTimeout(refreshStatus, 500);
  });
}

// Photo Gallery Slideshow Quick Controls
const btnOpenStudio = document.getElementById("btnOpenStudio");
if (btnOpenStudio) {
  btnOpenStudio.addEventListener("click", () => {
    chrome.tabs.create({ url: `${getHub()}/` });
  });
}

async function stepGallery(step) {
  await fetch(`${getHub()}/api/gallery`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action: "step", step }),
  });
  setTimeout(refreshStatus, 300);
}

const btnGalPrev = document.getElementById("btnGalPrev");
if (btnGalPrev) btnGalPrev.addEventListener("click", () => stepGallery(-1));

const btnGalNext = document.getElementById("btnGalNext");
if (btnGalNext) btnGalNext.addEventListener("click", () => stepGallery(1));

const btnStop = document.getElementById("btnStop");
if (btnStop) {
  btnStop.addEventListener("click", async () => {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (tab && tab.id) {
      try {
        chrome.tabs.sendMessage(tab.id, { action: "stopPageVideoSync" });
      } catch (e) {}
    }
    await fetch(`${getHub()}/api/standby`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ source: "Chrome Extension" }),
    });
    setTimeout(refreshStatus, 400);
  });
}
