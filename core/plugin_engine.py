"""
Plugin engine — ported from Hermes Agent hermes_cli/plugins.py.

Discovers and loads plugins from:
  1. ~/.cogman/plugins/<name>/  (user plugins)
  2. ./.cogman/plugins/<name>/  (project plugins, opt-in)
  3. pip entry-point group: cogman.plugins

Each plugin directory must contain:
  - plugin.yaml  (manifest: name, description, version, author)
  - __init__.py  (must define register(ctx: PluginContext))

Lifecycle hooks fired by the orchestrator:
  pre_tool_call, post_tool_call
  pre_llm_call,  post_llm_call
  on_session_start, on_session_end, on_session_reset
  pre_gateway_dispatch
"""

from __future__ import annotations

import importlib.util
import logging
import sys
import types
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set

log = logging.getLogger("cogman.plugins")

VALID_HOOKS: Set[str] = {
    "pre_tool_call",
    "post_tool_call",
    "transform_tool_result",
    "pre_llm_call",
    "post_llm_call",
    "on_session_start",
    "on_session_end",
    "on_session_reset",
    "pre_gateway_dispatch",
}

_COGMAN_HOME = Path.home() / ".cogman"


# ── PluginManifest ────────────────────────────────────────────────────────────

@dataclass
class PluginManifest:
    name: str
    description: str = ""
    version: str = "0.1.0"
    author: str = ""
    requires: List[str] = field(default_factory=list)  # pip packages
    hooks: List[str] = field(default_factory=list)      # hooks this plugin uses
    path: Optional[Path] = None


# ── PluginContext ─────────────────────────────────────────────────────────────

class PluginContext:
    """
    Context passed to plugin.register(ctx). Provides APIs for:
      - registering tools
      - adding lifecycle hooks
      - accessing config / cogman home
    """

    def __init__(self, manifest: PluginManifest, registry, engine: "PluginEngine"):
        self.manifest = manifest
        self._registry = registry
        self._engine = engine
        self.name = manifest.name

    def register_tool(self, name: str, func: Callable, description: str, parameters: Dict = None, requires_confirm: bool = False):
        """Register a tool from this plugin into the main tool registry."""
        self._registry.register(name, func, description, parameters or {}, requires_confirm)
        log.debug("Plugin %s registered tool: %s", self.name, name)

    def add_hook(self, hook_name: str, callback: Callable):
        """Register a lifecycle hook callback."""
        if hook_name not in VALID_HOOKS:
            log.warning("Plugin %s: unknown hook %s", self.name, hook_name)
            return
        self._engine._hooks[hook_name].append(callback)
        log.debug("Plugin %s added hook: %s", self.name, hook_name)

    def add_slash_command(self, name: str, handler: Callable, description: str = "", category: str = "Plugin"):
        """Register a custom /command."""
        self._engine._extra_commands[name] = (handler, description, category)

    @property
    def cogman_home(self) -> Path:
        return _COGMAN_HOME

    @property
    def plugin_home(self) -> Optional[Path]:
        return self.manifest.path

    def get_config(self, key: str, default: Any = None) -> Any:
        """Read plugin config from ~/.cogman/plugins/<name>/config.yaml."""
        if not self.manifest.path:
            return default
        cfg_path = self.manifest.path / "config.yaml"
        if not cfg_path.exists():
            return default
        try:
            import yaml
            with open(cfg_path) as f:
                cfg = yaml.safe_load(f) or {}
            return cfg.get(key, default)
        except Exception:
            return default


# ── PluginEngine ──────────────────────────────────────────────────────────────

