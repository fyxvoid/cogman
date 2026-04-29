# skill: note
# description: Save and list quick notes to ~/.cogman/notes.txt
# tags: productivity, notes, utility
# version: 1.0
# created: 2026-04-28

from pathlib import Path

NOTES = Path.home() / ".cogman" / "notes.txt"

def run(action: str = "list", text: str = "", **kwargs) -> str:
    NOTES.parent.mkdir(exist_ok=True)
    # If first positional arg isn't a verb AND no explicit text was given, treat it as the note
    if action not in ("list", "add", "clear") and not text:
        text = action
        action = "add"
    if action == "add":
        if not text:
            return "Usage: skill_note action=add text=<your note>"
        import time
        ts = time.strftime("%Y-%m-%d %H:%M")
        with open(NOTES, "a") as f:
            f.write(f"[{ts}] {text}\n")
        return f"Note saved: {text}"
    elif action == "list":
        if not NOTES.exists():
            return "No notes. Add one: skill_note action=add text=<note>"
        return NOTES.read_text().strip() or "No notes."
    elif action == "clear":
        NOTES.write_text("")
        return "Notes cleared."
    return f"Unknown action: {action}. Use: list, add, clear"
