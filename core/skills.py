"""
Skill system — composable, auto-discoverable skills for COGMAN.

Skills are Python modules stored in ~/.cogman/skills/ that:
  - Auto-load as callable tools at startup
  - Can be created by the LLM from experience
  - Self-improve through use
  - Are searchable and categorized

Each skill file structure:
  ~/.cogman/skills/<name>.py

  # skill: <name>
  # description: <what it does>
  # tags: tag1, tag2
  # version: 1.0
  # created: 2026-01-01

  def run(**kwargs):
      ...
      return str_result
"""

from __future__ import annotations

import importlib.util
import json
import logging
import os
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

log = logging.getLogger("cogman.skills")

_COGMAN_HOME = Path.home() / ".cogman"
_SKILLS_DIR = _COGMAN_HOME / "skills"
_SKILL_HEADER_RE = re.compile(r"^#\s*(\w[\w-]*):\s*(.+)$")


@dataclass
class Skill:
    name: str
    description: str = ""
    tags: List[str] = field(default_factory=list)
    version: str = "1.0"
    created: str = ""
    path: Optional[Path] = None
    use_count: int = 0
    func: Optional[Callable] = None

    def to_tool_schema(self) -> Dict:
        return {
            "name": f"skill_{self.name}",
            "description": f"[Skill] {self.description}",
            "input_schema": {
                "type": "object",
                "properties": {
                    "args": {"type": "string", "description": "Arguments to pass to the skill"},
                },
                "required": [],
            },
        }


