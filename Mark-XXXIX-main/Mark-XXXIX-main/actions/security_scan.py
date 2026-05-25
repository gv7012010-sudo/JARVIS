import base64
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from datetime import datetime

try:
    import psutil
    _PSUTIL = True
except ImportError:
    _PSUTIL = False

try:
    import pyperclip
    _PYPERCLIP = True
except ImportError:
    _PYPERCLIP = False


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


_SUSPICIOUS_NAMES = [
    "netcat", "ncat", "nc.exe", "nmap", "zenmap",
    "proxifier", "proxychains", "vnc", "anydesk",
    "teamviewer", "ammyy", "litemanager", "radmin",
    "keylogger", "keylog", "taskmgr", "regedit",
    "wireshark", "tcpview", "processhacker",
    "mimikatz", "pwdump", "cain", "abel",
    "hydra", "john", "hashcat", "aircrack",
    "meterpreter", "beacon", "cobaltstrike",
    "trojan", "backdoor", "ransomware",
    "miner", "monero", "ethminer", "xmrig",
    "coinminer", "cryptominer",
    "psexec", "remcom", "logmein", "screenconnect",
    "pup", "hacktool", "inject", "packer",
    "upx", "crack", "loader", "dropper",
    "keylogger", "spyware", "adware",
    "browserhelper", "searchprotect",
    "conduit", "opensrs", "sweetim",
]

_SPY_CAM_MIC_KEYWORDS = [
    "camera", "webcam", "capture", "record",
    "microphone", "mic", "audio capture",
    "screenshot", "screen capture", "obs",
    "bandicam", "fraps", "camtasia",
]

_PORTS_COMMON = [
    (21, "FTP"), (22, "SSH"), (23, "Telnet"),
    (25, "SMTP"), (53, "DNS"), (80, "HTTP"),
    (110, "POP3"), (135, "RPC"), (139, "NetBIOS"),
    (143, "IMAP"), (3389, "RDP"), (4444, "Metasploit"),
    (5555, "Android ADB"), (5900, "VNC"),
    (6379, "Redis"), (8080, "HTTP-Proxy"),
    (8443, "HTTPS-Alt"), (27017, "MongoDB"),
]

_SENSITIVE_FILE_PATTERNS = [
    "password", "contraseña", "senha", "passwd",
    "secret", "token", "api_key", "apikey",
    "credit", "tarjeta", "card", "cvv",
    "wallet", "billetera", "private.key",
    "id_rsa", ".env", "credentials",
    "backup", "dump", "export",
]


def _check_open_ports() -> list:
    open_ports = []
    for port, name in _PORTS_COMMON:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(0.3)
            r = s.connect_ex(("127.0.0.1", port))
            s.close()
            if r == 0:
                entries = []
                try:
                    for c in psutil.net_connections():
                        if c.laddr and c.laddr.port == port and c.status == "LISTEN":
                            pid_info = ""
                            try:
                                p = psutil.Process(c.pid)
                                pid_info = f" (PID {c.pid}: {p.name()})"
                            except Exception:
                                pid_info = f" (PID {c.pid})"
                            entries.append(f"{name} (port {port}){pid_info}")
                except Exception:
                    entries.append(f"{name} (port {port})")
                open_ports.extend(entries)
        except Exception:
            pass
    return open_ports


def _check_firewall() -> str:
    try:
        if sys.platform == "win32":
            r = subprocess.run(
                ["netsh", "advfirewall", "show", "currentprofile"],
                capture_output=True, text=True, timeout=5
            )
            for line in r.stdout.splitlines():
                if "State" in line:
                    return line.split(":")[-1].strip()
            return "Unknown"
        elif sys.platform == "darwin":
            r = subprocess.run(
                ["/usr/libexec/ApplicationFirewall/socketfilterfw", "--getglobalstate"],
                capture_output=True, text=True, timeout=5
            )
            return "Enabled" if "enabled" in r.stdout.lower() else "Disabled"
        else:
            r = subprocess.run(["ufw", "status"], capture_output=True, text=True, timeout=5)
            return r.stdout.strip()[:50] if r.returncode == 0 else "Unknown"
    except Exception:
        return "No se pudo verificar"


