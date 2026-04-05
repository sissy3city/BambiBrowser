// options.js – BambiBrowser settings + server status + punish mode

const DEFAULTS = {
  bambiActivated: false,
  bambiDomains: ["hypnotube.com"],
  bambiBlacklist: [],
  bambiIntensityLevel: 50,
  bambiMultiMonitor: true,
  bambiHardLock: true,
  bambiPunishMode: true,
  bambiSetupComplete: false,
  bambiSelectedMonitors: [],
  bambiPermanent: false,
  bambiPermanencePassword: null
};

const SERVER_URL = "http://127.0.0.1:5655/health";
const MONITORS_URL = "http://127.0.0.1:5655/monitors";

const els = {
  setupWarning: document.getElementById("setupWarning"),
  serverBadge: document.getElementById("serverBadge"),
  serverStatus: document.getElementById("serverStatus"),
  refreshServerBtn: document.getElementById("refreshServerBtn"),
  setupBadge: document.getElementById("setupBadge"),
  saveBadge: document.getElementById("saveBadge"),
  saveStatus: document.getElementById("saveStatus"),

  bambiActivated: document.getElementById("bambiActivated"),
  intensityRange: document.getElementById("intensityRange"),
  intensityValue: document.getElementById("intensityValue"),
  multiMonitor: document.getElementById("multiMonitor"),
  hardLock: document.getElementById("hardLock"),
  punishMode: document.getElementById("punishMode"),

  monitorSection: document.getElementById("monitorSection"),
  monitorList: document.getElementById("monitorList"),
  monitorStatus: document.getElementById("monitorStatus"),
  refreshMonitorsBtn: document.getElementById("refreshMonitorsBtn"),

  domainInput: document.getElementById("domainInput"),
  addDomainBtn: document.getElementById("addDomainBtn"),
  domainList: document.getElementById("domainList"),

  blacklistInput: document.getElementById("blacklistInput"),
  addBlacklistBtn: document.getElementById("addBlacklistBtn"),
  blacklistList: document.getElementById("blacklistList"),

  permanenceBadge: document.getElementById("permanenceBadge"),
  makePermanent: document.getElementById("makePermanent"),
  passwordSection: document.getElementById("passwordSection"),
  permanencePassword: document.getElementById("permanencePassword"),
  applyPermanenceBtn: document.getElementById("applyPermanenceBtn"),
  permanenceStatus: document.getElementById("permanenceStatus"),
  removePermanenceSection: document.getElementById("removePermanenceSection"),
  removePassword: document.getElementById("removePassword"),
  removePermanenceBtn: document.getElementById("removePermanenceBtn"),
  removeStatus: document.getElementById("removeStatus"),

  saveBtn: document.getElementById("saveBtn")
};

let currentState = { ...DEFAULTS };

