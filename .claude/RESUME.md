# cogman Rebuild — Resume State

## What We're Building
cogman: Jarvis-style Linux AI assistant at `/home/void/void/cogman`
**Goal**: Self-learning, self-evolving, short+long memory, context-aware, modular architecture

## Integrated From
- **Pi Agent** (`tmp/pi-mono`) — multi-provider LLM base layer, parallel tool execution, event streaming
- **OpenClaw** (`tmp/openclaw`) — 7-stage pipeline, multi-channel gateway, skill extensions
- **Hermes Agent** (`tmp/hermes-agent`) — slash commands, plugin engine, skills, memory, context compression

---

## Current Module Structure (DONE ✓)

```
cogman/
├── agents/               ✓ DONE — Pi Agent layer
│   ├── events.py         ✓ AgentEvent types
│   ├── providers.py      ✓ Anthropic/OpenAI/Groq/Gemini/Ollama + ProviderRegistry
│   └── loop.py           ✓ PiAgentCore — parallel tools, event streaming, abort/steer
│
├── memory/               ✓ DONE — Memory subsystem
│   ├── context.py        ✓ EnvironmentContext — git, project, system, services
│   └── manager.py        ✓ Memory façade (short-term + FTS5 + ChromaDB + tool_stats + task_patterns)
│
├── learning/             ✓ DONE — Self-learning + evolution
│   ├── learner.py        ✓ PostInteractionLearner — extracts facts/prefs after each turn
│   ├── evolver.py        ✓ SkillEvolver — auto-creates skills when pattern repeats ≥3x
│   └── compressor.py     ✓ shim → core/context_compressor.py
│
├── skills/               ✓ DONE — Skill system
│   ├── registry.py       ✓ SkillRegistry — loads builtin/ + ~/.cogman/skills/
│   └── builtin/          ✓ syshealth, weather, note, summarize, remind, translate
│
├── gateway/              ✓ DONE — Multi-channel (shims to core/gateway.py)
│   ├── runner.py         ✓ GatewayRunner shim
│   └── message.py        ✓ MessageEvent shim
│
├── commands/             ✓ DONE — Slash commands (shims to core/)
│   ├── registry.py       ✓ CommandDef, COMMAND_REGISTRY shim
│   └── dispatcher.py     ✓ CommandDispatcher shim
│
├── core/                 ✓ DONE — Core engine (updated)
│   ├── orchestrator.py   ✓ 7-stage pipeline + Pi Agent + env context + self-learn hooks
│   ├── memory.py         ✓ shim → memory/manager.py
│   ├── config.py         ✓ multi-provider, gateway, plugin, skill config
│   ├── command_registry.py ✓ 25+ slash commands + CommandDispatcher
│   ├── pi_agent.py       ✓ kept as legacy shim (real code in agents/)
│   ├── plugin_engine.py  ✓ Hermes-style plugin discovery + lifecycle hooks
│   ├── session.py        ✓ FTS5 session search + branching + rollback
│   ├── gateway.py        ✓ Telegram, Discord, Slack, Webhook adapters
│   ├── context_compressor.py ✓ auto-compress long conversations
│   └── skills.py         ✓ legacy shim (real code in skills/registry.py)
│
└── tools/                ✓ DONE — 242 tools total
    ├── browser_tools.py  ✓ NEW: fetch_page, web_search (DDG/Brave), screenshot, read_pdf
    ├── code_tools.py     ✓ NEW: run_python, run_script, check_syntax, format_code, lint_code
    └── image_tools.py    ✓ NEW: generate_image (DALL-E/SD), describe_image, resize, convert
```

---

## INCOMPLETE — Must Resume Here

### 1. `main.py` — NOT FULLY UPDATED YET
The main.py was last modified but was being rewritten when session ended.
It needs to wire up ALL new modules:
- Import from `agents/`, `memory/`, `learning/`, `skills/`, `gateway/`, `commands/`
- Instantiate `PostInteractionLearner`, `SkillEvolver`, `EnvironmentContext`
- Wire `learner` + `evolver` into `orchestrator`
- Use `skills/registry.py` `SkillRegistry` (NOT `core/skills.py`)
- `build_agent()` must return all components properly

