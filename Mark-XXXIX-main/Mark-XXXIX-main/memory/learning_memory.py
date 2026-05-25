import json
import re
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from threading import Lock
import sys


def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


LEARNING_PATH = get_base_dir() / "memory" / "learning_data.json"
_lock = Lock()
MAX_CORRECTIONS = 500
MAX_KNOWLEDGE = 300


def _empty() -> dict:
    return {"corrections": [], "knowledge": [], "user_preferences": {}, "interaction_stats": {"total_questions": 0, "total_corrections": 0, "subjects_asked": {}, "last_interaction": None}}


def load():
    if not LEARNING_PATH.exists():
        return _empty()
    with _lock:
        try:
            d = json.loads(LEARNING_PATH.read_text(encoding="utf-8"))
            base = _empty()
            for k in base:
                if k not in d:
                    d[k] = base[k]
            return d
        except Exception:
            return _empty()


def save(data: dict):
    LEARNING_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _lock:
        LEARNING_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def record_correction(topic: str, correction: str, context: str = ""):
    data = load()
    data["corrections"].append({"topic": topic.lower(), "correction": correction, "context": context, "timestamp": datetime.now().isoformat()})
    if len(data["corrections"]) > MAX_CORRECTIONS:
        data["corrections"] = data["corrections"][-MAX_CORRECTIONS:]
    data["interaction_stats"]["total_corrections"] += 1
    save(data)


def add_knowledge(topic: str, fact: str):
    data = load()
    for k in data["knowledge"]:
        if SequenceMatcher(None, k["topic"].lower(), topic.lower()).ratio() > 0.8:
            k["fact"] = fact
            k["updated"] = datetime.now().isoformat()
            save(data)
            return
    data["knowledge"].append({"topic": topic.lower(), "fact": fact, "created": datetime.now().isoformat(), "updated": datetime.now().isoformat()})
    if len(data["knowledge"]) > MAX_KNOWLEDGE:
        data["knowledge"] = data["knowledge"][-MAX_KNOWLEDGE:]
    save(data)


def search_corrections(query: str, top_k: int = 5) -> list:
    data = load()
    qw = set(re.findall(r'\w+', query.lower()))
    scored = []
    for c in reversed(data["corrections"]):
        tw = set(re.findall(r'\w+', c["topic"]))
        cw = set(re.findall(r'\w+', c["correction"].lower()))
        overlap = len(qw & (tw | cw))
        sim = SequenceMatcher(None, query.lower(), c["topic"]).ratio()
        score = overlap * 0.3 + sim * 0.4 + (0.1 if query.lower() in c["topic"] else 0)
        if score > 0.1:
            scored.append({**c, "score": score})
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:top_k]


def search_knowledge(query: str, top_k: int = 5) -> list:
    data = load()
    qw = set(re.findall(r'\w+', query.lower()))
    scored = []
    for k in reversed(data["knowledge"]):
        kw = set(re.findall(r'\w+', k["topic"]))
        fw = set(re.findall(r'\w+', k["fact"].lower()))
        overlap = len(qw & (kw | fw))
        score = overlap * 0.3 + SequenceMatcher(None, query.lower(), k["topic"]).ratio() * 0.4
        if score > 0.1:
            scored.append({**k, "score": score})
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:top_k]


def get_learning_context(query: str = "general") -> str:
    corrections = search_corrections(query, 3)
    knowledge = search_knowledge(query, 3)
    lines = []
    if corrections:
        lines.append("[LEARNED FROM CORRECTIONS]")
        for c in corrections:
            lines.append(f"- You corrected me about '{c['topic']}': {c['correction']}")
    if knowledge:
        lines.append("[KNOWLEDGE ACQUIRED]")
        for k in knowledge:
            lines.append(f"- {k['topic'].title()}: {k['fact']}")
    return "\n".join(lines)


def record_interaction(subject: str = "general"):
    data = load()
    s = data["interaction_stats"]
    s["total_questions"] += 1
    s["subjects_asked"][subject] = s["subjects_asked"].get(subject, 0) + 1
    s["last_interaction"] = datetime.now().isoformat()
    save(data)


def format_summary() -> str:
    data = load()
    s = data["interaction_stats"]
    lines = [f"Questions: {s['total_questions']}", f"Corrections: {s['total_corrections']}", f"Knowledge: {len(data['knowledge'])}", f"Corrections stored: {len(data['corrections'])}"]
    if s["subjects_asked"]:
        top = sorted(s["subjects_asked"].items(), key=lambda x: x[1], reverse=True)[:5]
        lines.append("Top subjects: " + ", ".join(f"{sub}({c})" for sub, c in top))
    return "\n".join(lines)
