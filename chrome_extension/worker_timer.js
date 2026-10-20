// Dedicated Manifest V3 'self' Web Worker timer (immune to background tab throttling and MV3 blob: CSP restrictions)
let timerId = null;

self.onmessage = function (e) {
  const data = e.data || {};
  if (data.cmd === "start") {
    if (timerId) clearInterval(timerId);
    const interval = Math.max(25, Number(data.interval) || 42);
    timerId = setInterval(() => {
      self.postMessage("tick");
    }, interval);
  } else if (data.cmd === "stop") {
    if (timerId) {
      clearInterval(timerId);
      timerId = null;
    }
  }
};
