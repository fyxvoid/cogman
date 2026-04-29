"""
Multi-provider LLM abstraction — Pi Agent pattern.

Auto-detects from env:
  ANTHROPIC_API_KEY       → Anthropic (claude-*)        priority 100
  GROQ_API_KEY            → Groq (llama-*, gemma-*)     priority 90
  OPENAI_API_KEY          → OpenAI (gpt-*, o1-*)        priority 80
  GEMINI_API_KEY          → Google Gemini               priority 70
  COGMAN_OPENAI_BASE_URL  → any OpenAI-compatible       priority 60
  Ollama running locally  → offline fallback            priority 50
"""
from __future__ import annotations

import json
import logging
import os
import uuid
from abc import ABC, abstractmethod
from typing import Callable, Dict, List, Optional

log = logging.getLogger("cogman.providers")


class LLMProvider(ABC):
    name: str = "base"
    priority: int = 0

    @abstractmethod
    def is_available(self) -> bool: ...

    @abstractmethod
    def chat_with_tools(
        self,
        messages: List[Dict],
        system: str,
        tools: List[Dict],
        model: Optional[str] = None,
        max_tokens: int = 4096,
        stream_callback: Optional[Callable[[str], None]] = None,
    ) -> Dict: ...

    def get_default_model(self) -> str:
        return ""


class AnthropicProvider(LLMProvider):
    name = "anthropic"
    priority = 100

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-6", max_tokens: int = 4096):
        self._api_key = api_key
        self._model = model
        self._max_tokens = max_tokens
        self._client = None

    def _client_(self):
        if not self._client:
            import anthropic
            self._client = anthropic.Anthropic(api_key=self._api_key)
        return self._client

    def is_available(self) -> bool:
        if not self._api_key:
            return False
        try:
            import anthropic  # noqa
            return True
        except ImportError:
            return False

    def get_default_model(self) -> str:
        return self._model

    def chat_with_tools(self, messages, system, tools, model=None, max_tokens=4096, stream_callback=None):
        client = self._client_()
        model = model or self._model
        try:
            with client.messages.stream(
                model=model, max_tokens=max_tokens, system=system,
                tools=tools or [], messages=messages,
            ) as stream:
                text_parts = []
                for text in stream.text_stream:
                    text_parts.append(text)
                    if stream_callback:
                        stream_callback(text)
                response = stream.get_final_message()
            tool_calls = []
            for block in response.content:
                if block.type == "tool_use":
                    tool_calls.append({"id": block.id, "name": block.name, "args": block.input})
            return {"text": "".join(text_parts), "tool_calls": tool_calls, "stop_reason": response.stop_reason}
        except Exception as e:
            log.error("Anthropic error: %s", e)
            raise


