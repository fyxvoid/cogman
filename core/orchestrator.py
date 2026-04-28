"""
Orchestrator — 4-tier routing, local-first, no API required by default.

Tier 1: Fast regex rules          (instant, zero deps, always on)
Tier 2: Local NLP                 (keyword + fuzzy, zero deps, always on)
Tier 3: Local LLM via Ollama      (optional, fully offline)
Tier 4: Cloud LLM via Anthropic   (optional, requires API key)

Fallback: Suggest closest matching commands.
"""
import logging
from typing import Optional

from core.intent_parser import parse_fast
from core.local_nlp import parse_keywords, parse_fuzzy, suggest_commands
from core.tool_registry import ToolRegistry
from core.memory import Memory
from core.safety import log_action
from core.config import (
    ANTHROPIC_API_KEY, LLM_MODEL, LLM_MAX_TOKENS,
    SYSTEM_PROMPT, OLLAMA_HOST, OLLAMA_MODEL, ENABLE_LOCAL_LLM,
)

log = logging.getLogger("cogman.orchestrator")


class Orchestrator:
    def __init__(self, registry: ToolRegistry, memory: Memory):
        self.registry = registry
        self.memory = memory
        self._anthropic: Optional[object] = None
        self._ollama_ok: Optional[bool] = None
        self._init_clients()

    def _init_clients(self):
        if ANTHROPIC_API_KEY:
            try:
                import anthropic
                self._anthropic = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
                log.info("Cloud LLM (Anthropic) available")
            except ImportError:
                log.debug("anthropic package not installed — cloud LLM disabled")
            except Exception as e:
                log.warning("Anthropic init failed: %s", e)
        else:
            log.info("No ANTHROPIC_API_KEY — running fully local")

    def _check_ollama(self) -> bool:
        if self._ollama_ok is not None:
            return self._ollama_ok
        if not ENABLE_LOCAL_LLM:
            self._ollama_ok = False
            return False
        try:
            import urllib.request
            with urllib.request.urlopen(f"{OLLAMA_HOST}/api/tags", timeout=2) as r:
                self._ollama_ok = r.status == 200
        except Exception:
            self._ollama_ok = False
        if self._ollama_ok:
            log.info("Local LLM (Ollama) available at %s — model: %s", OLLAMA_HOST, OLLAMA_MODEL)
        else:
            log.debug("Ollama not reachable at %s", OLLAMA_HOST)
        return self._ollama_ok

    # ── Public entry point ───────────────────────────────────────────────────

    def process(self, user_input: str) -> str:
        user_input = user_input.strip()
        if not user_input:
            return ""

        self.memory.add_message("user", user_input)

        # Tier 1: Fast regex rules (instant)
        intent = parse_fast(user_input)
        if intent:
            log.debug("Tier 1 (rule): %s", intent)
            return self._run_intent(intent)

        # Tier 2: Local NLP — keyword match
        intent = parse_keywords(user_input)
        if intent and intent.confidence >= 0.5:
            log.debug("Tier 2a (keyword): %s", intent)
            return self._run_intent(intent)

        # Tier 2b: Fuzzy match
        intent = parse_fuzzy(user_input, self.registry)
        if intent and intent.confidence >= 0.55:
            log.debug("Tier 2b (fuzzy): %s", intent)
            return self._run_intent(intent)

        # Tier 3: Local LLM (Ollama — offline)
        if self._check_ollama():
            log.debug("Tier 3: routing to local LLM")
            result = self._ollama_route(user_input)
            if result:
                return result

        # Tier 4: Cloud LLM (Anthropic)
        if self._anthropic:
            log.debug("Tier 4: routing to cloud LLM")
            return self._anthropic_route(user_input)

        # Fallback: suggest similar commands
        return self._suggest_fallback(user_input)

    # ── Intent execution ─────────────────────────────────────────────────────

    def _run_intent(self, intent) -> str:
        result = self.registry.run(intent.tool, intent.args)
        log_action(intent.tool, intent.args, result)
        self.memory.add_message("assistant", result)
        return result

    def _suggest_fallback(self, user_input: str) -> str:
        suggestions = suggest_commands(user_input, self.registry, top_n=3)
        lines = [f"I didn't understand: {user_input!r}"]
        if suggestions:
            lines.append("\nDid you mean one of these?")
            for s in suggestions:
                tool = self.registry.get(s)
                if tool:
                    lines.append(f"  • {s}: {tool.description}")
        lines.append("\nType 'help' to list all commands.")
        result = "\n".join(lines)
        self.memory.add_message("assistant", result)
        return result

    # ── Tier 3: Ollama (local LLM) ───────────────────────────────────────────

    def _ollama_route(self, user_input: str) -> Optional[str]:
        import json, urllib.request

        tools = self.registry.all_schemas()
        memories = self.memory.recall(user_input[:100])
        mem_block = ("\n\nRelevant memories:\n" + "\n".join(f"- {m}" for m in memories)) if memories else ""

        messages = list(self.memory.get_context())
        payload = {
            "model": OLLAMA_MODEL,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT + mem_block},
                *messages,
            ],
            "stream": False,
            "options": {"temperature": 0.1, "num_predict": 512},
        }

        try:
            data = json.dumps(payload).encode()
            req = urllib.request.Request(
                f"{OLLAMA_HOST}/api/chat",
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read())
            text = result.get("message", {}).get("content", "").strip()
            if text:
                self.memory.add_message("assistant", text)
                return text
        except Exception as e:
            log.warning("Ollama request failed: %s", e)

        return None

    # ── Tier 4: Anthropic (cloud LLM) ────────────────────────────────────────

    def _anthropic_route(self, user_input: str) -> str:
        import anthropic

        memories = self.memory.recall(user_input[:100])
        mem_block = ("\n\nRelevant memories:\n" + "\n".join(f"- {m}" for m in memories)) if memories else ""
        system = SYSTEM_PROMPT + mem_block
        messages = list(self.memory.get_context())
        tools = self.registry.all_schemas()

        try:
            response = self._anthropic.messages.create(
                model=LLM_MODEL,
                max_tokens=LLM_MAX_TOKENS,
                system=system,
                tools=tools,
                messages=messages,
            )
        except anthropic.AuthenticationError:
            return "Authentication failed — check your ANTHROPIC_API_KEY."
        except anthropic.RateLimitError:
            return "Rate limited — please wait a moment."
        except Exception as e:
            log.exception("Anthropic call failed")
            return f"LLM error: {e}"

        return self._handle_anthropic_response(response, messages, system, tools)

    def _handle_anthropic_response(self, response, messages, system, tools) -> str:
        final_text = ""

        while True:
            tool_uses = [b for b in response.content if b.type == "tool_use"]

            if not tool_uses:
                for block in response.content:
                    if hasattr(block, "text"):
                        final_text = block.text
                break

            tool_results = []
            for tu in tool_uses:
                log.info("LLM calling tool: %s(%s)", tu.name, tu.input)
                result = self.registry.run(tu.name, tu.input)
                log_action(tu.name, tu.input, result)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tu.id,
                    "content": result,
                })

            messages = messages + [
                {"role": "assistant", "content": response.content},
                {"role": "user", "content": tool_results},
            ]

            try:
                response = self._anthropic.messages.create(
                    model=LLM_MODEL,
                    max_tokens=LLM_MAX_TOKENS,
                    system=system,
                    tools=tools,
                    messages=messages,
                )
            except Exception as e:
                return f"LLM continuation error: {e}"

            if response.stop_reason == "end_turn":
                for block in response.content:
                    if hasattr(block, "text"):
                        final_text = block.text
                break

        self.memory.add_message("assistant", final_text or "(done)")
        return final_text or "(Task completed)"
