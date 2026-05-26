import json
from datetime import datetime
from threading import Lock
from pathlib import Path
import sys
import re
from difflib import SequenceMatcher


def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


BASE_DIR         = get_base_dir()
MEMORY_PATH      = BASE_DIR / "memory" / "long_term.json"
CONVERSATION_PATH = BASE_DIR / "memory" / "conversation_history.json"
_lock            = Lock()
MAX_VALUE_LENGTH = 500
MEMORY_MAX_CHARS = 8000
MAX_CONVERSATIONS = 100


def _empty_memory() -> dict:
    return {
        "identity":      {},
        "preferences":   {},
        "projects":      {},
        "relationships": {},
        "wishes":        {},
        "notes":         {},
    }


def load_memory() -> dict:
    if not MEMORY_PATH.exists():
        return _empty_memory()
    with _lock:
        try:
            data = json.loads(MEMORY_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                base = _empty_memory()
                for key in base:
                    if key not in data:
                        data[key] = {}
                return data
            return _empty_memory()
        except Exception as e:
            print(f"[Memory] Load error: {e}")
            return _empty_memory()


def _all_entries(memory: dict) -> list[tuple]:
    entries = []
    for cat, items in memory.items():
        if not isinstance(items, dict):
            continue
        for key, entry in items.items():
            if isinstance(entry, dict) and "value" in entry:
                entries.append((cat, key, entry))
    return entries


def _trim_to_limit(memory: dict) -> dict:
    if len(json.dumps(memory, ensure_ascii=False)) <= MEMORY_MAX_CHARS:
        return memory
    entries = _all_entries(memory)
    entries.sort(key=lambda t: t[2].get("updated", "0000-00-00"))
    for cat, key, _ in entries:
        if len(json.dumps(memory, ensure_ascii=False)) <= MEMORY_MAX_CHARS:
            break
        del memory[cat][key]
        print(f"[Memory] Trimmed {cat}/{key}")
    return memory


def save_memory(memory: dict) -> None:
    if not isinstance(memory, dict):
        return
    memory = _trim_to_limit(memory)
    MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _lock:
        MEMORY_PATH.write_text(
            json.dumps(memory, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )


def _truncate_value(val: str) -> str:
    if isinstance(val, str) and len(val) > MAX_VALUE_LENGTH:
        return val[:MAX_VALUE_LENGTH].rstrip() + "..."
    return val


def _recursive_update(target: dict, updates: dict) -> bool:
    changed = False
    for key, value in updates.items():
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        if isinstance(value, dict) and "value" not in value:
            if key not in target or not isinstance(target[key], dict):
                target[key] = {}
                changed = True
            if _recursive_update(target[key], value):
                changed = True
        else:
            new_val  = _truncate_value(str(value["value"] if isinstance(value, dict) else value))
            entry    = {"value": new_val, "updated": datetime.now().strftime("%Y-%m-%d")}
            existing = target.get(key, {})
            if not isinstance(existing, dict) or existing.get("value") != new_val:
                target[key] = entry
                changed = True
    return changed


def update_memory(memory_update: dict) -> dict:
    if not isinstance(memory_update, dict) or not memory_update:
        return load_memory()
    memory = load_memory()
    if _recursive_update(memory, memory_update):
        save_memory(memory)
        print(f"[Memory] Saved: {list(memory_update.keys())}")
    return memory


def semantic_search(query: str, top_k: int = 5) -> list[dict]:
    memory = load_memory()
    query_lower = query.lower()
    query_words = set(re.findall(r'\w+', query_lower))
    scored = []
    for cat, items in memory.items():
        if not isinstance(items, dict):
            continue
        for key, entry in items.items():
            if not isinstance(entry, dict) or "value" not in entry:
                continue
            val = str(entry.get("value", ""))
            key_text = key.replace("_", " ").lower()
            val_words = set(re.findall(r'\w+', val.lower()))
            word_overlap = len(query_words & val_words) / max(len(query_words | val_words), 1)
            key_sim = SequenceMatcher(None, query_lower, key_text).ratio()
            val_sim = SequenceMatcher(None, query_lower, val.lower()).ratio()
            exact_bonus = 0.3 if query_lower in val.lower() else (0.2 if query_lower in key_text else 0)
            score = word_overlap * 0.4 + val_sim * 0.3 + key_sim * 0.2 + exact_bonus * 0.1
            if score > 0.1:
                scored.append({"category": cat, "key": key, "value": val, "updated": entry.get("updated", ""), "score": round(score, 3)})
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:top_k]


def query_memory(query: str) -> str:
    results = semantic_search(query, top_k=5)
    if not results:
        return ""
    lines = ["[RELEVANT MEMORIES]"]
    for r in results:
        lines.append(f"- {r['category'].title()}: {r['key'].replace('_', ' ').title()} = {r['value']}")
    return "\n".join(lines)


def format_memory_for_prompt(memory: dict | None) -> str:
    if not memory:
        return ""
    lines = []
    identity = memory.get("identity", {})
    for field in ["name", "age", "birthday", "city", "job", "language", "school", "nationality"]:
        entry = identity.get(field)
        if entry:
            val = entry.get("value") if isinstance(entry, dict) else entry
            if val:
                lines.append(f"{field.title()}: {val}")
    for key, entry in identity.items():
        val = entry.get("value") if isinstance(entry, dict) else entry
        if val:
            lines.append(f"{key.replace('_', ' ').title()}: {val}")
    for label, cat, limit in [("", "preferences", 20), ("Active Projects:", "projects", 12), ("People:", "relationships", 12), ("Wishes:", "wishes", 10), ("Notes:", "notes", 10)]:
        items = memory.get(cat, {})
        if items:
            if label:
                lines.append(f"\n{label}")
            for key, entry in list(items.items())[:limit]:
                val = entry.get("value") if isinstance(entry, dict) else entry
                if val:
                    lines.append(f"  - {key.replace('_', ' ').title()}: {val}")
    if not lines:
        return ""
    result = "[WHAT YOU KNOW ABOUT THIS PERSON]\n" + "\n".join(lines)
    return (result[:1997] + "...") if len(result) > 2000 else result + "\n"


def remember(key: str, value: str, category: str = "notes") -> str:
    if category not in {"identity", "preferences", "projects", "relationships", "wishes", "notes"}:
        category = "notes"
    update_memory({category: {key: {"value": value}}})
    return f"Remembered: {category}/{key} = {value}"


def forget(key: str, category: str = "notes") -> str:
    memory = load_memory()
    cat = memory.get(category, {})
    if key in cat:
        del cat[key]
        memory[category] = cat
        save_memory(memory)
        return f"Forgotten: {category}/{key}"
    return f"Not found: {category}/{key}"


forget_memory = forget


def _empty_conversations() -> dict:
    return {"conversations": []}


def load_conversations() -> dict:
    if not CONVERSATION_PATH.exists():
        return _empty_conversations()
    with _lock:
        try:
            return json.loads(CONVERSATION_PATH.read_text(encoding="utf-8"))
        except Exception:
            return _empty_conversations()


def save_conversation(user_text: str, jarvis_text: str = ""):
    conv = load_conversations()
    conv.setdefault("conversations", []).append({"user": user_text, "jarvis": jarvis_text, "timestamp": datetime.now().isoformat()})
    if len(conv["conversations"]) > MAX_CONVERSATIONS:
        conv["conversations"] = conv["conversations"][-MAX_CONVERSATIONS:]
    with _lock:
        CONVERSATION_PATH.parent.mkdir(parents=True, exist_ok=True)
        CONVERSATION_PATH.write_text(json.dumps(conv, indent=2, ensure_ascii=False), encoding="utf-8")


def get_recent_conversations(n: int = 5) -> list[dict]:
    return load_conversations().get("conversations", [])[-n:]


def format_conversation_context(n: int = 3) -> str:
    recent = get_recent_conversations(n)
    if not recent:
        return ""
    lines = ["[RECENT CONVERSATION CONTEXT]"]
    for c in recent:
        if c.get("user"):
            lines.append(f"User: {c['user']}")
        if c.get("jarvis"):
            lines.append(f"You: {c['jarvis']}")
    return "\n".join(lines)