class OpenAICompatibleProvider(LLMProvider):
    name = "openai"
    priority = 80

    def __init__(self, api_key: str, base_url: str = None, model: str = "gpt-4o", provider_name: str = "openai"):
        self._api_key = api_key
        self._base_url = base_url
        self._model = model
        self.name = provider_name
        self._client = None

    def _client_(self):
        if not self._client:
            from openai import OpenAI
            kwargs = {"api_key": self._api_key}
            if self._base_url:
                kwargs["base_url"] = self._base_url
            self._client = OpenAI(**kwargs)
        return self._client

    def is_available(self) -> bool:
        if not self._api_key:
            return False
        try:
            from openai import OpenAI  # noqa
            return True
        except ImportError:
            return False

    def get_default_model(self) -> str:
        return self._model

    def chat_with_tools(self, messages, system, tools, model=None, max_tokens=4096, stream_callback=None):
        client = self._client_()
        model = model or self._model
        oai_tools = [
            {"type": "function", "function": {"name": t["name"], "description": t.get("description", ""),
             "parameters": t.get("input_schema", {"type": "object", "properties": {}})}}
            for t in (tools or [])
        ]
        msgs = [{"role": "system", "content": system}] + messages
        try:
            if stream_callback:
                stream = client.chat.completions.create(
                    model=model, messages=msgs, tools=oai_tools or None,
                    max_tokens=max_tokens, stream=True,
                )
                text_parts, tool_calls_raw = [], {}
                for chunk in stream:
                    delta = chunk.choices[0].delta if chunk.choices else None
                    if delta and delta.content:
                        text_parts.append(delta.content)
                        stream_callback(delta.content)
                    if delta and delta.tool_calls:
                        for tc in delta.tool_calls:
                            idx = tc.index
                            if idx not in tool_calls_raw:
                                tool_calls_raw[idx] = {"id": "", "name": "", "args": ""}
                            if tc.id: tool_calls_raw[idx]["id"] = tc.id
                            if tc.function:
                                if tc.function.name: tool_calls_raw[idx]["name"] = tc.function.name
                                if tc.function.arguments: tool_calls_raw[idx]["args"] += tc.function.arguments
                tool_calls = []
                for tc in tool_calls_raw.values():
                    try: args = json.loads(tc["args"]) if tc["args"] else {}
                    except: args = {}
                    tool_calls.append({"id": tc["id"], "name": tc["name"], "args": args})
                return {"text": "".join(text_parts), "tool_calls": tool_calls, "stop_reason": "end_turn"}
            else:
                resp = client.chat.completions.create(model=model, messages=msgs, tools=oai_tools or None, max_tokens=max_tokens)
                msg = resp.choices[0].message
                tool_calls = []
                if msg.tool_calls:
                    for tc in msg.tool_calls:
                        try: args = json.loads(tc.function.arguments)
                        except: args = {}
                        tool_calls.append({"id": tc.id, "name": tc.function.name, "args": args})
                return {"text": msg.content or "", "tool_calls": tool_calls, "stop_reason": resp.choices[0].finish_reason}
        except Exception as e:
            log.error("%s error: %s", self.name, e)
            raise


class GeminiProvider(LLMProvider):
    name = "gemini"
    priority = 70

    def __init__(self, api_key: str, model: str = "gemini-2.0-flash"):
        self._api_key = api_key
        self._model = model

    def is_available(self) -> bool:
        if not self._api_key:
            return False
        try:
            import google.generativeai  # noqa
            return True
        except ImportError:
            return False

    def get_default_model(self) -> str:
        return self._model

    def chat_with_tools(self, messages, system, tools, model=None, max_tokens=4096, stream_callback=None):
        import google.generativeai as genai
        genai.configure(api_key=self._api_key)
        gemini_msgs = []
        for m in messages:
            role = "user" if m["role"] == "user" else "model"
            gemini_msgs.append({"role": role, "parts": [str(m.get("content", ""))]})
        m = genai.GenerativeModel(model or self._model, system_instruction=system)
        chat = m.start_chat(history=gemini_msgs[:-1] if len(gemini_msgs) > 1 else [])
        last = gemini_msgs[-1]["parts"][0] if gemini_msgs else ""
        try:
            response = chat.send_message(last)
            text = "".join(p.text for p in response.parts if hasattr(p, "text"))
            if stream_callback and text:
                stream_callback(text)
            return {"text": text, "tool_calls": [], "stop_reason": "end_turn"}
        except Exception as e:
            log.error("Gemini error: %s", e)
            raise


