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
  // ACTIVATION STATE (PERMANENT, chrome.storage.local)
  // ------------------------------------------------------

  let bambiActivated = false;
  let initialized = false;

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
  // FULLSCREEN + INPUT LOCK
  // ------------------------------------------------------

  async function enterFullscreen(elem) {
    try {
      if (!document.fullscreenElement && elem?.requestFullscreen) {
        console.log("[Bambi] requesting fullscreen on", elem);
        await elem.requestFullscreen();
      } else {
        console.log("[Bambi] fullscreen already active or elem missing");
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
  // MAIN VIDEO DETECTION (ONLY REAL PLAYER, NOT ADS)
  // ------------------------------------------------------

function isMainHypnoTubeVideo(video) {
  if (!(video instanceof HTMLVideoElement)) return false;

  const src = video.currentSrc || video.src || "";
  if (!src) return false;

  // Accept only real HypnoTube CDN sources
  const isRealSource =
    src.includes("media.hypnotube.com") ||
    src.includes("cdn.hypnotube.com") ||
    src.includes("video.hypnotube.com");

  if (!isRealSource) {
    console.log("[Bambi] rejecting non-HypnoTube video:", src);
    return false;
  }

  const rect = video.getBoundingClientRect();
  if (rect.width < 300 || rect.height < 200) {
    console.log("[Bambi] ignoring small video", rect.width, rect.height, src);
    return false;
  }

  console.log("[Bambi] identified MAIN video:", src, rect.width, rect.height);
  return true;
}

  // ------------------------------------------------------
  // GLOBAL PLAY LISTENER
  // ------------------------------------------------------

  document.addEventListener(
    "play",
    (e) => {
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

      enterFullscreen(target);
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

      await enableKeyboardLock();
      await enablePointerLock();

      const videos = document.querySelectorAll("video");
      for (const v of videos) {
        if (isMainHypnoTubeVideo(v)) {
          console.log("[Bambi] forcing main video to play");
          try {
            await v.play();
          } catch (err) {
            console.warn("[Bambi] video.play() failed:", err);
          }
          break;
        }
      }
    });

    document.body.appendChild(overlay);
  }

  // ------------------------------------------------------
  // NEW INSERTION: AUTOPLAY MAIN VIDEO IN NEW TABS
  // ------------------------------------------------------

  // If already activated, auto-play main video in new tabs
  if (bambiActivated) {
    const tryAutoplay = () => {
      const videos = document.querySelectorAll("video");
      for (const v of videos) {
        if (isMainHypnoTubeVideo(v) && v.paused) {
          console.log("[Bambi] auto-playing main video in new tab");
          v.play().catch(err => console.warn("[Bambi] autoplay failed:", err));
          return;
        }
      }
    };

    tryAutoplay();
    setTimeout(tryAutoplay, 500);
    setTimeout(tryAutoplay, 1500);
  }

// ------------------------------------------------------
// ENTRY POINT
// ------------------------------------------------------
if (isHypnoTube) {
  chrome.storage.local.get({ bambiActivated: false }, (data) => {
    bambiActivated = Boolean(data.bambiActivated);
    initialized = true;
    console.log("[Bambi] initial storage load → bambiActivated:", bambiActivated);

    // AUTOPLAY MAIN VIDEO IN NEW TABS
    if (bambiActivated) {
      const tryAutoplay = () => {
        const videos = document.querySelectorAll("video");
        for (const v of videos) {
          if (isMainHypnoTubeVideo(v) && v.paused) {
            console.log("[Bambi] auto-playing main video in new tab");
            v.play().catch(err => console.warn("[Bambi] autoplay failed:", err));
            return;
          }
        }
      };

      tryAutoplay();
      setTimeout(tryAutoplay, 500);
      setTimeout(tryAutoplay, 1500);
    }

    injectOverlay();
  });
}

}
