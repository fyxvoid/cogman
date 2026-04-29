"""
Context compressor — ported from Hermes Agent agent/context_compressor.py.

Auto-compresses conversation context when approaching the context window limit.
Uses an LLM to summarize middle turns while protecting head + tail.

Algorithm:
  1. Pre-pass: prune old tool results (no LLM needed)
  2. Protect head (system equivalents) + tail (recent N messages)
  3. Summarize middle with structured template:
     - Summary, Resolved Questions, Pending Questions, Active Task, Files Touched
  4. Replace middle with summary message
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any, Dict, List, Optional

log = logging.getLogger("cogman.compressor")

SUMMARY_PREFIX = (
    "[CONTEXT COMPACTION — REFERENCE ONLY] Earlier turns were compacted "
    "into the summary below. This is a handoff from a previous context window. "
    "Treat it as background reference, NOT active instructions. "
    "Do NOT re-execute anything mentioned in the summary. "
    "Resume from the '## Active Task' section. "
    "Respond ONLY to the latest user message after this summary:"
)

SUMMARY_TEMPLATE = """Summarize the conversation so far into this exact structure:

## Summary
<2-3 sentence overview of what was accomplished>

## Resolved Questions
<bullet list of questions/tasks that are DONE>

## Pending Questions
<bullet list of open questions or issues NOT yet resolved>

## Active Task
<the current task the user is working on>

## Files / Resources Touched
<list of files, URLs, services modified or discussed>