def _check_suspicious_processes() -> list:
    if not _PSUTIL:
        return []
    found = []
    for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent", "exe", "cmdline"]):
        try:
            name = (p.info["name"] or "").lower()
            cmd = " ".join(p.info.get("cmdline") or [])
            if any(s in name for s in _SUSPICIOUS_NAMES) or any(s in cmd.lower() for s in _SUSPICIOUS_NAMES if len(s) > 3):
                found.append(f"PID {p.info['pid']}: {p.info['name']} ({p.info.get('cpu_percent',0)}% CPU, {p.info.get('memory_percent',0):.1f}% MEM)")
        except Exception:
            continue
    return found


def _check_spy_processes() -> list:
    if not _PSUTIL:
        return []
    found = []
    for p in psutil.process_iter(["pid", "name", "connections"]):
        try:
            name = (p.info["name"] or "").lower()
            if any(s in name for s in _SPY_CAM_MIC_KEYWORDS):
                found.append(f"PID {p.info['pid']}: {p.info['name']}")
        except Exception:
            continue
    return found


def _check_network_connections() -> list:
    if not _PSUTIL:
        return []
    suspicious = []
    try:
        conns = psutil.net_connections()
        for c in conns:
            if c.status == "ESTABLISHED" and c.raddr:
                ip = c.raddr.ip
                if not ip.startswith(("192.168.", "10.", "172.16.", "127.0.0.")):
                    try:
                        p = psutil.Process(c.pid)
                        suspicious.append(f"{p.name()} -> {ip}:{c.raddr.port}")
                    except Exception:
                        suspicious.append(f"PID {c.pid} -> {ip}:{c.raddr.port}")
    except Exception:
        pass
    return suspicious


def _check_data_exfiltration() -> list:
    if not _PSUTIL:
        return []
    warnings = []
    try:
        net_before = psutil.net_io_counters()
        time.sleep(0.5)
        net_after = psutil.net_io_counters()
        sent_mb = (net_after.bytes_sent - net_before.bytes_sent) / (1024 * 1024)
        if sent_mb > 5:
            warnings.append(f"Alta transferencia de salida: {sent_mb:.1f} MB en 0.5s")
    except Exception:
        pass
    try:
        for p in psutil.process_iter(["pid", "name", "io_counters"]):
            try:
                io = p.info.get("io_counters")
                if io and io.write_bytes > 100 * 1024 * 1024:
                    warnings.append(f"Proceso con mucha escritura: {p.info['name']} ({io.write_bytes/1024/1024:.0f} MB)")
            except Exception:
                continue
    except Exception:
        pass
    return warnings


def _check_vpn() -> str:
    try:
        if sys.platform == "win32":
            r = subprocess.run(["netsh", "interface", "show", "interface"],
                               capture_output=True, text=True, timeout=5)
            for line in r.stdout.splitlines():
                if "VPN" in line or "Tunnel" in line or "WSL" in line:
                    pass
        interfaces = psutil.net_if_addrs() if _PSUTIL else {}
        for name, addrs in interfaces.items():
            low_name = name.lower()
            if any(k in low_name for k in ["tun", "tap", "vpn", "tunnel", "tailscale", "wireguard", "openvpn", "nord", "expressvpn"]):
                for addr in addrs:
                    if addr.family == socket.AF_INET:
                        return f"Conectado a VPN: {name} ({addr.address})"
        return "No se detecto VPN activa"
    except Exception:
        return "No se pudo verificar VPN"


def _check_wifi_security() -> str:
    try:
        if sys.platform == "win32":
            r = subprocess.run(
                ["netsh", "wlan", "show", "interfaces"],
                capture_output=True, text=True, timeout=5
            )
            for line in r.stdout.splitlines():
                if "SSID" in line and "BSSID" not in line:
                    ssid = line.split(":")[-1].strip()
                if "Authentication" in line:
                    auth = line.split(":")[-1].strip()
                    if auth.upper() in ("WEP", "OPEN", "NONE"):
                        return f"WiFi insegura: {ssid} usa {auth}"
                    return f"WiFi: {ssid} ({auth})"
            return "WiFi no detectada (cableada?)"
        return "Disponible solo en Windows"
    except Exception:
        return "No se pudo verificar"


