(function () {
  function injectNVRButton() {
    const rightControls = document.querySelector(".ytp-right-controls");
    if (!rightControls || document.getElementById("nvr-cast-yt-btn")) return;

    const btn = document.createElement("button");
    btn.id = "nvr-cast-yt-btn";
    btn.className = "ytp-button";
    btn.title = "Cast this YouTube video to NVR Monitor (v0.1.0-beta)";
    btn.style.cssText =
      "width: auto !important; padding: 0 10px !important; font-weight: 700; font-size: 12px; color: #fff; background: #ef4444; border-radius: 4px; margin: 8px 6px; height: 28px; line-height: 28px; display: inline-flex; align-items: center; cursor: pointer;";
    btn.textContent = "📺 Cast to NVR";

    btn.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      const v = document.querySelector("video");
      const startSec = v ? Math.floor(v.currentTime || 0) : 0;
      btn.textContent = "⏳ Casting...";
      btn.style.background = "#f59e0b";

      chrome.runtime.sendMessage(
        {
          action: "castYoutube",
          url: window.location.href,
          start_sec: startSec,
        },
        (resp) => {
          if (resp && resp.ok) {
            btn.textContent = "✅ On NVR!";
            btn.style.background = "#22c55e";
          } else {
            alert("Could not reach NVR Cast Hub on http://127.0.0.1:8090. Make sure NVR Cast Hub is running on your PC!");
            btn.textContent = "📺 Cast to NVR";
            btn.style.background = "#ef4444";
            return;
          }
          setTimeout(() => {
            btn.textContent = "📺 Cast to NVR";
            btn.style.background = "#ef4444";
          }, 3000);
        }
      );
    });

    rightControls.prepend(btn);
  }

  setInterval(injectNVRButton, 1500);
})();
