# 💖 BambiBrowser 💖

OMG, like, literally THE cutest Python-based media browser and player application with the most adorable browser extension support ever! We're talking **mpv** playback, **AutoHotkey** text replacement and gagging, **HardLock** input blocking, **FFmpeg** duration detection, and a super secure **OTP‑locked settings** panel – basically everything you could ever want and MORE! 🎉

---

## ✨ Features ✨

- **Desktop Application** – A gorgeous PyQt6 GUI with an integrated HTTP server that handles extension requests like a dream. 💅
- **Browser Extension** – Chrome **and** Firefox compatible! Automatically detects videos on supported sites and sends them to the app (with a browser fallback if the app is offline). 🌐
- **BambiCloud Support** – Detects BambiCloud UUID media links, tests MP3/WAV candidates, and plays the first valid direct CDN file through mpv. ☁️
- **mpv‑Powered Playback** – Fast, hardware‑accelerated video player that supports **fullscreen**, **multi‑monitor**, **opacity**, **click‑through**, and **HardLock** input lockdown. 🎬
- **BambiCloud Countdown and Visuals** – Optional countdown from 5 seconds to 5 minutes, followed by a fullscreen spiral during BambiCloud audio playback. 🔢
- **Custom BambiCloud Animation** – Select a local GIF or video file and play it muted in a fullscreen infinite loop. 🖼️
- **BambiCloud Color Presets** – Neon, pastel, dark, or custom hex colors for the BambiCloud spiral bands and outlines. 🎨
- **HardLock™** – System‑wide input blocking at the device level (keyboard, mouse, touch). Locks out **everything** during playback – no escape, bestie! 🔒
- **Audio Control** – Mute other applications automatically while your video plays, so you stay completely immersed. 🔊
- **Safety Limits** – Set a maximum video length and queue duration. Choose what happens when limits are hit: block, skip, stop playback, or just warn. Stay in control! ⏱️
- **OTP‑Protected Settings** – Lock your entire configuration with a 6‑digit BambiCode. No code? No changes. Perfect for keeping your settings safe from prying eyes. 🔐
- **OS‑Level Text Replacement** – Powered by AutoHotkey, this replaces any word you type system‑wide with your custom replacements. Comes with built‑in Bambi presets and fully editable rules. 📖
- **Bambi Gag** – Another AutoHotkey gem! Gags your typed messages in Discord (and other apps) by transforming letters into cute syllable‑based gibberish. Can be toggled remotely via a URL or locally. 🔇
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
├── core/                     # Backend modules (cross-platform + platform dispatchers)
│   ├── audio_muter.py        # Dispatcher -> windows/audio_muter_windows.py or linux/audio_muter_linux.py
│   ├── auto_updater.py       # GitHub update checker & installer
│   ├── autostart.py          # Start-at-login registration (Registry on Windows, .desktop on Linux)
│   ├── diagnostics.py        # "Run Diagnostics" checks + manual checks (audio tone/noise player, keyboard-layout preview & override)
│   ├── duration_helper.py    # Video duration detection (ffprobe, VLC, headers)
│   ├── ffmpeg_downloader.py  # Downloads ffprobe (Windows only; Linux uses the system package)
│   ├── gag_manager.py        # Bambi Gag - AutoHotkey on Windows, evdev/uinput on Linux
│   ├── hard_lock.py          # Dispatcher -> windows/hard_lock_windows.py or linux/hard_lock_linux.py
│   ├── player.py             # mpv‑based video player with multi‑screen, queue, BambiCloud overlays
│   ├── server.py             # HTTP server for extension communication
│   ├── settings_manager.py   # Central settings with OTP lock
│   ├── text_replacer.py      # OS‑level text replacement - AutoHotkey on Windows, native engine on Linux
│   ├── utils.py              # Base path, logging setup
│   ├── window_manager.py     # Dispatcher -> windows/window_manager_windows.py or linux/window_manager_linux.py
│   ├── windows/               # Windows-only implementations
│   │   ├── ahk_downloader.py  # AutoHotkey download/extraction
│   │   ├── ahk_generator.py   # AutoHotkey script generation
│   │   ├── ahk_manager.py     # AutoHotkey process management
│   │   ├── audio_muter_windows.py    # pycaw-based audio muting
│   │   ├── hard_lock_windows.py      # Driver-level keyboard disable + BlockInput + low-level hook
│   │   └── window_manager_windows.py # win32gui opacity/click-through/topmost
│   └── linux/                 # Linux-only implementations
│       ├── _uinput_compat.py       # uinput compatibility shim
│       ├── audio_muter_linux.py    # pactl/wpctl (PipeWire) audio muting
│       ├── hard_lock_linux.py      # Exclusive evdev device grab
│       ├── linux_gag_engine.py     # evdev/uinput-based Bambi Gag
│       ├── linux_keymap.py         # xkbcommon keyboard layout mapping
│       ├── linux_text_replacer.py  # evdev/uinput-based text replacement
│       └── window_manager_linux.py # xdotool/wmctrl/python-xlib opacity/click-through/topmost (XWayland)
├── ui/                       # PyQt6 UI components
│   ├── main_window.py        # Main application window
│   ├── settings_panel.py     # Unified settings (General, Playback, BambiCloud, Safety, TextReplacer, Gag)
│   ├── otp_dialog.py         # OTP lock/unlock dialog
│   ├── tray_icon.py          # System tray integration
│   ├── update_dialog.py      # Update notification & progress
│   └── styles.py             # Dark theme QSS
├── extension/                # Browser extension (Chrome & Firefox)
│   ├── manifest.json         # Chrome manifest (v3)
│   ├── manifest.firefox.json # Firefox manifest (v3, rename to use)
│   ├── background.js         # Service worker / background script
│   ├── content.js            # Main content script (video detection & fallback)
│   ├── popup.html            # Extension popup UI
│   ├── popup.js              # Popup logic (enable/disable, server status)
│   └── detectors/            # Site‑specific video detectors
│       ├── hypnotube.js      # Hypnotube.com detector
│       ├── bambicloud.js     # BambiCloud.com detector
│       └── spankbang.js      # Spankbang.com detector
├── ahk/                      # AutoHotkey binaries (Windows, auto‑downloaded if missing)
├── ffmpeg/                   # ffprobe binary (Windows, auto‑downloaded if missing)
├── mpv/                      # mpv player binaries (bundled on Windows, system package on Linux)
└── resources/                # Icons and static assets
```

---

## 💻 Requirements

BambiBrowser runs on **Windows** and **Linux** (developed/tested on Fedora KDE Plasma).

- **Python 3.9+**
- **mpv** – bundled on Windows; on Linux, install via your package manager
- **Qt Multimedia** – included through PyQt6, used for the BambiCloud custom GIF/video animation
- **A modern web browser** (Chrome, Firefox, Edge, etc.)

**Windows-specific:** AutoHotkey (auto-downloaded on first use) and HardLock use Windows-native APIs (BlockInput, low-level keyboard hooks, driver-level device disable).

**Linux-specific:** HardLock uses an exclusive `python-evdev` device grab, audio muting uses `pactl`/`wpctl` (PipeWire), window opacity/click-through/topmost use `xdotool`/`wmctrl`/`python-xlib` against an XWayland window, and the text replacer's keystroke matching goes through `libxkbcommon` (via the `xkbcommon` pip package, already in `requirements.txt`) so it correctly reads whatever keyboard layout you actually have configured (US, German, French, ...) instead of assuming US QWERTY. Install system packages first:

```bash
sudo dnf install mpv ffmpeg ffmpeg-libs python3-evdev python3-xlib wmctrl xdotool ydotool pipewire-utils xorg-x11-server-utils
```

> `xorg-x11-server-utils` provides `setxkbmap`, used to detect your active keyboard layout via XWayland. `libxkbcommon` itself is almost always already present (every X11/Wayland desktop depends on it); if the "Keyboard layout (xkbcommon)" diagnostics check fails, install it explicitly with `sudo dnf install libxkbcommon`.

> `ffmpeg`/`ffmpeg-libs` require [RPM Fusion](https://rpmfusion.org/) enabled — stock Fedora repos only ship `ffmpeg-free`, which lacks some codecs.
>
> **If that fails with a conflict** between `ffmpeg-free`/`libswscale-free` (stock Fedora) and `ffmpeg`/`libswscale` (RPM Fusion) — a common one-time gotcha on Fedora, not specific to this app — swap the free build for the full one first, then retry:
> ```bash
> sudo dnf swap ffmpeg-free ffmpeg --allowerasing
> sudo dnf install mpv python3-evdev python3-xlib wmctrl xdotool ydotool pipewire-utils xorg-x11-server-utils
> ```

For HardLock and text replacement/gag to grab input devices, your user needs access to `/dev/input/event*`:

```bash
sudo usermod -aG input $USER
# then log out and back in
```

> **Wayland note:** BambiBrowser's window opacity, click-through, and always-on-top tricks only work against an X11/XWayland window — Wayland's security model doesn't allow one app to inspect or restyle another app's window. On a Fedora KDE Plasma **Wayland** session, mpv still creates an XWayland window by default (no code changes needed), so these features work as long as XWayland is available. If you run a pure Wayland compositor with no XWayland, those specific features degrade gracefully (logged, not fatal) while playback itself keeps working.

> **BambiCloud custom animation on Linux:** a custom GIF plays fine everywhere (Qt's own `QMovie`, no extra backend needed). A custom **video** file goes through Qt Multimedia, which on Linux needs a GStreamer backend (e.g. `sudo dnf install gstreamer1-plugins-good gstreamer1-plugins-bad-free gstreamer1-libav`) — without it, `QMediaPlayer` silently fails to play the file at runtime rather than at import time. This hasn't been exercised on Linux yet; if it doesn't work, use a GIF or the built-in spiral instead.

---

## 🎀 Installation

1. **Clone or download the repository**  
   ```bash
   git clone https://github.com/sissy3city/BambiBrowser.git
   cd BambiBrowser
   ```

2. **(Linux only) Install system packages and add yourself to the `input` group** — see Requirements above.

3. **Install Python dependencies**  
   ```bash
   pip install -r requirements.txt
   ```

4. **Install the browser extension**  
   - **Chrome/Chromium**:  
     - Open `chrome://extensions/`  
     - Enable **Developer mode**  
     - Click **Load unpacked** and select the `extension/` folder.  
   - **Firefox**:  
     - Open `about:debugging#/runtime/this-firefox`  
     - Click **Load Temporary Add‑on**  
     - Select any file inside the `extension/` folder (or rename `manifest.firefox.json` to `manifest.json` and load the folder).  

