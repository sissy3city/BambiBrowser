// Cross-browser compatible popup script
const browserAPI = typeof browser !== 'undefined' ? browser : chrome;
const SERVER_URL = "http://127.0.0.1:5655";

const enableToggle = document.getElementById("enableToggle");
const toggleSwitch = document.getElementById("toggleSwitch");
const toggleLabel = document.getElementById("toggleLabel");
const serverDot = document.getElementById("serverDot");
const serverStatus = document.getElementById("serverStatus");
const hintText = document.getElementById("hintText");

let isEnabled = true;
let isOnline = false;

async function checkServer() {
  try {
    const res = await fetch(`${SERVER_URL}/health`);
    isOnline = res.ok;

    if (isOnline) {
      serverDot.className = "dot online";
      serverStatus.textContent = "App Online - MPV Mode";
      hintText.innerHTML = "✅ App connected<br>Videos play in MPV";
    } else {
      throw new Error();
    }
  } catch {
    isOnline = false;
    serverDot.className = "dot offline";
    serverStatus.textContent = "App Offline - Browser Mode";
    hintText.innerHTML = "⚠️ Start desktop app for MPV<br>Browser fallback active";
  }
}

browserAPI.storage.local.get({ enabled: true }, (data) => {
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

enableToggle.addEventListener("click", () => {
  isEnabled = !isEnabled;
  updateToggleUI();
  browserAPI.storage.local.set({ enabled: isEnabled });
});

document.getElementById("openApp").onclick = () => {
  fetch(`${SERVER_URL}/health`)
    .then(() => {
      // Show brief confirmation that app is running
      const originalText = document.getElementById("serverStatus").textContent;
      document.getElementById("serverStatus").textContent = "App is running!";
      setTimeout(() => {
        document.getElementById("serverStatus").textContent = originalText;
        window.close();
      }, 1500);
    })
    .catch(() => {
      // Provide more helpful instructions
      if (!confirm("BambiBrowser app is not running or not accessible.\n\n" +
                   "Make sure the app is running and try again.\n\n" +
                   "To start the app:\n" +
                   "1. Look for BambiBrowser in your Start menu or applications folder\n" +
                   "2. Or run bambi_browser.pyw from the installation directory\n" +
                   "3. The app needs to be running for MPV fullscreen mode\n\n" +
                   "Would you like to try checking again?")) {
        // User cancelled, do nothing
      } else {
        // User wants to try again, recursively call the handler
        document.getElementById("openApp").onclick();
      }
    });
};

// Initialize
checkServer();
setInterval(checkServer, 3000);