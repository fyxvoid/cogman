"""
Slash command registry for COGMAN.

Single source of truth for all /commands. Every consumer (CLI, gateway,
autocomplete, help) derives from COMMAND_REGISTRY.

Add a command: add a CommandDef to COMMAND_REGISTRY.
Add an alias:  set aliases=("short",) on the existing CommandDef.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple


@dataclass(frozen=True)
class CommandDef:
    name: str                          # canonical name without slash: "new"
    description: str
    category: str                      # "Session", "Memory", "Skills", etc.
    aliases: Tuple[str, ...] = ()
    args_hint: str = ""                # shown in help: "<topic>", "[n]"
    cli_only: bool = False
    gateway_only: bool = False
    handler: Optional[str] = None      # name of handler fn in CommandDispatcher


COMMAND_REGISTRY: List[CommandDef] = [
    # ── Session ──────────────────────────────────────────────────────────────
    CommandDef("new",      "Start a fresh session (clear context)",        "Session", aliases=("reset",)),
    CommandDef("clear",    "Clear screen and start fresh",                 "Session", cli_only=True),
    CommandDef("history",  "Show conversation history",                    "Session", cli_only=True),
    CommandDef("save",     "Save current conversation to file",            "Session", args_hint="[filename]"),
    CommandDef("retry",    "Resend the last user message",                 "Session"),
    CommandDef("undo",     "Remove last user/assistant exchange",          "Session"),
    CommandDef("branch",   "Branch this session (explore alternate path)", "Session", aliases=("fork",), args_hint="[name]"),
    CommandDef("rollback", "List or restore session checkpoints",          "Session", args_hint="[number]"),
    CommandDef("compress", "Compress conversation context",                "Session", args_hint="[topic]"),
    CommandDef("search",   "Search conversation history (FTS)",            "Session", args_hint="<query>"),
    CommandDef("export",   "Export conversation as markdown/JSON",         "Session", args_hint="[format]"),

    # ── Model / Provider ─────────────────────────────────────────────────────
    CommandDef("model",    "Show or switch active LLM model/provider",     "Model",   args_hint="[provider:model]"),
    CommandDef("status",   "Show all provider/tool/tier status",           "Model"),
    CommandDef("providers","List available LLM providers",                 "Model"),

    # ── Memory ───────────────────────────────────────────────────────────────
    CommandDef("remember", "Save something to long-term memory",           "Memory",  args_hint="<text>"),
    CommandDef("forget",   "Delete a memory by search term",               "Memory",  args_hint="<query>"),
    CommandDef("recall",   "Search long-term memory",                      "Memory",  args_hint="<query>"),
    CommandDef("memories", "Show recent memories",                         "Memory",  args_hint="[n]"),
    CommandDef("pref",     "Get or set a persistent preference",           "Memory",  args_hint="<key> [value]"),

    # ── Skills ───────────────────────────────────────────────────────────────
    CommandDef("skills",   "List, install, show, or create skills",        "Skills",  args_hint="[list|show|create|delete] [name]"),

    # ── Plugins ──────────────────────────────────────────────────────────────
    CommandDef("plugins",  "List loaded plugins and their hooks",          "Plugins"),
    CommandDef("reload",   "Hot-reload plugins and skills",                "Plugins"),

    # ── Planning / Tasks ─────────────────────────────────────────────────────
    CommandDef("plan",     "Ask cogman to write an execution plan",        "Tasks",   args_hint="<goal>"),
    CommandDef("tasks",    "Show background task queue",                   "Tasks"),
    CommandDef("kill",     "Cancel a background task",                     "Tasks",   args_hint="<task_id>"),

    # ── System ───────────────────────────────────────────────────────────────
    CommandDef("help",     "Show all commands or help for one",            "System",  args_hint="[command]"),
    CommandDef("tools",    "List all registered tools",                    "System"),
    CommandDef("version",  "Show cogman version",                          "System"),
    CommandDef("debug",    "Toggle debug logging",                         "System"),
]

# Build lookup maps
_BY_NAME: Dict[str, CommandDef] = {}
_BY_ALIAS: Dict[str, CommandDef] = {}

for _cmd in COMMAND_REGISTRY:
    _BY_NAME[_cmd.name] = _cmd
    for _alias in _cmd.aliases:
        _BY_ALIAS[_alias] = _cmd


def resolve_command(text: str) -> Optional[Tuple[CommandDef, str]]:
    """
    Parse a slash command from user input.

    Returns (CommandDef, args_string) or None if not a slash command.
    """
    text = text.strip()
    if not text.startswith("/"):
        return None

    parts = text[1:].split(None, 1)
    if not parts:
        return None

    name = parts[0].lower()
    args = parts[1] if len(parts) > 1 else ""

    cmd = _BY_NAME.get(name) or _BY_ALIAS.get(name)
    return (cmd, args) if cmd else None


def gateway_help_lines(gateway_only: bool = False) -> List[str]:
    """Return formatted help lines for gateway display."""
    lines = []
    current_cat = None
    for cmd in COMMAND_REGISTRY:
        if cmd.cli_only:
            continue
        if gateway_only and not cmd.gateway_only:
            pass  # include all non-cli-only commands in gateway
        if cmd.category != current_cat:
            if lines:
                lines.append("")
            lines.append(f"*{cmd.category}*")
            current_cat = cmd.category
        hint = f" `{cmd.args_hint}`" if cmd.args_hint else ""
        aliases = f" (also: /{', /'.join(cmd.aliases)})" if cmd.aliases else ""
        lines.append(f"/{cmd.name}{hint} — {cmd.description}{aliases}")
    return lines


def cli_help_text() -> str:
    """Return formatted help for CLI display."""
    lines = ["", "Slash commands:"]
    current_cat = None
    for cmd in COMMAND_REGISTRY:
        if cmd.gateway_only:
            continue
        if cmd.category != current_cat:
            lines.append(f"\n  {cmd.category}:")
            current_cat = cmd.category
        hint = f" {cmd.args_hint}" if cmd.args_hint else ""
        lines.append(f"    /{cmd.name:<14}{hint:<20}  {cmd.description}")
    lines.append("")
    return "\n".join(lines)


# ── Command dispatcher ────────────────────────────────────────────────────────

class CommandDispatcher:
    """
    Handles slash command execution. Wired up to orchestrator and memory.
    """

    def __init__(self, orchestrator, memory, registry, session_mgr=None, plugin_engine=None, skill_registry=None):
        self.orch = orchestrator
        self.memory = memory
        self.registry = registry
        self.session = session_mgr
        self.plugins = plugin_engine
        self.skills = skill_registry

    def dispatch(self, cmd: CommandDef, args: str) -> str:
        handler = getattr(self, f"_cmd_{cmd.name}", None)
        if handler:
            try:
                return handler(args.strip())
            except Exception as e:
                return f"Command error: {e}"
        return f"/{cmd.name}: not yet implemented."

    # ── Session commands ──────────────────────────────────────────────────────

    def _cmd_new(self, args: str) -> str:
        self.memory.short.clear()
        if self.session:
            self.session.new_session()
        return "New session started. Context cleared."

    def _cmd_clear(self, args: str) -> str:
        self.memory.short.clear()
        return "CLEAR_SCREEN"  # signal to main loop to clear terminal

    def _cmd_history(self, args: str) -> str:
        msgs = self.memory.short.get()
        if not msgs:
            return "No conversation history."
        lines = []
        for i, m in enumerate(msgs):
            role = "you" if m["role"] == "user" else "cogman"
            content = m["content"]
            if len(content) > 200:
                content = content[:200] + "..."
            lines.append(f"[{i+1}] {role}: {content}")
        return "\n".join(lines)

    def _cmd_save(self, args: str) -> str:
        import json, time
        filename = args or f"cogman_session_{int(time.time())}.json"
        msgs = self.memory.short.get()
        try:
            with open(filename, "w") as f:
                json.dump(msgs, f, indent=2)
            return f"Saved {len(msgs)} messages to {filename}"
        except Exception as e:
            return f"Save failed: {e}"

    def _cmd_search(self, args: str) -> str:
        if not args:
            return "Usage: /search <query>"
        if self.session:
            results = self.session.search(args)
            if not results:
                return f"No results for: {args}"
            lines = [f"Found {len(results)} result(s) for '{args}':"]
            for r in results[:5]:
                lines.append(f"  [{r.get('session_id','?')}] {r.get('snippet','')[:100]}")
            return "\n".join(lines)
        results = self.memory.recall(args)
        if not results:
            return f"No memories matching: {args}"
        return "\n".join(f"  - {r}" for r in results)

    def _cmd_compress(self, args: str) -> str:
        try:
            from core.context_compressor import ContextCompressor
            compressor = ContextCompressor()
            msgs = self.memory.short.get()
            compressed = compressor.compress(msgs, focus_topic=args or None)
            self.memory.short._messages = compressed
            saved = len(msgs) - len(compressed)
            return f"Context compressed: {len(msgs)} → {len(compressed)} messages (saved {saved})."
        except ImportError:
            return "Context compressor not available."

    def _cmd_branch(self, args: str) -> str:
        if self.session:
            name = args or None
            bid = self.session.branch(name)
            return f"Branched session: {bid}"
        return "Session manager not available."

    def _cmd_export(self, args: str) -> str:
        import json, time
        fmt = args.lower() if args else "markdown"
        msgs = self.memory.short.get()
        if fmt == "json":
            filename = f"cogman_export_{int(time.time())}.json"
            with open(filename, "w") as f:
                json.dump(msgs, f, indent=2)
            return f"Exported to {filename}"
        else:
            filename = f"cogman_export_{int(time.time())}.md"
            lines = ["# cogman Conversation\n"]
            for m in msgs:
                role = "**You**" if m["role"] == "user" else "**cogman**"
                lines.append(f"{role}\n\n{m['content']}\n\n---\n")
            with open(filename, "w") as f:
                f.write("\n".join(lines))
            return f"Exported to {filename}"

    def _cmd_rollback(self, args: str) -> str:
        if self.session:
            return self.session.rollback(args)
        return "Session manager not available."

    def _cmd_retry(self, args: str) -> str:
        msgs = self.memory.short.get()
        last_user = next((m["content"] for m in reversed(msgs) if m["role"] == "user"), None)
        if not last_user:
            return "No previous message to retry."
        # Remove last exchange
        while msgs and msgs[-1]["role"] == "assistant":
            msgs.pop()
        if msgs and msgs[-1]["role"] == "user":
            msgs.pop()
        self.memory.short._messages = msgs
        return f"RETRY:{last_user}"  # signal to main loop

    def _cmd_undo(self, args: str) -> str:
        msgs = self.memory.short._messages
        removed = 0
        while msgs and msgs[-1]["role"] == "assistant":
            msgs.pop()
            removed += 1
        if msgs and msgs[-1]["role"] == "user":
            msgs.pop()
            removed += 1
        return f"Removed last exchange ({removed} messages)."

    # ── Model commands ────────────────────────────────────────────────────────

    def _cmd_model(self, args: str) -> str:
        if hasattr(self.orch, 'pi') and self.orch.pi:
            providers = self.orch.pi.providers
            if args:
                parts = args.split(":", 1)
                pname = parts[0]
                new_model = parts[1] if len(parts) > 1 else None
                p = providers.get(pname)
                if not p:
                    return f"Unknown provider: {pname}. Available: {providers.list_available()}"
                self.orch.pi.preferred_provider = pname
                if new_model:
                    p._model = new_model
                return f"Switched to {pname}" + (f":{new_model}" if new_model else "")
            available = providers.list_available()
            lines = [f"Active: {self.orch.pi.preferred_provider or 'auto'}", "Available:"]
            lines.append(providers.summary())
            return "\n".join(lines)
        return "Pi agent not active."

    def _cmd_status(self, args: str) -> str:
        if hasattr(self.orch, 'print_status'):
            return self.orch.print_status()
        return "Status not available."

    def _cmd_providers(self, args: str) -> str:
        if hasattr(self.orch, 'pi') and self.orch.pi:
            return "LLM Providers:\n" + self.orch.pi.providers.summary()
        return "Pi agent not initialized."

    # ── Memory commands ───────────────────────────────────────────────────────

    def _cmd_remember(self, args: str) -> str:
        if not args:
            return "Usage: /remember <text>"
        self.memory.remember(args)
        return f"Saved to long-term memory: {args[:80]}"

    def _cmd_forget(self, args: str) -> str:
        if not args:
            return "Usage: /forget <query>"
        count = self.memory.long.delete_matching(args)
        return f"Deleted {count} memories matching: {args}"

    def _cmd_recall(self, args: str) -> str:
        if not args:
            return "Usage: /recall <query>"
        results = self.memory.recall(args)
        if not results:
            return f"No memories for: {args}"
        return "\n".join(f"  • {r}" for r in results)

    def _cmd_memories(self, args: str) -> str:
        n = int(args) if args.isdigit() else 10
        recent = self.memory.long.recent(n)
        if not recent:
            return "No memories stored yet."
        lines = [f"Recent {n} memories:"]
        for m in recent:
            import time
            ts = time.strftime("%Y-%m-%d %H:%M", time.localtime(m["timestamp"]))
            lines.append(f"  [{ts}] [{m['category']}] {m['content'][:100]}")
        return "\n".join(lines)

    def _cmd_pref(self, args: str) -> str:
        if not args:
            return "Usage: /pref <key> [value]"
        parts = args.split(None, 1)
        key = parts[0]
        if len(parts) == 1:
            val = self.memory.get_pref(key)
            return f"{key} = {val!r}" if val else f"No preference set for: {key}"
        else:
            self.memory.set_pref(key, parts[1])
            return f"Set {key} = {parts[1]!r}"

    # ── Skills commands ───────────────────────────────────────────────────────

    def _cmd_skills(self, args: str) -> str:
        if self.skills:
            return self.skills.handle_command(args)
        return "Skill system not initialized."

    # ── Plugin commands ───────────────────────────────────────────────────────

    def _cmd_plugins(self, args: str) -> str:
        if self.plugins:
            return self.plugins.status()
        return "Plugin engine not initialized."

    def _cmd_reload(self, args: str) -> str:
        count = 0
        if self.plugins:
            count += self.plugins.reload()
        if self.skills:
            count += self.skills.reload()
        return f"Reloaded {count} plugins/skills."

    # ── Task/plan commands ────────────────────────────────────────────────────

    def _cmd_plan(self, args: str) -> str:
        if not args:
            return "Usage: /plan <goal>"
        return self.orch.process(
            f"Write a step-by-step execution plan for: {args}\n"
            "Format as numbered list. Be specific and actionable."
        )

    def _cmd_tasks(self, args: str) -> str:
        from tools.process_tools import top_processes
        return top_processes()

    def _cmd_kill(self, args: str) -> str:
        if not args:
            return "Usage: /kill <pid>"
        from tools.process_tools import send_signal
        return send_signal(args, "TERM")

    # ── System commands ───────────────────────────────────────────────────────

    def _cmd_help(self, args: str) -> str:
        if args:
            cmd = _BY_NAME.get(args.lstrip("/")) or _BY_ALIAS.get(args.lstrip("/"))
            if cmd:
                hint = f"\n  Args: {cmd.args_hint}" if cmd.args_hint else ""
                aliases = f"\n  Aliases: /{', /'.join(cmd.aliases)}" if cmd.aliases else ""
                return f"/{cmd.name} [{cmd.category}]\n  {cmd.description}{hint}{aliases}"
            return f"Unknown command: {args}"
        return cli_help_text()

    def _cmd_tools(self, args: str) -> str:
        return self.registry.summary()

    def _cmd_version(self, args: str) -> str:
        return "cogman — self-learning Linux AI assistant"

    def _cmd_debug(self, args: str) -> str:
        import logging
        root = logging.getLogger("cogman")
        if root.level == logging.DEBUG:
            root.setLevel(logging.WARNING)
            return "Debug logging OFF."
        else:
            root.setLevel(logging.DEBUG)
            return "Debug logging ON."