def _check_autoruns() -> list:
    if sys.platform != "win32":
        return []
    suspicious = []
    try:
        import winreg
        keys = [
            (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run"),
            (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Run"),
            (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\RunOnce"),
        ]
        for hive, key_path in keys:
            try:
                k = winreg.OpenKey(hive, key_path)
                i = 0
                while True:
                    try:
                        name, value, _ = winreg.EnumValue(k, i)
                        low_val = value.lower()
                        if any(s in low_val for s in ["temp", "startup", "hidden", "crypto", "miner", "svchost"]):
                            suspicious.append(f"{name} -> {value[:80]}")
                        i += 1
                    except OSError:
                        break
                winreg.CloseKey(k)
            except Exception:
                continue
    except Exception:
        pass
    return suspicious[:10]


def _check_sensitive_files() -> list:
    sensitive = []
    paths_to_check = [
        Path.home() / "Desktop",
        Path.home() / "Documents",
        Path.home() / "Downloads",
    ]
    exts = (".txt", ".csv", ".json", ".xml", ".env", ".cfg", ".conf", ".ini")
    for folder in paths_to_check:
        if not folder.exists():
            continue
        try:
            for f in folder.iterdir():
                if f.is_file() and f.suffix.lower() in exts:
                    try:
                        content = f.read_text(encoding="utf-8", errors="ignore")[:2000].lower()
                        if any(p in content for p in _SENSITIVE_FILE_PATTERNS):
                            sensitive.append(f.name)
                    except Exception:
                        continue
        except Exception:
            continue
    return sensitive[:15]


def _clear_clipboard() -> str:
    try:
        if _PYPERCLIP:
            pyperclip.copy("")
            return "Portapapeles limpiado."
        subprocess.run(["cmd", "/c", "echo", "off", "|", "clip"], capture_output=True, timeout=3)
        return "Portapapeles limpiado."
    except Exception:
        return "No se pudo limpiar el portapapeles."


def _clear_browser_data() -> str:
    results = []
    try:
        if sys.platform == "win32":
            paths = [
                Path(os.environ.get("LOCALAPPDATA", "")) / "Google" / "Chrome" / "User Data" / "Default" / "Cache",
                Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "Edge" / "User Data" / "Default" / "Cache",
                Path(os.environ.get("APPDATA", "")) / "Mozilla" / "Firefox" / "Profiles",
            ]
            for p in paths:
                if p.exists():
                    results.append(f"Cache encontrado: {p.parent.name}")
        results.append("Limpieza manual recomendada desde el navegador")
    except Exception:
        pass
    return "Datos de navegador:\n" + "\n".join(results) if results else "No se encontraron datos de navegador para limpiar"


def _delete_temp_files() -> str:
    deleted = 0
    try:
        if sys.platform == "win32":
            temp_dirs = [
                Path(os.environ.get("TEMP", "")),
                Path(os.environ.get("TMP", "")),
                Path(os.environ.get("LOCALAPPDATA", "")) / "Temp",
            ]
            for td in temp_dirs:
                if td.exists():
                    for f in td.iterdir():
                        try:
                            if f.is_file() and time.time() - f.stat().st_atime > 86400 * 7:
                                f.unlink()
                                deleted += 1
                        except Exception:
                            continue
        return f"Eliminados {deleted} archivos temporales antiguos."
    except Exception:
        return "No se pudieron eliminar archivos temporales."


def _encrypt_file(path: str) -> str:
    try:
        from cryptography.fernet import Fernet
    except ImportError:
        return "Cryptography no instalado. Ejecuta: pip install cryptography"

    p = Path(path)
    if not p.exists():
        return f"Archivo no encontrado: {path}"

    try:
        key_file = _base_dir() / "config" / ".encryption_key"
        if key_file.exists():
            key = key_file.read_bytes()
        else:
            key = Fernet.generate_key()
            key_file.parent.mkdir(parents=True, exist_ok=True)
            key_file.write_bytes(key)
            print(f"[Security] Clave de cifrado guardada en: {key_file}")

        fernet = Fernet(key)
        data = p.read_bytes()
        encrypted = fernet.encrypt(data)
        out_path = p.with_suffix(p.suffix + ".encrypted")
        out_path.write_bytes(encrypted)
        p.unlink()
        return f"Archivo cifrado: {out_path.name}. NO PIERDAS LA CLAVE."
    except Exception as e:
        return f"Error al cifrar: {e}"


def _decrypt_file(path: str) -> str:
    try:
        from cryptography.fernet import Fernet, InvalidToken
    except ImportError:
        return "Cryptography no instalado. Ejecuta: pip install cryptography"

    p = Path(path)
    if not p.exists():
        return f"Archivo no encontrado: {path}"

    try:
        key_file = _base_dir() / "config" / ".encryption_key"
        if not key_file.exists():
            return "No se encuentra la clave de cifrado."

        key = key_file.read_bytes()
        fernet = Fernet(key)
        data = p.read_bytes()
        decrypted = fernet.decrypt(data)
        out_path = p.with_name(p.stem)
        out_path.write_bytes(decrypted)
        p.unlink()
        return f"Archivo descifrado: {out_path.name}"
    except InvalidToken:
        return "Clave incorrecta o archivo corrupto."
    except Exception as e:
        return f"Error al descifrar: {e}"


_RECOMMENDATIONS = [
    "1. Manten Windows Defender / antivirus activo y actualizado en todo momento",
    "2. No descargues archivos ni programas de fuentes no confiables",
    "3. Usa una VPN en redes WiFi publicas para cifrar tu trafico",
    "4. Activa el firewall de Windows si esta desactivado",
    "5. No ejecutes archivos .exe, .scr ni .msi de dudosa procedencia",
    "6. Manten Windows y todos tus programas siempre actualizados",
    "7. Usa contrasenas fuertes y autenticacion en 2 pasos",
    "8. No guardes contrasenas ni datos bancarios en archivos de texto plano",
    "9. Desconfia de correos electronicos con enlaces o archivos adjuntos desconocidos (phishing)",
    "10. Cifra archivos sensibles con el comando 'cifrar' de JARVIS",
    "11. Limpia tu portapapeles si copias informacion sensible",
    "12. Revisa que aplicaciones tienen acceso a tu camara y microfono",
    "13. Cierra sesion en tus cuentas cuando no uses el equipo",
    "14. Usa el modo privado periodicamente para limpiar datos temporales",
]


def run_security_scan() -> str:
    lines = []
    lines.append("=" * 55)
    lines.append("           ANALISIS DE SEGURIDAD Y PRIVACIDAD")
    lines.append("=" * 55)

    firewall_status = _check_firewall()
    lines.append(f"\n[FIREWALL] Estado: {firewall_status}")
    if "off" in firewall_status.lower() or "disabled" in firewall_status.lower():
        lines.append("  ! RECOMENDACION: Activa el firewall para proteger tu equipo")

    wifi = _check_wifi_security()
    lines.append(f"\n[WIFI] {wifi}")

    vpn = _check_vpn()
    lines.append(f"\n[VPN] {vpn}")

    if _PSUTIL:
        susp_procs = _check_suspicious_processes()
        if susp_procs:
            lines.append(f"\n[PROCESOS] Sospechosos detectados ({len(susp_procs)}):")
            for p in susp_procs:
                lines.append(f"  ! {p}")
        else:
            lines.append("\n[PROCESOS] Sin procesos sospechosos detectados")

        spy_procs = _check_spy_processes()
        if spy_procs:
            lines.append(f"\n[CAM/MIC] Programas con acceso a camara/microfono ({len(spy_procs)}):")
            for p in spy_procs:
                lines.append(f"  i {p}")

        net_conns = _check_network_connections()
        if net_conns:
            lines.append(f"\n[RED] Conexiones a IPs externas ({len(net_conns)}):")
            for c in net_conns[:10]:
                lines.append(f"  i {c}")
            if len(net_conns) > 10:
                lines.append(f"  ... y {len(net_conns) - 10} mas")
        else:
            lines.append("\n[RED] Sin conexiones salientes a IPs externas")

        exfil = _check_data_exfiltration()
        if exfil:
            lines.append(f"\n[EXFILTRACION] Posible fuga de datos:")
            for w in exfil:
                lines.append(f"  ! {w}")

    open_ports = _check_open_ports()
    if open_ports:
        lines.append(f"\n[PUERTOS] Puertos abiertos ({len(open_ports)}):")
        for p in open_ports:
            lines.append(f"  i {p}")
        lines.append("  ! Cierra los puertos que no uses desde el firewall")
    else:
        lines.append("\n[PUERTOS] Sin puertos de alto riesgo abiertos")

    autoruns = _check_autoruns()
    if autoruns:
        lines.append(f"\n[INICIO] Programas sospechosos al inicio ({len(autoruns)}):")
        for a in autoruns:
            lines.append(f"  i {a}")

    sens_files = _check_sensitive_files()
    if sens_files:
        lines.append(f"\n[ARCHIVOS] Posibles archivos con informacion sensible ({len(sens_files)}):")
        for f in sens_files[:8]:
            lines.append(f"  i {f}")
        lines.append("  ! Revisa estos archivos, podrian contener contrasenas o datos personales")

    lines.append(f"\n{'=' * 55}")
    lines.append("RECOMENDACIONES DE SEGURIDAD:")
    lines.append("=" * 55)
    for r in _RECOMMENDATIONS:
        lines.append(f"  {r}")

    lines.append(f"\n{'=' * 55}")
    return "\n".join(lines)


def privacy_mode() -> str:
    results = []
    results.append("--- ACTIVANDO MODO PRIVADO ---")

    results.append(_clear_clipboard())
    results.append(_delete_temp_files())
    results.append(_clear_browser_data())

    log_path = _base_dir() / "memory" / "conversations"
    if log_path.exists():
        try:
            for f in log_path.iterdir():
                if f.suffix == ".json":
                    f.unlink()
            results.append("Historial de conversaciones eliminado.")
        except Exception:
            results.append("No se pudo limpiar el historial.")

    try:
        recent = Path.home() / "Recent"
        if recent.exists():
            for f in recent.iterdir():
                try:
                    f.unlink()
                except Exception:
                    continue
            results.append("Archivos recientes limpiados.")
    except Exception:
        pass

    results.append("\nModo privado activado. Datos temporales eliminados.")
    return "\n".join(results)


def security_scan(parameters: dict = None, player=None, speak=None) -> str:
    params = parameters or {}
    action = params.get("action", "").strip().lower()
    file_path = params.get("file_path", "").strip()

    if player:
        player.write_log(f"[Security] {action or 'full_scan'}")

    if action in ("scan", "full", ""):
        if speak:
            speak("Iniciando analisis de seguridad completo, espere un momento.")
        result = run_security_scan()
        if speak:
            issues = result.count("!") + result.count("PROCESOS") + result.count("EXFILTRACION")
            if issues > 0:
                speak(f"Analisis completo. Se encontraron {issues} posibles problemas. Revise los detalles.")
            else:
                speak("Analisis completo. No se encontraron problemas de seguridad. Su sistema esta limpio.")
        return result

    elif action == "ports":
        open_ports = _check_open_ports()
        if open_ports:
            return f"Puertos abiertos ({len(open_ports)}):\n" + "\n".join(f"  i {p}" for p in open_ports)
        return "No hay puertos de alto riesgo abiertos."

    elif action == "firewall":
        return f"Firewall: {_check_firewall()}"

    elif action == "processes":
        if not _PSUTIL:
            return "psutil no instalado."
        susp = _check_suspicious_processes()
        if susp:
            return f"Procesos sospechosos ({len(susp)}):\n" + "\n".join(f"  ! {p}" for p in susp)
        return "No hay procesos sospechosos ejecutandose."

    elif action == "network":
        if not _PSUTIL:
            return "psutil no instalado."
        conns = _check_network_connections()
        if conns:
            return f"Conexiones a IPs externas ({len(conns)}):\n" + "\n".join(f"  i {c}" for c in conns[:15])
        return "Sin conexiones salientes a IPs externas."

    elif action == "privacy":
        if speak:
            speak("Activando modo privado, espere.")
        return privacy_mode()

    elif action == "clipboard":
        return _clear_clipboard()

    elif action == "temp":
        return _delete_temp_files()

    elif action == "wifi":
        return f"WiFi: {_check_wifi_security()}"

    elif action == "vpn":
        return f"VPN: {_check_vpn()}"

    elif action == "sensitive":
        files = _check_sensitive_files()
        if files:
            return f"Archivos con posible info sensible ({len(files)}):\n" + "\n".join(f"  i {f}" for f in files[:10])
        return "No se encontraron archivos con informacion sensible en escritorio/documentos."

    elif action == "encrypt":
        if not file_path:
            return "Especifica file_path del archivo a cifrar."
        return _encrypt_file(file_path)

    elif action == "decrypt":
        if not file_path:
            return "Especifica file_path del archivo a descifrar."
        return _decrypt_file(file_path)

    elif action == "recommendations":
        return "RECOMENDACIONES:\n" + "\n".join(f"  {r}" for r in _RECOMMENDATIONS)

    return "Acciones: scan, ports, firewall, processes, network, privacy, clipboard, temp, wifi, vpn, sensitive, encrypt, decrypt, recommendations"