5. **Run the application**  
   ```bash
   python bambi_browser.pyw
   ```  
   On Windows, the app will request Administrator rights (if needed). On Linux, no elevation is used or needed — HardLock/input access instead depends on `input` group membership (see Requirements). The app starts with a system tray icon either way.

### Standalone Windows Build

The repository includes a PyInstaller spec that bundles the desktop application, mpv, AutoHotkey, FFmpeg, resources, and Qt Multimedia support:

```powershell
.\.venv\Scripts\python.exe -m PyInstaller --clean --noconfirm bambi_browser.spec
```

The standalone application is created under `dist\bambi_browser\bambi_browser.exe`. Keep the bundled `mpv`, `ahk`, `ffmpeg`, and `resources` folders beside the executable. User-selected BambiCloud custom animation files remain external and are selected at runtime. This packaged build is Windows-only; run Linux from source per the steps above.

---

## 💕 Usage

### Desktop Application

- The main window opens with **four tabs**:
  1. **⚙️ General** – Start-at-login toggle, a "Run Diagnostics" check (mpv/evdev/xdotool, permissions, HardLock, per-monitor windows), and **Manual checks** for inspecting one subsystem on demand:
     - **🎧 Audio check** – opens a small windowed (non-fullscreen) player showing a test pattern and playing a 440 Hz tone or static noise, shows the current output device and volume, and lets you switch the output device or change the volume (and save it as the Bambi Player volume) on the spot.
     - **⌨️ Keyboard layout check** – shows the keyboard layout the Bambi Dictionary auto-detected, previews what each physical key would type (normal / with Shift) under any layout you pick, and lets you **force a specific layout + variant** when detection is wrong (e.g. a pure-Wayland session with no XWayland to query). The forced layout is saved and used by the text replacer; if it's running it reloads immediately.
  2. **🎬 Bambi Player** – Playback settings (HardLock, opacity, click‑through, multi‑monitor, volume, audio muting), **Safety Limits** (max single file length, queue duration), and **BambiCloud** (countdown, spiral/custom animation, color scheme).
  3. **📖 Bambi Dictionary** – Enable OS‑level text replacement, manage your replacement rules, import/export presets.
  4. **🔇 Bambi Gag** – Enable the gag, set a remote URL for toggling, or use local toggle.

