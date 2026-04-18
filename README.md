# 💖 BambiBrowser 💖

OMG, like, literally THE cutest Python-based media browser and player application with the most adorable browser extension support ever! We're talking AutoHotkey integration, FFmpeg transcoding, AND VLC playback capabilities - basically everything you could ever want and MORE! 🎉

## ✨ Features ✨

- **Desktop Application**: Like, a totally gorgeous Python GUI with an integrated media server that's SO smart! 💅
- **Browser Extension**: Chrome AND Firefox compatible extension that's literally SO seamless, babe! 
- **Media Detection**: Automatic detection of all the media content from the hottest websites (HyperboTube, SpankBang) - it just KNOWS! 👀
- **Local Server**: A super cute built-in server that handles all your media requests and streaming! Like, hello, efficiency! 
- **Media Player**: VLC-based playback with like, CRAZY advanced controls - talk about feature-rich, bestie! 🎬
- **AutoHotkey Integration**: System-level automation and hotkey support because we're THAT extra! 💋
- **FFmpeg Support**: Video transcoding and format conversion - basically like a makeover for your files! 💄
- **Settings Management**: Customizable configuration panel with persistent storage - save YOUR preferences, queen! 👑
- **Text Replacement**: Dynamic text replacement functionality that's literally genius! ✨
- **Auto-Updates**: Automatic update checking and installation - stay fresh and fabulous, always! 💫
- **OTP Support**: One-time password dialog for keeping your stuff super secure and protected! 🔐

## Project Structure

```
BambiBrowser/
├── bambi_browser.py          # Main application entry point
├── requirements.txt          # Python dependencies
├── VERSION                   # Version information
├── core/                     # Core Python modules
│   ├── ahk_downloader.py     # AutoHotkey installation
│   ├── ahk_generator.py      # AutoHotkey script generation
│   ├── auto_updater.py       # Update management
│   ├── ffmpeg_downloader.py  # FFmpeg setup
│   ├── player.py             # Media player controls
│   ├── server.py             # Local HTTP server
│   ├── settings_manager.py   # Configuration management
│   ├── text_replacer.py      # Text replacement engine
│   └── utils.py              # Utility functions
├── ui/                       # User interface components
│   ├── main_window.py        # Main application window
│   ├── settings_panel.py     # Settings interface
│   ├── tray_icon.py          # System tray integration
│   └── ...                   # Additional UI modules
├── extension/                # Browser extension
│   ├── manifest.json         # Chrome manifest
│   ├── manifest.firefox.json # Firefox manifest
│   ├── popup.html            # Extension popup UI
│   ├── popup.js              # Extension popup logic
│   ├── content.js            # Content script
│   ├── background.js         # Background service worker
│   └── detectors/            # Media site detectors
├── ahk/                      # AutoHotkey scripts and resources
├── ffmpeg/                   # FFmpeg binaries
├── vlc/                      # VLC player resources and plugins
└── resources/                # Static resources
```

## 💻 Requirements

Like, okay, so here's what you're gonna need to make BambiBrowser absolutely SLAY:

- Python 3.7+ (newer is like, SO much better, babe!)
- Windows OS (because AutoHotkey is obsessed with Windows, duh!) 
- FFmpeg (don't worry, we'll literally download it FOR you on first run! 💕)
- VLC libraries (bestie, they're already included - you're welcome!) 
- A modern web browser (Chrome, Firefox, or literally any Chromium-based cutie works!) 🌐

## 🎀 Installation

Okay bestie, it's like SUPER easy to get this hotness up and running! Follow these adorable little steps:

1. **Clone or download the repository** (literally just grab it!)
```bash
git clone https://github.com/yourusername/BambiBrowser.git
cd BambiBrowser
```

2. **Install Python dependencies** (this is gonna be SO good!)
```bash
pip install -r requirements.txt
```

