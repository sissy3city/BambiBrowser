# 💖 BambiBrowser 💖

OMG, like, literally THE cutest Python-based media browser and player application with the most adorable browser extension support ever! We're talking **mpv** playback, **AutoHotkey** text replacement and gagging, **HardLock** input blocking, **FFmpeg** duration detection, and a super secure **OTP‑locked settings** panel – basically everything you could ever want and MORE! 🎉

---

## ✨ Features ✨

- **Desktop Application** – A gorgeous PyQt6 GUI with an integrated HTTP server that handles extension requests like a dream. 💅
- **Browser Extension** – Chrome **and** Firefox compatible! Automatically detects videos on supported sites and sends them to the app (with a browser fallback if the app is offline). 🌐
- **mpv‑Powered Playback** – Fast, hardware‑accelerated video player that supports **fullscreen**, **multi‑monitor**, **opacity**, **click‑through**, and **HardLock** input lockdown. 🎬
- **HardLock™** – System‑wide input blocking at the device level (keyboard, mouse, touch). Locks out **everything** during playback – no escape, bestie! 🔒
- **Audio Control** – Mute other applications automatically while your video plays, so you stay completely immersed. 🔊
- **Safety Limits** – Set a maximum video length and queue duration. Choose what happens when limits are hit: block, skip, stop playback, or just warn. Stay in control! ⏱️
- **OTP‑Protected Settings** – Lock your entire configuration with a 6‑digit BambiCode. No code? No changes. Perfect for keeping your settings safe from prying eyes. 🔐
- **OS‑Level Text Replacement** – Powered by AutoHotkey, this replaces any word you type system‑wide with your custom replacements. Comes with built‑in Bambi presets and fully editable rules. 📖
- **Bambi Gag™** – Another AutoHotkey gem! Gags your typed messages in Discord (and other apps) by transforming letters into cute syllable‑based gibberish. Can be toggled remotely via a URL or locally. 🔇
- **Auto‑Updater** – Checks GitHub for new releases, downloads, and installs them with a single click. Stay fresh and fabulous! 💫
- **Auto‑Elevation** – Requests Administrator rights on Windows so HardLock and AutoHotkey work flawlessly. 🛡️
- **System Tray** – Runs quietly in the background with a handy tray menu to show/hide the main window or quit.

---

## 📁 Project Structure

```
BambiBrowser/
├── bambi_browser.pyw         # Main entry point
├── requirements.txt          # Python dependencies
├── VERSION                   # Version info
├── core/                     # Backend modules
│   ├── ahk_manager.py        # AutoHotkey download & script management
│   ├── audio_muter.py        # System audio muting via pycaw
│   ├── auto_updater.py       # GitHub update checker & installer
│   ├── duration_helper.py    # Video duration detection (ffprobe, VLC, headers)
│   ├── ffmpeg_downloader.py  # Downloads ffprobe for accurate duration
│   ├── gag_manager.py        # Bambi Gag – AutoHotkey‑based text gagging
│   ├── hard_lock.py          # System‑wide input blocker
│   ├── player.py             # mpv‑based video player with multi‑screen
│   ├── server.py             # HTTP server for extension communication
│   ├── settings_manager.py   # Central settings with OTP lock
│   ├── text_replacer.py      # OS‑level text replacement (AutoHotkey)
│   └── utils.py              # Base path, logging setup
├── ui/                       # PyQt6 UI components
│   ├── main_window.py        # Main application window
│   ├── settings_panel.py     # Unified settings (Playback, Safety, TextReplacer, Gag)
│   ├── otp_dialog.py         # OTP lock/unlock dialog
│   ├── tray_icon.py          # System tray integration
│   ├── update_dialog.py      # Update notification & progress
│   └── styles.py             # Dark theme QSS
├── extension/                # Browser extension (Chrome & Firefox)
│   ├── manifest.json         # Chrome manifest (v3)
│   ├── manifest.firefox.json # Firefox manifest (rename to use)
│   ├── background.js         # Service worker / background script
│   ├── content.js            # Main content script (video detection & fallback)
│   ├── popup.html            # Extension popup UI
│   ├── popup.js              # Popup logic (enable/disable, server status)
│   └── detectors/            # Site‑specific video detectors
│       └── hypnotube.js      # Hypnotube.com detector
├── ahk/                      # AutoHotkey binaries (auto‑downloaded if missing)
├── ffmpeg/                   # ffprobe binary (auto‑downloaded if missing)
├── mpv/                      # mpv player binaries (bundled or system)
└── resources/                # Icons and static assets
```

---

## 💻 Requirements

- **Windows** (7, 10, 11 – because AutoHotkey and HardLock are Windows‑native)
- **Python 3.7+** (newer is better, babe!)
- **mpv** – bundled with the app (or you can provide your own)
- **AutoHotkey** – auto‑downloaded on first use (or you can install it manually)
- **FFmpeg** – auto‑downloads `ffprobe` for accurate video duration detection
- A modern web browser (Chrome, Firefox, Edge, etc.)

---

## 🎀 Installation

1. **Clone or download the repository**  
   ```bash
   git clone https://github.com/sissy3city/BambiBrowser.git
   cd BambiBrowser
   ```

2. **Install Python dependencies**  
   ```bash
   pip install -r requirements.txt
   ```

3. **Install the browser extension**  
   - **Chrome/Chromium**:  
     - Open `chrome://extensions/`  
     - Enable **Developer mode**  
     - Click **Load unpacked** and select the `extension/` folder.  
   - **Firefox**:  
     - Open `about:debugging#/runtime/this-firefox`  
     - Click **Load Temporary Add‑on**  
     - Select any file inside the `extension/` folder (or rename `manifest.firefox.json` to `manifest.json` and load the folder).  

