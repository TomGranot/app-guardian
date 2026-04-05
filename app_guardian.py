#!/usr/bin/env python3
"""
App Guardian — macOS menu-bar app that auto-closes inactive apps.

• Polls the frontmost app every N seconds to track last-active time.
• Periodically checks all running apps; idle ones past the threshold
  are sent to Apple's on-device Foundation Model (via apfel) for a
  YES/NO close decision (skippable).
• Graceful quit first, force-quit if the app doesn't respond.
• Cleans ~/Library/Caches/<bundle> after each close.

Requires: apfel running  →  `apfel --serve`
Install:  brew tap Arthur-Ficial/tap && brew install apfel
"""

import rumps
import time
import json
import os
import shutil
import threading
import subprocess
from datetime import datetime
from AppKit import NSWorkspace

# ── Config ────────────────────────────────────────────────────────────────────

CONFIG_DIR    = os.path.expanduser("~/.config/app-guardian")
CONFIG_FILE   = os.path.join(CONFIG_DIR, "config.json")
LOG_FILE      = os.path.join(CONFIG_DIR, "guardian.log")
HISTORY_FILE  = os.path.join(CONFIG_DIR, "history.json")

SYSTEM_DEFAULTS = {
    "Finder", "Dock", "SystemUIServer", "loginwindow", "WindowServer",
    "Spotlight", "NotificationCenter", "Control Center", "AirPlayUIAgent",
    "ControlStrip", "TextInputMenuAgent", "Siri", "System Preferences",
    "System Settings", "App Guardian", "Activity Monitor",
}

DEFAULT_CFG = {
    "enabled":           True,
    "timeout_minutes":   30,
    "check_interval":    60,    # seconds between idle checks
    "poll_interval":     10,    # seconds between frontmost-app polls
    "excluded_apps":     sorted(SYSTEM_DEFAULTS),
    "apfel_url":         "http://localhost:11434/v1",
    "use_apfel":         True,
    "clean_cache":       True,
    "force_quit_timeout": 10,   # seconds to wait before force-quit
}


def cfg_load():
    os.makedirs(CONFIG_DIR, exist_ok=True)
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE) as f:
                return {**DEFAULT_CFG, **json.load(f)}
        except Exception:
            pass
    cfg_save(DEFAULT_CFG)
    return DEFAULT_CFG.copy()


def cfg_save(c):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(c, f, indent=2)


# ── Logging ───────────────────────────────────────────────────────────────────

