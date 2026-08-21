(function() {
  "use strict";

  const browserAPI = typeof browser !== 'undefined' ? browser : chrome;
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
  
  // Global tracker for the spiral container
  let spiralContainer = null;

  // ---- Fuzzy Spiral (Nimja-style interlocking bands) ----
  class FuzzySpiral {
    constructor(canvas, wordsList) {
      this.canvas = canvas;
      this.ctx = canvas.getContext('2d');
      this.words = wordsList;
      this.wordIndex = 0;
      this.frameCount = 0;
      this.lastTime = 0;

      this.settings = {
        arms: 5,
        turns: 2,
        curve: 2.5,
        width: 0.5,
        wobble: 0.05,
        wphase: 0.1,
        wspeed: 0.5,
        speed: 0.8,
        dir: 1
      };

      this.TAU = Math.PI * 2;
      this.HPI = Math.PI / 2;
      this.resize();
    }

    resize() {
      const rect = this.canvas.parentElement.getBoundingClientRect();
      this.canvas.width = rect.width;
      this.canvas.height = rect.height;
      this.centerX = this.canvas.width / 2;
      this.centerY = this.canvas.height / 2;
      this.radius = Math.max(this.canvas.width, this.canvas.height) * 0.95;
    }

    calculatePoint(settings, offset, cur, wAngle, wSize) {
      let curRot = (cur * settings.turns * this.TAU) + offset;
      let curRadius = this.radius * Math.pow(cur, settings.curve);
      if (settings.dir) curRot = this.TAU - curRot;
      curRot += settings.wobble * Math.sin(cur * wSize + wAngle);
      return {
        x: this.centerX + curRadius * Math.cos(curRot),
        y: this.centerY + curRadius * Math.sin(curRot)
      };
    }

    calculateArm(settings, offset, wAngle, wSize) {
      let result = [];
      let steps = 180 * settings.turns;
      let step = 1 / steps;
      for (let i = 0; i <= 1; i += step) {
        result.push(this.calculatePoint(settings, offset, i, wAngle, wSize));
      }
      return result;
    }

    drawArm(ctx, coords, reverse) {
      if (reverse) coords.reverse();
      for (let c of coords) {
        ctx.lineTo(c.x, c.y);
      }
    }

    drawArc(ctx, outCoords, inCoords, antiClockwise) {
      let c1 = outCoords[outCoords.length - 1];
      let c2 = inCoords[inCoords.length - 1];
      let a1 = Math.atan2(c1.y - this.centerY, c1.x - this.centerX);
      let a2 = Math.atan2(c2.y - this.centerY, c2.x - this.centerX);
      ctx.arc(this.centerX, this.centerY, this.radius, a1, a2, antiClockwise);
    }

    animate(timestamp) {
      if (!this.lastTime) this.lastTime = timestamp;
      const time = timestamp / 1000;
      const ctx = this.ctx;
      const settings = this.settings;

      ctx.fillStyle = '#000000';
      ctx.fillRect(0, 0, this.canvas.width, this.canvas.height);

      const speed = time * settings.dir * settings.speed;
      const wAngle = time * settings.wspeed;
      const wPhase = time * settings.wphase;
      const wSize = Math.PI * (5 - 4 * Math.cos(wPhase));

      this.drawLayer(ctx, speed, '#ffffff', '#00ff00', wAngle, wSize);
      this.drawLayer(ctx, speed + this.HPI, '#000000', '#ff00ff', wAngle + this.HPI, wSize);

      this.frameCount++;
      if (this.frameCount > 180) {
        this.wordIndex = (this.wordIndex + 1) % this.words.length;
        this.frameCount = 0;
      }
      ctx.save();
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillStyle = '#ff6bd6';
      ctx.font = 'bold 28px Arial';
      ctx.shadowColor = '#ff6bd6';
      ctx.shadowBlur = 20;
      ctx.fillText(this.words[this.wordIndex], this.centerX, this.centerY);
      ctx.restore();

      requestAnimationFrame(this.animate.bind(this));
    }

    drawLayer(ctx, angle, fillColor, strokeColor, wAngle, wSize) {
      const settings = this.settings;
      const width = 1 / settings.arms * settings.width;
      const TAU = this.TAU;

      ctx.lineJoin = 'round';
      ctx.lineCap = 'round';

      for (let i = 0; i < settings.arms; i++) {
        ctx.beginPath();
        ctx.moveTo(this.centerX, this.centerY);

        const offset = i / settings.arms * TAU + angle;
        const outCoords = this.calculateArm(settings, offset, wAngle, wSize);
        const inCoords = this.calculateArm(settings, offset + width * TAU, wAngle, wSize);

        this.drawArm(ctx, outCoords, false);
        this.drawArc(ctx, outCoords, inCoords, settings.dir > 0);
        this.drawArm(ctx, inCoords, true);
        ctx.closePath();

        ctx.fillStyle = fillColor;
        ctx.fill();

        if (strokeColor) {
          ctx.strokeStyle = strokeColor;
          ctx.lineWidth = 2.5;
          ctx.stroke();
        }
      }
    }
  }

  // Get detector for current site
  function getDetector() {
    const hostname = window.location.hostname;
    if (hostname.includes('hypnotube.com')) {
      return window.BambiDetectors?.hypnotube;
    }
    if (hostname.includes('bambicloud.com')) {
      return window.BambiDetectors?.bambicloud;
    }
    return null;
  }

  const detector = getDetector();
  if (!detector) {
    console.log("[Bambi] Site not supported");
    return;
  }

  console.log("[Bambi] Using detector:", detector.name);

  // Load enabled setting with Promise fallback
  browserAPI.storage.local.get({ enabled: true })
    .then(data => {
      settings.enabled = data.enabled;
    })
    .catch(() => {
      settings.enabled = true; // Fallback if storage is blocked
    });

  browserAPI.storage.onChanged.addListener((changes) => {
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

      enterFullscreenMode(video);
    };

    enterOverlay.addEventListener('click', enterHandler);
    document.addEventListener('keydown', enterHandler);

    document.body.appendChild(enterOverlay);
  }

  function showPauseOverlay() {
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

      if (pauseOverlay) {
        if (pauseOverlay._escapeBlocker) {
          document.removeEventListener('keydown', pauseOverlay._escapeBlocker, true);
        }
        pauseOverlay.remove();
        pauseOverlay = null;
      }
      document.removeEventListener('keydown', resumeHandler);

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
  }

  function showBambicloudEnterOverlay(specialInfo) {
    if (enterOverlay) {
      enterOverlay.remove();
      enterOverlay = null;
    }
    if (pauseOverlay) {
      if (pauseOverlay._escapeBlocker) {
        document.removeEventListener('keydown', pauseOverlay._escapeBlocker, true);
      }
      pauseOverlay.remove();
      pauseOverlay = null;
    }

    let bambicloudEnterOverlay = document.createElement("div");
    bambicloudEnterOverlay.id = "bambi-bambicloud-enter-overlay";
    bambicloudEnterOverlay.style.cssText = `
      position: fixed;
      top: 0;
      left: 0;
      width: 100vw;
      height: 100vh;
      background: #0a0a0a;
      color: #ff6bd6;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      font-size: 2rem;
      z-index: 99999999;
    `;

    bambicloudEnterOverlay.addEventListener('contextmenu', e => e.preventDefault(), false);

    bambicloudEnterOverlay.innerHTML = `
      <div style="font-size: 5rem; margin-bottom: 20px;">🎀</div>
      <div style="font-size: 2rem; margin-bottom: 10px;">Enter Bambicloud Session</div>
      <div style="font-size: 1.2rem; opacity: 0.8;">Click or Press SPACE</div>
    `;

    const enterHandler = function(e) {
      if (e.type === 'keydown') {
        if (e.code !== 'Space' && e.key !== ' ') return;
        e.preventDefault();
        e.stopPropagation();
      } else if (e.type === 'keyup') {
        return;
      }

      if (bambicloudEnterOverlay) {
        bambicloudEnterOverlay.remove();
        bambicloudEnterOverlay = null;
      }
      document.removeEventListener('keydown', enterHandler);
      document.removeEventListener('keyup', enterHandler);

      showBambicloudFallbackOverlay(specialInfo);
    };

    bambicloudEnterOverlay.addEventListener('click', enterHandler);
    document.addEventListener('keydown', enterHandler);
    document.addEventListener('keyup', enterHandler);
    document.body.appendChild(bambicloudEnterOverlay);
  }

  // --- BULLETPROOF: Handle Direct Audio Links ---
  function handleDirectAudio(specialInfo) {
    // The main start function
    const startSession = () => {
      if (videoSent) return;
      videoSent = true;
      console.log("[Bambi] Direct Audio detected, launching overlay...");

      // Create container immediately
      const container = document.createElement("div");
      container.id = "bambi-bambicloud-spiral-overlay";
      container.style.cssText = `
        position: fixed;
        top: 0; left: 0;
        width: 100vw; height: 100vh;
        background: #000000;
        display: flex;
        align-items: center;
        justify-content: center;
        z-index: 99999999;
        overflow: hidden;
        cursor: none;
        touch-action: none;
        user-select: none;
      `;
      document.body.appendChild(container);

      // Try to enter fullscreen
      if (container.requestFullscreen) {
        container.requestFullscreen().catch(() => {});
      }

      // Start the spiral
      showBambicloudSpiralOverlay(container, specialInfo);

      // Poll for audio ending
      const audioEndChecker = setInterval(() => {
        const audio = document.querySelector('audio');
        if (audio && audio.ended) {
          clearInterval(audioEndChecker);
          if (container._cleanup) container._cleanup();
          container.remove();
          videoSent = false;
          console.log("[Bambi] Audio ended, overlay removed.");
        }
      }, 500);
    };

    // 1. If audio is already playing, start immediately
    const existingAudio = document.querySelector('audio');
    if (existingAudio && !existingAudio.paused && existingAudio.currentTime > 0) {
      console.log("[Bambi] Audio is already playing, starting immediately.");
      startSession();
      return;
    }

    // 2. Otherwise, listen for the 'play' event globally (catches shadow DOM)
    document.addEventListener('play', (e) => {
      if (e.target && e.target.tagName === 'AUDIO') {
        startSession();
      }
    }, true);

    // 3. Aggressive Fallback: Poll for audio starting
    const startChecker = setInterval(() => {
      const audio = document.querySelector('audio');
      if (audio && !audio.paused && audio.currentTime > 0) {
        clearInterval(startChecker);
        startSession();
      }
    }, 500);

    // 4. Ultimate Fallback: If it autoplays and we still missed it, force it after 1.5 seconds.
    setTimeout(() => {
      if (!videoSent) {
        console.log("[Bambi] Assumed autoplay, forcing overlay launch.");
        clearInterval(startChecker);
        startSession();
      }
    }, 1500);
  }

  // --- UPDATED: Fallback Overlay for file/playlist pages ---
  function showBambicloudFallbackOverlay(specialInfo) {
    if (enterOverlay) {
      enterOverlay.remove();
      enterOverlay = null;
    }
    if (pauseOverlay) {
      if (pauseOverlay._escapeBlocker) {
        document.removeEventListener('keydown', pauseOverlay._escapeBlocker, true);
      }
      pauseOverlay.remove();
      pauseOverlay = null;
    }

    spiralContainer = document.createElement("div");
    spiralContainer.id = "bambi-bambicloud-spiral-overlay";
    spiralContainer.style.cssText = `
      position: fixed;
      top: 0; left: 0;
      width: 100vw; height: 100vh;
      background: #000000;
      display: none;
      align-items: center;
      justify-content: center;
      z-index: 99999999;
      overflow: hidden;
      cursor: none;
      touch-action: none;
      user-select: none;
    `;
    document.body.appendChild(spiralContainer);

    const bambicloudOverlay = document.createElement("div");
    bambicloudOverlay.id = "bambi-bambicloud-overlay";
    bambicloudOverlay.style.cssText = `
      position: fixed;
      top: 0;
      left: 0;
      width: 100vw;
      height: 100vh;
      background: #0a0a0a;
      color: #ff6bd6;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      font-size: 2rem;
      z-index: 99999999;
      cursor: pointer;
    `;

    const countdownElement = document.createElement("div");
    countdownElement.id = "bambi-countdown";
    countdownElement.style.cssText = `
      font-size: 4rem;
      font-weight: bold;
      margin-bottom: 20px;
      min-height: 60px;
      visibility: hidden;
    `;

    const instructions = document.createElement("div");
    instructions.innerHTML = `
      <div style="font-size: 1.5rem; margin-bottom: 15px;">Get comfortable and prepare for your session</div>
      <div style="font-size: 1.2rem; opacity: 0.8; margin-bottom: 10px;">Put on your headphones and relax</div>
      <div style="font-size: 1rem; opacity: 0.6;" id="bambi-start-instructions">Click anywhere or press SPACE to start session</div>
    `;

    bambicloudOverlay.appendChild(instructions);
    bambicloudOverlay.appendChild(countdownElement);
    document.body.appendChild(bambicloudOverlay);

    let countdownDuration = 30;
    let countdownInterval = null;

    const startCountdownHandler = (e) => {
      e.preventDefault();
      e.stopPropagation();

      bambicloudOverlay.removeEventListener('click', startCountdownHandler);
      document.removeEventListener('keydown', startCountdownHandler);

      if (spiralContainer.requestFullscreen) {
        spiralContainer.requestFullscreen().catch(err => {
          console.warn("[Bambi] Fullscreen trigger failed:", err);
        });
      }

      instructions.innerHTML = `
        <div style="font-size: 1.5rem; margin-bottom: 15px;">Session starting in...</div>
        <div style="font-size: 1.2rem; margin-bottom: 10px;">Get ready...</div>
        <div style="font-size: 1rem; opacity: 0.8;"></div>
      `;

      countdownElement.style.visibility = 'visible';
      let remainingTime = countdownDuration;
      countdownElement.textContent = remainingTime.toString();

      countdownInterval = setInterval(() => {
        remainingTime--;
        if (remainingTime <= 0) {
          clearInterval(countdownInterval);
          bambicloudOverlay.remove();
          spiralContainer.style.display = 'flex';
          playAudioAndShowSpiral(spiralContainer, specialInfo);
          return;
        }
        countdownElement.textContent = remainingTime.toString();
      }, 1000);
    };

    bambicloudOverlay.addEventListener('click', startCountdownHandler);
    document.addEventListener('keydown', startCountdownHandler);
  }

  function playAudioAndShowSpiral(container, specialInfo) {
    const urlMatch = specialInfo.url.match(/[0-9a-f\-]{8}-[0-9a-f\-]{4}-[0-9a-f\-]{4}-[0-9a-f\-]{4}-[0-9a-f\-]{12}/);
    if (urlMatch) {
      const uuid = urlMatch[0];
      const urlsToTry = [
          `https://cdn.bambicloud.com/${uuid}.wav`,
          `https://cdn.bambicloud.com/${uuid}.mp3`,
          `https://bambicloud.com/${uuid}.mp3`,
          `https://media.bambicloud.com/${uuid}.mp3`
      ];
      let tryNextUrl = (index) => {
        if (index >= urlsToTry.length) {
          console.log("[Bambi] All direct URLs failed, falling back to element search");
          showBambicloudSpiralOverlay(container, specialInfo);
          fallbackAudioPlay(specialInfo);
          return;
        }
        const audio = new Audio(urlsToTry[index]);
        audio.play().then(() => {
          console.log("[Bambi] Audio started, now showing spiral");
          showBambicloudSpiralOverlay(container, specialInfo);
          window._currentBambicloudAudio = audio;

          audio.onended = () => {
            if (container) {
              if (container._cleanup) container._cleanup();
              container.remove();
              spiralContainer = null;
            }
            window._currentBambicloudAudio = null;
          };
        }).catch(() => {
          tryNextUrl(index + 1);
        });
      };
      tryNextUrl(0);
    } else {
      console.log("[Bambi] Could not extract UUID, falling back to element search");
      showBambicloudSpiralOverlay(container, specialInfo);
      fallbackAudioPlay(specialInfo);
    }
  }

  function showBambicloudSpiralOverlay(container, specialInfo) {
    container.innerHTML = '';

    const canvasWrapper = document.createElement("div");
    canvasWrapper.style.cssText = "width: 100%; height: 100%; position: relative;";
    const canvas = document.createElement("canvas");
    canvas.style.cssText = "position: absolute; top: 0; left: 0; width: 100%; height: 100%;";
    canvasWrapper.appendChild(canvas);
    container.appendChild(canvasWrapper);

    const reEnterFullscreen = () => {
      if (!document.fullscreenElement && container.isConnected) {
        container.requestFullscreen().catch(() => {});
      }
    };
    document.addEventListener('fullscreenchange', reEnterFullscreen);

    const globalBlocker = (e) => {
      const key = e.key;
      if (key === 'Escape' || key === 'F11' || key === 'F5' || key === 'F1' || key === 'F12' ||
          (e.ctrlKey && key === 'w') || (e.ctrlKey && key === 'W') ||
          (e.altKey && key === 'Enter') || e.key === 'Meta' || e.key === 'Alt' || e.key === 'Tab') {
        e.preventDefault();
        e.stopPropagation();
        e.stopImmediatePropagation();
        return false;
      }
    };
    document.addEventListener('keydown', globalBlocker, true);

    const blockAll = (e) => {
      e.preventDefault();
      e.stopPropagation();
      return false;
    };
    ['click','mousedown','mouseup','keydown','keyup','keypress','contextmenu'].forEach(evt => {
      container.addEventListener(evt, blockAll, true);
    });

    if (navigator.keyboard?.lock) {
      navigator.keyboard.lock([
        "Escape", "F11", "F1", "F2", "F3", "F4", "F5", "F6", "F7", "F8", "F9", "F10", "F12",
        "AltLeft", "AltRight", "ControlLeft", "ControlRight", "MetaLeft", "MetaRight",
        "Tab", "CapsLock", "ShiftLeft", "ShiftRight"
      ]).catch(() => {});
    }

    container._cleanup = () => {
      document.removeEventListener('fullscreenchange', reEnterFullscreen);
      document.removeEventListener('keydown', globalBlocker, true);
      if (navigator.keyboard?.unlock) navigator.keyboard.unlock();
    };

    const words = [
      "Airhead barbie","Bambi","Bambi butt lock","Bambi cum and collapse",
      "Bambi cunt lock","Bambi does as shes told","Bambi face lock",
      "Bambi freeze","Bambi hips lock","Bambi limbs lock","Bambi limp",
      "Bambi lips lock","Bambi posture lock","Bambi reset","Bambi sleep",
      "Bambi throat lock","Bambi tits lock","Bambi uniform lock",
      "Bambi waist lock","Bambi wake and obey","Bimbo doll",
      "Blonde moment","Braindead bobblehead","Cock zombie now",
      "Cockblank lovedoll","Drop for cock","Giggletime","Good girl",
      "Primped and pampered","Safe and secure","Snap and forget",
      "Zap cock drain obey"
    ];

    const spiral = new FuzzySpiral(canvas, words);
    const resizeHandler = () => spiral.resize();
    window.addEventListener('resize', resizeHandler);
    requestAnimationFrame(spiral.animate.bind(spiral));
  }

  function fallbackAudioPlay(specialInfo) {
    const audioSelectors = [
      "audio",
      "[src*='.mp3']",
      "[src*='.wav']",
      "[src*='.ogg']",
      ".audio-player",
      "#audio-player"
    ];

    let audioElement = null;
    for (const selector of audioSelectors) {
      audioElement = document.querySelector(selector);
      if (audioElement) break;
    }

    if (audioElement) {
      console.log("[Bambi] Found audio element, attempting to play");
      const playPromise = audioElement.play();
      if (playPromise !== undefined) {
        playPromise.then(_ => {
          console.log("[Bambi] Successfully started playing found audio element");
        }).catch(e => {
          console.error("[Bambi] Error playing found audio element:", e);
        });
      }
    } else {
      console.log("[Bambi] No audio element found");
    }
  }

  function createKeyBlockHandler() {
    return function(e) {
      const key = e.key;
      if (key === 'F11' || key === 'F5' || key === 'F1' || key === 'F2' || key === 'F3' ||
          key === 'F4' || key === 'F6' || key === 'F7' || key === 'F8' || key === 'F9' ||
          key === 'F10' || key === 'F12' || (e.altKey && key === 'Enter') ||
          key === 'Meta' || key === 'Alt' || key === 'Control' || key === 'Tab') {
        e.preventDefault();
        e.stopPropagation();
        e.stopImmediatePropagation();
        return false;
      }
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

      if (video.requestFullscreen) {
        await video.requestFullscreen();
      } else if (video.mozRequestFullScreen) {
        await video.mozRequestFullScreen();
      } else if (video.webkitRequestFullscreen) {
        await video.webkitRequestFullscreen();
      }

      await video.play();

      fallbackActive = true;
      videoSent = true;
      escapeDebounce = false;

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

    const hostname = window.location.hostname;
    if (hostname.includes('bambicloud.com')) {
      const specialInfo = detector.handleSpecialPage();
      if (specialInfo.isSpecial) {
        // Direct media link (e.g., cdn.bambicloud.com/uuid.mp3)
        if (specialInfo.type === 'direct') {
          const online = await checkServer();
          if (online && specialInfo.uuid) {
            const mediaUrls = [
              `https://cdn.bambicloud.com/${specialInfo.uuid}.mp3`,
              `https://cdn.bambicloud.com/${specialInfo.uuid}.wav`
            ];
            try {
              const res = await fetch(`${SERVER_URL}/play`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                  url: mediaUrls[0],
                  media_urls: mediaUrls,
                  bambicloud: true,
                  bambicloud_type: "direct",
                  bambicloud_uuid: specialInfo.uuid,
                  bambicloud_audioOnly: true
                })
              });
              if (res.ok) {
                videoSent = true;
                console.log("[Bambi] Sent direct BambiCloud media candidates to desktop app");
                return;
              }
            } catch (err) {
              console.error("[Bambi] Error sending direct BambiCloud media:", err);
            }
          }
          handleDirectAudio(specialInfo);
          return;
        }

        const url = specialInfo.url;
        currentVideoUrl = url;
        console.log(`[Bambi] Bambicloud special page detected:`, url.substring(0, 80));

        const online = await checkServer();

        if (online) {
          let playUrl = specialInfo.url;
          let mediaUrls = [];
          if (specialInfo.uuid) {
            mediaUrls = [
              `https://cdn.bambicloud.com/${specialInfo.uuid}.mp3`,
              `https://cdn.bambicloud.com/${specialInfo.uuid}.wav`
            ];
            playUrl = mediaUrls[0];
          }
          try {
            const res = await fetch(`${SERVER_URL}/play`, {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                url: playUrl,
                media_urls: mediaUrls,
                bambicloud: true,
                bambicloud_type: specialInfo.type,
                bambicloud_uuid: specialInfo.uuid,
                bambicloud_visualSession: specialInfo.visualSession,
                bambicloud_audioOnly: specialInfo.audioOnly
              })
            });
            if (res.ok) {
              videoSent = true;
              console.log("[Bambi] ✅ Sent bambicloud request to desktop app");
              return;
            }
          } catch (err) {
            console.error("[Bambi] Error sending bambicloud request:", err);
          }
        }

        console.log("[Bambi] App offline - using bambicloud browser fallback");
        showBambicloudFallbackOverlay(specialInfo);
        return;
      }
    }

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
  const fullscreenEvents = ['fullscreenchange', 'mozfullscreenchange', 'webkitfullscreenchange', 'msfullscreenchange'];
  fullscreenEvents.forEach(event => {
    document.addEventListener(event, () => {
      const isFullscreen = document.fullscreenElement || document.mozFullScreenElement ||
                          document.webkitFullscreenElement || document.msFullscreenElement;
      if (!isFullscreen && fallbackActive) {
        exitFullscreenMode();
      }
    });
  });

  // Video ended
  document.addEventListener('ended', (e) => {
    if (fallbackActive && e.target === originalVideo) {
      const exitFullscreen = document.exitFullscreen || document.mozCancelFullScreen ||
                            document.webkitExitFullscreen || document.msExitFullscreen;
      if (exitFullscreen) {
        exitFullscreen.call(document);
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

  // Global dangerous key blocker
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