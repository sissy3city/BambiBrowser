// popup.js - Quick enable/disable
const SERVER_URL = "http://127.0.0.1:5655";

const enableToggle = document.getElementById("enableToggle");
const toggleSwitch = document.getElementById("toggleSwitch");
const toggleLabel = document.getElementById("toggleLabel");
const serverDot = document.getElementById("serverDot");
const serverStatus = document.getElementById("serverStatus");
const hintText = document.getElementById("hintText");

let isEnabled = true;
let isOnline = false;

// Check server
async function checkServer() {
  try {
    const res = await fetch(`${SERVER_URL}/health`);
    isOnline = res.ok;
    
    if (isOnline) {
      serverDot.className = "dot online";
      serverStatus.textContent = "App Online - VLC Mode";
      hintText.innerHTML = "✅ App connected<br>Videos play in VLC";
    } else {
      throw new Error();
    }
  } catch {
    isOnline = false;
    serverDot.className = "dot offline";
    serverStatus.textContent = "App Offline - Browser Mode";
    hintText.innerHTML = "⚠️ Start desktop app for VLC<br>Browser fallback active";
  }
}

// Load enabled state
chrome.storage.local.get({ enabled: true }, (data) => {
  isEnabled = data.enabled;
  updateToggleUI();
});

function updateToggleUI() {
  if (isEnabled) {
    toggleSwitch.classList.remove("off");
    toggleLabel.textContent = "Enabled";
    toggleLabel.style.color = "#7dff9a";
  } else {
    toggleSwitch.classList.add("off");
    toggleLabel.textContent = "Disabled";
    toggleLabel.style.color = "#ff9b9b";
  }
}

// Toggle click
enableToggle.addEventListener("click", () => {
  isEnabled = !isEnabled;
  updateToggleUI();
  chrome.storage.local.set({ enabled: isEnabled });
});

// Open app
document.getElementById("openApp").onclick = () => {
  fetch(`${SERVER_URL}/health`)
    .then(() => window.close())
    .catch(() => alert("BambiBrowser app is not running.\n\nStart the app for VLC fullscreen mode."));
};

// Init
checkServer();
setInterval(checkServer, 3000);