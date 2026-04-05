// background.js – punishment mode, redirect logic, force hijack

const DEFAULTS = {
  bambiActivated: false,
  bambiDomains: ["hypnotube.com"],
  bambiBlacklist: [],
  bambiIntensityLevel: 5,
  bambiMultiMonitor: true,
  bambiHardLock: true,
  bambiPunishMode: true,
  bambiSetupComplete: false,
  bambiServerOnline: false,
  bambiVideoHistory: [],
  bambiForceHijack: false,
  bambiPermanent: false,
  bambiPermanencePassword: null
};

// INSTALLATION HANDLER - Open settings on first install
chrome.runtime.onInstalled.addListener(async (details) => {
  if (details.reason === "install") {
    // First time installation - open settings page
    const data = await chrome.storage.local.get(DEFAULTS);
    if (!data.bambiSetupComplete) {
      chrome.runtime.openOptionsPage();
    }
  }
});

// Utility: random pick
function pickRandom(arr) {
  return arr[Math.floor(Math.random() * arr.length)];
}

// Utility: check domain match
function domainMatches(url, list) {
  try {
    const host = new URL(url).hostname.toLowerCase();
    return list.some(d => host.endsWith(d.toLowerCase()));
  } catch {
    return false;
  }
}

// MAIN NAVIGATION HANDLER
chrome.webNavigation.onCommitted.addListener(async (details) => {
  if (details.frameId !== 0) return; // only top frame

  const url = details.url;
  const data = await chrome.storage.local.get(DEFAULTS);

  // First-run setup not complete → do nothing
  if (!data.bambiSetupComplete) return;

  // Bambi Mode disabled → do nothing
  if (!data.bambiActivated) return;

  const isAllowed = domainMatches(url, data.bambiDomains);
  const isBlacklisted = domainMatches(url, data.bambiBlacklist);

  // Allowed domain → normal behavior
  if (isAllowed) return;

  // Not allowed + not blacklisted → ignore
  if (!isBlacklisted) return;

  // Blacklisted domain
  if (!data.bambiPunishMode) return;

  // Punish mode active → ask content script to show warning overlay
  chrome.tabs.sendMessage(details.tabId, { type: "BAMBI_SHOW_PUNISH_WARNING" });
});

// MESSAGE HANDLER (punish click → redirect)
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (!msg || typeof msg !== "object") return;

  if (msg.type === "BAMBI_PUNISH_CONFIRM") {
    (async () => {
      const data = await chrome.storage.local.get(DEFAULTS);

      const history = data.bambiVideoHistory || [];
      if (!history.length) {
        sendResponse?.({ ok: false, reason: "no_history" });
        return;
      }

      const randomVideo = pickRandom(history);

      // Set force hijack flag
      await chrome.storage.local.set({ bambiForceHijack: true });

      // Redirect tab to random video
      if (sender.tab && sender.tab.id != null) {
        chrome.tabs.update(sender.tab.id, { url: randomVideo });
      }

      sendResponse?.({ ok: true, url: randomVideo });
    })();

    // keep channel open for async sendResponse
    return true;
  }

  // PERMANENCE: Enable permanence mode
  if (msg.type === "ENABLE_PERMANENCE") {
    (async () => {
      const passphrase = msg.passphrase || "";
      const data = await chrome.storage.local.get(DEFAULTS);

      // Basic validation - store permanently (no encryption for now)
      if (passphrase.length < 4) {
        sendResponse?.({ success: false, error: "passphrase_too_short" });
        return;
      }

      // Call backend to create startup shortcut
      try {
        const backendResponse = await fetch("http://127.0.0.1:5655/permanence", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ enable: true })
        });

        const result = await backendResponse.json();
        if (!backendResponse.ok) {
          console.error("Backend permanence request failed:", result);
          sendResponse?.({ success: false, error: "backend_error" });
          return;
        }
      } catch (err) {
        console.error("Backend call failed:", err);
        sendResponse?.({ success: false, error: "backend_unreachable" });
        return;
      }

      // Store permanence state
      await chrome.storage.local.set({
        bambiPermanent: true,
        bambiPermanencePassword: passphrase
      });

      // Notify options page of success (it will refresh from storage)
      chrome.tabs.query({ url: "*://*/options.html" }, (tabs) => {
        tabs.forEach(tab => {
          chrome.tabs.sendMessage(tab.id, { type: "PERMANENCE_UPDATED", permanent: true }).catch(() => {});
        });
      });

      sendResponse?.({ success: true });
    })();
    return true;
  }

  // PERMANENCE: Disable permanence mode
  if (msg.type === "DISABLE_PERMANENCE") {
    (async () => {
      const passphrase = msg.passphrase || "";
      const data = await chrome.storage.local.get(DEFAULTS);

      // Verify passphrase matches
      if (passphrase !== data.bambiPermanencePassword) {
        sendResponse?.({ success: false, error: "invalid_passphrase" });
        return;
      }

      // Call backend to remove startup shortcut
      try {
        const backendResponse = await fetch("http://127.0.0.1:5655/permanence", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ enable: false })
        });

        const result = await backendResponse.json();
        if (!backendResponse.ok) {
          console.error("Backend permanence request failed:", result);
          sendResponse?.({ success: false, error: "backend_error" });
          return;
        }
      } catch (err) {
        console.error("Backend call failed:", err);
        sendResponse?.({ success: false, error: "backend_unreachable" });
        return;
      }

      // Clear permanence state
      await chrome.storage.local.set({
        bambiPermanent: false,
        bambiPermanencePassword: null
      });

      // Notify options page of success
      chrome.tabs.query({ url: "*://*/options.html" }, (tabs) => {
        tabs.forEach(tab => {
          chrome.tabs.sendMessage(tab.id, { type: "PERMANENCE_UPDATED", permanent: false }).catch(() => {});
        });
      });

      sendResponse?.({ success: true });
    })();
    return true;
  }
});
