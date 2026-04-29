"""
PostInteractionLearner — self-learning after every interaction.

After each LLM response:
  1. Extract learnings (user facts, preferences, task outcomes)
  2. Auto-save to long-term memory
  3. Track tool usage patterns for skill evolution
  4. Identify when a task pattern repeats (trigger evolution)

Learnings are extracted either by a fast LLM call or by rule-based patterns
(so it works without an LLM provider too).
"""
from __future__ import annotations

import logging
import re
import threading
import time
from typing import Dict, List, Optional, Tuple

log = logging.getLogger("cogman.learner")

# Patterns that indicate learnable facts from conversation
_PREFERENCE_PATTERNS = [
    r"i (?:prefer|like|want|always|usually|always use) (.{5,80})",
    r"my (?:preferred|favourite|default) (.{5,80}) is (.{2,50})",
    r"use (.{3,40}) instead of (.{3,40})",
    r"don'?t (?:use|do|show) (.{5,80})",
    r"always (?:use|run|do) (.{5,80})",
    r"remember that (.{10,150})",
    r"my name is (\w+)",
    r"i work (?:on|with|at|for) (.{5,80})",
    r"i'?m (?:a|an) (.{5,60})",
]

_FACT_PATTERNS = [
    r"my (?:project|app|service) is called (.{3,60})",
    r"the (?:server|database|api) (?:is|runs) (?:on|at) (.{5,80})",
    r"my (?:api|token|key) (?:prefix|pattern) is (.{3,40})",
]


class PostInteractionLearner:
    """
    Runs after each successful interaction to extract and save learnings.
    Uses background thread to not block responses.
    """

    def __init__(self, memory, provider_registry=None, min_response_len: int = 50):
        self.memory = memory
        self.providers = provider_registry
        self.min_response_len = min_response_len
        self._queue: List[Dict] = []
        self._lock = threading.Lock()
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._running = True
        self._thread.start()

    def learn_from(self, user_input: str, response: str, tools_used: List[str] = None):
        """Queue a learning task (non-blocking)."""
        if len(response) < self.min_response_len:
            return
        with self._lock:
            self._queue.append({
                "user_input": user_input,
                "response": response,
                "tools_used": tools_used or [],
                "timestamp": time.time(),
            })

    def _worker(self):
        while self._running:
            item = None
            with self._lock:
                if self._queue:
                    item = self._queue.pop(0)
            if item:
                try:
                    self._process(item)
                except Exception as e:
                    log.debug("Learner error: %s", e)
            else:
                time.sleep(2)

    def _process(self, item: Dict):
        user_input = item["user_input"]
        response = item["response"]
        tools_used = item["tools_used"]

        # 1. Rule-based extraction (works without LLM)
        learnings = self._extract_rule_based(user_input, response)

        # 2. Tool pattern tracking
        if tools_used:
            pattern_key = self._classify_task(user_input)
            count = self.memory.long.record_task_pattern(pattern_key, tools_used)
            log.debug("Task pattern '%s' seen %d times, tools: %s", pattern_key, count, tools_used)

        # 3. LLM-based extraction (background, only if provider available)
        if len(user_input) > 30 and len(response) > 100:
            llm_learnings = self._extract_with_llm(user_input, response)
            learnings.extend(llm_learnings)

        # 4. Save learnings to long-term memory
        for learning in learnings:
            category = learning.get("category", "general")
            content = learning.get("content", "")
            if content and len(content) > 5:
                self.memory.long.save(content, category=category, metadata={
                    "source": "auto_learn",
                    "from_input": user_input[:100],
                })
                log.debug("Learned [%s]: %s", category, content[:80])

    def _extract_rule_based(self, user_input: str, response: str) -> List[Dict]:
        """Extract learnings using regex patterns — no LLM needed."""
        learnings = []
        text = user_input.lower()

        # Preferences
        for pat in _PREFERENCE_PATTERNS:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                content = f"User preference: {user_input.strip()}"
                learnings.append({"category": "preference", "content": content})
                break

        # Facts
        for pat in _FACT_PATTERNS:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                content = f"System fact: {user_input.strip()}"
                learnings.append({"category": "fact", "content": content})
                break

        # Task success (if response is substantial and positive)
        if len(response) > 200 and not any(w in response.lower() for w in ["error", "failed", "cannot", "unable"]):
            task_type = self._classify_task(user_input)
            if task_type != "general":
                learnings.append({
                    "category": "task_success",
                    "content": f"Successfully completed {task_type}: {user_input[:100]}",
                })

        return learnings

    def _extract_with_llm(self, user_input: str, response: str) -> List[Dict]:
        """Use LLM to extract structured learnings from the conversation."""
        if not self.providers:
            return []
        provider = self.providers.best_available()
        if not provider:
            return []

        prompt = f"""Extract any learnable facts from this conversation exchange.
Return JSON array of objects with 'category' and 'content' keys.
Categories: preference, fact, skill_needed, user_info, system_config

Only include SPECIFIC, REUSABLE information. Skip generic exchanges.
Return [] if nothing worth learning.

User: {user_input[:300]}
Assistant: {response[:500]}

JSON array:"""

        try:
            result = provider.chat_with_tools(
                messages=[{"role": "user", "content": prompt}],
                system="You are a concise fact extractor. Output only valid JSON.",
                tools=[], max_tokens=300,
            )
            text = result.get("text", "").strip()
            # Extract JSON from response
            json_match = re.search(r'\[.*?\]', text, re.DOTALL)
            if json_match:
                import json
                items = json.loads(json_match.group())
                return [i for i in items if isinstance(i, dict) and i.get("content")]
        except Exception as e:
            log.debug("LLM extraction failed: %s", e)
        return []

    def _classify_task(self, text: str) -> str:
        """Classify the type of task from user input."""
        text = text.lower()
        if any(w in text for w in ["git", "commit", "push", "pull", "branch", "merge"]):
            return "git_operation"
        if any(w in text for w in ["docker", "container", "image", "compose"]):
            return "docker_operation"
        if any(w in text for w in ["install", "apt", "pip", "npm", "package"]):
            return "package_management"
        if any(w in text for w in ["file", "read", "write", "copy", "move", "delete"]):
            return "file_operation"
        if any(w in text for w in ["python", "script", "code", "run", "execute"]):
            return "code_execution"
        if any(w in text for w in ["search", "find", "look", "google", "web"]):
            return "search"
        if any(w in text for w in ["service", "systemd", "start", "stop", "restart"]):
            return "service_management"
        if any(w in text for w in ["network", "ip", "ping", "port", "wifi"]):
            return "network"
        return "general"

    def stop(self):
        self._running = False
