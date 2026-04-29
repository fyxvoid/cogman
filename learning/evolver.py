"""
SkillEvolver — self-evolution: auto-creates and improves skills from experience.

Triggers:
  1. Pattern repeat (≥3 times) → auto-generate a skill for it
  2. Skill failure → auto-fix with LLM
  3. Background sweep (every 10 min) → review patterns, improve weak skills

The evolver reads task_patterns from the memory DB to find what to evolve.
"""
from __future__ import annotations

import logging
import re
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional

log = logging.getLogger("cogman.evolver")

_EVOLVE_THRESHOLD = 3    # min pattern count before auto-skill
_SWEEP_INTERVAL  = 600   # seconds between background sweeps


class SkillEvolver:
    """
    Watches task patterns and automatically creates/improves skills.
    Runs a background thread for periodic evolution.
    """

    def __init__(self, memory, skill_registry, provider_registry=None):
        self.memory = memory
        self.skills = skill_registry
        self.providers = provider_registry
        self._evolved: set = set()          # patterns already evolved
        self._running = True
        self._thread = threading.Thread(target=self._sweep_loop, daemon=True)
        self._thread.start()

    # ── Public API ────────────────────────────────────────────────────────────

    def on_skill_failure(self, skill_name: str, error: str, last_args: Dict):
        """Called when a skill fails. Queue an LLM repair."""
        threading.Thread(
            target=self._repair_skill, args=(skill_name, error, last_args), daemon=True
        ).start()

    def check_evolve_now(self):
        """Manually trigger a pattern check."""
        threading.Thread(target=self._evolve_patterns, daemon=True).start()

    def stop(self):
        self._running = False

    # ── Background sweep ──────────────────────────────────────────────────────

    def _sweep_loop(self):
        time.sleep(60)  # let the system settle first
        while self._running:
            try:
                self._evolve_patterns()
            except Exception as e:
                log.debug("Evolution sweep error: %s", e)
            for _ in range(_SWEEP_INTERVAL):
                if not self._running:
                    return
                time.sleep(1)

    # ── Pattern evolution ─────────────────────────────────────────────────────

    def _evolve_patterns(self):
        """Check for frequent task patterns and create skills for them."""
        patterns = self.memory.long.get_frequent_patterns(min_count=_EVOLVE_THRESHOLD)
        for p in patterns:
            key = p["pattern"]
            if key in self._evolved:
                continue
            if self._pattern_already_covered(key):
                self._evolved.add(key)
                continue
            log.info("Evolving pattern '%s' (seen %d times, tools: %s)", key, p["count"], p["tool_sequence"])
            skill = self._generate_skill_for_pattern(key, p["tool_sequence"], p["count"])
            if skill:
                self._evolved.add(key)
                log.info("Created skill from pattern: %s", skill.name)

    def _pattern_already_covered(self, pattern: str) -> bool:
        """Check if an existing skill already handles this pattern."""
        results = self.skills.search(pattern)
        return len(results) > 0

    def _generate_skill_for_pattern(self, pattern: str, tool_sequence: List[str], count: int):
        """Ask LLM to create a skill for a recurring task pattern."""
        provider = self.providers.best_available() if self.providers else None
        if not provider:
            return None

        tools_desc = ", ".join(tool_sequence)
        prompt = f"""Create a Python skill for cogman to automate this recurring task pattern.

Pattern: {pattern}
Tools typically used: {tools_desc}
Times seen: {count}

Requirements:
1. Start with these header comments (exactly):
   # skill: <snake_case_name>
   # description: <what it does in one sentence>
   # tags: <comma,separated,tags>
   # version: 1.0

2. Define: def run(**kwargs) -> str:
3. The skill should automate the entire {pattern} workflow
4. Return a clear string result
5. Handle errors with try/except
6. Keep it focused and reusable

Return ONLY the Python code block (```python ... ```)"""

        try:
            result = provider.chat_with_tools(
                messages=[{"role": "user", "content": prompt}],
                system="You are an expert Python developer creating reusable automation skills.",
                tools=[], max_tokens=800,
            )
            code_text = result.get("text", "")
            return self._save_skill_from_response(code_text)
        except Exception as e:
            log.error("Skill generation failed: %s", e)
            return None

    def _save_skill_from_response(self, response: str):
        """Parse and save a skill from LLM response."""
        match = re.search(r"```python\s*(# skill:.+?)```", response, re.DOTALL)
        if not match:
            # Try without code fence
            match = re.search(r"(# skill:\s*\S+.+?def run\(.+?\)\s*->.*?(?:\n\n|\Z))", response, re.DOTALL)
        if not match:
            return None

        code = match.group(1).strip()
        name_m = re.search(r"# skill:\s*(\S+)", code)
        desc_m = re.search(r"# description:\s*(.+)", code)
        tags_m = re.search(r"# tags:\s*(.+)", code)

        if not name_m:
            return None

        name = name_m.group(1).strip()
        description = desc_m.group(1).strip() if desc_m else name
        tags = [t.strip() for t in tags_m.group(1).split(",")] if tags_m else ["auto"]

        # Strip header from code body
        body_lines = [l for l in code.splitlines() if not l.startswith("#")]
        body = "\n".join(body_lines).strip()

        if "def run(" not in body:
            return None

        try:
            return self.skills.create_skill(name, description, body, tags + ["auto_evolved"])
        except Exception as e:
            log.error("Skill save failed: %s", e)
            return None

    # ── Skill repair ──────────────────────────────────────────────────────────

    def _repair_skill(self, skill_name: str, error: str, last_args: Dict):
        """Use LLM to fix a broken skill."""
        skill = self.skills.get(skill_name)
        if not skill or not skill.path:
            return

        provider = self.providers.best_available() if self.providers else None
        if not provider:
            return

        try:
            current_code = skill.path.read_text()
        except Exception:
            return

        import json
        args_str = json.dumps(last_args, indent=2)[:300]
        prompt = f"""Fix this cogman skill. It failed with an error.

Skill: {skill_name}
Error: {error}
Args used: {args_str}

Current code:
```python
{current_code}
```

Return the COMPLETE fixed Python code (```python ... ```).
Keep the same header comments and run() signature. Fix only the bug."""

        try:
            result = provider.chat_with_tools(
                messages=[{"role": "user", "content": prompt}],
                system="You are an expert Python debugger. Fix the skill precisely.",
                tools=[], max_tokens=800,
            )
            fixed_code = result.get("text", "")
            match = re.search(r"```python\s*(# skill:.+?)```", fixed_code, re.DOTALL)
            if match:
                skill.path.write_text(match.group(1).strip())
                # Reload the skill
                self.skills.reload()
                log.info("Repaired skill: %s", skill_name)
                self.memory.long.save(
                    f"Auto-repaired skill '{skill_name}' after error: {error[:100]}",
                    category="skill_repair",
                )
        except Exception as e:
            log.error("Skill repair failed for %s: %s", skill_name, e)
