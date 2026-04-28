You are a senior systems engineer and AI architect.

Your task is to design and implement a **modular, production-ready Linux AI assistant (Jarvis-like)** from scratch.

This assistant must:

* Run locally on Linux
* Be voice-enabled (speech-to-text + text-to-speech)
* Execute real system actions (shell, apps, automation)
* Maintain memory (short-term + long-term)
* Be safe, modular, and extensible
* Work as a background assistant (daemon-style)

---

# 🧱 TECH STACK (MANDATORY)

Use the following tools and structure:

## Orchestration

* LangChain (or minimal custom alternative if better)

## Action System

* Python subprocess
* bash
* xdotool, wmctrl

## Memory

* Chroma or FAISS
* SQLite for structured storage

## Voice

* Whisper (speech-to-text)
* Coqui TTS (text-to-speech)

## Intent Layer

* Hybrid system:

  * rule-based (fast commands)
  * LLM fallback

## Linux Integration

* DBus
* systemd
* PipeWire or PulseAudio

## Context Awareness

* psutil
* xprop / xdotool

## Event System

* inotify
* cron/systemd timers

## Safety

* command validation layer
* permission checks
* logging

## API / Plugins

* FastAPI

## Interface

* CLI first (GUI optional later)

---

# 🧠 GOALS

Design a system that:

1. Listens to voice or text input
2. Understands intent
3. Executes real system actions
4. Responds via voice/text
5. Learns user preferences over time

---

# 📦 OUTPUT REQUIREMENTS

You must generate:

## 1. High-Level Architecture

* Clear explanation of system design
* Component interaction diagram (text-based is fine)

## 2. Project Folder Structure

* Complete directory layout
* Modular separation (core, tools, memory, voice, etc.)

## 3. Step-by-Step Roadmap

Break into phases:

### Phase 1: Core CLI Assistant

* Input → intent → action → output

### Phase 2: Tool Integration

* Shell execution
* App control

### Phase 3: Memory System

* Add vector DB + persistence

### Phase 4: Voice System

* Whisper + TTS integration

### Phase 5: Context Awareness

* System state tracking

### Phase 6: Event System

* Background triggers

### Phase 7: Safety Layer

* Command validation + sandboxing

### Phase 8: Background Daemon

* systemd service

---

## 4. Code Implementation (VERY IMPORTANT)

For EACH phase:

* Provide working Python code
* Keep modules clean and minimal
* Avoid overengineering
* Use real, runnable examples

---

## 5. Core Modules to Implement

Design and implement:

* orchestrator.py → routes tasks
* intent_parser.py → rule + LLM hybrid
* tool_registry.py → all actions
* memory.py → vector + persistent memory
* voice.py → STT + TTS
* system_controller.py → Linux integration
* safety.py → validation layer
* config.py → settings

---

## 6. Tool System Design

* Define tools as functions
* Register tools dynamically
* Allow LLM to call tools safely

---

## 7. Safety Design

* Prevent dangerous commands
* Add confirmation layer for risky actions
* Log all actions

---

## 8. Minimal Working Prototype FIRST

Do NOT start with full complexity.

Start with:

* CLI input
* 3–5 commands (open browser, run command, get time)
* Simple routing

Then scale step by step.

---

## 9. Design Principles

* Keep everything modular
* Avoid unnecessary abstractions
* Prefer simple working code over complex frameworks
* Make it debuggable
* Make it extensible

---

## 10. Final Output

At the end, provide:

* How to run the system
* Example commands
* How to extend with new tools
* Next improvements

---

# ⚠️ IMPORTANT RULES

* Do NOT skip steps
* Do NOT jump to advanced features early
* Do NOT assume hidden setup
* Explain reasoning briefly, then show code
* Keep everything practical and runnable

---

# 🚀 START NOW

Begin with:

1. High-level architecture
2. Folder structure
3. Phase 1 implementation (CLI assistant)

Then proceed step by step.

