// ------------------------------------------------------
// PREVENT DOUBLE LOADING
// ------------------------------------------------------
if (window.__bambiLoaded) {
} else {
  window.__bambiLoaded = true;

  const hostname = location.hostname.toLowerCase();

  console.log("[Bambi] content script loaded on", location.href);

  // ------------------------------------------------------
  // CONFIG
  // ------------------------------------------------------
  const BAMBI_SERVER = "http://127.0.0.1:5655";
  const BAMBI_ENDPOINT = BAMBI_SERVER + "/play";

  const DEFAULT_DOMAINS = ["hypnotube.com"];
  const VIDEO_HISTORY_LIMIT = 20;

  const HYPNOTUBE_DOMAIN = "hypnotube.com";

  // ------------------------------------------------------
  // SAFE CHROME HELPERS
  // ------------------------------------------------------
  function isExtensionContextValid() {
    try {
      return typeof chrome !== "undefined" && Boolean(chrome.runtime && chrome.runtime.id);
    } catch {
      return false;
    }
  }

  function safeStorageSet(value) {
    if (!isExtensionContextValid()) return false;
    try {
      chrome.storage.local.set(value);
      return true;
    } catch (e) {
      const msg = String(e?.message || e || "");
      if (/extension context invalidated/i.test(msg)) {
        return false;
      }
      console.warn("[Bambi] storage.set failed:", e);
      return false;
    }
  }

  function normalizeDomainInput(value) {
    if (!value) return "";
    let v = String(value).trim().toLowerCase();
    v = v
      .replace(/^https?:\/\//, "")
      .replace(/^www\./, "")
      .replace(/\/.*$/, "")
      .replace(/\.$/, "");
    return v;
  }

  function hostMatchesDomain(host, domain) {
    const h = normalizeDomainInput(host);
    const d = normalizeDomainInput(domain);
    if (!h || !d) return false;
    return h === d || h.endsWith(`.${d}`);
  }

  // ------------------------------------------------------
  // STATE
  // ------------------------------------------------------
  let bambiActivated = false;
  let bambiDomains = [];
  let bambiBlacklist = [];
  let bambiIntensityLevel = 1;
  let bambiMultiMonitor = true;
  let bambiSelectedMonitors = [];
  let bambiInputLockEnabled = false;
  let bambiSetupComplete = false;
  let bambiForceHijack = false;

  let isMatchedDomain = false;
  let serverAvailable = false;
  let mainVideo = null;
  let videoAlreadySent = false;

  // ------------------------------------------------------
  // DOMAIN / BLACKLIST HELPERS
  // ------------------------------------------------------
  function refreshDomainMatch() {
    const domains = (bambiDomains || []).map(normalizeDomainInput).filter(Boolean);
    isMatchedDomain = domains.some(d => hostMatchesDomain(hostname, d));
  }

  function isHypnoTube() {
    return hostMatchesDomain(hostname, HYPNOTUBE_DOMAIN);
  }

  function isBlacklistedUrl() {
    const url = location.href.toLowerCase();
    return (bambiBlacklist || []).some(entry => {
      if (!entry) return false;
      return url.includes(String(entry).toLowerCase());
    });
  }

  function isBambiActiveOnThisPage() {
    if (!bambiSetupComplete && !bambiForceHijack) return false;

    if (bambiForceHijack) {
      // punishment redirect → always active, regardless of domain/blacklist
      return true;
    }

    if (!bambiActivated) return false;
    if (!isMatchedDomain) return false;
    if (!isHypnoTube()) return false;
    if (isBlacklistedUrl()) return false;
    return true;
  }

  // ------------------------------------------------------
  // VIDEO HISTORY
  // ------------------------------------------------------
  function addToVideoHistory(videoUrl) {
    if (!isExtensionContextValid()) return;
    const url = String(videoUrl || "").trim();
    if (!url) return;

    chrome.storage.local.get({ bambiVideoHistory: [] }, (data) => {
      const history = Array.isArray(data.bambiVideoHistory)
        ? data.bambiVideoHistory.slice()
        : [];
      if (history[history.length - 1] === url) {
        // Avoid duplicate last entry
      } else {
        history.push(url);
      }
      while (history.length > VIDEO_HISTORY_LIMIT) {
        history.shift();
      }
      safeStorageSet({ bambiVideoHistory: history });
    });
  }

  // ------------------------------------------------------
  // ACTIVATION STATE
  // ------------------------------------------------------
  function isBambiActivated() {
    return isBambiActiveOnThisPage();
  }

  function markBambiActivated() {
    bambiActivated = true;
    console.log("[Bambi] markBambiActivated → true");
    safeStorageSet({ bambiActivated: true });
  }

  chrome.storage.onChanged.addListener((changes, areaName) => {
    if (areaName !== "local") return;

    if (changes.bambiActivated) {
      bambiActivated = Boolean(changes.bambiActivated.newValue);
      console.log("[Bambi] storage change → bambiActivated:", bambiActivated);
    }
    if (changes.bambiDomains) {
      bambiDomains = (changes.bambiDomains.newValue || DEFAULT_DOMAINS)
        .map(normalizeDomainInput)
        .filter(Boolean);
      refreshDomainMatch();
      console.log("[Bambi] storage change → domains:", bambiDomains, "matched:", isMatchedDomain);
    }
    if (changes.bambiBlacklist) {
      bambiBlacklist = changes.bambiBlacklist.newValue || [];
      console.log("[Bambi] storage change → blacklist:", bambiBlacklist);
    }
    if (changes.bambiIntensityLevel) {
      bambiIntensityLevel = Number(changes.bambiIntensityLevel.newValue) || 1;
      console.log("[Bambi] storage change → intensity level:", bambiIntensityLevel);
    }
    if (changes.bambiMultiMonitor) {
      bambiMultiMonitor = Boolean(changes.bambiMultiMonitor.newValue);
      console.log("[Bambi] storage change → multi-monitor:", bambiMultiMonitor);
    }
    if (changes.bambiSelectedMonitors) {
      bambiSelectedMonitors = Array.isArray(changes.bambiSelectedMonitors.newValue)
        ? changes.bambiSelectedMonitors.newValue
        : [];
      console.log("[Bambi] storage change → selected monitors:", bambiSelectedMonitors);
    }
    if (changes.bambiHardLock) {
      bambiInputLockEnabled = Boolean(changes.bambiHardLock.newValue);
      console.log("[Bambi] storage change → hard lock enabled:", bambiInputLockEnabled);
    }
    if (changes.bambiSetupComplete) {
      bambiSetupComplete = Boolean(changes.bambiSetupComplete.newValue);
      console.log("[Bambi] storage change → setup complete:", bambiSetupComplete);
    }
    if (changes.bambiForceHijack) {
      bambiForceHijack = Boolean(changes.bambiForceHijack.newValue);
      console.log("[Bambi] storage change → force hijack:", bambiForceHijack);
    }
  });

  // ------------------------------------------------------
  // SERVER HEALTH
  // ------------------------------------------------------
  async function isServerRunning() {
    try {
      const response = await fetch(BAMBI_SERVER + "/health", { method: "GET" });
      return response.status === 200;
    } catch (e) {
      console.log("[Bambi] Server unreachable:", e.message);
      return false;
    }
  }

  async function sendVideoToServer(videoUrl) {
    try {
      const payload = {
        url: videoUrl,
        multi_monitor: bambiMultiMonitor,
        input_lock: bambiInputLockEnabled
      };
      
      // Include selected monitors if multi-monitor is enabled and monitors are selected
      if (bambiMultiMonitor && Array.isArray(bambiSelectedMonitors) && bambiSelectedMonitors.length > 0) {
        payload.selected_monitors = bambiSelectedMonitors;
      }

      const response = await fetch(BAMBI_ENDPOINT, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      return response.ok;
    } catch (e) {
      console.log("[Bambi] Failed to send to server:", e.message);
      return false;
    }
  }

  function showServerOfflineOverlay() {
    const overlay = document.createElement("div");
    overlay.style = `
      position: fixed;
      inset: 0;
      background: rgba(0,0,0,0.85);
      color: white;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      font-size: 2rem;
      z-index: 999999999;
      text-align: center;
      padding: 20px;
    `;
    overlay.innerHTML = `
      <div>Bambi Player is not running</div>
      <div style="font-size:1.2rem; margin-top:10px;">
        Start <b>bambi_player.py</b> to enable fullscreen hijack.
      </div>
    `;
    document.body.appendChild(overlay);
  }


  // ------------------------------------------------------
  // FULLSCREEN + INPUT LOCK
  // ------------------------------------------------------
  async function enterFullscreen(elem) {
    try {
      if (!document.fullscreenElement && elem?.requestFullscreen) {
        console.log("[Bambi] requesting fullscreen on", elem);
        await elem.requestFullscreen();
      }
    } catch (e) {
      console.warn("[Bambi] requestFullscreen failed:", e);
    }
  }

  async function enableKeyboardLock() {
    if (!bambiInputLockEnabled) return;
    if (!navigator.keyboard?.lock) return;
    try {
      console.log("[Bambi] enabling keyboard lock");
      await navigator.keyboard.lock([
        "Escape",
        "F11",
        "AltLeft",
        "AltRight",
        "MetaLeft",
        "MetaRight"
      ]);
    } catch (e) {
      console.warn("[Bambi] keyboard.lock failed:", e);
    }
  }

  async function enablePointerLock() {
    if (!bambiInputLockEnabled) return;
    try {
      const req =
        document.body.requestPointerLock ||
        document.body.mozRequestPointerLock ||
        document.body.webkitRequestPointerLock;

      if (req) {
        console.log("[Bambi] requesting pointer lock");
        req.call(document.body);
      }
    } catch (e) {
      console.warn("[Bambi] pointer lock failed:", e);
    }
  }

  function suppressKeys(e) {
    if (!bambiInputLockEnabled) return;
    e.stopPropagation();
    e.preventDefault();
  }

  document.addEventListener("fullscreenchange", () => {
    console.log("[Bambi] fullscreenchange →", !!document.fullscreenElement);
    if (document.fullscreenElement && bambiInputLockEnabled) {
      enableKeyboardLock();
      enablePointerLock();
      window.addEventListener("keydown", suppressKeys, true);
    } else {
      window.removeEventListener("keydown", suppressKeys, true);
      if (navigator.keyboard?.unlock) {
        console.log("[Bambi] unlocking keyboard");
        navigator.keyboard.unlock();
      }
      document.exitPointerLock?.();
    }
  });

  // ------------------------------------------------------
  // MAIN VIDEO DETECTION (HypnoTube-specific)
  // ------------------------------------------------------
  function findMainVideoHypnoTube() {
    if (mainVideo) return mainVideo;

    const videos = document.querySelectorAll("video");
    for (const v of videos) {
      if (!(v instanceof HTMLVideoElement)) continue;

      const src = v.currentSrc || v.src || "";
      if (!src) continue;

      const isRealSource =
        src.includes("media.hypnotube.com") ||
        src.includes("cdn.hypnotube.com") ||
        src.includes("video.hypnotube.com");

      if (!isRealSource) continue;

      const rect = v.getBoundingClientRect();
      if (rect.width < 300 || rect.height < 200) continue;

      mainVideo = v;
      console.log("[Bambi] MAIN video locked (HypnoTube):", src, rect.width, rect.height);
      return v;
    }

    return null;
  }

  function findMainVideo() {
    if (isHypnoTube()) {
      return findMainVideoHypnoTube();
    }
    // For punishment redirects, we still just pick the largest video
    if (bambiForceHijack) {
      const vids = document.querySelectorAll("video");
      let best = null;
      let bestArea = 0;
      vids.forEach(v => {
        if (!(v instanceof HTMLVideoElement)) return;
        const r = v.getBoundingClientRect();
        const area = r.width * r.height;
        if (area > bestArea) {
          bestArea = area;
          best = v;
        }
      });
      if (best) {
        mainVideo = best;
        console.log("[Bambi] MAIN video locked (force hijack):", best.currentSrc || best.src);
      }
      return best;
    }
    return null;
  }

  function isMainHypnoTubeVideo(video) {
    const v = findMainVideoHypnoTube();
    return v && v === video;
  }

  // ------------------------------------------------------
  // AUTOPLAY + BLOCK HANDLING
  // ------------------------------------------------------
  function handleAutoplayBlocked(v) {
    console.log("[Bambi] autoplay or unmute blocked → showing continue overlay");

    const overlay = document.createElement("div");
    overlay.style = `
      position: fixed;
      inset: 0;
      background: black;
      color: white;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 3rem;
      z-index: 999999;
      cursor: pointer;
      user-select: none;
    `;
    overlay.textContent = "Click to continue Bambi Mode";

    const continueHandler = async () => {
      overlay.remove();

      try {
        v.muted = false;
        await v.play();
      } catch (err) {
        console.warn("[Bambi] play() failed after gesture:", err);
      }

      await enterFullscreen(v);
      await enableKeyboardLock();
      await enablePointerLock();

      document.removeEventListener("click", continueHandler, true);
      document.removeEventListener("keydown", continueHandler, true);
    };

    document.addEventListener("click", continueHandler, true);
    document.addEventListener("keydown", continueHandler, true);

    document.body.appendChild(overlay);
  }

  function autoplayWithUnmute(v) {
    console.log("[Bambi] autoplay fallback → starting muted");

    v.muted = true;
    v.autoplay = true;

    v.play()
      .then(() => {
        console.log("[Bambi] autoplay started, attempting immediate unmute");

        v.muted = false;

        if (v.paused) {
          handleAutoplayBlocked(v);
        }
      })
      .catch(err => {
        console.warn("[Bambi] autoplay failed:", err);
        handleAutoplayBlocked(v);
      });
  }

  // ------------------------------------------------------
  // HIJACK LOGIC
  // ------------------------------------------------------
  async function tryHijackOrFallback() {
    if (!isBambiActivated()) {
      console.log("[Bambi] not active on this page → no hijack");
      return;
    }
    if (videoAlreadySent) return;

    const v = findMainVideo();
    if (!v) {
      console.log("[Bambi] no main video found for this domain");
      return;
    }

    const videoSrc = v.currentSrc || v.src || "";
    if (!videoSrc) {
      console.log("[Bambi] main video has no src");
      return;
    }

    console.log("[Bambi] main video detected:", videoSrc.substring(0, 80));

    if (serverAvailable) {
      console.log("[Bambi] server available → sending to VLC");
      const sent = await sendVideoToServer(videoSrc);
      if (sent) {
        console.log("[Bambi] ✓ Video sent to VLC");
        videoAlreadySent = true;
        addToVideoHistory(videoSrc);
        v.pause();
        v.autoplay = false;

        if (bambiForceHijack) {
          // clear force flag after successful punishment hijack
          bambiForceHijack = false;
          safeStorageSet({ bambiForceHijack: false });
        }
        return;
      } else {
        console.log("[Bambi] server error → using browser autoplay fallback");
        autoplayWithUnmute(v);
        return;
      }
    } else {
      console.log("[Bambi] server offline → using browser autoplay fallback");
      autoplayWithUnmute(v);
      return;
    }
  }

  // ------------------------------------------------------
  // GLOBAL PLAY LISTENER (extra safety)
  // ------------------------------------------------------
  document.addEventListener(
    "play",
    async (e) => {
      const target = e.target;
      console.log("[Bambi] global play event on", target);

      if (!isHypnoTube() && !bambiForceHijack) return;
      if (!isBambiActivated()) {
        console.log("[Bambi] play ignored, not activated");
        return;
      }

      if (!bambiForceHijack && !isMainHypnoTubeVideo(target)) {
        console.log("[Bambi] play ignored, not main video");
        return;
      }

      if (videoAlreadySent) {
        console.log("[Bambi] video already sent to server, ignoring play");
        return;
      }

      await tryHijackOrFallback();
    },
    true
  );

  // ------------------------------------------------------
  // EXIT FULLSCREEN WHEN MAIN VIDEO ENDS
  // ------------------------------------------------------
  document.addEventListener(
    "ended",
    (e) => {
      const target = e.target;

      if (!isHypnoTube() && !bambiForceHijack) return;
      if (!bambiForceHijack && !isMainHypnoTubeVideo(target)) return;

      console.log("[Bambi] main video ended → exiting fullscreen");

      if (document.fullscreenElement) {
        document.exitFullscreen().catch(err =>
          console.warn("[Bambi] exitFullscreen failed:", err)
        );
      }

      if (navigator.keyboard?.unlock) {
        navigator.keyboard.unlock();
      }
      document.exitPointerLock?.();
    },
    true
  );

  // ------------------------------------------------------
  // ACTIVATION OVERLAY (HypnoTube only)
  // ------------------------------------------------------
  function injectOverlay() {
    if (!isHypnoTube()) return;
    if (!isMatchedDomain) return;
    if (isBlacklistedUrl()) return;
    if (bambiActivated) return;

    console.log("[Bambi] injecting activation overlay");

    const overlay = document.createElement("div");
    overlay.style = `
      position: fixed;
      inset: 0;
      background: black;
      color: white;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 3rem;
      z-index: 999999;
      cursor: pointer;
      user-select: none;
    `;
    overlay.textContent = "Click to permanently enable Bambi Mode";

    overlay.addEventListener("click", async () => {
      console.log("[Bambi] overlay clicked → activating");
      overlay.remove();
      markBambiActivated();

      const v = findMainVideo();
      if (v) {
        autoplayWithUnmute(v);
      }
    });

    document.body.appendChild(overlay);
  }

  // ------------------------------------------------------
  // BLACKLIST PUNISHMENT - Check if visiting blacklist domain and apply intensity chance
  // ------------------------------------------------------
  function checkBlacklistPunishment() {
    if (!isBlacklistedUrl()) {
      return; // Not on blacklist
    }

    console.log("[Bambi] On blacklisted domain, checking punishment...");

    // Get video history to use for punishment redirect
    chrome.storage.local.get({ bambiVideoHistory: [] }, (data) => {
      const history = Array.isArray(data.bambiVideoHistory) ? data.bambiVideoHistory : [];
      
      if (history.length === 0) {
        console.log("[Bambi] No previous videos available for punishment");
        return;
      }

      // Roll chance based on intensity level (0-100%)
      const rollChance = Math.random() * 100;
      const intensityChance = bambiIntensityLevel || 50;
      const triggers = rollChance <= intensityChance;

      console.log(`[Bambi] Punishment roll: ${rollChance.toFixed(1)}% vs intensity ${intensityChance}% → ${triggers ? "TRIGGERED" : "SKIPPED"}`);

      if (!triggers) {
        return; // Didn't roll in favor
      }

      // Show warning overlay and wait for click to trigger punishment hijack
      showPunishWarningOverlay();
    });
  }

  // PUNISH WARNING OVERLAY (Soft mode)
// ------------------------------------------------------
  function showPunishWarningOverlay() {
    console.log("[Bambi] showing punish warning overlay");

    const overlay = document.createElement("div");
    overlay.style = `
      position: fixed;
      inset: 0;
      background: rgba(0,0,0,0.9);
      color: white;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      font-size: 2.2rem;
      z-index: 999999999;
      cursor: pointer;
      user-select: none;
      text-align: center;
      padding: 20px;
    `;
    overlay.innerHTML = `
      <div>You shouldn't be here.</div>
      <div style="font-size:1.2rem; margin-top:10px;">
        Click to go back where you belong.
      </div>
    `;

    overlay.addEventListener("click", () => {
      overlay.remove();
      if (!isExtensionContextValid()) return;
      
      // Get a random video from history and trigger hijack
      chrome.storage.local.get({ bambiVideoHistory: [] }, (data) => {
        const history = Array.isArray(data.bambiVideoHistory) ? data.bambiVideoHistory : [];
        if (history.length === 0) {
          console.log("[Bambi] No videos in history for punishment");
          return;
        }
        
        const randomVideo = history[Math.floor(Math.random() * history.length)];
        console.log("[Bambi] Punishment hijack triggered with video:", randomVideo);
        
        // Trigger force hijack
        safeStorageSet({ bambiForceHijack: true });
        
        // Send to VLC
        fetch("http://127.0.0.1:5655/play", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            url: randomVideo,
            multi_monitor: bambiMultiMonitor,
            input_lock: bambiInputLockEnabled
          })
        }).then(() => {
          console.log("[Bambi] ✓ Punishment video sent to VLC");
        }).catch(e => {
          console.error("[Bambi] Punishment send failed:", e);
        });
      });
    });

    document.body.appendChild(overlay);
  }

  // ------------------------------------------------------
  // SetupRequiredOverlay