3. **Install browser extension** (the fun part!)
   - **Chrome/Chromium**: Open `chrome://extensions/`, flip on "Developer mode" (we're not scared of developer mode!), and load the `extension/` folder like the tech goddess you are! 💃
   - **Firefox**: Open `about:debugging#/runtime/this-firefox`, click "Load Temporary Add-on", and change filename from `manifest.firefox.json` to `manifest.json` select it - easy peasy! 🦊

4. **Run the application** (moment of truth, honey!)
```bash
python bambi_browser.py
```

And like, that's literally IT! You're DONE! 🎉✨

## 💕 Usage

Like, okay, using BambiBrowser is literally the most fun thing EVER! Let us show you how fabulous this is:

### Desktop Application
- **Launch that gorgeous application** and watch the main window appear - like magic, but like, TECH magic! ✨
- **Configure settings in the Settings panel** - customize everything to match YOUR vibe, queen! 👑
- **Access even MORE options via the system tray icon** - it's like a secret menu of fabulousness! 🎭

### Browser Extension
- The extension like, AUTOMATICALLY detects all the hottest media sites - it's basically psychic! 🔮
- **Click the extension icon** to interact with the application like the tech-savvy babe you are!
- **Media content automatically gets forwarded to the player** - no manual labor required, bestie! 💁

### Settings
Like, there are SO many adorable things you can customize in three gorgeous tabs:
- **🎬 Playback Tab**: HardLock (total input control!), Click-Through mode, opacity, multi-monitor support, and volume control - basically everything to customize YOUR perfect playback experience! 🎮
- **⏱️ Safety Limits Tab**: Set max video length, queue duration limits, and choose what happens when limits are hit - safety first, bestie! 🛡️
- **🔄 Text Replacer Tab**: Create custom text replacement rules to totally personalize your experience! 💬

## ⚙️ Configuration

Like, your settings are stored in the application's configuration directory, and honestly, they're like the CUTEST settings ever! Key things you can tweak:

- **HardLock & Input Control** - lock down your keyboard and mouse, babe! 🔒
- **Opacity & Click-Through** - make the video transparent or click-through so you can peek at other stuff! 👻
- **Volume & Audio** - control your audio levels and mute other apps - who's the boss now? 🔊
- **Multi-Monitor Support** - spread that hotness across multiple displays! 🖥️
- **Safety Limits** - set max video length and queue duration for peace of mind! ⏱️
- **Text Replacer Rules** - customize the text replacement patterns to make it all about YOU! ✨

## 🆘 Troubleshooting (AKA: When Things Get Messy)

Like, sometimes things can be a little finicky, but don't worry babe, we got you! 💋

### Extension not detecting sites
- **Make sure the extension is like, ENABLED** in your browser - no shade but turn it ON, gurl! 🙄
- **Verify the local server is running** - check that adorable system tray icon! 
- **Check browser console for errors** - press F12 and look for the scary red messages (we promise they're not scary once you read them!)

### Media player issues
- **Verify VLC libraries are present** in the `vlc/` directory - they should be chilling there! 🎬
- **Check that FFmpeg is properly installed** - it auto-downloads on launch like a total sweetheart! 💕
- **Review application logs** - they'll literally tell you what's wrong! Like having a therapist for your code! 👨‍⚕️

### Server connection errors
- **Check your firewall settings** - sometimes it's just being overprotective! 🔥
- **Verify the configured server port is available** - make sure nothing else is using YOUR port, bestie!
- **Review server logs** in the application - they spill the tea on what went wrong! ☕

## ⚖️ License (The Boring But Necessary Part)

Okay so like, this project is built on the shoulders of GIANTS, and we gotta give them props! 👑

- **VLC**: Licensed under LGPL 2.1+ (see `vlc/COPYING.txt` - it's like THE ultimate team player!)
- **FFmpeg**: Licensed under LGPL 2.1+ (varies by codec - it's complicated, like a relationship status!)
- **AutoHotkey**: Licensed under GPL 2.0 (see `ahk/license.txt` - the OG automation tool!)

Like, seriously though, check out each component's license for the deets! We're all about respecting the legal stuff! 📋✨

## 🌟 Contributing (We WANT Your Fabulousness!)

Like, OMG, we literally LOVE contributions! You're basically a genius if you wanna help! 💖

Just follow these adorable little guidelines:

1. **Fork the repository** - make it YOUR thing, bestie! 👯
2. **Create a feature branch** - name it something cute like `feature/add-sparkles` ✨
3. **Make your changes** - work your magic, babe!
4. **Test thoroughly** - we're perfectionists here! 💅
5. **Submit a pull request** - show us what you got! 

Like, we promise we'll be nice in code review! Promise! 🤝

## 💬 Support

Like, need help? Got questions? Feature ideas? SPILL! ☕

Open an issue on the project repository and we'll literally get back to you like the awesome devs we are! We're here for you! 💕

---

**Version**: Check [VERSION](VERSION) file for like, the MOST current version number ever! 

**Made with 💋 and lots of ✨ by the Sissy3City ~ Bambi Lana!**

---

*P.S. - If you're still reading this, you're basically already obsessed! Welcome to the fam, babe! 👯‍♀️💖*
