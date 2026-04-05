// popup.js – quick toggle + server + setup status

const SERVER_URL = "http://127.0.0.1:5655/health";

const els = {
  toggleBambi: document.getElementById("toggleBambi"),
  bambiStatus: document.getElementById("bambiStatus"),
  serverBadge: document.getElementById("serverBadge"),
  serverStatus: document.getElementById("serverStatus"),
  setupBadge: document.getElementById("setupBadge"),
  setupStatus: document.getElementById("setupStatus"),
  openSettingsBtn: document.getElementById("openSettingsBtn")
};

const DEFAULTS = {
  bambiActivated: false,
  bambiSetupComplete: false,
  bambiServerOnline: false
};

function loadState() {
  chrome.storage.local.get(DEFAULTS, (data) => {
    els.toggleBambi.checked = !!data.bambiActivated;
    updateBambiStatus(!!data.bambiActivated);

    if (data.bambiSetupComplete) {
      els.setupBadge.textContent = "Complete";
      els.setupBadge.className = "badge badge-ok";
      els.setupStatus.textContent = "Setup complete. You can use Bambi Mode.";
      els.setupStatus.className = "status-line success-text";
    } else {
      els.setupBadge.textContent = "Required";
      els.setupBadge.className = "badge badge-warn";
      els.setupStatus.textContent = "Open settings to finish first‑time setup.";
      els.setupStatus.className = "status-line danger-text";
    }

    // Use cached server status first, then recheck
    if (data.bambiServerOnline) {
      els.serverBadge.textContent = "Online";
      els.serverBadge.className = "badge badge-ok";
      els.serverStatus.textContent = "Bambi Player is running.";
      els.serverStatus.className = "status-line success-text";
    } else {
      els.serverBadge.textContent = "Offline";
      els.serverBadge.className = "badge badge-warn";
      els.serverStatus.textContent = "Bambi Player is not running.";
      els.serverStatus.className = "status-line danger-text";
    }

    checkServerStatus();
  });
}

function updateBambiStatus(enabled) {
  if (enabled) {
    els.bambiStatus.textContent = "Bambi Mode is enabled for supported sites.";
    els.bambiStatus.className = "status-line success-text";
  } else {
    els.bambiStatus.textContent = "Bambi Mode is disabled.";
    els.bambiStatus.className = "status-line";
  }
}

function checkServerStatus() {
  els.serverBadge.textContent = "Checking…";
  els.serverBadge.className = "badge badge-info";
  els.serverStatus.textContent = "Checking connection to Bambi Player…";

  fetch(SERVER_URL, { method: "GET" })
    .then((res) => {
      if (!res.ok) throw new Error("HTTP " + res.status);
      return res.json();
    })
    .then((json) => {
      if (json && json.status === "running") {
        els.serverBadge.textContent = "Online";
        els.serverBadge.className = "badge badge-ok";
        els.serverStatus.textContent = "Bambi Player is running. VLC hijack is available.";
        els.serverStatus.className = "status-line success-text";
        chrome.storage.local.set({ bambiServerOnline: true });
      } else {
        throw new Error("Unexpected response");
      }
    })
    .catch(() => {
      els.serverBadge.textContent = "Offline";
      els.serverBadge.className = "badge badge-warn";
      els.serverStatus.textContent = "Bambi Player is not running. Start bambi_player.py.";
      els.serverStatus.className = "status-line danger-text";
      chrome.storage.local.set({ bambiServerOnline: false });
    });
}

function initEvents() {
  els.toggleBambi.addEventListener("change", () => {
    const enabled = els.toggleBambi.checked;
    chrome.storage.local.set({ bambiActivated: enabled }, () => {
      updateBambiStatus(enabled);
    });
  });

  els.openSettingsBtn.onclick = () => {
    chrome.runtime.openOptionsPage();
  };
}

document.addEventListener("DOMContentLoaded", () => {
  initEvents();
  loadState();
});
