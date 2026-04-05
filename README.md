# 👻 App Guardian

> A macOS menu-bar app that automatically closes inactive applications and cleans up their caches — powered by Apple's on-device AI.

![macOS](https://img.shields.io/badge/macOS-26%2B-black?style=flat-square&logo=apple)
![Python](https://img.shields.io/badge/Python-3.11%2B-blue?style=flat-square&logo=python)
![License](https://img.shields.io/badge/license-MIT-green?style=flat-square)
![Status](https://img.shields.io/badge/status-active-brightgreen?style=flat-square)

---

## What it does

Your Mac accumulates open apps you forgot about. App Guardian silently watches which app you're using, and after a configurable idle period it asks Apple's on-device AI whether the app is safe to close — then quits it and cleans its cache directory.

**No cloud. No API keys. Runs entirely on your machine.**

---

## Features

- 🕵️ **Passive monitoring** — polls the frontmost app every 10 seconds; zero performance impact
- 🤖 **Apple Intelligence decisions** — uses [apfel](https://github.com/Arthur-Ficial/apfel) to ask Apple's Foundation Model whether an app should be closed (skippable)
- 🧹 **Cache cleanup** — deletes `~/Library/Caches/<bundle-id>` after each close
- 🚫 **Exclusion list** — protect any app from ever being touched
- ⏱ **Configurable timeout** — default 30 min, change it in the menu
- 💀 **Force-quit fallback** — graceful quit first; force-kills if the app doesn't respond in 10 s
- 📈 **Statistics screen** — today / 7-day / all-time closes and cache freed, top closed apps
- 📋 **Persistent log** — every action written to `~/.config/app-guardian/guardian.log`
- 🟢 **Coloured menu-bar icon** — custom green ghost, always visible

---

## Requirements

| Requirement | Notes |
|---|---|
| macOS 26 (Tahoe) | Required for Apple Intelligence via apfel |
| Apple Silicon | M1 or later |
| Python 3.11+ | `brew install python` |
| [apfel](https://github.com/Arthur-Ficial/apfel) | Optional — disable in menu if not installed |

> **No apfel?** The app works fine without it. Toggle off "Use Apple Intelligence" in the menu and it will close all idle apps that aren't on the exclusion list.

---

## Installation

### Homebrew (easiest)

```bash
brew tap TomGranot/tap
brew install app-guardian
brew services start app-guardian
```

### From source

```bash
# 1. Clone
git clone https://github.com/TomGranot/app-guardian.git
cd app-guardian

# 2. Install apfel (optional but recommended)
brew tap Arthur-Ficial/tap && brew install apfel

# 3. Install Python dependencies
./setup.sh

# 4. Run
./run.sh
```

### Auto-start on login

```bash
./install-agent.sh
```

This installs a LaunchAgent that starts App Guardian on login and restarts it if it crashes.

To uninstall:
```bash
launchctl unload ~/Library/LaunchAgents/com.appguardian.menubar.plist
rm ~/Library/LaunchAgents/com.appguardian.menubar.plist
```

---

## Usage

Click the 👻 icon in your menu bar:

| Menu item | What it does |
|---|---|
| ● Monitoring ON | Toggle monitoring on/off |
| 📊 N apps tracked | Click to see idle times for all tracked apps |
| ⏱ Timeout: 30 min | Set the inactivity threshold |
| 🚫 Excluded Apps… | Edit the list of apps that are never closed |
| ✅ Use Apple Intelligence | Toggle apfel AI decisions on/off |
| ✅ Clean cache on close | Toggle cache cleanup on/off |
| 🧹 Clean All Caches Now | One-shot cache clean for all running apps |
| 📈 Statistics… | View close history and cache savings |
| 📋 View Log | Open the log in Console.app |

---

## How Apple Intelligence is used

When an app has been idle past the timeout, App Guardian sends a one-sentence prompt to the local Foundation Model:

```
macOS app: 'Slack'  Idle: 45 min  RAM: 312 MB

Should this app be auto-quit when idle?
Reply with exactly one word — YES or NO.
```

The model's YES/NO answer is **cached for the session** so it only calls the model once per app. If apfel is unreachable, the app defaults to closing.

---

## Configuration

Settings are stored at `~/.config/app-guardian/config.json`:

```json
{
  "enabled": true,
  "timeout_minutes": 30,
  "excluded_apps": ["Finder", "Dock", "Siri", "..."],
  "apfel_url": "http://localhost:11434/v1",
  "use_apfel": true,
  "clean_cache": true,
  "force_quit_timeout": 10
}
```

---

## Data & Privacy

- Everything runs **locally** — no network requests except to `localhost:11434` (apfel)
- History is stored at `~/.config/app-guardian/history.json` (never uploaded anywhere)
- No telemetry, no analytics, no accounts

---

## Contributing

PRs welcome. Open an issue first for anything beyond a small fix.

```bash
git clone https://github.com/TomGranot/app-guardian.git
cd app-guardian && ./setup.sh
python app_guardian.py   # runs directly for development
```

---

## License

MIT — see [LICENSE](LICENSE).
