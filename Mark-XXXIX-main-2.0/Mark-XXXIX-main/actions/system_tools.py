import json
import os
import subprocess
import sys
from pathlib import Path

try:
    import psutil
    _PSUTIL = True
except ImportError:
    _PSUTIL = False


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def _list_procs(search: str = "", limit: int = 20) -> str:
    if not _PSUTIL:
        return "psutil not installed."
    results = []
    for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent", "status"]):
        try:
            if search and search.lower() not in (p.info["name"] or "").lower():
                continue
            results.append(p.info)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    results = results[:limit]
    if not results:
        return f"No processes found{' for ' + search if search else ''}."
    lines = [f"{'PID':<8} {'NAME':<25} {'CPU':<8} {'MEM':<8} STATUS"]
    for p in results:
        lines.append(f"{p['pid']:<8} {(p['name'] or '?')[:24]:<25} {p['cpu_percent'] or 0:.1f}% {p['memory_percent'] or 0:.1f}% {p['status']}")
    return "\n".join(lines)


def _kill_proc(pid: int = None, name: str = "") -> str:
    if not _PSUTIL:
        return "psutil not installed."
    if pid:
        try:
            psutil.Process(pid).terminate()
            return f"Process {pid} terminated."
        except Exception as e:
            return f"Error: {e}"
    if name:
        killed = 0
        for p in psutil.process_iter(["pid", "name"]):
            try:
                if name.lower() in (p.info["name"] or "").lower():
                    p.terminate()
                    killed += 1
            except Exception:
                continue
        return f"Terminated {killed} process(es)."
    return "Specify pid or name."


def _sys_info() -> str:
    if not _PSUTIL:
        return "psutil not installed."
    from datetime import datetime
    cpu = psutil.cpu_percent(interval=0.5)
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    net = psutil.net_io_counters()
    boot = datetime.fromtimestamp(psutil.boot_time()).strftime("%Y-%m-%d %H:%M:%S")
    return (f"CPU: {cpu}% | RAM: {mem.used//10**9}GB/{mem.total//10**9}GB ({mem.percent}%) | "
            f"Disk: {disk.used//10**9}GB/{disk.total//10**9}GB ({disk.percent}%) | "
            f"Net: {net.bytes_sent//10**6}MB/{net.bytes_recv//10**6}MB | Boot: {boot} | "
            f"Procs: {len(psutil.pids())}")


def _battery() -> str:
    if not _PSUTIL or not psutil.sensors_battery():
        return "No battery info available."
    b = psutil.sensors_battery()
    return f"Battery: {b.percent}% ({'Plugged' if b.power_plugged else 'On battery'})"


def _clipboard_get() -> str:
    try:
        import pyperclip
        c = pyperclip.paste()
        return f"Clipboard: {c[:500]}" if c else "Clipboard empty."
    except Exception:
        return "Could not read clipboard."


def _clipboard_set(text: str) -> str:
    try:
        import pyperclip
        pyperclip.copy(text)
        return "Copied to clipboard."
    except Exception:
        return "Could not set clipboard."


def system_tools(parameters: dict = None, response=None, player=None, session_memory=None) -> str:
    params = parameters or {}
    action = params.get("action", "").strip().lower()
    if player:
        player.write_log(f"[System] {action}")
    try:
        if action in ("processes", "list_processes"):
            return _list_procs(params.get("search", ""), int(params.get("limit", 20)))
        elif action in ("kill", "kill_process"):
            return _kill_proc(int(params["pid"]) if params.get("pid") else None, params.get("name", ""))
        elif action in ("system_info", "info"):
            return _sys_info()
        elif action == "battery":
            return _battery()
        elif action in ("clipboard", "get_clipboard"):
            return _clipboard_get()
        elif action in ("set_clipboard", "copy"):
            return _clipboard_set(params.get("text", ""))
        elif action == "network":
            import socket
            return f"Host: {socket.gethostname()}, IP: {socket.gethostbyname(socket.gethostname())}"
        elif action == "uptime":
            from datetime import datetime
            if not _PSUTIL:
                return "psutil not installed."
            up = datetime.now() - datetime.fromtimestamp(psutil.boot_time())
            return f"Uptime: {up.days}d {up.seconds//3600}h {(up.seconds%3600)//60}m"
        elif action == "disk_usage":
            if not _PSUTIL:
                return "psutil not installed."
            d = psutil.disk_usage(params.get("path", "/"))
            return f"Disk: {d.used//10**9}GB/{d.total//10**9}GB ({d.percent}%)"
        return f"Available: processes, kill, system_info, battery, clipboard, set_clipboard, network, uptime, disk_usage"
    except Exception as e:
        return f"System error: {e}"