Be concise. Focus on facts, not conversation style. Omit pleasantries."""

_CHARS_PER_TOKEN = 4
_TAIL_PROTECT_TOKENS = 2000
_HEAD_PROTECT_MESSAGES = 2
_MIN_MESSAGES_TO_COMPRESS = 6
_PRUNED_PLACEHOLDER = "[Old tool output cleared to save context space]"


class ContextCompressor:
    """
    Compresses long conversations using an auxiliary LLM call.
    Falls back to truncation if no LLM is available.
    """

    def __init__(self, aux_provider=None):
        """
        aux_provider: optional LLMProvider to use for summarization.
        If None, will try to detect from environment.
        """
        self._provider = aux_provider
        self._last_summary: Optional[str] = None

    def _get_provider(self):
        if self._provider:
            return self._provider
        try:
            from core.pi_agent import ProviderRegistry
            reg = ProviderRegistry()
            return reg.best_available()
        except Exception:
            return None

    def should_compress(self, messages: List[Dict], context_limit_tokens: int = 100_000) -> bool:
        """Return True if compression is warranted."""
        total_chars = sum(
            len(str(m.get("content", ""))) for m in messages
        )
        total_tokens_est = total_chars // _CHARS_PER_TOKEN
        return (
            len(messages) > _MIN_MESSAGES_TO_COMPRESS
            and total_tokens_est > context_limit_tokens * 0.75
        )

    def compress(
        self,
        messages: List[Dict],
        focus_topic: Optional[str] = None,
        context_limit_tokens: int = 100_000,
    ) -> List[Dict]:
        """
        Compress messages. Returns new (shorter) message list.
        Protects head (first N messages) and tail (last N tokens).
        """
        if len(messages) <= _MIN_MESSAGES_TO_COMPRESS:
            return messages

        # Step 1: Prune old tool outputs (cheap, no LLM)
        messages = self._prune_tool_outputs(messages)

        # Step 2: Identify protected head and tail
        head = messages[:_HEAD_PROTECT_MESSAGES]
        tail_chars = _TAIL_PROTECT_TOKENS * _CHARS_PER_TOKEN
        tail, middle = self._split_tail(messages[_HEAD_PROTECT_MESSAGES:], tail_chars)

        if not middle:
            return messages  # nothing to compress

        # Step 3: Summarize middle
        summary_text = self._summarize(middle, focus_topic)
        if not summary_text:
            # Fallback: just drop middle
            log.warning("Summarization failed — truncating middle")
            return head + tail

        # Step 4: Build summary message
        if self._last_summary:
            # Iterative: prepend previous summary
            full_summary = f"{self._last_summary}\n\n---\nUpdate:\n{summary_text}"
        else:
            full_summary = summary_text

        self._last_summary = full_summary

        summary_msg = {
            "role": "user",
            "content": f"{SUMMARY_PREFIX}\n\n{full_summary}",
        }
        # Add a brief assistant ack so the history is valid
        ack_msg = {
            "role": "assistant",
            "content": "Understood. I have the context summary. What would you like to continue with?",
        }

        compressed = head + [summary_msg, ack_msg] + tail
        log.info(
            "Compressed: %d → %d messages (saved %d)",
            len(messages), len(compressed), len(messages) - len(compressed),
        )
        return compressed

    def _prune_tool_outputs(self, messages: List[Dict]) -> List[Dict]:
        """Replace old tool outputs with a placeholder to save tokens."""
        result = list(messages)
        # Keep last 4 tool results intact; prune older ones
        tool_result_indices = [
            i for i, m in enumerate(result)
            if m.get("role") in ("tool",) or
               (isinstance(m.get("content"), list) and
                any(c.get("type") == "tool_result" for c in m["content"] if isinstance(c, dict)))
        ]
        to_prune = tool_result_indices[:-4]  # keep last 4
        for i in to_prune:
            msg = dict(result[i])
            if isinstance(msg.get("content"), str) and len(msg["content"]) > 200:
                msg["content"] = _PRUNED_PLACEHOLDER
            elif isinstance(msg.get("content"), list):
                new_content = []
                for part in msg["content"]:
                    if isinstance(part, dict) and part.get("type") == "tool_result":
                        new_content.append({**part, "content": _PRUNED_PLACEHOLDER})
                    else:
                        new_content.append(part)
                msg["content"] = new_content
            result[i] = msg
        return result

    def _split_tail(self, messages: List[Dict], tail_chars: int):
        """Split messages into (tail, middle) protecting last tail_chars chars."""
        tail = []
        chars = 0
        for msg in reversed(messages):
            content = msg.get("content", "")
            msg_chars = len(str(content))
            if chars + msg_chars > tail_chars and tail:
                break
            tail.insert(0, msg)
            chars += msg_chars

        middle = messages[: len(messages) - len(tail)]
        return tail, middle

    def _summarize(self, messages: List[Dict], focus_topic: Optional[str] = None) -> Optional[str]:
        """Call LLM to summarize the given messages."""
        provider = self._get_provider()
        if not provider:
            return self._simple_summarize(messages)

        # Build a readable transcript of the middle
        transcript_lines = []
        for m in messages:
            role = m.get("role", "?")
            content = m.get("content", "")
            if isinstance(content, list):
                parts = []
                for part in content:
                    if isinstance(part, dict):
                        if part.get("type") == "text":
                            parts.append(part.get("text", ""))
                        elif part.get("type") == "tool_use":
                            parts.append(f"[Tool: {part.get('name')}({json.dumps(part.get('input', {}))[:100]})]")
                        elif part.get("type") == "tool_result":
                            r = str(part.get("content", ""))
                            parts.append(f"[Result: {r[:200]}]")
                content = " ".join(parts)
            if content:
                transcript_lines.append(f"{role.upper()}: {str(content)[:500]}")

        transcript = "\n".join(transcript_lines)
        if not transcript:
            return None

        focus = f"\nFocus especially on: {focus_topic}" if focus_topic else ""
        prompt = f"{SUMMARY_TEMPLATE}{focus}\n\nConversation:\n{transcript}"

        try:
            result = provider.chat_with_tools(
                messages=[{"role": "user", "content": prompt}],
                system="You are a concise technical summarizer. Be factual and brief.",
                tools=[],
                max_tokens=1500,
            )
            return result.get("text", "").strip() or None
        except Exception as e:
            log.error("Summarization LLM call failed: %s", e)
            return self._simple_summarize(messages)

    def _simple_summarize(self, messages: List[Dict]) -> str:
        """Fallback: extract key lines without LLM."""
        lines = [f"[Summarized {len(messages)} messages]"]
        for m in messages[-6:]:
            role = m.get("role", "?")
            content = str(m.get("content", ""))[:150]
            lines.append(f"{role}: {content}...")
        return "\n".join(lines)
