// ------------------------------------------------------
// PREVENT DOUBLE LOADING
// ------------------------------------------------------
if (window.__bambiLoaded) {
} else {
  window.__bambiLoaded = true;

  const hostname = location.hostname.toLowerCase();
  const isHypnoTube = hostname.includes("hypnotube");

  console.log("[Bambi] content script loaded on", location.href, "isHypnoTube:", isHypnoTube);

  // ------------------------------------------------------
  // CONFIG
  // ------------------------------------------------------
  const BAMBI_SERVER = "http://127.0.0.1:5655";
  const BAMBI_ENDPOINT = BAMBI_SERVER + "/play";

  // ------------------------------------------------------
  // STATE
  // ------------------------------------------------------
  let bambiActivated = false;
  let initialized = false;
  let serverAvailable = false;
  let videoAlreadySent = false;
  let mainVideo = null;

  // ------------------------------------------------------
  // ACTIVATION STATE
  // ------------------------------------------------------
  function isBambiActivated() {
    return bambiActivated;
  }

  function markBambiActivated() {
    bambiActivated = true;
    console.log("[Bambi] markBambiActivated → true");
    chrome.storage.local.set({ bambiActivated: true });
  }

  chrome.storage.onChanged.addListener((changes, areaName) => {
    if (areaName === "local" && changes.bambiActivated) {
      bambiActivated = Boolean(changes.bambiActivated.newValue);
      console.log("[Bambi] storage change → bambiActivated:", bambiActivated);
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
      const response = await fetch(BAMBI_ENDPOINT, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: videoUrl })
      });
      return response.ok;
    } catch (e) {
      console.log("[Bambi] Failed to send to server:", e.message);
      return false;
    }
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
    e.stopPropagation();
    e.preventDefault();
  }

  document.addEventListener("fullscreenchange", () => {
    console.log("[Bambi] fullscreenchange →", !!document.fullscreenElement);
    if (document.fullscreenElement) {
      enableKeyboardLock();
      enablePointerLock();
      window.addEventListener("keydown", suppressKeys, true);
    } else {
      window.removeEventListener("keydown", suppressKeys, true);
      if (navigator.keyboard?.unlock) {
        console.log("[Bambi] unlocking keyboard");
        navigator.keyboard.unlock();
      }
    }
  });

  // ------------------------------------------------------
  // MAIN VIDEO DETECTION
  // ------------------------------------------------------
  function findMainVideo() {
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
      console.log("[Bambi] MAIN video locked:", src, rect.width, rect.height);
      return v;
    }

    return null;
  }

  function isMainHypnoTubeVideo(video) {
    const v = findMainVideo();
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

    v.play().then(() => {
      console.log("[Bambi] autoplay started, attempting immediate unmute");

      v.muted = false;

      if (v.paused) {
        handleAutoplayBlocked(v);
      }
    }).catch(err => {
      console.warn("[Bambi] autoplay failed:", err);
      handleAutoplayBlocked(v);
    });
  }

  // ------------------------------------------------------
  // HIJACK LOGIC
  // ------------------------------------------------------
  async function tryHijackOrFallback() {
    if (!isHypnoTube) return;
    if (!isBambiActivated()) {
      console.log("[Bambi] not activated → no hijack");
      return;
    }
    if (videoAlreadySent) return;

    const v = findMainVideo();
    if (!v) return;

    const videoSrc = v.currentSrc || v.src || "";
    console.log("[Bambi] main video detected:", videoSrc.substring(0, 80));

    if (serverAvailable) {
      console.log("[Bambi] server available → sending to VLC");
      const sent = await sendVideoToServer(videoSrc);
      if (sent) {
        console.log("[Bambi] ✓ Video sent to VLC");
        videoAlreadySent = true;
        v.pause();
        v.autoplay = false;
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

      if (!isHypnoTube) return;
      if (!isBambiActivated()) {
        console.log("[Bambi] play ignored, not activated");
        return;
      }

      if (!isMainHypnoTubeVideo(target)) {
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

      if (!isHypnoTube) return;
      if (!isMainHypnoTubeVideo(target)) return;

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
  // ACTIVATION OVERLAY
  // ------------------------------------------------------
  function injectOverlay() {
    if (!isHypnoTube) return;
    if (isBambiActivated()) return;

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
  // ENTRY POINT
  // ------------------------------------------------------
  if (isHypnoTube) {
    chrome.storage.local.get({ bambiActivated: false }, async (data) => {
      bambiActivated = Boolean(data.bambiActivated);
      initialized = true;
      console.log("[Bambi] initial storage load → bambiActivated:", bambiActivated);

      const running = await isServerRunning();
      serverAvailable = running;

      if (running) {
        console.log("[Bambi] ✓ Python server is running! VLC hijack mode enabled.");
      } else {
        console.log("[Bambi] Python server not running. Using browser autoplay fallback.");
      }

      if (bambiActivated) {
        // Try hijack or fallback once DOM is ready
        setTimeout(tryHijackOrFallback, 300);
        setTimeout(tryHijackOrFallback, 1000);
      }

      injectOverlay();
    });
  }
}