// ------------------------------------------------------
  function showSetupRequiredOverlay() {
    const overlay = document.createElement("div");
    overlay.style = `
      position: fixed;
      inset: 0;
      background: rgba(0,0,0,0.85);
      color: white;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      font-size: 2rem;
      z-index: 999999999;
      text-align: center;
      padding: 20px;
    `;
    overlay.innerHTML = `
      <div>Welcome to BambiBrowser</div>
      <div style="font-size:1.2rem; margin-top:10px;">
        Please open the extension settings to complete setup.
      </div>
    `;
    overlay.onclick = () => chrome.runtime.openOptionsPage();
    document.body.appendChild(overlay);
  }

  // ------------------------------------------------------
  // MESSAGE HANDLING (from background/popup/options)
// ------------------------------------------------------
  if (isExtensionContextValid()) {
    chrome.runtime.onMessage.addListener((msg, _sender, _sendResponse) => {
      if (!msg || typeof msg !== "object") return;

      if (msg.type === "BAMBI_ACTIVATE") {
        setTimeout(() => {
          tryHijackOrFallback();
        }, 300);
      }

      if (msg.type === "BAMBI_FORCE_REFRESH_CONFIG") {
        // placeholder
      }
    });
  }

  // ------------------------------------------------------
  // ENTRY POINT
  // ------------------------------------------------------
  if (isExtensionContextValid()) {
    chrome.storage.local.get(
      {
        bambiActivated: false,
        bambiDomains: DEFAULT_DOMAINS,
        bambiBlacklist: [],
        bambiIntensityLevel: 1,
        bambiMultiMonitor: true,
        bambiSelectedMonitors: [],
        bambiHardLock: false,
        bambiSetupComplete: false,
        bambiForceHijack: false
      },
      async (data) => {
        bambiActivated = Boolean(data.bambiActivated);
        bambiDomains = (data.bambiDomains || DEFAULT_DOMAINS)
          .map(normalizeDomainInput)
          .filter(Boolean);
        bambiBlacklist = data.bambiBlacklist || [];
        bambiIntensityLevel = Number(data.bambiIntensityLevel) || 1;
        bambiMultiMonitor = Boolean(data.bambiMultiMonitor);
        bambiSelectedMonitors = Array.isArray(data.bambiSelectedMonitors) ? data.bambiSelectedMonitors : [];
        bambiInputLockEnabled = Boolean(data.bambiHardLock);
        bambiSetupComplete = Boolean(data.bambiSetupComplete);
        bambiForceHijack = Boolean(data.bambiForceHijack);

        refreshDomainMatch();

        console.log("[Bambi] initial storage load →", {
          bambiActivated,
          bambiDomains,
          bambiBlacklist,
          bambiIntensityLevel,
          bambiMultiMonitor,
          bambiSelectedMonitors,
          bambiInputLockEnabled,
          bambiSetupComplete,
          bambiForceHijack,
          isMatchedDomain
        });

        const running = await isServerRunning();
        serverAvailable = running;

        safeStorageSet({ bambiServerOnline: running });

        if (!bambiSetupComplete) {
            showSetupRequiredOverlay();
            return;
        }

        if (!running) {
            showServerOfflineOverlay();
            return;
        }

        if (running) {
          console.log("[Bambi] ✓ Python server is running! VLC hijack mode enabled.");
        } else {
          console.log("[Bambi] Server offline → blocking hijack + activation");
          showServerOfflineOverlay();
          return;
        }

        // Check for blacklist punishment redirect
        if (bambiSetupComplete && running && bambiBlacklist.length > 0) {
          checkBlacklistPunishment();
        }

        if (isBambiActivated()) {
          setTimeout(tryHijackOrFallback, 300);
          setTimeout(tryHijackOrFallback, 1000);
        }

        injectOverlay();
      }
    );
  }
}
