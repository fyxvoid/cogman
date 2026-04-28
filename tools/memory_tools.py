"""Memory tools: save, recall, preferences."""
import logging
from core.tool_registry import ToolRegistry

log = logging.getLogger("cogman.tools.memory")

_memory = None  # lazy singleton


def _get_mem():
    global _memory
    if _memory is None:
        from core.memory import Memory
        _memory = Memory()
    return _memory


def set_memory_backend(memory) -> None:
    """Inject a specific Memory instance (used by orchestrator/tests)."""
    global _memory
    _memory = memory


def save_memory(content: str, category: str = "general") -> str:
    _get_mem().remember(content, category=category)
    return f"Remembered: {content[:80]}..."


def search_memory(query: str) -> str:
    results = _get_mem().recall(query)
    if not results:
        return f"No memories found for: {query}"
    lines = [f"  {i+1}. {r}" for i, r in enumerate(results)]
    return "Recalled memories:\n" + "\n".join(lines)


def set_preference(key: str, value: str) -> str:
    _get_mem().set_pref(key, value)
    return f"Preference saved: {key} = {value}"


def get_preference(key: str) -> str:
    val = _get_mem().get_pref(key)
    return f"{key} = {val}" if val else f"No preference set for '{key}'"


def register_memory_tools(registry: ToolRegistry, memory=None):
    if memory is not None:
        set_memory_backend(memory)

    registry.register(
        "save_memory",
        save_memory,
        "Save a fact or note to long-term memory",
        {
            "content": {"type": "string", "description": "What to remember", "required": True},
            "category": {"type": "string", "description": "Category tag (default: general)"},
        },
    )
    registry.register(
        "search_memory",
        search_memory,
        "Search long-term memory for relevant information",
        {"query": {"type": "string", "description": "Search query", "required": True}},
    )
    registry.register(
        "set_preference",
        set_preference,
        "Save a user preference (e.g. favorite browser, default city)",
        {
            "key": {"type": "string", "description": "Preference key", "required": True},
            "value": {"type": "string", "description": "Preference value", "required": True},
        },
    )
    registry.register(
        "get_preference",
        get_preference,
        "Retrieve a stored user preference",
        {"key": {"type": "string", "description": "Preference key", "required": True}},
    )