function normalizeDomain(value) {
  if (!value) return null;
  value = value.trim().toLowerCase();
  if (!value) return null;
  // strip protocol and path
  value = value.replace(/^https?:\/\//, "");
  value = value.split("/")[0];
  return value || null;
}

function renderList(container, items, onRemove) {
  container.innerHTML = "";
  items.forEach((domain, idx) => {
    const pill = document.createElement("div");
    pill.className = "pill";
    pill.textContent = domain + " ";
    const btn = document.createElement("button");
    btn.textContent = "×";
    btn.onclick = () => onRemove(idx);
    pill.appendChild(btn);
    container.appendChild(pill);
  });
}

function loadSettings() {
  chrome.storage.local.get(DEFAULTS, (data) => {
    currentState = { ...DEFAULTS, ...data };

    els.bambiActivated.checked = !!currentState.bambiActivated;
    els.intensityRange.value = currentState.bambiIntensityLevel || 50;
    updateIntensityDisplay();
    els.multiMonitor.checked = !!currentState.bambiMultiMonitor;
    els.hardLock.checked = !!currentState.bambiHardLock;
    els.punishMode.checked = !!currentState.bambiPunishMode;

    renderList(els.domainList, currentState.bambiDomains || [], (idx) => {
      currentState.bambiDomains.splice(idx, 1);
      renderList(els.domainList, currentState.bambiDomains, () => {});
      markUnsaved();
    });

    renderList(els.blacklistList, currentState.bambiBlacklist || [], (idx) => {
      currentState.bambiBlacklist.splice(idx, 1);
      renderList(els.blacklistList, currentState.bambiBlacklist, () => {});
      markUnsaved();
    });

    if (!currentState.bambiSetupComplete) {
      els.setupWarning.style.display = "block";
      els.setupBadge.textContent = "Not complete";
      els.setupBadge.className = "badge badge-warn";
    } else {
      els.setupWarning.style.display = "none";
      els.setupBadge.textContent = "Complete";
      els.setupBadge.className = "badge badge-ok";
    }

    updateMonitorSection();
    markSaved(false);
    
    // Update permanence badge and lock settings if permanent
    if (currentState.bambiPermanent) {
      els.permanenceBadge.textContent = "PERMANENT";
      els.permanenceBadge.className = "badge badge-ok";
      els.makePermanent.checked = false;
      els.passwordSection.style.display = "none";
      els.removePermanenceSection.style.display = "block";
      lockSettings(true);
    } else {
      els.permanenceBadge.textContent = "PERMANENT";
      els.permanenceBadge.className = "badge badge-warn";
      els.makePermanent.checked = false;
      els.passwordSection.style.display = "none";
      els.removePermanenceSection.style.display = "none";
      lockSettings(false);
    }
    
    checkServerStatus();
  });
}

function markUnsaved() {
  els.saveBadge.textContent = "Unsaved";
  els.saveBadge.className = "badge badge-info";
  els.saveStatus.textContent = "";
}

function markSaved(showMessage = true) {
  els.saveBadge.textContent = "Saved";
  els.saveBadge.className = "badge badge-ok";
  if (showMessage) {
    els.saveStatus.textContent = "Settings saved.";
    els.saveStatus.className = "status-line success-text";
  }
}

function saveSettings() {
  currentState.bambiActivated = els.bambiActivated.checked;
  currentState.bambiIntensityLevel = parseInt(els.intensityRange.value, 10) || 50;
  currentState.bambiMultiMonitor = els.multiMonitor.checked;
  currentState.bambiHardLock = els.hardLock.checked;
  currentState.bambiPunishMode = els.punishMode.checked;
  currentState.bambiSetupComplete = true;
  // bambiSelectedMonitors is already maintained in currentState by the checkbox change handlers

  chrome.storage.local.set(currentState, () => {
    markSaved(true);
    els.setupWarning.style.display = "none";
    els.setupBadge.textContent = "Complete";
    els.setupBadge.className = "badge badge-ok";
  });
}

function fetchMonitors() {
  els.monitorStatus.textContent = "Fetching available monitors…";
  
  fetch(MONITORS_URL, { method: "GET" })
    .then((res) => {
      if (!res.ok) throw new Error("HTTP " + res.status);
      return res.json();
    })
    .then((json) => {
      if (json && Array.isArray(json.monitors)) {
        renderMonitorSelectors(json.monitors);
      } else {
        throw new Error("Unexpected response format");
      }
    })
    .catch((err) => {
      els.monitorStatus.textContent = "Failed to fetch monitors. Make sure Bambi Player is running.";
      els.monitorStatus.style.color = "#ff9b9b";
      console.error("Monitor fetch error:", err);
    });
}

function renderMonitorSelectors(monitors) {
  els.monitorList.innerHTML = "";
  const selectedMonitors = currentState.bambiSelectedMonitors || [];

  if (!monitors || monitors.length === 0) {
    els.monitorStatus.textContent = "No monitors detected.";
    els.monitorStatus.style.color = "#ff9b9b";
    return;
  }

  monitors.forEach((monitorIdx) => {
    const label = document.createElement("label");
    label.className = "monitor-checkbox";
    
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.value = monitorIdx;
    checkbox.checked = selectedMonitors.includes(monitorIdx);
    
    checkbox.addEventListener("change", () => {
      if (checkbox.checked) {
        if (!currentState.bambiSelectedMonitors.includes(monitorIdx)) {
          currentState.bambiSelectedMonitors.push(monitorIdx);
        }
      } else {
        const idx = currentState.bambiSelectedMonitors.indexOf(monitorIdx);
        if (idx > -1) {
          currentState.bambiSelectedMonitors.splice(idx, 1);
        }
      }
      markUnsaved();
    });

    label.appendChild(checkbox);
    label.appendChild(document.createTextNode(`Monitor ${monitorIdx + 1}`));
    els.monitorList.appendChild(label);
  });

  els.monitorStatus.textContent = `${monitors.length} monitor(s) available.`;
  els.monitorStatus.style.color = "#9bc5ff";
}

function updateMonitorSection() {
  if (els.multiMonitor.checked) {
    els.monitorSection.style.display = "block";
    fetchMonitors();
  } else {
    els.monitorSection.style.display = "none";
    currentState.bambiSelectedMonitors = [];
  }
}

function lockSettings(isLocked) {
  // Disable all main settings controls when permanence is enabled
  const controlsToLock = [
    els.bambiActivated,
    els.intensityRange,
    els.multiMonitor,
    els.hardLock,
    els.punishMode,
    els.addDomainBtn,
    els.addBlacklistBtn,
    els.saveBtn,
    els.refreshMonitorsBtn
  ];
  
  controlsToLock.forEach(el => {
    if (el) {
      el.disabled = isLocked;
      if (isLocked) {
        el.style.opacity = "0.5";
        el.style.cursor = "not-allowed";
      } else {
        el.style.opacity = "1";
        el.style.cursor = "pointer";
      }
    }
  });
  
  // Show/hide lock message
  const lockMessage = document.getElementById("settingsLockMessage");
  if (isLocked) {
    if (!lockMessage) {
      const msg = document.createElement("div");
      msg.id = "settingsLockMessage";
      msg.className = "status-line danger-text";
      msg.textContent = "⚠️ Settings are locked because Bambi Player is permanent. Remove permanence to make changes.";
      msg.style.marginTop = "16px";
      msg.style.padding = "12px";
      msg.style.border = "1px solid #ff9b9b";
      msg.style.borderRadius = "4px";
      msg.style.backgroundColor = "rgba(255, 155, 155, 0.1)";
      const container = document.body || document.documentElement;
      const saveSection = els.saveBtn?.parentElement;
      if (saveSection && saveSection.parentElement) {
        saveSection.parentElement.insertBefore(msg, saveSection.nextSibling);
      } else {
        container.appendChild(msg);
      }
    }
  } else {
    if (lockMessage) lockMessage.remove();
  }
}

function updateIntensityDisplay() {
  const value = parseInt(els.intensityRange.value, 10) || 50;
  if (els.intensityValue) {
    els.intensityValue.textContent = value + "%";
  }
}
function checkServerStatus() {
  els.serverBadge.textContent = "Checking…";
  els.serverBadge.className = "badge badge-info";
  els.serverStatus.textContent = "Checking connection to bambi_player…";

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
      els.serverStatus.textContent = "Bambi Player is not running. Start bambi_player.py for VLC hijack.";
      els.serverStatus.className = "status-line danger-text";
      chrome.storage.local.set({ bambiServerOnline: false });
    });
}