- **Lock your settings** with a 6‑digit BambiCode by clicking the **💾 Save & Lock Settings** button at the bottom. Once locked, no changes can be made without entering the code.

- The **system tray icon** lets you show/hide the window or quit the app.

### Browser Extension

- Navigate to a supported site (e.g., `hypnotube.com`).
- The extension **automatically detects** the main video and attempts to send it to the desktop app.
- If the app is **online**, the video will play in fullscreen mpv with all your settings (HardLock, etc.).
- If the app is **offline**, the extension falls back to **browser fullscreen** with keyboard blocking (limited HardLock) – so you’re never stuck!

- Click the extension icon to see the connection status and toggle the extension on/off.

- On BambiCloud, the extension extracts the UUID and sends MP3/WAV CDN candidates to the desktop app. The app validates each candidate and uses the first available audio file.

---

## ⚙️ Configuration

All settings are stored via `QSettings` and can be locked with an OTP — on Windows this is the Registry (`HKEY_CURRENT_USER`), on Linux it's an INI file at `~/.config/BambiBrowser/Settings.conf`. Key settings include:

| Category          | Setting                          | Description                                                                 |
|-------------------|----------------------------------|-----------------------------------------------------------------------------|
| **Playback**      | HardLock                         | Blocks all system input during playback.                                   |
|                   | Click‑Through                    | Makes the video window transparent and click‑through.                      |
|                   | Opacity                          | Transparency level (10–100%) when click‑through is on.                     |
|                   | Multi‑Monitor                    | Play video across multiple screens.                                        |
|                   | Mute Other Audio                 | Mutes all other applications during playback (pycaw).                      |
|                   | Volume                           | Master volume (0–256).                                                     |
| **Safety**        | Max Single File Length           | Enforce a maximum media duration (5–120 min) for Hypnotube and BambiCloud. Action: Block, Stop, Skip, Warn. |
|                   | Max Queue Duration               | Limit total queue time (30–600 min). Action: Reject, Stop, Clear, Warn.    |
| **BambiCloud**    | Countdown                        | Optional 5-second to 5-minute preparation countdown for all supported sessions. |
|                   | Animation                        | Spiral, none, or a local GIF/video in a muted fullscreen loop.              |
|                   | Color Scheme                     | Changes the BambiCloud spiral band and outline colors; presets or custom hex colors are available. |
| **Text Replacer** | Enable / Disable                 | Turns OS‑level text replacement on/off.                                    |
|                   | Rules                            | Custom trigger → replacement pairs.                                        |
|                   | Presets                          | Quick‑load Bambi L1, L2, L3 presets.                                       |
|                   | Import / Export                  | JSON files.                                                                |
| **Gag**           | Enable / Disable                 | Turns Bambi Gag on/off.                                                    |
|                   | Remote URL                       | A URL (Notepad.cc, txt.fyi etc.) containing `ON` or `OFF` toggles the gag remotely.   |
|                   | Local Toggle                     | Overrides remote when no URL is set.                                       |

