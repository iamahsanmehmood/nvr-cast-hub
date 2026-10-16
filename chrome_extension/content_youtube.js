(function () {
  function injectNVRButton() {
    const rightControls = document.querySelector(".ytp-right-controls");
    if (!rightControls || document.getElementById("nvr-cast-yt-btn")) return;

    const btn = document.createElement("button");
    btn.id = "nvr-cast-yt-btn";
    btn.className = "ytp-button";
    btn.title = "Cast this YouTube video to Hikvision NVR Monitor";
    btn.style.cssText =
      "width: auto !important; padding: 0 10px !important; font-weight: 700; font-size: 12px; color: #fff; background: #ef4444; border-radius: 4px; margin: 8px 6px; height: 28px; line-height: 28px; display: inline-flex; align-items: center; cursor: pointer;";
    btn.textContent = "📺 Cast to NVR";

    btn.addEventListener("click", async (e) => {
      e.preventDefault();
      e.stopPropagation();
      const v = document.querySelector("video");
      const startSec = v ? Math.floor(v.currentTime || 0) : 0;
      btn.textContent = "⏳ Casting...";
      btn.style.background = "#f59e0b";
      try {
        await fetch("http://127.0.0.1:8090/api/youtube", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ url: window.location.href, start_sec: startSec }),
        });
        btn.textContent = "✅ On NVR!";
        btn.style.background = "#22c55e";
        setTimeout(() => {
          btn.textContent = "📺 Cast to NVR";
          btn.style.background = "#ef4444";
        }, 3000);
      } catch (err) {
        alert("Could not reach NVR Cast Hub on http://127.0.0.1:8090. Make sure the desktop app is running!");
        btn.textContent = "📺 Cast to NVR";
        btn.style.background = "#ef4444";
      }
    });

    rightControls.prepend(btn);
  }

  setInterval(injectNVRButton, 1500);
})();