function initEvents() {
  els.addDomainBtn.onclick = () => {
    const value = normalizeDomain(els.domainInput.value);
    if (!value) return;
    if (!currentState.bambiDomains.includes(value)) {
      currentState.bambiDomains.push(value);
      renderList(els.domainList, currentState.bambiDomains, () => {});
      markUnsaved();
    }
    els.domainInput.value = "";
  };

  els.addBlacklistBtn.onclick = () => {
    const value = normalizeDomain(els.blacklistInput.value);
    if (!value) return;
    if (!currentState.bambiBlacklist.includes(value)) {
      currentState.bambiBlacklist.push(value);
      renderList(els.blacklistList, currentState.bambiBlacklist, () => {});
      markUnsaved();
    }
    els.blacklistInput.value = "";
  };

  els.saveBtn.onclick = saveSettings;
  els.refreshServerBtn.onclick = checkServerStatus;
  els.refreshMonitorsBtn.onclick = fetchMonitors;

  // Permanence controls
  els.makePermanent.addEventListener("change", () => {
    if (els.makePermanent.checked) {
      els.passwordSection.style.display = "block";
      els.removePermanenceSection.style.display = "none";
    } else {
      els.passwordSection.style.display = "none";
    }
  });

  els.applyPermanenceBtn.onclick = () => {
    const passphrase = els.permanencePassword.value.trim();
    if (!passphrase) {
      els.permanenceStatus.textContent = "Passphrase required!";
      els.permanenceStatus.className = "status-line danger-text";
      return;
    }
    
    // Send message to background script to enable permanence
    chrome.runtime.sendMessage({
      type: "ENABLE_PERMANENCE",
      passphrase: passphrase
    }, (response) => {
      if (response && response.success) {
        els.permanenceStatus.textContent = "Permanence enabled! ✓";
        els.permanenceStatus.className = "status-line success-text";
        els.permanenceBadge.textContent = "PERMANENT";
        els.permanenceBadge.className = "badge badge-ok";
        els.passwordSection.style.display = "none";
        els.removePermanenceSection.style.display = "block";
        els.makePermanent.checked = false;
        els.permanencePassword.value = "";
        lockSettings(true);
      } else {
        els.permanenceStatus.textContent = "Failed to enable permanence";
        els.permanenceStatus.className = "status-line danger-text";
      }
    });
  };

  els.removePermanenceBtn.onclick = () => {
    const passphrase = els.removePassword.value.trim();
    if (!passphrase) {
      els.removeStatus.textContent = "Passphrase required!";
      els.removeStatus.className = "status-line danger-text";
      return;
    }
    
    chrome.runtime.sendMessage({
      type: "DISABLE_PERMANENCE",
      passphrase: passphrase
    }, (response) => {
      if (response && response.success) {
        els.removeStatus.textContent = "Permanence removed! ✓";
        els.removeStatus.className = "status-line success-text";
        els.permanenceBadge.textContent = "Not Permanent";
        els.permanenceBadge.className = "badge badge-warn";
        els.removePermanenceSection.style.display = "none";
        els.passwordSection.style.display = "none";
        els.removePassword.value = "";
        lockSettings(false);
      } else {
        els.removeStatus.textContent = "Incorrect passphrase!";
        els.removeStatus.className = "status-line danger-text";
      }
    });
  };

  [
    els.bambiActivated,
    els.intensityRange,
    els.multiMonitor,
    els.hardLock,
    els.punishMode
  ].forEach((el) => {
    el.addEventListener("change", markUnsaved);
  });

  els.intensityRange.addEventListener("input", updateIntensityDisplay);

  els.multiMonitor.addEventListener("change", updateMonitorSection);
}

document.addEventListener("DOMContentLoaded", () => {
  initEvents();
  loadSettings();
});

// Listen for permanence state updates from background script
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.type === "PERMANENCE_UPDATED") {
    currentState.bambiPermanent = msg.permanent;
    
    if (msg.permanent) {
      els.permanenceBadge.textContent = "PERMANENT";
      els.permanenceBadge.className = "badge badge-ok";
      els.passwordSection.style.display = "none";
      els.removePermanenceSection.style.display = "block";
      els.makePermanent.checked = false;
      lockSettings(true);
    } else {
      els.permanenceBadge.textContent = "Not Permanent";
      els.permanenceBadge.className = "badge badge-warn";
      els.passwordSection.style.display = "none";
      els.removePermanenceSection.style.display = "none";
      els.makePermanent.checked = false;
      lockSettings(false);
    }
  }
});
