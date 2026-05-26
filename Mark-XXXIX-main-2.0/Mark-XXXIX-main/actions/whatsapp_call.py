import re
import time

try:
    import pyautogui
    pyautogui.FAILSAFE = True
    pyautogui.PAUSE    = 0.06
    _PYAUTOGUI = True
except ImportError:
    _PYAUTOGUI = False

from actions.send_message import _open_app, _search_in_app, _require_pyautogui


def whatsapp_call(parameters: dict, player=None) -> str:
    params = parameters or {}
    raw_contact = params.get("contact", "").strip()
    call_type = params.get("call_type", "").strip().lower()

    if not raw_contact:
        return "Please specify a contact."

    # Auto-detect call type from contact text if call_type not explicit
    if not call_type or call_type not in ("voice", "video"):
        text = raw_contact.lower()
        if any(w in text for w in ("video", "videollamada", "video llamada", "videocall")):
            call_type = "video"
            raw_contact = re.sub(r"(video|videollamada|video llamada|videocall)\s*", "", text, flags=re.IGNORECASE).strip()
        else:
            call_type = "voice"

    _require_pyautogui()

    call_label = "video call" if call_type == "video" else "voice call"
    print(f"[WhatsAppCall] {call_label} -> {raw_contact}")
    if player:
        player.write_log(f"[call] WhatsApp {call_label} -> {raw_contact}")

    if not _open_app("WhatsApp"):
        return "Could not open WhatsApp."

    time.sleep(1.5)

    _search_in_app(raw_contact)
    time.sleep(0.5)
    pyautogui.press("enter")
    time.sleep(2.0)

    pyautogui.press("esc")
    time.sleep(0.2)

    # Navigate to call button area
    for _ in range(10):
        pyautogui.hotkey("shift", "tab")
        time.sleep(0.05)

    if call_type == "video":
        pyautogui.press("tab")
        time.sleep(0.05)

    for _ in range(2):
        pyautogui.press("tab")
        time.sleep(0.05)

    pyautogui.press("enter")
    time.sleep(0.5)

    result = f"Initiated {call_label} to {raw_contact} via WhatsApp."
    print(f"[WhatsAppCall] {result}")
    if player:
        player.write_log(f"[call] {result}")
    return result
