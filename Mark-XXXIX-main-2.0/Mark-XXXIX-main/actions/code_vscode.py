import re
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


def _get_api_key() -> str:
    api_path = Path(__file__).resolve().parent.parent / "config" / "api_keys.json"
    import json
    with open(api_path, "r", encoding="utf-8") as f:
        return json.load(f)["gemini_api_key"]


def _get_gemini():
    import google.generativeai as genai
    genai.configure(api_key=_get_api_key())
    return genai.GenerativeModel("gemini-2.5-flash")


def _clean_code(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
    text = re.sub(r"\n?```$", "", text)
    return text.strip()


def _generate_code(description: str, language: str) -> str:
    model = _get_gemini()
    prompt = f"""You are an expert {language} developer.
Write clean, working, beginner-friendly {language} code for the description below.

Rules:
- Output ONLY the code. No explanation, no markdown, no backticks.
- Add helpful inline comments in Spanish.
- Handle errors and edge cases properly.
- Include a main() function and call it under if __name__ == "__main__".

Description: {description}

Code:"""
    response = model.generate_content(prompt)
    return _clean_code(response.text)


def code_vscode(parameters: dict, player=None, speak=None) -> str:
    params = parameters or {}
    description = params.get("description", "").strip()
    language = params.get("language", "python").strip().lower()
    project_name = params.get("project_name", "").strip()

    if not description:
        return "Please describe what code you want me to write, sir."

    if player:
        player.write_log(f"[VSCode] Generating {language} code...")

    ext_map = {
        "python": ".py", "py": ".py",
        "javascript": ".js", "js": ".js",
        "html": ".html", "css": ".css",
        "typescript": ".ts", "ts": ".ts",
        "cpp": ".cpp", "c": ".c", "java": ".java",
    }
    ext = ext_map.get(language, ".py")

    if not project_name:
        safe = re.sub(r"[^a-zA-Z0-9_]", "_", description.lower())[:30]
        project_name = safe

    desktop = Path.home() / "Desktop"
    file_path = desktop / f"{project_name}{ext}"

    try:
        code = _generate_code(description, language)
    except Exception as e:
        msg = f"Could not generate code: {e}"
        if speak:
            speak(msg)
        return msg

    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(code, encoding="utf-8")
    except Exception as e:
        msg = f"Could not save file: {e}"
        if speak:
            speak(msg)
        return msg

    if player:
        player.write_log(f"[VSCode] Saved: {file_path}")

    try:
        subprocess.Popen(
            ["code", str(file_path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        time.sleep(3.0)
    except Exception as e:
        msg = f"Could not open VS Code: {e}"
        if speak:
            speak(msg)
        return f"Code saved to {file_path} but could not open VS Code: {e}"

    if _PYAUTOGUI and language in ("python", "py"):
        try:
            pyautogui.hotkey("ctrl", "f5")
            time.sleep(1.0)
        except Exception:
            pass

    preview = "\n".join(code.splitlines()[:10])
    suffix = f"\n... ({len(code.splitlines()) - 10} more lines)" if len(code.splitlines()) > 10 else ""

    msg = f"Code written and opened in VS Code. Saved to: {file_path}"
    if speak:
        speak(f"I've written the code and opened it in VS Code for you, sir.")

    return f"{msg}\n\nPreview:\n{preview}{suffix}"