class OllamaProvider(LLMProvider):
    name = "ollama"
    priority = 50

    def __init__(self, host: str = "http://localhost:11434", model: str = "mistral"):
        self._host = host
        self._model = model

    def is_available(self) -> bool:
        try:
            import urllib.request
            with urllib.request.urlopen(f"{self._host}/api/tags", timeout=2) as r:
                return r.status == 200
        except Exception:
            return False

    def get_default_model(self) -> str:
        return self._model

    def chat_with_tools(self, messages, system, tools, model=None, max_tokens=4096, stream_callback=None):
        import urllib.request
        model = model or self._model
        payload = {
            "model": model,
            "messages": [{"role": "system", "content": system}] + messages,
            "stream": bool(stream_callback),
            "options": {"temperature": 0.1, "num_predict": max_tokens},
        }
        if tools:
            payload["tools"] = [
                {"type": "function", "function": {"name": t["name"], "description": t.get("description", ""),
                 "parameters": t.get("input_schema", {})}}
                for t in tools
            ]
        data = json.dumps(payload).encode()
        req = urllib.request.Request(f"{self._host}/api/chat", data=data,
                                     headers={"Content-Type": "application/json"}, method="POST")
        try:
            if stream_callback:
                text_parts = []
                with urllib.request.urlopen(req, timeout=60) as resp:
                    for line in resp:
                        line = line.decode().strip()
                        if not line: continue
                        try: chunk = json.loads(line)
                        except: continue
                        delta = chunk.get("message", {}).get("content", "")
                        if delta:
                            text_parts.append(delta)
                            stream_callback(delta)
                        if chunk.get("done"): break
                return {"text": "".join(text_parts), "tool_calls": [], "stop_reason": "end_turn"}
            else:
                with urllib.request.urlopen(req, timeout=60) as resp:
                    result = json.loads(resp.read())
                msg = result.get("message", {})
                text = msg.get("content", "")
                tool_calls = []
                for tc in msg.get("tool_calls", []):
                    fn = tc.get("function", {})
                    tool_calls.append({"id": str(uuid.uuid4()), "name": fn.get("name", ""), "args": fn.get("arguments", {})})
                return {"text": text, "tool_calls": tool_calls, "stop_reason": "end_turn"}
        except Exception as e:
            log.error("Ollama error: %s", e)
            raise


class ProviderRegistry:
    """Auto-detects and ranks all available LLM providers."""

    def __init__(self):
        self._providers: List[LLMProvider] = []
        self._load_from_env()

    def _load_from_env(self):
        key = os.getenv("ANTHROPIC_API_KEY", "")
        if key:
            self.register(AnthropicProvider(key, os.getenv("COGMAN_MODEL", "claude-sonnet-4-6")))

        groq_key = os.getenv("GROQ_API_KEY", "")
        if groq_key:
            p = OpenAICompatibleProvider(groq_key, base_url="https://api.groq.com/openai/v1",
                                         model=os.getenv("COGMAN_GROQ_MODEL", "llama-3.3-70b-versatile"),
                                         provider_name="groq")
            p.priority = 90
            self.register(p)

        oai_key = os.getenv("OPENAI_API_KEY", "")
        if oai_key:
            self.register(OpenAICompatibleProvider(oai_key,
                                                   model=os.getenv("COGMAN_OPENAI_MODEL", "gpt-4o")))

        gem_key = os.getenv("GEMINI_API_KEY", "")
        if gem_key:
            self.register(GeminiProvider(gem_key, os.getenv("COGMAN_GEMINI_MODEL", "gemini-2.0-flash")))

        custom_base = os.getenv("COGMAN_OPENAI_BASE_URL", "")
        if custom_base:
            p = OpenAICompatibleProvider(os.getenv("COGMAN_OPENAI_API_KEY", "sk-local"),
                                         base_url=custom_base,
                                         model=os.getenv("COGMAN_OPENAI_MODEL", "local-model"),
                                         provider_name="custom")
            p.priority = 60
            self.register(p)

        if os.getenv("COGMAN_LOCAL_LLM", "true").lower() == "true":
            self.register(OllamaProvider(
                os.getenv("COGMAN_OLLAMA_HOST", "http://localhost:11434"),
                os.getenv("COGMAN_OLLAMA_MODEL", "mistral"),
            ))

    def register(self, provider: LLMProvider):
        self._providers.append(provider)
        self._providers.sort(key=lambda p: p.priority, reverse=True)

    def best_available(self) -> Optional[LLMProvider]:
        for p in self._providers:
            if p.is_available():
                return p
        return None

    def get(self, name: str) -> Optional[LLMProvider]:
        for p in self._providers:
            if p.name == name:
                return p
        return None

    def list_available(self) -> List[str]:
        return [p.name for p in self._providers if p.is_available()]

    def summary(self) -> str:
        if not self._providers:
            return "  No providers. Set ANTHROPIC_API_KEY, OPENAI_API_KEY, or GROQ_API_KEY"
        lines = []
        for p in self._providers:
            ok = p.is_available()
            lines.append(f"  [{'✓' if ok else '✗'}] {p.name:<12} {p.get_default_model()}")
        return "\n".join(lines)
