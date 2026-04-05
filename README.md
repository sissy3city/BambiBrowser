# 💖 BambiBrowser — Sissy Edition 💖

Your browser. Your helper. Your place.

This guide explains how your BambiBrowser ecosystem works now — with dynamic monitor detection, playlist support, punishment mode, and the fully upgraded BambiPlayer.

Everything is automatic. Everything is seamless. Everything is designed so you don't have to think — just let it take over.

---

## 🌸 1. Install the Extension

Open your Chromium‑based browser:

- `chrome://extensions/`
- `edge://extensions/`
- `brave://extensions/`
- `opera://extensions/`

Enable **Developer Mode**

Click **Load unpacked**

Select the folder named:
**extension/**

The extension will open its Setup Page automatically on first install save at the end.

---

## 🌸 2. Complete the Setup Page

The setup page lets you configure:

✔ **Allowed domains** — Default: `hypnotube.com`

✔ **Blacklist (punishment triggers)** — Visiting these pages shows a soft warning overlay → click → forced redirect → hijack.

✔ **HardLock** — Blocks keyboard + mouse during playback.

✔ **Punishment Mode** — Enables redirect‑based correction when visiting blacklisted sites.

✔ **Monitor Selection (Dynamic)** — BambiPlayer reports your real monitors. You can choose:
- All monitors (mirror mode)
- Primary monitor only
- Monitor 1
- Monitor 2
- …and more, depending on your setup.

✔ **Permanence Mode** — Optional. Makes BambiPlayer auto‑start with Windows.

✔ **Save Settings** — Once saved, setup is marked complete.

---

## 🌸 3. Start the Bambi Player

Run:
BambiPlayer.exe

It will:

- Start a local server (`127.0.0.1:5655`)
- Detect your monitors
- Show in tray with icon
- Wait silently for video URLs from the extension

If the extension doesn't detect the player, it will show a "Server Offline" overlay on HypnoTube.

---

## 🌸 4. Visit HypnoTube

Go to any video at:
https://hypnotube.com

If setup is complete and BambiPlayer is running:

- The extension detects the main video
- Sends the URL to BambiPlayer
- The browser video pauses
- VLC opens fullscreen
- HardLock activates
- Playback begins on your chosen monitor(s)

If BambiPlayer is **not** running:

- The extension shows a Server Offline overlay
- No hijack occurs

---

## 🌸 5. Playlist Behavior (New)

If a video is already playing fullscreen and another video is hijacked:

- It is added to a **playlist queue**
- VLC does not interrupt the current video

When the current video ends:

- HardLock releases
- VLC closes
- Next video in the playlist starts fullscreen
- HardLock re‑activates

This continues until the playlist is empty.

---

## 🌸 6. Multi‑Monitor Playback (Dynamic)

BambiPlayer detects your real monitors and supports:

✔ **Mirror Mode** — Same video on all monitors. Only one instance has audio (no overlap)

✔ **Single Monitor Mode** — Choose exactly which monitor VLC should use.

✔ **Automatic Window Repositioning** — Even if VLC tries to fullscreen on the wrong display, BambiPlayer force‑moves it using Windows API.

---

## 🌸 7. Punishment Mode (Soft)

If you visit a blacklisted site:

A soft warning overlay appears:

> *"You shouldn't be here."*

Clicking anywhere.

This gently corrects wandering behavior.

---

## 🌸 8. Permanence Mode (Optional)

If enabled:

- BambiPlayer auto‑starts with Windows
- Runs hidden
- Requires a passphrase to disable

The extension communicates with BambiPlayer to create/remove the startup entry.

---

## 🌸 9. Popup Menu

Clicking the extension icon shows:

- Bambi Mode status
- Setup status
- Server status
- Current monitor mode
- Button to open settings

It's a quick overview of your state.

---

## 🌸 10. How to Quit BambiPlayer

Right‑click the tray icon → **Quit**