class PluginEngine:
    """Discovers, loads, and manages plugins."""

    def __init__(self, registry, allow_project_plugins: bool = False):
        self._registry = registry
        self._allow_project = allow_project_plugins
        self._plugins: Dict[str, PluginManifest] = {}
        self._modules: Dict[str, types.ModuleType] = {}
        self._hooks: Dict[str, List[Callable]] = {h: [] for h in VALID_HOOKS}
        self._extra_commands: Dict[str, tuple] = {}  # name → (handler, desc, category)
        self._disabled: Set[str] = set()

    # ── Discovery ─────────────────────────────────────────────────────────────

    def _discover_dirs(self) -> List[Path]:
        dirs = []
        # User plugins
        user_dir = _COGMAN_HOME / "plugins"
        if user_dir.is_dir():
            dirs.append(user_dir)
        # Project plugins
        if self._allow_project:
            project_dir = Path.cwd() / ".cogman" / "plugins"
            if project_dir.is_dir():
                dirs.append(project_dir)
        return dirs

    def _load_manifest(self, plugin_dir: Path) -> Optional[PluginManifest]:
        yaml_path = plugin_dir / "plugin.yaml"
        init_path = plugin_dir / "__init__.py"

        if not init_path.exists():
            return None

        name = plugin_dir.name

        if yaml_path.exists():
            try:
                import yaml
                with open(yaml_path) as f:
                    data = yaml.safe_load(f) or {}
                return PluginManifest(
                    name=data.get("name", name),
                    description=data.get("description", ""),
                    version=data.get("version", "0.1.0"),
                    author=data.get("author", ""),
                    requires=data.get("requires", []),
                    hooks=data.get("hooks", []),
                    path=plugin_dir,
                )
            except Exception as e:
                log.warning("Failed to load plugin.yaml for %s: %s", name, e)

        return PluginManifest(name=name, path=plugin_dir)

    def load_all(self) -> int:
        """Discover and load all plugins. Returns count loaded."""
        count = 0
        for base_dir in self._discover_dirs():
            for plugin_dir in sorted(base_dir.iterdir()):
                if not plugin_dir.is_dir() or plugin_dir.name.startswith("_"):
                    continue
                manifest = self._load_manifest(plugin_dir)
                if not manifest:
                    continue
                if manifest.name in self._disabled:
                    log.info("Plugin %s disabled — skipping", manifest.name)
                    continue
                if self._load_plugin(manifest):
                    count += 1

        # pip entry-point plugins
        count += self._load_entrypoint_plugins()
        return count

    def _load_plugin(self, manifest: PluginManifest) -> bool:
        name = manifest.name
        if name in self._plugins:
            log.debug("Plugin %s already loaded — skipping", name)
            return False

        # Check requirements
        for req in manifest.requires:
            try:
                importlib.util.find_spec(req.replace("-", "_"))
            except Exception:
                log.warning("Plugin %s missing requirement: %s", name, req)
                return False

        init_path = manifest.path / "__init__.py" if manifest.path else None
        if not init_path or not init_path.exists():
            return False

        # Load module
        module_name = f"cogman_plugin_{name}"
        spec = importlib.util.spec_from_file_location(module_name, init_path)
        if not spec:
            return False
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module

        try:
            spec.loader.exec_module(module)
        except Exception as e:
            log.error("Plugin %s load error: %s", name, e)
            return False

        if not hasattr(module, "register"):
            log.warning("Plugin %s has no register(ctx) function", name)
            return False

        ctx = PluginContext(manifest, self._registry, self)
        try:
            module.register(ctx)
        except Exception as e:
            log.error("Plugin %s register() failed: %s", name, e)
            return False

        self._plugins[name] = manifest
        self._modules[name] = module
        log.info("Loaded plugin: %s v%s", name, manifest.version)
        return True

    def _load_entrypoint_plugins(self) -> int:
        count = 0
        try:
            from importlib.metadata import entry_points
            eps = entry_points(group="cogman.plugins")
            for ep in eps:
                try:
                    module = ep.load()
                    manifest = PluginManifest(name=ep.name, description=f"pip plugin: {ep.value}")
                    ctx = PluginContext(manifest, self._registry, self)
                    if hasattr(module, "register"):
                        module.register(ctx)
                        self._plugins[ep.name] = manifest
                        self._modules[ep.name] = module
                        count += 1
                        log.info("Loaded pip plugin: %s", ep.name)
                except Exception as e:
                    log.error("pip plugin %s failed: %s", ep.name, e)
        except Exception:
            pass
        return count

    def reload(self) -> int:
        """Hot-reload all plugins."""
        old_hooks = {h: [] for h in VALID_HOOKS}
        self._hooks = old_hooks
        self._plugins.clear()
        self._modules.clear()
        self._extra_commands.clear()
        return self.load_all()

    def disable(self, name: str):
        self._disabled.add(name)

    def enable(self, name: str):
        self._disabled.discard(name)

    # ── Hook invocation ───────────────────────────────────────────────────────

    def invoke_hook(self, hook_name: str, **kwargs) -> List[Any]:
        """Invoke all registered callbacks for a hook. Returns list of results."""
        results = []
        for callback in self._hooks.get(hook_name, []):
            try:
                result = callback(**kwargs)
                results.append(result)
            except Exception as e:
                log.error("Hook %s callback error: %s", hook_name, e)
        return results

    def invoke_hook_first(self, hook_name: str, **kwargs) -> Optional[Any]:
        """Invoke hook and return first non-None result."""
        for result in self.invoke_hook(hook_name, **kwargs):
            if result is not None:
                return result
        return None

    # ── Status / info ─────────────────────────────────────────────────────────

    def status(self) -> str:
        if not self._plugins:
            return "No plugins loaded. Place plugins in ~/.cogman/plugins/<name>/"
        lines = [f"Loaded plugins ({len(self._plugins)}):"]
        for name, manifest in self._plugins.items():
            hooks_used = [h for h in VALID_HOOKS if any(True for _ in self._hooks[h])]
            lines.append(f"  • {name} v{manifest.version} — {manifest.description}")
        lines.append(f"\nHook registrations:")
        for hook, callbacks in self._hooks.items():
            if callbacks:
                lines.append(f"  {hook}: {len(callbacks)} handler(s)")
        if self._extra_commands:
            lines.append(f"\nExtra slash commands: /{', /'.join(self._extra_commands)}")
        return "\n".join(lines)

    def get_extra_command(self, name: str) -> Optional[tuple]:
        return self._extra_commands.get(name)

    @property
    def loaded_names(self) -> List[str]:
        return list(self._plugins.keys())
