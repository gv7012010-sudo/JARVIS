import json
import sys
import traceback
from pathlib import Path

try:
    from PIL import Image
    _PIL = True
except ImportError:
    _PIL = False

try:
    import google.generativeai as genai
    _GENAI = True
except ImportError:
    _GENAI = False


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def _get_api_key() -> str:
    return json.loads((_base_dir() / "config" / "api_keys.json").read_text(encoding="utf-8"))["gemini_api_key"]


def _get_model():
    genai.configure(api_key=_get_api_key())
    return genai.GenerativeModel("gemini-2.5-flash")


LEVEL_PROMPTS = {
    "basic": "Explain in simple terms for a beginner.",
    "medium": "Detailed explanation with examples.",
    "advanced": "In-depth, technical explanation.",
    "university": "University-level rigorous analysis.",
}


def _build_prompt(question: str, subject: str, level: str, has_photo: bool = False) -> str:
    lvl = LEVEL_PROMPTS.get(level, LEVEL_PROMPTS["medium"])
    media = "The user uploaded a PHOTO of their work. Analyze the image." if has_photo else ""
    return f"""You are JARVIS Study Assistant — expert tutor in ALL subjects.

Subject: {subject or "General"}
{media}
Question: {question}

{lvl}

INSTRUCTIONS:
1. Solve step-by-step, showing all work
2. Explain the CONCEPTS — don't just give answers
3. Give study tips related to this topic
4. Be encouraging and supportive

FORMAT: Clear sections, show formulas, highlight key concepts.
Goal: HELP THE USER LEARN. Adapt to their level and language."""


def _analyze_photo(photo_path: str, question: str, subject: str, level: str) -> str:
    if not _PIL:
        return "Pillow library required."
    if not _GENAI:
        return "Google AI library required."
    try:
        model = _get_model()
        prompt = _build_prompt(question, subject, level, has_photo=True)
        response = model.generate_content([prompt, Image.open(photo_path)])
        return response.text.strip()
    except Exception as e:
        return f"Photo analysis error: {e}"


def _answer(question: str, subject: str, level: str) -> str:
    if not _GENAI:
        return "Google AI library required."
    try:
        response = _get_model().generate_content(_build_prompt(question, subject, level))
        return response.text.strip()
    except Exception as e:
        return f"Error: {e}"


def study_assistant(parameters: dict = None, response=None, player=None, session_memory=None) -> str:
    params = parameters or {}
    action = params.get("action", "").strip().lower()
    question = params.get("question", "").strip()
    subject = params.get("subject", "general").strip().lower()
    level = params.get("level", "medium").strip().lower()
    photo_path = params.get("photo_path", "").strip()

    if player:
        player.write_log(f"[Study] {action} | {subject}")

    try:
        if action in ("solve_photo", "photo", "solve"):
            if not photo_path:
                return "Provide a photo path."
            if not Path(photo_path).exists():
                return f"Photo not found: {photo_path}"
            return _analyze_photo(photo_path, question or "Solve this step by step", subject, level)

        elif action in ("ask", "question", "help", "explain", "answer"):
            if not question:
                return "What is your question?"
            return _answer(question, subject, level)

        elif action in ("practice",):
            return _answer(f"Generate 5 practice problems with answers for: {question or subject}. Mix easy, medium, hard.", subject, level)

        elif action in ("concept", "explain_concept"):
            return _answer(f"Explain the concept of '{question}' in {subject}. Use analogies and examples.", subject, level)

        elif action in ("grade", "check", "review"):
            if photo_path:
                return _analyze_photo(photo_path, f"Grade this work. Check errors. Give constructive feedback: {question}", subject, level)
            return _answer(f"Review and grade this. Check for errors, give feedback: {question}", subject, level)

        elif action == "translate":
            target = params.get("target_language", "English")
            return _answer(f"Translate this to {target}: {question}. Explain cultural nuances.", subject, level)

        elif action == "summarize":
            return _answer(f"Summarize this concisely: {question}", subject, level)

        elif action in ("essay", "write"):
            return _answer(f"Help write about: {question}. Give outline, arguments, sample paragraph.", subject, level)

        elif action == "subjects":
            subs = {"math": "Mathematics", "physics": "Physics", "chemistry": "Chemistry", "biology": "Biology", "history": "History", "literature": "Literature", "programming": "Programming/CS", "economics": "Economics", "philosophy": "Philosophy", "psychology": "Psychology", "engineering": "Engineering", "medicine": "Medicine", "law": "Law", "art": "Art & Design", "music": "Music", "language": "Languages", "geography": "Geography", "general": "General"}
            return "Subjects:\n" + "\n".join(f"  {k}: {v}" for k, v in subs.items())

        elif question:
            return _answer(question, subject, level)

        return "Actions: solve_photo, ask, practice, concept, grade, translate, summarize, essay, subjects"

    except Exception as e:
        traceback.print_exc()
        return f"Study error: {e}"
