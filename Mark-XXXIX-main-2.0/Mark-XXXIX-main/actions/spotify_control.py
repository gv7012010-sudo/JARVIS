import json
import subprocess
import sys
import time
from pathlib import Path

try:
    import pyautogui
    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.06
    _PYAUTOGUI = True
except ImportError:
    _PYAUTOGUI = False

try:
    import pyperclip
    _PYPERCLIP = True
except ImportError:
    _PYPERCLIP = False


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def _get_os() -> str:
    try:
        cfg = json.loads(
            (_base_dir() / "config" / "api_keys.json").read_text(encoding="utf-8")
        )
        return cfg.get("os_system", "windows").lower()
    except Exception:
        return "windows"


def _require_pyautogui():
    if not _PYAUTOGUI:
        raise RuntimeError("PyAutoGUI not installed.")


def _paste_text(text: str):
    _require_pyautogui()
    os_name = _get_os()
    paste_hotkey = ("command", "v") if os_name == "mac" else ("ctrl", "v")
    if _PYPERCLIP:
        pyperclip.copy(text)
        time.sleep(0.15)
        pyautogui.hotkey(*paste_hotkey)
        time.sleep(0.1)
    else:
        pyautogui.write(text, interval=0.03)


def _open_spotify_app() -> bool:
    _require_pyautogui()
    os_name = _get_os()
    try:
        if os_name == "windows":
            pyautogui.press("win")
            time.sleep(0.5)
            _paste_text("Spotify")
            time.sleep(0.6)
            pyautogui.press("enter")
            time.sleep(3.0)
            return True
        elif os_name == "mac":
            subprocess.run(["open", "-a", "Spotify"], capture_output=True, timeout=10)
            time.sleep(3.0)
            return True
        else:
            for launcher in [["spotify"], ["flatpak", "run", "com.spotify.Client"]]:
                try:
                    subprocess.Popen(launcher, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    time.sleep(3.0)
                    return True
                except FileNotFoundError:
                    continue
            return False
    except Exception as e:
        print(f"[Spotify] Could not open app: {e}")
        return False


def _playback(action: str) -> str:
    _require_pyautogui()
    if not _open_spotify_app():
        return "Could not open Spotify."
    os_name = _get_os()
    time.sleep(0.5)
    if action in ("play", "resume", "play_pause"):
        pyautogui.press("space")
        return "Playback toggled."
    elif action == "pause":
        pyautogui.press("space")
        return "Paused."
    elif action == "next":
        keys = ("command", "right") if os_name == "mac" else ("ctrl", "right")
        pyautogui.hotkey(*keys)
        return "Next track."
    elif action == "previous":
        keys = ("command", "left") if os_name == "mac" else ("ctrl", "left")
        pyautogui.hotkey(*keys)
        return "Previous track."
    elif action == "volume_up":
        keys = ("command", "up") if os_name == "mac" else ("ctrl", "up")
        pyautogui.hotkey(*keys)
        return "Volume up."
    elif action == "volume_down":
        keys = ("command", "down") if os_name == "mac" else ("ctrl", "down")
        pyautogui.hotkey(*keys)
        return "Volume down."
    return f"Unknown action: {action}"


def _search_and_play(query: str) -> str:
    _require_pyautogui()
    if not _open_spotify_app():
        return "Could not open Spotify."
    time.sleep(1.0)
    os_name = _get_os()
    search_hotkey = ("command", "l") if os_name == "mac" else ("ctrl", "l")
    pyautogui.hotkey(*search_hotkey)
    time.sleep(0.5)
    _paste_text(query)
    time.sleep(2.0)
    pyautogui.press("down")
    time.sleep(0.3)
    pyautogui.press("down")
    time.sleep(0.3)
    pyautogui.press("down")
    time.sleep(0.3)
    pyautogui.press("enter")
    time.sleep(1.0)
    pyautogui.press("space")
    time.sleep(0.3)
    return f"Playing: {query}"


def _current_track() -> str:
    os_name = _get_os()
    try:
        if os_name == "mac":
            r = subprocess.run(
                ["osascript", "-e", 'tell app "Spotify" to get name of current track & " - " & artist of current track'],
                capture_output=True, text=True, timeout=5
            )
            if r.stdout.strip():
                return f"Now playing: {r.stdout.strip()}"
        return "Could not detect current track."
    except Exception:
        return "Could not detect current track."


def _like_song() -> str:
    _require_pyautogui()
    if not _open_spotify_app():
        return "Could not open Spotify."
    time.sleep(0.5)
    os_name = _get_os()
    key = ("command", "shift", "l") if os_name == "mac" else ("ctrl", "shift", "l")
    pyautogui.hotkey(*key)
    return "Song liked."


def _shuffle() -> str:
    _require_pyautogui()
    if not _open_spotify_app():
        return "Could not open Spotify."
    time.sleep(0.5)
    os_name = _get_os()
    key = ("command", "s") if os_name == "mac" else ("ctrl", "s")
    pyautogui.hotkey(*key)
    return "Shuffle toggled."


def spotify_control(parameters: dict = None, response=None, player=None, session_memory=None) -> str:
    params = parameters or {}
    action = params.get("action", "").strip().lower()
    query = params.get("query", "").strip()
    if player:
        player.write_log(f"[Spotify] {action}")
    if not _PYAUTOGUI:
        return "PyAutoGUI is not installed."
    try:
        if action in ("play", "resume", "pause", "play_pause", "next", "previous", "volume_up", "volume_down"):
            return _playback(action)
        elif action in ("search", "play_song", "play_playlist"):
            q = params.get("playlist", "") or query
            if not q:
                return "Please specify a song or playlist."
            return _search_and_play(q)
        elif action == "current":
            return _current_track()
        elif action == "like":
            return _like_song()
        elif action == "shuffle":
            return _shuffle()
        elif action == "stop":
            return _playback("pause")
        else:
            return _search_and_play(action)
    except Exception as e:
        return f"Spotify error: {e}"