4. **Run the application**  
   ```bash
   python bambi_browser.pyw
   ```  
   The app will request Administrator rights (if needed) and start with a system tray icon.

---

## 💕 Usage

### Desktop Application

- The main window opens with **three tabs**:
  1. **🎬 Bambi Player** – Playback settings (HardLock, opacity, click‑through, multi‑monitor, volume, audio muting) and **Safety Limits** (max video length, queue duration).
  2. **📖 Bambi Dictionary** – Enable OS‑level text replacement, manage your replacement rules, import/export presets.
  3. **🔇 Bambi Gag** – Enable the gag, set a remote URL for toggling, or use local toggle.

- **Lock your settings** with a 6‑digit BambiCode by clicking the **💾 Save & Lock Settings** button at the bottom. Once locked, no changes can be made without entering the code.

- The **system tray icon** lets you show/hide the window or quit the app.

### Browser Extension

- Navigate to a supported site (e.g., `hypnotube.com`).
- The extension **automatically detects** the main video and attempts to send it to the desktop app.
- If the app is **online**, the video will play in fullscreen mpv with all your settings (HardLock, etc.).
- If the app is **offline**, the extension falls back to **browser fullscreen** with keyboard blocking (limited HardLock) – so you’re never stuck!

- Click the extension icon to see the connection status and toggle the extension on/off.

---

## ⚙️ Configuration

All settings are stored in `QSettings` (Windows Registry) and can be locked with an OTP. Key settings include:

| Category          | Setting                          | Description                                                                 |
|-------------------|----------------------------------|-----------------------------------------------------------------------------|
| **Playback**      | HardLock                         | Blocks all system input during playback.                                   |
|                   | Click‑Through                    | Makes the video window transparent and click‑through.                      |
|                   | Opacity                          | Transparency level (10–100%) when click‑through is on.                     |
|                   | Multi‑Monitor                    | Play video across multiple screens.                                        |
|                   | Mute Other Audio                 | Mutes all other applications during playback (pycaw).                      |
|                   | Volume                           | Master volume (0–256).                                                     |
| **Safety**        | Max Video Length                 | Enforce a maximum video duration (5–120 min). Action: Block, Stop, Skip, Warn. |
|                   | Max Queue Duration               | Limit total queue time (30–600 min). Action: Reject, Stop, Clear, Warn.    |
| **Text Replacer** | Enable / Disable                 | Turns OS‑level text replacement on/off.                                    |
|                   | Rules                            | Custom trigger → replacement pairs.                                        |
|                   | Presets                          | Quick‑load Bambi L1, L2, L3 presets.                                       |
|                   | Import / Export                  | JSON files.                                                                |
| **Gag**           | Enable / Disable                 | Turns Bambi Gag on/off.                                                    |
|                   | Remote URL                       | A URL (Dropbox, etc.) containing `ON` or `OFF` toggles the gag remotely.   |
|                   | Local Toggle                     | Overrides remote when no URL is set.                                       |

---

## 🆘 Troubleshooting

### Extension not detecting videos
- Ensure the extension is **enabled** (toggle in popup).
- Make sure the desktop app is **running** (check system tray).
- Open the browser console (F12) for any error messages.

### Playback issues
- Verify that `mpv.exe` is in the `mpv/` folder (or in `PATH`).
- Check that `ffprobe.exe` is available (auto‑downloads on first launch) – used for duration detection.
- Review the log file `bambi_browser.log` in the application directory.

### Server connection errors
- Port `5655` might be blocked by your firewall. Add an exception.
- Ensure no other application is using port `5655`.
- The server runs on `127.0.0.1` – it’s local only.

### Text Replacer or Gag not working
- AutoHotkey must be installed. The app will attempt to download it automatically to the `ahk/` folder. If that fails, install AutoHotkey manually from [autohotkey.com](https://www.autohotkey.com/).
- Run the app as Administrator – AutoHotkey works better with elevated privileges.

---

## ⚖️ License

BambiBrowser is built on the shoulders of **amazing open‑source projects**. We love and respect their licenses!

- **mpv** – Licensed under GPLv2+ ([mpv.io](https://mpv.io/))
- **AutoHotkey** – Licensed under GPLv2+ ([autohotkey.com](https://www.autohotkey.com/))
- **FFmpeg** – Licensed under LGPLv2.1+ (components vary by codec) ([ffmpeg.org](http://ffmpeg.org/))
- **PyQt6** – Licensed under GPLv3 (Riverbank Computing)
- **python-mpv** – Licensed under MIT
- **pycaw** – Licensed under BSD‑3‑Clause

This project itself is released under the **MIT License** – see [LICENSE](LICENSE) for details.

---

## 🌟 Contributing

We **adore** contributions! Whether it’s a bug fix, a new feature, or a pretty icon – we want it! 💖

1. **Fork** the repository.
2. Create a **feature branch** (`git checkout -b feature/amazing-idea`).
3. **Commit** your changes (`git commit -m 'Add some amazingness'`).
4. **Push** to the branch (`git push origin feature/amazing-idea`).
5. Open a **Pull Request** and tell us all about it!

We promise to be gentle in code review. 🤗

---

## 💬 Support

Have a question? Found a bug? Want to request a new site detector?  
**Open an issue** on the GitHub repository and we’ll get back to you as soon as we can!

---

**Made with 💋 and lots of ✨ by the Sissy3City ~ Bambi Lana!**

---

*P.S. – If you’re reading this, you’re already part of the fam. Welcome, bestie! 👯‍♀️💖*