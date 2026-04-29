"""
Skill registry — moved from core/skills.py.
Backward-compatible re-export + discovers builtin skills automatically.
"""
from __future__ import annotations

import logging
import re
import sys
import time
import importlib.util
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional

log = logging.getLogger("cogman.skills")

_COGMAN_HOME = Path.home() / ".cogman"
_SKILLS_DIR  = _COGMAN_HOME / "skills"
_BUILTIN_DIR = Path(__file__).parent / "builtin"
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
    is_builtin: bool = False


class SkillRegistry:
    """Discovers and loads skills from builtin/ and ~/.cogman/skills/."""

    def __init__(self, skills_dir: Optional[Path] = None):
        self._user_dir = skills_dir or _SKILLS_DIR
        self._skills: Dict[str, Skill] = {}
        self._user_dir.mkdir(parents=True, exist_ok=True)

    def load_all(self, tool_registry=None) -> int:
        count = 0
        # 1. Load built-in skills first
        if _BUILTIN_DIR.is_dir():
            for path in sorted(_BUILTIN_DIR.glob("*.py")):
                if path.name.startswith("_"):
                    continue
                skill = self._load_file(path, is_builtin=True)
                if skill:
                    self._skills[skill.name] = skill
                    if tool_registry:
                        self._register_tool(skill, tool_registry)
                    count += 1
        # 2. User skills override builtins
        for path in sorted(self._user_dir.glob("*.py")):
            if path.name.startswith("_"):
                continue
            skill = self._load_file(path, is_builtin=False)
            if skill:
                self._skills[skill.name] = skill
                if tool_registry:
                    self._register_tool(skill, tool_registry)
                count += 1
        log.info("Loaded %d skills", count)
        return count

    def reload(self, tool_registry=None) -> int:
        self._skills.clear()
        return self.load_all(tool_registry)

    def _load_file(self, path: Path, is_builtin: bool = False) -> Optional[Skill]:
        name = path.stem
        meta = {"description": "", "tags": [], "version": "1.0", "created": ""}
        try:
            source = path.read_text()
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

            # Use path-based unique name to avoid pyc collisions between
            # builtin and user skills with the same filename
            source_tag = "builtin" if is_builtin else "user"
            module_name = f"cogman_skill_{source_tag}_{name}"
            # Evict any cached version so we always load fresh source
            sys.modules.pop(module_name, None)
            spec = importlib.util.spec_from_file_location(module_name, path)
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)

            func = getattr(module, "run", None)
            if not func:
                return None

            return Skill(
                name=name,
                description=meta.get("description") or f"Skill: {name}",
                tags=meta.get("tags", []),
                version=meta.get("version", "1.0"),
                created=meta.get("created", ""),
                path=path,
                func=func,
                is_builtin=is_builtin,
            )
        except Exception as e:
            log.error("Failed to load skill %s: %s", name, e)
            return None

    def _register_tool(self, skill: Skill, registry):
        tool_name = f"skill_{skill.name}"

        def _wrapped(**kwargs):
            skill.use_count += 1
            try:
                result = skill.func(**kwargs)
                return str(result)
            except Exception as e:
                return f"Skill error ({skill.name}): {e}"

        registry.register(tool_name, _wrapped, f"[Skill] {skill.description}",
                          parameters={"args": {"type": "string", "description": "Input to the skill"}})

    def create_skill(self, name: str, description: str, code: str, tags: List[str] = None) -> Skill:
        self._user_dir.mkdir(parents=True, exist_ok=True)
        path = self._user_dir / f"{name}.py"
        tags_str = ", ".join(tags or [])
        created = time.strftime("%Y-%m-%d")
        header = f"# skill: {name}\n# description: {description}\n# tags: {tags_str}\n# version: 1.0\n# created: {created}\n\n"
        if "def run(" not in code:
            code = f"def run(**kwargs):\n    {code.strip()}\n"
        path.write_text(header + code)
        skill = self._load_file(path)
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
            if q in skill.name.lower(): score += 3
            if q in skill.description.lower(): score += 2
            if any(q in tag for tag in skill.tags): score += 1
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
        return skill.path.read_text() if skill.path else f"Skill {name}: no source."

    def handle_command(self, args: str) -> str:
        parts = args.split(None, 2) if args else []
        sub = parts[0].lower() if parts else "list"

        if sub in ("list", ""):
            skills = self.list()
            if not skills:
                return f"No skills. Add .py files to {self._user_dir}"
            lines = [f"Skills ({len(skills)}):"]
            for s in skills:
                builtin = " [builtin]" if s.is_builtin else ""
                tags = f" [{', '.join(s.tags)}]" if s.tags else ""
                lines.append(f"  • {s.name}{tags}{builtin} — {s.description}")
            return "\n".join(lines)
        if sub == "show":
            return self.show(parts[1]) if len(parts) > 1 else "Usage: /skills show <name>"
        if sub == "search":
            q = " ".join(parts[1:])
            results = self.search(q) if q else []
            if not results:
                return f"No skills matching: {q}"
            return "\n".join(f"  • {s.name} — {s.description}" for s in results)
        if sub in ("delete", "remove"):
            name = parts[1] if len(parts) > 1 else ""
            return f"Deleted: {name}" if (name and self.delete(name)) else f"Not found: {name}"
        if sub == "create":
            return "Ask cogman to create a skill:\n  'Create a skill that <does something>'"
        return f"Unknown: {sub}. Usage: /skills [list|show|search|delete|create]"
