(function() {
  "use strict";
  
  const SERVER_URL = "http://127.0.0.1:5655";
  
  let settings = { enabled: true };
  let serverOnline = false;
  let videoSent = false;
  let currentVideoUrl = null;
  let fallbackActive = false;
  let originalVideo = null;
  let enterOverlay = null;
  let pauseOverlay = null;
  let keyBlockHandler = null;
  let escapeDebounce = false;
  
  // Get detector for current site
  function getDetector() {
    const hostname = window.location.hostname;
    if (hostname.includes('hypnotube.com')) {
      return window.BambiDetectors?.hypnotube;
    }
    return null;
  }
  
  const detector = getDetector();
  if (!detector) {
    console.log("[Bambi] Site not supported");
    return;
  }
  
  console.log("[Bambi] Using detector:", detector.name);
  
  // Load enabled setting
  chrome.storage.local.get({ enabled: true }, (data) => {
    settings.enabled = data.enabled;
  });
  
  chrome.storage.onChanged.addListener((changes) => {
    if (changes.enabled) {
      settings.enabled = changes.enabled.newValue;
    }
  });
  
  async function checkServer() {
    try {
      const res = await fetch(`${SERVER_URL}/health`);
      serverOnline = res.ok;
      return serverOnline;
    } catch {
      serverOnline = false;
      return false;
    }
  }
  
  async function sendToApp(url) {
    try {
      const res = await fetch(`${SERVER_URL}/play`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: url })
      });
      return res.ok;
    } catch {
      return false;
    }
  }
  
  function showEnterOverlay(video) {
    if (enterOverlay) enterOverlay.remove();
    if (pauseOverlay) {
      if (pauseOverlay._escapeBlocker) {
        document.removeEventListener('keydown', pauseOverlay._escapeBlocker, true);
      }
      pauseOverlay.remove();
      pauseOverlay = null;
    }
    
    originalVideo = video;
    video.pause();
    
    enterOverlay = document.createElement("div");
    enterOverlay.id = "bambi-enter-overlay";
    enterOverlay.style.cssText = `
      position: fixed;
      top: 0;
      left: 0;
      width: 100vw;
      height: 100vh;
      background: black;
      color: white;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      font-size: 2rem;
      z-index: 99999999;
      cursor: pointer;
    `;
    enterOverlay.innerHTML = `
      <div style="font-size: 5rem; margin-bottom: 20px;">🎀</div>
      <div style="font-size: 2rem; margin-bottom: 10px;">Enter Bambi Mode</div>
      <div style="font-size: 1.2rem; opacity: 0.8;">Click or Press SPACE</div>
    `;
    
    const enterHandler = (e) => {
      if (e.type === 'keydown') {
        if (e.key !== ' ' && e.key !== 'Space') return;
        e.preventDefault();
        e.stopPropagation();
      }
      
      enterOverlay.remove();
      enterOverlay = null;
      document.removeEventListener('keydown', enterHandler);
      
      // Direct call - this is from user gesture so fullscreen will work
      enterFullscreenMode(video);
    };
    
    enterOverlay.addEventListener('click', enterHandler);
    document.addEventListener('keydown', enterHandler);
    
    document.body.appendChild(enterOverlay);
    console.log("[Bambi] Enter overlay shown");
  }
  
  function showPauseOverlay() {
    // Clean up existing overlays
    if (pauseOverlay) {
      if (pauseOverlay._escapeBlocker) {
        document.removeEventListener('keydown', pauseOverlay._escapeBlocker, true);
      }
      pauseOverlay.remove();
      pauseOverlay = null;
    }
    if (enterOverlay) {
      enterOverlay.remove();
      enterOverlay = null;
    }
    
    if (originalVideo) {
      originalVideo.pause();
    }
    
    pauseOverlay = document.createElement("div");
    pauseOverlay.id = "bambi-pause-overlay";
    pauseOverlay.style.cssText = `
      position: fixed;
      top: 0;
      left: 0;
      width: 100vw;
      height: 100vh;
      background: rgba(0, 0, 0, 0.95);
      color: white;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      font-size: 2rem;
      z-index: 99999999;
      cursor: pointer;
      backdrop-filter: blur(10px);
    `;
    pauseOverlay.innerHTML = `
      <div style="font-size: 5rem; margin-bottom: 20px;">🎀</div>
      <div style="font-size: 2rem; margin-bottom: 10px;">Escape try detected</div>
      <div style="font-size: 1.2rem; opacity: 0.8;">Click or Press SPACE to Resume</div>
    `;
    
    const resumeHandler = (e) => {
      if (e.type === 'keydown') {
        if (e.key !== ' ' && e.key !== 'Space') return;
        e.preventDefault();
        e.stopPropagation();
      }
      
      // Remove overlay and listeners
      if (pauseOverlay) {
        if (pauseOverlay._escapeBlocker) {
          document.removeEventListener('keydown', pauseOverlay._escapeBlocker, true);
        }
        pauseOverlay.remove();
        pauseOverlay = null;
      }
      document.removeEventListener('keydown', resumeHandler);
      
      // Resume fullscreen with the original video
      if (originalVideo) {
        enterFullscreenMode(originalVideo);
      }
    };
    
    const blockEscapeHandler = (e) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        e.stopPropagation();
        e.stopImmediatePropagation();
        return false;
      }
    };
    
    pauseOverlay.addEventListener('click', resumeHandler);
    document.addEventListener('keydown', resumeHandler);
    document.addEventListener('keydown', blockEscapeHandler, true);
    
    pauseOverlay._escapeBlocker = blockEscapeHandler;
    
    document.body.appendChild(pauseOverlay);
    console.log("[Bambi] Pause overlay shown");
  }
  
  function createKeyBlockHandler() {
    return function(e) {
      const key = e.key;
      
      // Always block dangerous keys
      if (key === 'F11' || key === 'F5' || key === 'F1' || key === 'F2' || key === 'F3' ||
          key === 'F4' || key === 'F6' || key === 'F7' || key === 'F8' || key === 'F9' ||
          key === 'F10' || key === 'F12' || (e.altKey && key === 'Enter') ||
          key === 'Meta' || key === 'Alt' || key === 'Control' || key === 'Tab') {
        e.preventDefault();
        e.stopPropagation();
        e.stopImmediatePropagation();
        return false;
      }
      
      // Block everything except Escape during HardLock
      if (key !== 'Escape') {
        e.preventDefault();
        e.stopPropagation();
        e.stopImmediatePropagation();
        return false;
      }
    };
  }
  
  function blockContext(e) {
    e.preventDefault();
    return false;
  }
  
  async function enterFullscreenMode(video) {
    if (fallbackActive) return;
    
    try {
      originalVideo = video;
      
      video.muted = false;
      video.volume = 1.0;
      
      // Request fullscreen first
      if (video.requestFullscreen) {
        await video.requestFullscreen();
      }
      
      // Then play
      await video.play();
      
      fallbackActive = true;
      videoSent = true;
      escapeDebounce = false;
      
      // Apply HardLock
      if (keyBlockHandler) {
        document.removeEventListener('keydown', keyBlockHandler, true);
        window.removeEventListener('keydown', keyBlockHandler, true);
      }
      
      keyBlockHandler = createKeyBlockHandler();
      document.addEventListener('keydown', keyBlockHandler, true);
      window.addEventListener('keydown', keyBlockHandler, true);
      
      document.addEventListener('contextmenu', blockContext, true);
      
      if (navigator.keyboard?.lock) {
        navigator.keyboard.lock([
          "Escape", "F11", "F1", "F2", "F3", "F4", "F5", "F6", "F7", "F8", "F9", "F10", "F12",
          "AltLeft", "AltRight", "ControlLeft", "ControlRight", "MetaLeft", "MetaRight",
          "Tab", "CapsLock", "ShiftLeft", "ShiftRight"
        ]).catch(() => {});
      }
      
      if (document.body.requestPointerLock) {
        document.body.requestPointerLock();
      }
      
      console.log("[Bambi] 🔒 HardLock ACTIVE - Fullscreen mode");
      
    } catch (err) {
      console.error("[Bambi] Fullscreen error:", err);
      fallbackActive = false;
      videoSent = false;
    }
  }
  
  function exitFullscreenMode() {
    if (!fallbackActive) return;
    
    console.log("[Bambi] Exiting fullscreen");
    
    if (keyBlockHandler) {
      document.removeEventListener('keydown', keyBlockHandler, true);
      window.removeEventListener('keydown', keyBlockHandler, true);
      keyBlockHandler = null;
    }
    
    document.removeEventListener('contextmenu', blockContext, true);
    
    if (navigator.keyboard?.unlock) {
      navigator.keyboard.unlock();
    }
    document.exitPointerLock();
    
    fallbackActive = false;
    
    if (!escapeDebounce) {
      escapeDebounce = true;
      setTimeout(() => {
        showPauseOverlay();
        escapeDebounce = false;
      }, 100);
    }
    
    console.log("[Bambi] 🔓 Locks released");
  }
  
  async function hijackVideo() {
    if (!settings.enabled) return;
    if (videoSent || fallbackActive) return;
    
    const video = detector.findVideo();
    if (!video) return;
    
    const url = detector.getVideoUrl(video);
    if (!url || url === currentVideoUrl) return;
    
    currentVideoUrl = url;
    console.log(`[Bambi] Video detected:`, url.substring(0, 80));
    
    const online = await checkServer();
    
    if (online) {
      const sent = await sendToApp(url);
      if (sent) {
        videoSent = true;
        video.pause();
        console.log("[Bambi] ✅ Sent to desktop app");
        return;
      }
    }
    
    console.log("[Bambi] App offline - using browser fallback");
    showEnterOverlay(video);
  }
  
  // Fullscreen change listener
  document.addEventListener('fullscreenchange', () => {
    if (!document.fullscreenElement && fallbackActive) {
      exitFullscreenMode();
    }
  });
  
  // Video ended
  document.addEventListener('ended', (e) => {
    if (fallbackActive && e.target === originalVideo) {
      if (document.fullscreenElement) {
        document.exitFullscreen();
      }
      exitFullscreenMode();
    }
  }, true);
  
  // Play event
  document.addEventListener("play", (e) => {
    const video = e.target;
    if (video.tagName === "VIDEO" && !videoSent && !fallbackActive) {
      setTimeout(hijackVideo, 100);
    }
  }, true);
  
  // Global dangerous key blocker (always active)
  window.addEventListener('keydown', (e) => {
    if (e.key === 'F11' || e.key === 'F5' || (e.altKey && e.key === 'Enter')) {
      e.preventDefault();
      e.stopPropagation();
      return false;
    }
  }, true);
  
  // Try after load
  setTimeout(hijackVideo, 1000);
  setTimeout(hijackVideo, 2000);
  
  // Reset on navigation
  let lastUrl = location.href;
  new MutationObserver(() => {
    if (location.href !== lastUrl) {
      lastUrl = location.href;
      videoSent = false;
      fallbackActive = false;
      currentVideoUrl = null;
      originalVideo = null;
      if (enterOverlay) enterOverlay.remove();
      if (pauseOverlay) {
        if (pauseOverlay._escapeBlocker) {
          document.removeEventListener('keydown', pauseOverlay._escapeBlocker, true);
        }
        pauseOverlay.remove();
      }
      enterOverlay = null;
      pauseOverlay = null;
      if (keyBlockHandler) {
        document.removeEventListener('keydown', keyBlockHandler, true);
        window.removeEventListener('keydown', keyBlockHandler, true);
        keyBlockHandler = null;
      }
      setTimeout(hijackVideo, 1000);
    }
  }).observe(document, { subtree: true, childList: true });
  
  console.log("[Bambi] Ready");
})();