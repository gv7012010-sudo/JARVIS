import json
import smtplib
import ssl
import sys
import time
import webbrowser
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
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
        cfg = json.loads((_base_dir() / "config" / "api_keys.json").read_text(encoding="utf-8"))
        return cfg.get("os_system", "windows").lower()
    except Exception:
        return "windows"


def _get_email_config() -> dict:
    p = _base_dir() / "config" / "email_config.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_email_config(gmail_user="", gmail_pass="", outlook_user="", outlook_pass=""):
    cfg = _get_email_config()
    if gmail_user: cfg["gmail_user"] = gmail_user
    if gmail_pass: cfg["gmail_password"] = gmail_pass
    if outlook_user: cfg["outlook_user"] = outlook_user
    if outlook_pass: cfg["outlook_password"] = outlook_pass
    p = _base_dir() / "config" / "email_config.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(cfg, indent=2), encoding="utf-8")


def _require_pyautogui():
    if not _PYAUTOGUI:
        raise RuntimeError("PyAutoGUI not installed. Run: pip install pyautogui")


def _paste_text(text: str) -> None:
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


def _send_via_browser(provider: str, to: str, subject: str, body: str) -> str:
    _require_pyautogui()
    from urllib.parse import quote

    to_enc = quote(to)
    sub_enc = quote(subject)
    body_enc = quote(body).replace("+", "%20")

    if provider == "gmail":
        url = f"https://mail.google.com/mail/?view=cm&fs=1&to={to_enc}&su={sub_enc}&body={body_enc}"
    else:
        url = f"https://outlook.live.com/mail/0/deeplink/compose?to={to_enc}&subject={sub_enc}&body={body_enc}"

    webbrowser.open(url)
    time.sleep(5.0)

    pyautogui.hotkey("ctrl", "enter")
    time.sleep(1.5)

    return f"Email sent to {to} via {provider.title()} web."


def _send_via_desktop(to: str, subject: str, body: str) -> str:
    _require_pyautogui()
    from urllib.parse import quote

    mailto = f"mailto:{to}?subject={quote(subject)}&body={quote(body)}"
    webbrowser.open(mailto)
    time.sleep(2.0)

    os_name = _get_os()
    if os_name == "windows":
        pyautogui.hotkey("alt", "s")
        time.sleep(0.5)
    elif os_name == "mac":
        pyautogui.hotkey("command", "shift", "d")
        time.sleep(0.5)

    return f"Email compose opened for {to} via default mail client."


def _send_smtp(provider: str, to: str, subject: str, body: str) -> str:
    cfg = _get_email_config()
    if provider == "gmail":
        user, pw = cfg.get("gmail_user", ""), cfg.get("gmail_password", "")
        server, port = "smtp.gmail.com", 587
    elif provider == "outlook":
        user, pw = cfg.get("outlook_user", ""), cfg.get("outlook_password", "")
        server, port = "smtp.office365.com", 587
    else:
        return f"Unknown provider: {provider}"
    if not user or not pw:
        return f"{provider.title()} credentials not configured. Use action='configure' first."
    msg = MIMEMultipart("alternative")
    msg["From"] = user
    msg["To"] = to
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))
    try:
        ctx = ssl.create_default_context()
        with smtplib.SMTP(server, port, timeout=30) as s:
            s.starttls(context=ctx)
            s.login(user, pw)
            s.sendmail(user, to, msg.as_string())
        return f"Email sent to {to} via {provider.title()} SMTP."
    except smtplib.SMTPAuthenticationError:
        return (f"{provider.title()} auth failed. Enable 2FA and use an App Password, "
                f"or use mode='browser' to send via the web browser instead.")
    except Exception as e:
        return f"Email failed: {e}"


def _compose_browser(provider: str, to: str, subject: str, body: str) -> str:
    from urllib.parse import quote
    to_enc = quote(to)
    sub_enc = quote(subject)
    body_enc = quote(body).replace("+", "%20")

    if provider == "gmail":
        if not to and not subject and not body:
            webbrowser.open("https://mail.google.com/mail/u/0/#inbox?compose=new")
        else:
            webbrowser.open(f"https://mail.google.com/mail/?view=cm&fs=1&to={to_enc}&su={sub_enc}&body={body_enc}")
    else:
        if not to and not subject and not body:
            webbrowser.open("https://outlook.live.com/mail/0/")
        else:
            webbrowser.open(f"https://outlook.live.com/mail/0/deeplink/compose?to={to_enc}&subject={sub_enc}&body={body_enc}")

    return f"Opened {provider.title()} compose for {to or 'new email'}."


def email_control(parameters: dict = None, response=None, player=None, session_memory=None) -> str:
    params = parameters or {}
    action = params.get("action", "").strip().lower()
    provider = params.get("provider", "gmail").strip().lower()
    mode = params.get("mode", "browser").strip().lower()
    to = params.get("to", "").strip()
    subject = params.get("subject", "").strip()
    body = params.get("body", "").strip()

    if player:
        player.write_log(f"[Email] {action} via {provider} ({mode})")

    try:
        if action == "configure":
            _save_email_config(params.get("gmail_user",""), params.get("gmail_password",""),
                               params.get("outlook_user",""), params.get("outlook_password",""))
            return "Email credentials saved."

        if action == "send":
            if not to or not subject or not body:
                return "Need: to, subject, body."
            if mode == "browser":
                return _send_via_browser(provider, to, subject, body)
            elif mode == "desktop":
                return _send_via_desktop(to, subject, body)
            else:
                return _send_smtp(provider, to, subject, body)

        if action in ("compose", "open"):
            return _compose_browser(provider, to, subject, body)

        if action == "desktop":
            from urllib.parse import quote
            mailto = f"mailto:{to}?subject={quote(subject)}&body={quote(body)}"
            webbrowser.open(mailto)
            return f"Opened default mail client."

        return "Actions: send | compose | desktop | configure. Mode: browser (default) | desktop | smtp."
    except Exception as e:
        return f"Email error: {e}"
