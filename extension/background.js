// Cross-browser compatible background script
const browserAPI = typeof browser !== 'undefined' ? browser : chrome;
const SERVER_URL = "http://127.0.0.1:5655";

browserAPI.runtime.onInstalled.addListener(() => {
  browserAPI.storage.local.set({ enabled: true });
});

browserAPI.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.type === "CHECK_SERVER") {
    fetch(`${SERVER_URL}/health`)
      .then(res => sendResponse({ online: res.ok }))
      .catch(() => sendResponse({ online: false }));
    return true;  // Keep channel open for async response
  }
  
  if (msg.type === "SEND_VIDEO") {
    fetch(`${SERVER_URL}/play`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url: msg.url })
    })
      .then(res => sendResponse({ success: res.ok }))
      .catch(() => sendResponse({ success: false }));
    return true;
  }
});