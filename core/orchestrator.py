"""
Orchestrator — COGMAN 7-stage processing pipeline + self-learning.

Stage 1: Normalize   — clean input, detect slash commands
Stage 2: Route       — Tier 1 regex → Tier 2 NLP → Cognitive loop
Stage 3: Assemble    — memory + environment context + skills
Stage 4: Plugin hook — pre_llm_call
Stage 5: Infer       — multi-provider LLM + tool calling
Stage 6: ReAct       — parallel tool execution
Stage 7: Persist     — save to memory + session + self-learn
"""
import logging
import re
import shlex
from typing import Dict, List, Optional


def _parse_tool_args(text: str) -> Dict:
    """
    Parse tool arguments from text into a dict.
    Handles: key=value, key="multi word", key='multi word', bare positional.

    Examples:
      "city=London"                → {"city": "London"}
      'text=hello world target=es' → {"text": "hello world", "target": "es"}
      'action=add text=some note'  → {"action": "add", "text": "some note"}
    """
    if not text:
        return {}

    result = {}
    # Find all key= positions so we know where each value ends
    key_positions = [(m.start(), m.group(1)) for m in re.finditer(r'(\w+)=', text)]

    if not key_positions:
        # No key=value pairs at all — treat as positional 'args'
        return {"args": text.strip()}

    for i, (pos, key) in enumerate(key_positions):
        val_start = pos + len(key) + 1  # after "key="
        val_end = key_positions[i + 1][0] if i + 1 < len(key_positions) else len(text)
        raw = text[val_start:val_end].strip()
        # Strip surrounding quotes
        if (raw.startswith('"') and raw.endswith('"')) or \
           (raw.startswith("'") and raw.endswith("'")):
            raw = raw[1:-1]
        result[key] = raw

    return result

from core.intent_parser import parse_fast
from core.local_nlp import parse_keywords, parse_fuzzy, suggest_commands
from core.tool_registry import ToolRegistry
from core.safety import log_action
from core.config import SYSTEM_PROMPT
from agents.providers import ProviderRegistry
from agents.loop import CogmanCore as PiAgentCore
from memory.context import EnvironmentContext

log = logging.getLogger("cogman.orchestrator")