class SkillRegistry:
    """Discovers, loads, and manages skills."""

    def __init__(self, skills_dir: Optional[Path] = None):
        self._dir = skills_dir or _SKILLS_DIR
        self._skills: Dict[str, Skill] = {}
        self._ensure_dir()

    def _ensure_dir(self):
        self._dir.mkdir(parents=True, exist_ok=True)

    def load_all(self, tool_registry=None) -> int:
        """Load all skills from disk. Register with tool registry if provided."""
        count = 0
        for path in sorted(self._dir.glob("*.py")):
            if path.name.startswith("_"):
                continue
            skill = self._load_skill_file(path)
            if skill:
                self._skills[skill.name] = skill
                if tool_registry:
                    self._register_with_tools(skill, tool_registry)
                count += 1
        log.info("Loaded %d skills from %s", count, self._dir)
        return count

    def reload(self, tool_registry=None) -> int:
        self._skills.clear()
        return self.load_all(tool_registry)

    def _load_skill_file(self, path: Path) -> Optional[Skill]:
        name = path.stem
        meta = {"description": "", "tags": [], "version": "1.0", "created": ""}

        try:
            source = path.read_text()
            # Parse header comments
            for line in source.splitlines():
                if not line.startswith("#"):
                    break
                m = _SKILL_HEADER_RE.match(line)
                if m:
                    key, val = m.group(1).lower(), m.group(2).strip()
                    if key == "tags":
                        meta["tags"] = [t.strip() for t in val.split(",")]
                    elif key in meta:
                        meta[key] = val

            # Load module
            module_name = f"cogman_skill_{name}"
            spec = importlib.util.spec_from_file_location(module_name, path)
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)

            func = getattr(module, "run", None)
            if not func:
                log.warning("Skill %s has no run() function", name)
                return None

            skill = Skill(
                name=name,
                description=meta.get("description") or f"Skill: {name}",
                tags=meta.get("tags", []),
                version=meta.get("version", "1.0"),
                created=meta.get("created", ""),
                path=path,
                func=func,
            )
            return skill
        except Exception as e:
            log.error("Failed to load skill %s: %s", name, e)
            return None

    def _register_with_tools(self, skill: Skill, registry):
        tool_name = f"skill_{skill.name}"

        def _wrapped(**kwargs):
            skill.use_count += 1
            try:
                result = skill.func(**kwargs)
                return str(result)
            except Exception as e:
                return f"Skill error ({skill.name}): {e}"

        registry.register(
            tool_name,
            _wrapped,
            f"[Skill] {skill.description}",
            parameters={"args": {"type": "string", "description": "Input to the skill"}},
        )

    def create_skill(self, name: str, description: str, code: str, tags: List[str] = None) -> Skill:
        """Create a new skill file from LLM-generated code."""
        self._ensure_dir()
        path = self._dir / f"{name}.py"

        tags_str = ", ".join(tags or [])
        created = time.strftime("%Y-%m-%d")

        header = f"""# skill: {name}
# description: {description}
# tags: {tags_str}
# version: 1.0
# created: {created}

"""
        # Ensure code has a run() function
        if "def run(" not in code:
            code = f"def run(**kwargs):\n    {code.strip()}\n"

        full_code = header + code
        path.write_text(full_code)
        log.info("Created skill: %s at %s", name, path)

        skill = self._load_skill_file(path)
        if skill:
            self._skills[skill.name] = skill
        return skill

    def get(self, name: str) -> Optional[Skill]:
        return self._skills.get(name) or self._skills.get(name.removeprefix("skill_"))

    def list(self, tag_filter: str = None) -> List[Skill]:
        skills = list(self._skills.values())
        if tag_filter:
            skills = [s for s in skills if tag_filter in s.tags]
        return sorted(skills, key=lambda s: s.name)

    def search(self, query: str) -> List[Skill]:
        q = query.lower()
        results = []
        for skill in self._skills.values():
            score = 0
            if q in skill.name.lower():
                score += 3
            if q in skill.description.lower():
                score += 2
            if any(q in tag for tag in skill.tags):
                score += 1
            if score:
                results.append((score, skill))
        return [s for _, s in sorted(results, reverse=True)]

    def delete(self, name: str) -> bool:
        skill = self._skills.get(name)
        if not skill:
            return False
        if skill.path and skill.path.exists():
            skill.path.unlink()
        del self._skills[name]
        return True

    def show(self, name: str) -> str:
        skill = self._skills.get(name)
        if not skill:
            return f"Skill not found: {name}"
        if skill.path:
            return skill.path.read_text()
        return f"Skill {name} — no source available."

    def handle_command(self, args: str) -> str:
        """Handle /skills command."""
        parts = args.split(None, 2) if args else []
        sub = parts[0].lower() if parts else "list"

        if sub == "list" or sub == "":
            skills = self.list()
            if not skills:
                return f"No skills installed. Add Python files to {self._dir}"
            lines = [f"Skills ({len(skills)}) — stored in {self._dir}:"]
            for s in skills:
                tags = f" [{', '.join(s.tags)}]" if s.tags else ""
                lines.append(f"  • {s.name}{tags} — {s.description}")
            return "\n".join(lines)

        if sub == "show":
            name = parts[1] if len(parts) > 1 else ""
            if not name:
                return "Usage: /skills show <name>"
            return self.show(name)

        if sub == "search":
            query = " ".join(parts[1:]) if len(parts) > 1 else ""
            if not query:
                return "Usage: /skills search <query>"
            results = self.search(query)
            if not results:
                return f"No skills matching: {query}"
            lines = [f"Found {len(results)} skill(s):"]
            for s in results:
                lines.append(f"  • {s.name} — {s.description}")
            return "\n".join(lines)

        if sub == "delete" or sub == "remove":
            name = parts[1] if len(parts) > 1 else ""
            if not name:
                return "Usage: /skills delete <name>"
            if self.delete(name):
                return f"Deleted skill: {name}"
            return f"Skill not found: {name}"

        if sub == "create":
            return "Usage: Ask cogman to create a skill, e.g.:\n  'Create a skill called summarize that summarizes text'"

        return f"Unknown skills subcommand: {sub}\nUsage: /skills [list|show|search|delete|create] [name]"

    def generate_skill_prompt(self, goal: str) -> str:
        """Return a prompt to ask the LLM to create a skill for `goal`."""
        return f"""Create a Python skill for cogman.

Goal: {goal}

Requirements:
1. File starts with header comments: # skill: name, # description: ..., # tags: tag1, tag2
2. Must define def run(**kwargs) -> str: function
3. The function returns a string result
4. Handle errors gracefully
5. Keep it focused and reusable

Return ONLY the Python code, no explanation.
"""


# ── Skill creation from LLM output ───────────────────────────────────────────

def extract_skill_from_response(response: str, skill_registry: SkillRegistry) -> Optional[Skill]:
    """
    Parse LLM response that might contain a skill definition.
    If it contains ```python ... ``` with proper header, auto-save it.
    """
    match = re.search(r"```python\s*(# skill:.+?)```", response, re.DOTALL)
    if not match:
        return None

    code = match.group(1).strip()
    name_match = re.search(r"# skill:\s*(\S+)", code)
    if not name_match:
        return None

    name = name_match.group(1)
    desc_match = re.search(r"# description:\s*(.+)", code)
    description = desc_match.group(1).strip() if desc_match else name
    tags_match = re.search(r"# tags:\s*(.+)", code)
    tags = [t.strip() for t in tags_match.group(1).split(",")] if tags_match else []

    # Strip header comments from code body
    body_lines = [l for l in code.splitlines() if not l.startswith("#")]
    body = "\n".join(body_lines).strip()

    return skill_registry.create_skill(name, description, body, tags)