def log(msg):
    ts   = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    try:
        with open(LOG_FILE, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


# ── Persistent History ────────────────────────────────────────────────────────

def history_append(entry: dict):
    """Append one close event to the persistent JSON history log."""
    os.makedirs(CONFIG_DIR, exist_ok=True)
    records = history_load()
    records.append(entry)
    # Keep at most 10 000 entries to prevent unbounded growth
    if len(records) > 10_000:
        records = records[-10_000:]
    try:
        with open(HISTORY_FILE, "w") as f:
            json.dump(records, f, indent=2)
    except Exception as e:
        log(f"history write error: {e}")


def history_load() -> list[dict]:
    if not os.path.exists(HISTORY_FILE):
        return []
    try:
        with open(HISTORY_FILE) as f:
            return json.load(f)
    except Exception:
        return []


def history_stats() -> dict:
    """Compute summary statistics from the history file."""
    from collections import Counter
    records = history_load()
    now     = datetime.now()

    def _date(r):
        try:
            return datetime.fromisoformat(r["timestamp"])
        except Exception:
            return None

    today      = [r for r in records if (d := _date(r)) and d.date() == now.date()]
    this_week  = [r for r in records if (d := _date(r)) and (now - d).days < 7]

    def _freed(rs):
        return sum(r.get("freed_bytes", 0) for r in rs)

    def _top_apps(rs, n=5):
        c = Counter(r["name"] for r in rs)
        return c.most_common(n)

    return {
        "total":            len(records),
        "today":            len(today),
        "week":             len(this_week),
        "freed_today":      _freed(today),
        "freed_week":       _freed(this_week),
        "freed_total":      _freed(records),
        "top_apps_week":    _top_apps(this_week),
        "top_apps_total":   _top_apps(records),
        "first_event":      records[0]["timestamp"][:10] if records else "—",
    }


# ── App Monitor ───────────────────────────────────────────────────────────────

class Monitor:
    """Tracks which app was last in the foreground and when."""

    def __init__(self):
        self._last: dict[str, float] = {}
        self._lock = threading.Lock()

    def poll(self):
        """Call on main thread via rumps.Timer to record the frontmost app."""
        try:
            app = NSWorkspace.sharedWorkspace().frontmostApplication()
            if app:
                name = app.localizedName()
                if name:
                    with self._lock:
                        self._last[name] = time.time()
        except Exception as e:
            log(f"poll error: {e}")

    def running_apps(self):
        """Return list of dicts for every running GUI app."""
        try:
            result = []
            for app in NSWorkspace.sharedWorkspace().runningApplications():
                name = app.localizedName()
                if not name:
                    continue
                with self._lock:
                    last = self._last.get(name, 0)
                result.append({
                    "name":   name,
                    "pid":    app.processIdentifier(),
                    "bundle": app.bundleIdentifier() or "",
                    "last":   last,
                    "ref":    app,          # NSRunningApplication
                })
            return result
        except Exception as e:
            log(f"running_apps error: {e}")
            return []


# ── Apfel Classifier ──────────────────────────────────────────────────────────

class Apfel:
    """
    Asks Apple's on-device Foundation Model (via apfel's OpenAI-compatible
    server) whether an idle app is safe to auto-quit.
    Results are cached per app name for the session so we only call once.

    Requires: `apfel --serve` running (brew tap Arthur-Ficial/tap && brew install apfel)
    """

    MODEL = "apple-foundationmodel"

    def __init__(self, url: str):
        self.url   = url
        self._cache: dict[str, bool] = {}

    def safe_to_close(self, name: str, idle_min: float, mem_mb: float = 0) -> bool:
        """Returns True if the app should be closed."""
        if name in self._cache:
            return self._cache[name]

        prompt = (
            f"macOS app: {name!r}  Idle: {idle_min:.0f} min  RAM: {mem_mb:.0f} MB\n\n"
            "Should this app be auto-quit when idle?\n"
            "Reply with exactly one word — YES or NO.\n\n"
            "Say NO for: system daemons, menu-bar utilities, Finder, Dock, "
            "media players that may be streaming audio/video, background sync "
            "tools, VPN clients, password managers.\n"
            "Say YES for: web browsers, text editors, chat apps, IDEs, "
            "creative apps, productivity tools."
        )

        try:
            from openai import OpenAI
            client = OpenAI(base_url=self.url, api_key="unused")
            resp = client.chat.completions.create(
                model=self.MODEL,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=5,
            )
            text   = resp.choices[0].message.content.strip().upper()
            result = text.startswith("YES")
        except Exception as e:
            log(f"Apfel error ({name}): {e} — defaulting to CLOSE")
            result = True

        self._cache[name] = result
        log(f"Apfel [{name}]: {'CLOSE' if result else 'KEEP'}")
        return result

    def invalidate(self, name: str | None = None):
        if name:
            self._cache.pop(name, None)
        else:
            self._cache.clear()


# ── Cache Cleanup ─────────────────────────────────────────────────────────────

def clean_cache(name: str, bundle: str) -> int:
    """
    Delete ~/Library/Caches entries for the given app.
    Returns total bytes freed.
    """
    freed      = 0
    cache_root = os.path.expanduser("~/Library/Caches")
    candidates: set[str] = set()

    if bundle:
        candidates.add(bundle)
    for v in (name, name.lower(), name.replace(" ", ""), name.replace(" ", "-")):
        candidates.add(v)

    # Fuzzy scan: any cache dir whose name contains the app name
    try:
        for entry in os.scandir(cache_root):
            if name.lower() in entry.name.lower():
                candidates.add(entry.name)
    except Exception:
        pass

    for c in candidates:
        path = os.path.join(cache_root, c)
        if not os.path.isdir(path):
            continue
        size = 0
        try:
            for dp, _, files in os.walk(path):
                for fn in files:
                    fp = os.path.join(dp, fn)
                    if not os.path.islink(fp):
                        size += os.path.getsize(fp)
            shutil.rmtree(path)
            freed += size
            log(f"Cleaned {path} ({size // 1024} KB)")
        except Exception as ex:
            log(f"Clean failed {path}: {ex}")

    return freed


# ── App Closer ────────────────────────────────────────────────────────────────

def close_app(ref, name: str, timeout: int = 10) -> bool:
    """Graceful quit, then force-quit if needed. Returns True if the app exited."""
    try:
        if ref.isTerminated():
            return True
        log(f"Quitting {name!r}…")
        ref.terminate()
        deadline = time.time() + timeout
        while time.time() < deadline:
            time.sleep(0.5)
            if ref.isTerminated():
                log(f"{name!r} quit gracefully.")
                return True
        log(f"{name!r} still alive — force-quitting…")
        ref.forceTerminate()
        time.sleep(1.0)
        ok = bool(ref.isTerminated())
        log(f"{name!r} force-quit: {'OK' if ok else 'FAILED'}")
        return ok
    except Exception as e:
        log(f"close_app error ({name}): {e}")
        return False


# ── Menu Bar App ──────────────────────────────────────────────────────────────

class AppGuardian(rumps.App):

    def __init__(self):
        _here     = os.path.dirname(os.path.abspath(__file__))
        _icon     = os.path.join(_here, "icons", "menubar.png")
        _icon_arg = _icon if os.path.exists(_icon) else None
        super().__init__(
            "App Guardian",
            icon=_icon_arg,
            template=False,        # coloured icon — not a template
            quit_button=None,
        )
        self.cfg          = cfg_load()
        self.mon          = Monitor()
        self.apl          = Apfel(self.cfg["apfel_url"])
        self.closed_today: list[dict] = []
        self._closing:     set[str]   = set()
        self._lock        = threading.Lock()

        # Mutable menu items (titles updated dynamically)
        self.mi_toggle  = rumps.MenuItem("", callback=self._toggle)
        self.mi_status  = rumps.MenuItem("", callback=self._show_status)
        self.mi_timeout = rumps.MenuItem("", callback=self._set_timeout)
        self.mi_apfel   = rumps.MenuItem("", callback=self._toggle_apfel)
        self.mi_clean   = rumps.MenuItem("", callback=self._toggle_clean)
        self.mi_closed  = rumps.MenuItem("", callback=self._show_stats)
        self._refresh_titles()

        self.menu = [
            self.mi_toggle,
            self.mi_status,
            None,
            self.mi_timeout,
            rumps.MenuItem("🚫 Excluded Apps…", callback=self._edit_excluded),
            self.mi_apfel,
            self.mi_clean,
            None,
            rumps.MenuItem("🧹 Clean All Caches Now", callback=self._clean_all),
            rumps.MenuItem("📈 Statistics…", callback=self._show_stats),
            rumps.MenuItem("📋 View Log", callback=self._view_log),
            self.mi_closed,
            None,
            rumps.MenuItem("Quit App Guardian", callback=self._quit),
        ]

        # All timers run on the main NSRunLoop — no threading issues
        self._pt = rumps.Timer(self._on_poll,  self.cfg["poll_interval"])
        self._ct = rumps.Timer(self._on_check, self.cfg["check_interval"])
        self._mt = rumps.Timer(self._on_menu,  30)
        self._pt.start()
        self._ct.start()
        self._mt.start()

        log("App Guardian started.")

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _refresh_titles(self):
        on = self.cfg.get("enabled", True)
        self.mi_toggle.title  = "● Monitoring ON" if on else "○ Monitoring PAUSED"
        self.mi_timeout.title = f"⏱  Timeout: {self.cfg['timeout_minutes']} min"
        self.mi_apfel.title   = ("✅ Use Apple Intelligence (apfel)" if self.cfg["use_apfel"] else "☐ Use Apple Intelligence (apfel)")
        self.mi_clean.title   = ("✅ Clean cache on close" if self.cfg["clean_cache"] else "☐ Clean cache on close")
        today_freed = sum(e.get("freed_bytes", 0) for e in self.closed_today)
        self.mi_closed.title  = (
            f"Closed today: {len(self.closed_today)}"
            + (f"  ({today_freed // (1024**2)} MB freed)" if today_freed else "")
        )

    def _mem_mb(self, pid: int) -> float:
        try:
            r = subprocess.run(
                ["ps", "-o", "rss=", "-p", str(pid)],
                capture_output=True, text=True, timeout=2,
            )
            return int(r.stdout.strip()) / 1024
        except Exception:
            return 0.0

    # ── Timers (main thread) ──────────────────────────────────────────────────

    def _on_poll(self, _):
        self.mon.poll()

    def _on_menu(self, _):
        apps  = self.mon.running_apps()
        excl  = set(self.cfg["excluded_apps"])
        tracked = [a for a in apps if a["last"] > 0 and a["name"] not in excl]
        self.mi_status.title = f"📊 {len(tracked)} apps tracked — view status…"
        self.mi_closed.title = f"Closed today: {len(self.closed_today)}"

    def _on_check(self, _):
        if not self.cfg.get("enabled", True):
            return

        apps  = self.mon.running_apps()
        now   = time.time()
        limit = self.cfg["timeout_minutes"] * 60
        excl  = set(self.cfg["excluded_apps"])

        for app in apps:
            name = app["name"]
            if name in excl or app["last"] == 0:
                continue
            if (now - app["last"]) < limit:
                continue

            with self._lock:
                if name in self._closing:
                    continue
                self._closing.add(name)

            # All heavy work (Apple Intelligence + close + cache) in a background thread
            threading.Thread(
                target=self._evaluate_and_close,
                args=(app, (now - app["last"]) / 60),
                daemon=True,
            ).start()

    # ── Background worker ─────────────────────────────────────────────────────

    def _evaluate_and_close(self, app: dict, idle_min: float):
        name   = app["name"]
        bundle = app["bundle"]
        ref    = app["ref"]

        try:
            # 1. Ask Apple Intelligence via apfel (cached after first call)
            if self.cfg.get("use_apfel", True):
                mem = self._mem_mb(app["pid"])
                if not self.apl.safe_to_close(name, idle_min, mem):
                    return   # Apple Intelligence says keep it

            # 2. Close the app
            ok = close_app(ref, name, self.cfg["force_quit_timeout"])
            if not ok:
                return

            # 3. Clean caches
            freed = 0
            if self.cfg.get("clean_cache", True):
                freed = clean_cache(name, bundle)

            # 4. Record + notify
            entry = {
                "name":        name,
                "bundle":      bundle,
                "timestamp":   datetime.now().isoformat(timespec="seconds"),
                "idle_min":    round(idle_min, 1),
                "freed_bytes": freed,
                "used_apfel":  self.cfg.get("use_apfel", True),
            }
            history_append(entry)
            with self._lock:
                self.closed_today.append(entry)
            self._refresh_titles()

            msg = (f"Idle {idle_min:.0f} min · Freed {freed // (1024 ** 2)} MB cache"
                   if freed else f"Idle {idle_min:.0f} min")
            rumps.notification("App Guardian", f"Closed {name}", msg)

        finally:
            with self._lock:
                self._closing.discard(name)

    # ── Menu callbacks ────────────────────────────────────────────────────────

    def _toggle(self, _):
        self.cfg["enabled"] = not self.cfg.get("enabled", True)
        cfg_save(self.cfg)
        self._refresh_titles()
        log(f"Monitoring {'ON' if self.cfg['enabled'] else 'OFF'}.")

    def _set_timeout(self, _):
        w = rumps.Window(
            "Minutes of inactivity before closing an app:",
            "Set Timeout",
            default_text=str(self.cfg["timeout_minutes"]),
            ok="Set", cancel="Cancel",
        )
        r = w.run()
        if r.clicked:
            try:
                m = int(r.text)
                if m > 0:
                    self.cfg["timeout_minutes"] = m
                    cfg_save(self.cfg)
                    self._refresh_titles()
            except ValueError:
                pass

    def _edit_excluded(self, _):
        w = rumps.Window(
            "One app name per line (exact match as shown in Activity Monitor):",
            "Excluded Apps",
            default_text="\n".join(self.cfg["excluded_apps"]),
            ok="Save", cancel="Cancel",
            dimensions=(340, 260),
        )
        r = w.run()
        if r.clicked:
            self.cfg["excluded_apps"] = [
                a.strip() for a in r.text.splitlines() if a.strip()
            ]
            cfg_save(self.cfg)

    def _toggle_apfel(self, _):
        self.cfg["use_apfel"] = not self.cfg.get("use_apfel", True)
        cfg_save(self.cfg)
        self._refresh_titles()

    def _toggle_clean(self, _):
        self.cfg["clean_cache"] = not self.cfg.get("clean_cache", True)
        cfg_save(self.cfg)
        self._refresh_titles()

    def _clean_all(self, _):
        apps  = self.mon.running_apps()
        excl  = set(self.cfg["excluded_apps"])
        total = sum(
            clean_cache(a["name"], a["bundle"])
            for a in apps if a["name"] not in excl
        )
        rumps.alert(
            "Cache Cleanup",
            f"Freed {total // (1024 ** 2)} MB from app caches.",
        )

    def _show_status(self, _):
        apps = self.mon.running_apps()
        now  = time.time()
        excl = set(self.cfg["excluded_apps"])
        lim  = self.cfg["timeout_minutes"] * 60
        rows = []
        for a in sorted(apps, key=lambda x: -(now - x["last"]) if x["last"] else 0):
            if a["name"] in excl or a["last"] == 0:
                continue
            idle = (now - a["last"]) / 60
            warn = "  ⚠️ will close soon" if (now - a["last"]) >= lim else ""
            rows.append(f"{a['name']}: {idle:.0f} min idle{warn}")
        msg = "\n".join(rows[:30]) or (
            "No apps tracked yet.\n\n"
            "Apps are tracked the first time you bring them to the foreground."
        )
        rumps.alert("Tracked App Idle Times", msg)

    def _show_stats(self, _):
        s = history_stats()

        def _mb(b):
            return f"{b / (1024 ** 2):.1f} MB"

        def _top_list(pairs):
            if not pairs:
                return "  (none yet)"
            return "\n".join(f"  {i+1}. {name} ({n}×)" for i, (name, n) in enumerate(pairs))

        lines = [
            "─────────────────────────────",
            f"  Today          {s['today']:>4} apps   {_mb(s['freed_today']):>9} freed",
            f"  Last 7 days    {s['week']:>4} apps   {_mb(s['freed_week']):>9} freed",
            f"  All time       {s['total']:>4} apps   {_mb(s['freed_total']):>9} freed",
            f"  Tracking since {s['first_event']}",
            "─────────────────────────────",
            "",
            "Top apps closed (last 7 days):",
            _top_list(s["top_apps_week"]),
            "",
            "Top apps closed (all time):",
            _top_list(s["top_apps_total"]),
        ]
        rumps.alert("App Guardian — Statistics", "\n".join(lines))

    def _view_log(self, _):
        subprocess.run(["open", "-a", "Console", LOG_FILE])

    def _quit(self, _):
        log("App Guardian stopped.")
        rumps.quit_application()


# ── Entry ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    AppGuardian().run()