### 2. Known Bug — `Skill.is_builtin` AttributeError
**File**: `core/orchestrator.py` line 232
**Error**: `'Skill' object has no attribute 'is_builtin'`
**Cause**: `core/orchestrator.py` references `skills/registry.py`'s `Skill` dataclass
  which has `is_builtin`, but `core/skills.py` (old shim) `Skill` does NOT.
**Fix**: Make sure orchestrator imports `SkillRegistry` from `skills.registry` not `core.skills`

### 3. `memory/session.py` — NOT CREATED YET
Need to create `memory/session.py` as a proper shim or move `core/session.py` content there.
Currently `core/session.py` exists with full implementation.

### 4. `agents/__init__.py` — needs to export PiAgentCore
```python
from agents.loop import PiAgentCore
from agents.providers import ProviderRegistry
from agents.events import *
```

### 5. `memory/__init__.py` — needs to export Memory
```python
from memory.manager import Memory, ShortTermMemory, LongTermMemory
from memory.context import EnvironmentContext
```

### 6. `skills/__init__.py` — needs to export SkillRegistry
```python
from skills.registry import SkillRegistry, Skill
```

### 7. `learning/__init__.py` — needs to export
```python
from learning.learner import PostInteractionLearner
from learning.evolver import SkillEvolver
```

---

## Updated `main.py` Build Plan

```python
def build_agent():
    from memory.manager import Memory
    from core.tool_registry import ToolRegistry
    from core.orchestrator import Orchestrator
    from core.command_registry import CommandDispatcher
    from core.plugin_engine import PluginEngine
    from skills.registry import SkillRegistry        # ← NEW module
    from core.session import SessionManager
    from learning.learner import PostInteractionLearner
    from learning.evolver import SkillEvolver
    from agents.providers import ProviderRegistry

    memory   = Memory()
    registry = ToolRegistry()
    # ... register all tools ...
    orchestrator = Orchestrator(registry, memory)

    plugin_engine = PluginEngine(registry)
    plugin_engine.load_all()

    skill_registry = SkillRegistry()               # loads builtin/ + ~/.cogman/skills/
    skill_registry.load_all(registry)

    session_mgr = SessionManager()

    learner = PostInteractionLearner(memory, orchestrator._providers)
    evolver = SkillEvolver(memory, skill_registry, orchestrator._providers)

    dispatcher = CommandDispatcher(orchestrator, memory, registry,
                                   session_mgr=session_mgr,
                                   plugin_engine=plugin_engine,
                                   skill_registry=skill_registry)

    # Wire everything
    orchestrator.plugin_engine  = plugin_engine
    orchestrator.skill_registry = skill_registry
    orchestrator.session_mgr    = session_mgr
    orchestrator.dispatcher     = dispatcher
    orchestrator.learner        = learner
    orchestrator.evolver        = evolver

    return orchestrator, memory, registry, plugin_engine, skill_registry, session_mgr
```

---

## Remaining Work After main.py Fix

1. **Git commit** all current work
2. **Test** `python main.py --status` passes cleanly
3. **Test** `python main.py -c "/skills list"` shows 6 builtins
4. **Test** `python main.py -c "skill_syshealth"` (direct tool call via NLP)
5. **Test** self-learning fires after LLM interaction (with API key set)
6. **Write** `memory/session.py` shim if needed
7. **Update** `cogman_tools.py` to import from new module paths

## Key Env Vars to Set for Full Power
```bash
export ANTHROPIC_API_KEY=...     # best overall
export GROQ_API_KEY=...          # free, fast (groq.com)
export OPENAI_API_KEY=...        # DALL-E + GPT-4o
export GEMINI_API_KEY=...        # Gemini
export COGMAN_TELEGRAM_TOKEN=... # for --gateway
```