---

## 🆘 Troubleshooting

### Extension not detecting videos
- Ensure the extension is **enabled** (toggle in popup).
- Make sure the desktop app is **running** (check system tray).
- Open the browser console (F12) for any error messages.

### Playback issues
- **Windows:** Verify that `mpv.exe` is in the `mpv/` folder (or in `PATH`).
- **Linux:** Verify `mpv` is installed and on `PATH` (`dnf install mpv`).
- Check that `ffprobe` is available – used for duration detection (Windows auto-downloads it; Linux needs `dnf install ffmpeg` with RPM Fusion enabled).
- Review the log file `bambi_browser.log` in the application directory.
- **Linux:** opacity/click-through/topmost require an XWayland window for mpv — see the Wayland note under Requirements. If mpv ends up as a native Wayland surface with no XWayland, only those specific effects are unavailable; playback itself is unaffected.
- For BambiCloud, verify the UUID's CDN MP3/WAV file exists. The server logs the selected URL and skips unavailable candidates.

### Standalone build issues
- Build with the project virtual environment so PyQt6 Multimedia and PyInstaller use the same interpreter.
- The standalone build still requires Windows and a working display/audio device.
- Run the executable from its extracted folder so bundled `mpv`, `ahk`, `ffmpeg`, and `resources` paths remain available.

### Server connection errors
- Port `5655` might be blocked by your firewall. Add an exception.
- Ensure no other application is using port `5655`.
- The server runs on `127.0.0.1` – it’s local only.

### Text Replacer or Gag not working
- **Windows:** AutoHotkey must be installed. The app will attempt to download it automatically to the `ahk/` folder. If that fails, install AutoHotkey manually from [autohotkey.com](https://www.autohotkey.com/). Run the app as Administrator for best results.
- **Linux:** these features use an evdev device grab + virtual-input injection instead of AutoHotkey. Make sure `python3-evdev` is installed and your user is in the `input` group (see Requirements). If devices fail to grab, check the app log for a permission error and the group/udev instructions it prints. This is a from-scratch Linux implementation and has a smaller reliability envelope than the Windows AutoHotkey version, especially around detecting which window has focus (Bambi Gag).
- **Linux, wrong/non-US keyboard layout:** the text replacer detects your active layout via `xkbcommon`/`setxkbmap` at startup and matches keystrokes through it, so non-US layouts (German, French, etc.) should work automatically. Run the diagnostics check to confirm what got detected ("Keyboard layout (xkbcommon)"); if it says "couldn't detect layout" it's silently falling back to US, which will misfire on non-US layouts. If detection is wrong, use **General → Manual checks → ⌨️ Keyboard layout check** to preview what the keys produce and **force the correct layout + variant** — the override is saved and used from then on. Note the layout (detected or forced) is read when the text replacer starts — switching layouts at runtime (e.g. via a KDE layout-switcher applet) requires restarting the text replacer (or the app), or re-applying from the keyboard check, to pick up the change.

### HardLock not blocking input (Linux)
- Confirm `python3-evdev` is installed and your user is in the `input` group (`groups $USER`), then log out/in after adding yourself.
- Check the app log for `grabbed_device_count` in the HardLock status — `0` means no devices could be opened, usually a permissions issue.

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