class Orchestrator:
    def __init__(self, registry: ToolRegistry, memory):
        self.registry = registry
        self.memory = memory

        # Provider registry + Pi Agent Core
        self._providers = ProviderRegistry()
        self.pi: Optional[PiAgentCore] = None
        self._init_pi()

        # Environment context (injected into every LLM call)
        self._env_ctx = EnvironmentContext()

        # Extensions (wired up by main after construction)
        self.plugin_engine = None
        self.skill_registry = None
        self.session_mgr = None
        self.dispatcher = None
        self.learner = None    # PostInteractionLearner
        self.evolver = None    # SkillEvolver

        # Event listeners (for rich TUI streaming display)
        self._event_listeners = []

        # Track tools used in current turn (for pattern learning)
        self._current_turn_tools: List[str] = []

    def _init_pi(self):
        try:
            self.pi = PiAgentCore(  # cognitive agent loop
                registry=self.registry,
                memory=self.memory,
                system_prompt=SYSTEM_PROMPT,
                provider_registry=self._providers,
                parallel_tools=True,
                max_tool_turns=25,
            )
            self.pi.subscribe(self._on_pi_event)
            log.info("Cognitive loop ready. Providers: %s", self._providers.list_available())
        except Exception as e:
            log.warning("Pi Agent Core init failed: %s", e)

    def _on_pi_event(self, event):
        from agents.events import ToolExecutionEndEvent
        if isinstance(event, ToolExecutionEndEvent):
            self._current_turn_tools.append(event.tool_name)
        for fn in self._event_listeners:
            try:
                fn(event)
            except Exception:
                pass

    def add_event_listener(self, fn):
        self._event_listeners.append(fn)

    # ── Main process ──────────────────────────────────────────────────────────

    def process(self, user_input: str) -> str:
        user_input = user_input.strip()
        if not user_input:
            return ""

        self._current_turn_tools = []

        # Stage 1: Slash command detection
        if user_input.startswith("/") and self.dispatcher:
            from core.command_registry import resolve_command
            result = resolve_command(user_input)
            if result:
                cmd, args = result
                response = self.dispatcher.dispatch(cmd, args)
                if response == "CLEAR_SCREEN":
                    import os; os.system("clear")
                    return ""
                if response and response.startswith("RETRY:"):
                    user_input = response[6:]
                elif response is not None:
                    return response or ""

        # Plugin: check extra commands
        if self.plugin_engine and user_input.startswith("/"):
            name = user_input[1:].split()[0]
            extra = self.plugin_engine.get_extra_command(name)
            if extra:
                handler, _, _ = extra
                try:
                    return str(handler(user_input))
                except Exception as e:
                    return f"Plugin command error: {e}"

        # Stage 1b: Direct skill/tool call (skill_name or skill_name arg=val ...)
        direct = self._try_direct_tool(user_input)
        if direct is not None:
            self.memory.add_message("user", user_input)
            self.memory.add_message("assistant", direct)
            return direct

        # Stage 2: Add to memory
        self.memory.add_message("user", user_input)
        if self.session_mgr:
            self.session_mgr.add_message("user", user_input)

        # Tier 1 — fast regex
        intent = parse_fast(user_input)
        if intent:
            log.debug("Tier 1: %s", intent)
            return self._run_intent(intent)

        # Tier 2a — keyword NLP
        intent = parse_keywords(user_input)
        if intent and intent.confidence >= 0.5:
            log.debug("Tier 2a: %s", intent)
            return self._run_intent(intent)

        # Tier 2b — fuzzy NLP
        intent = parse_fuzzy(user_input, self.registry)
        if intent and intent.confidence >= 0.55:
            log.debug("Tier 2b: %s", intent)
            return self._run_intent(intent)

        # Stage 3: Assemble environment context
        env_context = self._env_ctx.get()

        # Stage 4: Plugin pre_llm hook
        if self.plugin_engine:
            hook_result = self.plugin_engine.invoke_hook_first(
                "pre_llm_call", user_input=user_input, memory=self.memory,
            )
            if isinstance(hook_result, str):
                return hook_result

        # Stage 5-6: Pi Agent Core (infer + ReAct tool loop)
        if self.pi:
            log.debug("Tier 3: Pi Agent (%s)", self._providers.list_available())
            response = self.pi.process(user_input, extra_context=env_context)
        else:
            response = self._suggest_fallback(user_input)

        # Stage 7: Persist + self-learn
        if self.session_mgr and response:
            self.session_mgr.add_message("assistant", response)

        if self.plugin_engine:
            self.plugin_engine.invoke_hook("post_llm_call", user_input=user_input, response=response)

        # Self-learning: extract learnings in background
        if self.learner and response:
            self.learner.learn_from(user_input, response, list(self._current_turn_tools))

        # Auto-detect skill creation in LLM response
        if self.skill_registry and "```python" in response and "# skill:" in response:
            self._try_save_skill_from_response(response)

        # Trigger evolution check if tools were used heavily
        if self.evolver and len(self._current_turn_tools) >= 3:
            self.evolver.check_evolve_now()

        return response

    def _run_intent(self, intent) -> str:
        result = self.registry.run(intent.tool, intent.args)
        log_action(intent.tool, intent.args, result)
        self.memory.add_message("assistant", result)
        return result

    def _try_direct_tool(self, user_input: str):
        """
        Detect bare tool/skill calls typed directly:
          skill_syshealth
          skill_weather city=Tokyo
          run_python code="print(1+1)"
        Returns result string or None if not a direct tool call.
        """
        import re
        # Must start with a known tool name (word chars + underscore)
        m = re.match(r'^([a-z][a-z0-9_]+)(\s+.*)?$', user_input.strip(), re.IGNORECASE)
        if not m:
            return None
        tool_name = m.group(1)
        if not self.registry.get(tool_name):
            return None
        # Parse key=value args from the rest
        args = {}
        rest = (m.group(2) or "").strip()
        if rest:
            args = _parse_tool_args(rest)
            # If no key=value pairs found, map space-separated tokens to params
            if "args" in args and len(args) == 1:
                try:
                    import inspect
                    params = None
                    # Try skill func first, then registered tool
                    if self.skill_registry:
                        skill = self.skill_registry.get(tool_name)
                        if skill and skill.func:
                            params = list(inspect.signature(skill.func).parameters.keys())
                    if not params:
                        tool_obj = self.registry.get(tool_name)
                        if tool_obj and tool_obj.func:
                            params = list(inspect.signature(tool_obj.func).parameters.keys())

                    if params:
                        raw = args["args"]
                        func = None
                        if self.skill_registry:
                            sk = self.skill_registry.get(tool_name)
                            if sk and sk.func:
                                func = sk.func
                        if func is None:
                            tool_obj = self.registry.get(tool_name)
                            if tool_obj:
                                func = tool_obj.func

                        sig = inspect.signature(func) if func else None
                        type_hints = {}
                        if sig:
                            for pname, pobj in sig.parameters.items():
                                if pobj.annotation is not inspect.Parameter.empty:
                                    type_hints[pname] = pobj.annotation

                        def _coerce(name, val):
                            ann = type_hints.get(name)
                            if ann in (int,):
                                try: return int(val)
                                except: pass
                            if ann in (float,):
                                try: return float(val)
                                except: pass
                            if ann is bool:
                                return val.lower() in ("true", "1", "yes")
                            return val

                        if len(params) == 1:
                            args = {params[0]: _coerce(params[0], raw)}
                        else:
                            tokens = raw.split()
                            if len(tokens) >= len(params):
                                mapped = {}
                                for i, p in enumerate(params[:-1]):
                                    mapped[p] = _coerce(p, tokens[i])
                                last = params[-1]
                                mapped[last] = _coerce(last, " ".join(tokens[len(params) - 1:]))
                                args = mapped
                            else:
                                args = {params[i]: _coerce(params[i], tokens[i]) for i in range(len(tokens))}
                except Exception:
                    pass
        log.debug("Direct tool call: %s(%s)", tool_name, args)
        return self.registry.run(tool_name, args)

    def _suggest_fallback(self, user_input: str) -> str:
        suggestions = suggest_commands(user_input, self.registry, top_n=3)
        lines = [f"I didn't understand: {user_input!r}"]
        if suggestions:
            lines.append("Did you mean:")
            for s in suggestions:
                tool = self.registry.get(s)
                if tool:
                    lines.append(f"  • {s}: {tool.description}")
        lines.append("Type /help for commands or ask me anything.")
        result = "\n".join(lines)
        self.memory.add_message("assistant", result)
        return result

    def _try_save_skill_from_response(self, response: str):
        import re
        match = re.search(r"```python\s*(# skill:.+?)```", response, re.DOTALL)
        if not match:
            return
        code = match.group(1).strip()
        name_m = re.search(r"# skill:\s*(\S+)", code)
        if not name_m:
            return
        name = name_m.group(1)
        desc_m = re.search(r"# description:\s*(.+)", code)
        description = desc_m.group(1).strip() if desc_m else name
        tags_m = re.search(r"# tags:\s*(.+)", code)
        tags = [t.strip() for t in tags_m.group(1).split(",")] if tags_m else []
        body_lines = [l for l in code.splitlines() if not l.startswith("#")]
        body = "\n".join(body_lines).strip()
        try:
            skill = self.skill_registry.create_skill(name, description, body, tags)
            if skill:
                self.skill_registry._register_tool(skill, self.registry)
                log.info("Auto-saved new skill: %s", name)
        except Exception as e:
            log.debug("Auto-skill save failed: %s", e)

    # ── Status ────────────────────────────────────────────────────────────────

    def print_status(self) -> str:
        from speech.tts import get_tts_backend, is_tts_available
        from speech.stt import get_stt_backend, is_stt_available

        n_tools   = len(self.registry.list_names())
        n_plugins = len(self.plugin_engine.loaded_names) if self.plugin_engine else 0
        n_skills  = len(self.skill_registry.list()) if self.skill_registry else 0
        n_builtin = sum(1 for s in (self.skill_registry.list() if self.skill_registry else []) if getattr(s, 'is_builtin', False))

        env = self._env_ctx.get()

        lines = [
            "─" * 62,
            " cogman  ·  Self-learning Linux AI Assistant",
            "─" * 62,
            f" Tools      : {n_tools}  |  Plugins: {n_plugins}  |  Skills: {n_skills} ({n_builtin} builtin)",
            "",
            " LLM Providers:",
            self._providers.summary(),
            "",
            " Routing Tiers:",
            "  [✓] Tier 1  Regex rules (instant)",
            "  [✓] Tier 2  Local NLP (keyword + fuzzy)",
            f"  [{'✓' if self.pi else '✗'}] Tier 3  Cognitive loop (multi-provider LLM)",
            "",
            " Self-learning:",
            f"  Learner : {'active' if self.learner else 'not initialized'}",
            f"  Evolver : {'active' if self.evolver else 'not initialized'}",
            "",
            " Voice:",
            f"  TTS: {get_tts_backend()}" + (" (audio)" if is_tts_available() else " (print)"),
            f"  STT: {get_stt_backend()}" + (" (mic)" if is_stt_available() else " (keyboard)"),
            "",
            " Connections:",
            f"  Session : {'✓ FTS5' if self.session_mgr else '✗'}",
            f"  Gateway : Telegram · Discord · Slack · IRC · Webhook  (--gateway)",
            "",
            " Environment:",
        ]
        for line in env.splitlines():
            if line and not line.startswith("<"):
                lines.append(f"  {line}")
        lines.append("─" * 62)
        return "\n".join(lines)

    def interrupt(self):
        if self.pi:
            self.pi.interrupt()

    def _check_ollama(self) -> bool:
        p = self._providers.get("ollama")
        return p.is_available() if p else False
