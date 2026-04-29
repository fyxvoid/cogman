"""
Multi-channel gateway — inspired by OpenClaw (src/channels/) and Hermes Agent (gateway/).

Connects cogman to messaging platforms:
  - Telegram (python-telegram-bot)
  - Discord (discord.py)
  - Slack (slack-bolt)
  - Webhook (FastAPI/httpx)
  - IRC (built-in socket)

Run with: python main.py --gateway

Config via env:
  COGMAN_TELEGRAM_TOKEN   → Telegram bot token
  COGMAN_DISCORD_TOKEN    → Discord bot token
  COGMAN_SLACK_BOT_TOKEN  → Slack bot token
  COGMAN_SLACK_APP_TOKEN  → Slack socket mode token
  COGMAN_WEBHOOK_PORT     → Webhook listener port (default 7778)
"""

from __future__ import annotations

import asyncio
import logging
import os
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

log = logging.getLogger("cogman.gateway")

# ── Message event (OpenClaw-style) ────────────────────────────────────────────

@dataclass
class MessageEvent:
    platform: str                    # "telegram", "discord", "slack", "webhook", "irc"
    channel_id: str                  # chat ID / channel ID
    user_id: str                     # user identifier
    user_name: str                   # display name
    text: str                        # message text
    timestamp: float = field(default_factory=time.time)
    is_direct: bool = True           # DM vs group
    attachments: List[str] = field(default_factory=list)
    raw: Any = None                  # original platform object


@dataclass
class GatewayResponse:
    text: str
    channel_id: str
    platform: str
    reply_to: Optional[str] = None
    image_url: Optional[str] = None


# ── Adapter base ──────────────────────────────────────────────────────────────

class GatewayAdapter(ABC):
    platform: str = "base"

    @abstractmethod
    def is_configured(self) -> bool: ...

    @abstractmethod
    def start(self, on_message: Callable[[MessageEvent], str]): ...

    @abstractmethod
    def stop(self): ...

    @abstractmethod
    def send(self, channel_id: str, text: str): ...


# ── Telegram ──────────────────────────────────────────────────────────────────

class TelegramAdapter(GatewayAdapter):
    platform = "telegram"

    def __init__(self, token: Optional[str] = None):
        self._token = token or os.getenv("COGMAN_TELEGRAM_TOKEN", "")
        self._app = None
        self._thread = None

    def is_configured(self) -> bool:
        if not self._token:
            return False
        try:
            from telegram.ext import Application  # noqa: F401
            return True
        except ImportError:
            return False

    def start(self, on_message: Callable[[MessageEvent], str]):
        if not self.is_configured():
            log.warning("Telegram not configured (missing token or python-telegram-bot)")
            return

        from telegram import Update
        from telegram.ext import Application, MessageHandler, filters, CommandHandler

        app = Application.builder().token(self._token).build()
        self._app = app

        async def _handle(update: Update, context):
            if not update.message or not update.message.text:
                return
            evt = MessageEvent(
                platform="telegram",
                channel_id=str(update.message.chat_id),
                user_id=str(update.message.from_user.id),
                user_name=update.message.from_user.first_name or "User",
                text=update.message.text,
                is_direct=update.message.chat.type == "private",
                raw=update,
            )
            log.info("[Telegram] %s: %s", evt.user_name, evt.text[:80])
            try:
                response = on_message(evt)
                if response:
                    # Split long messages
                    for chunk in _split_message(response, 4096):
                        await update.message.reply_text(chunk)
            except Exception as e:
                log.error("Telegram handler error: %s", e)
                await update.message.reply_text(f"Error: {e}")

        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, _handle))
        app.add_handler(CommandHandler("start", lambda u, c: u.message.reply_text("cogman online. Ask me anything.")))

        log.info("Telegram gateway starting...")
        self._thread = threading.Thread(
            target=lambda: app.run_polling(drop_pending_updates=True),
            daemon=True,
        )
        self._thread.start()

    def stop(self):
        if self._app:
            asyncio.run(self._app.shutdown())

    def send(self, channel_id: str, text: str):
        if not self._app:
            return
        async def _send():
            await self._app.bot.send_message(chat_id=channel_id, text=text)
        asyncio.run(_send())


# ── Discord ───────────────────────────────────────────────────────────────────

class DiscordAdapter(GatewayAdapter):
    platform = "discord"

    def __init__(self, token: Optional[str] = None):
        self._token = token or os.getenv("COGMAN_DISCORD_TOKEN", "")
        self._client = None
        self._thread = None

    def is_configured(self) -> bool:
        if not self._token:
            return False
        try:
            import discord  # noqa: F401
            return True
        except ImportError:
            return False

    def start(self, on_message: Callable[[MessageEvent], str]):
        if not self.is_configured():
            log.warning("Discord not configured (missing token or discord.py)")
            return

        import discord

        intents = discord.Intents.default()
        intents.message_content = True
        client = discord.Client(intents=intents)
        self._client = client

        @client.event
        async def on_ready():
            log.info("Discord gateway ready as %s", client.user)

        @client.event
        async def on_message(message):
            if message.author == client.user:
                return
            # Respond in DMs or when mentioned
            is_dm = isinstance(message.channel, discord.DMChannel)
            is_mentioned = client.user in message.mentions
            if not (is_dm or is_mentioned):
                return

            text = message.content
            if is_mentioned:
                text = text.replace(f"<@{client.user.id}>", "").strip()

            evt = MessageEvent(
                platform="discord",
                channel_id=str(message.channel.id),
                user_id=str(message.author.id),
                user_name=message.author.display_name,
                text=text,
                is_direct=is_dm,
                raw=message,
            )
            log.info("[Discord] %s: %s", evt.user_name, evt.text[:80])
            try:
                async with message.channel.typing():
                    response = on_message(evt)
                for chunk in _split_message(response, 2000):
                    await message.channel.send(chunk)
            except Exception as e:
                log.error("Discord handler error: %s", e)
                await message.channel.send(f"Error: {e}")

        self._thread = threading.Thread(
            target=lambda: client.run(self._token),
            daemon=True,
        )
        self._thread.start()

    def stop(self):
        if self._client:
            asyncio.run(self._client.close())

    def send(self, channel_id: str, text: str):
        if not self._client:
            return
        channel = self._client.get_channel(int(channel_id))
        if channel:
            asyncio.run(channel.send(text))


# ── Slack ─────────────────────────────────────────────────────────────────────

class SlackAdapter(GatewayAdapter):
    platform = "slack"

    def __init__(self, bot_token: Optional[str] = None, app_token: Optional[str] = None):
        self._bot_token = bot_token or os.getenv("COGMAN_SLACK_BOT_TOKEN", "")
        self._app_token = app_token or os.getenv("COGMAN_SLACK_APP_TOKEN", "")
        self._app = None
        self._thread = None

    def is_configured(self) -> bool:
        if not self._bot_token or not self._app_token:
            return False
        try:
            from slack_bolt import App  # noqa: F401
            return True
        except ImportError:
            return False

    def start(self, on_message: Callable[[MessageEvent], str]):
        if not self.is_configured():
            log.warning("Slack not configured (missing tokens or slack-bolt)")
            return

        from slack_bolt import App
        from slack_bolt.adapter.socket_mode import SocketModeHandler

        app = App(token=self._bot_token)
        self._app = app

        @app.event("message")
        def handle_message(event, say, client):
            text = event.get("text", "")
            if not text or event.get("bot_id"):
                return
            evt = MessageEvent(
                platform="slack",
                channel_id=event.get("channel", ""),
                user_id=event.get("user", ""),
                user_name=event.get("user", "user"),
                text=text,
                is_direct=event.get("channel_type") == "im",
                raw=event,
            )
            log.info("[Slack] %s: %s", evt.user_name, evt.text[:80])
            try:
                response = on_message(evt)
                for chunk in _split_message(response, 3000):
                    say(chunk)
            except Exception as e:
                log.error("Slack handler error: %s", e)
                say(f"Error: {e}")

        handler = SocketModeHandler(app, self._app_token)
        self._thread = threading.Thread(target=handler.start, daemon=True)
        self._thread.start()

    def stop(self):
        pass  # Slack socket mode stops with process

    def send(self, channel_id: str, text: str):
        if self._app:
            self._app.client.chat_postMessage(channel=channel_id, text=text)


# ── Webhook ───────────────────────────────────────────────────────────────────

class WebhookAdapter(GatewayAdapter):
    platform = "webhook"

    def __init__(self, port: Optional[int] = None, host: str = "0.0.0.0"):
        self._port = port or int(os.getenv("COGMAN_WEBHOOK_PORT", "7778"))
        self._host = host
        self._server = None
        self._thread = None
        self._on_message: Optional[Callable] = None

    def is_configured(self) -> bool:
        try:
            import fastapi  # noqa: F401
            import uvicorn  # noqa: F401
            return True
        except ImportError:
            return False

    def start(self, on_message: Callable[[MessageEvent], str]):
        if not self.is_configured():
            log.warning("Webhook adapter requires fastapi + uvicorn")
            return

        self._on_message = on_message
        import fastapi, uvicorn
        from fastapi import FastAPI
        from pydantic import BaseModel

        app = FastAPI(title="cogman webhook")

        class WebhookPayload(BaseModel):
            text: str
            channel_id: str = "webhook"
            user_id: str = "user"
            user_name: str = "user"

        @app.post("/chat")
        def chat(payload: WebhookPayload):
            evt = MessageEvent(
                platform="webhook",
                channel_id=payload.channel_id,
                user_id=payload.user_id,
                user_name=payload.user_name,
                text=payload.text,
            )
            response = self._on_message(evt)
            return {"response": response}

        @app.get("/health")
        def health():
            return {"status": "ok", "service": "cogman"}

        config = uvicorn.Config(app, host=self._host, port=self._port, log_level="warning")
        self._server = uvicorn.Server(config)
        self._thread = threading.Thread(target=self._server.run, daemon=True)
        self._thread.start()
        log.info("Webhook gateway on http://%s:%d/chat", self._host, self._port)

    def stop(self):
        if self._server:
            self._server.should_exit = True

    def send(self, channel_id: str, text: str):
        pass  # Webhook is request/response only


# ── Gateway Runner ────────────────────────────────────────────────────────────

class GatewayRunner:
    """
    Manages all gateway adapters. Inspired by OpenClaw GatewayRunner.

    OpenClaw's 7-stage pipeline per message:
      normalize → route → assemble context → infer → ReAct → load skills → persist memory
    """

    def __init__(self, orchestrator, memory, session_mgr=None, plugin_engine=None):
        self.orch = orchestrator
        self.memory = memory
        self.session = session_mgr
        self.plugins = plugin_engine
        self._adapters: List[GatewayAdapter] = []
        self._running = False
        self._per_channel_memory: Dict[str, "ChannelMemory"] = {}

        self._setup_adapters()

    def _setup_adapters(self):
        self._adapters = [
            TelegramAdapter(),
            DiscordAdapter(),
            SlackAdapter(),
            WebhookAdapter(),
        ]
        configured = [a.platform for a in self._adapters if a.is_configured()]
        if configured:
            log.info("Gateway adapters available: %s", configured)

    def start(self):
        """Start all configured adapters."""
        started = []
        for adapter in self._adapters:
            if adapter.is_configured():
                try:
                    adapter.start(self._handle_message)
                    started.append(adapter.platform)
                except Exception as e:
                    log.error("Failed to start %s adapter: %s", adapter.platform, e)

        if not started:
            print("\n[gateway] No adapters configured. Set one of:")
            print("  COGMAN_TELEGRAM_TOKEN    — Telegram bot")
            print("  COGMAN_DISCORD_TOKEN     — Discord bot")
            print("  COGMAN_SLACK_BOT_TOKEN + COGMAN_SLACK_APP_TOKEN — Slack")
            print("  (Webhook always on port 7778 if fastapi+uvicorn installed)")
            # Try webhook as fallback
            webhook = WebhookAdapter()
            if webhook.is_configured():
                webhook.start(self._handle_message)
                started.append("webhook")

        if started:
            print(f"\n[gateway] cogman online via: {', '.join(started)}")
            print("[gateway] Ctrl+C to stop\n")
            self._running = True
            try:
                while self._running:
                    time.sleep(1)
            except KeyboardInterrupt:
                self.stop()

    def stop(self):
        self._running = False
        for adapter in self._adapters:
            try:
                adapter.stop()
            except Exception:
                pass
        print("\n[gateway] Stopped.")

    def _handle_message(self, evt: MessageEvent) -> str:
        """
        Process a gateway message through the 7-stage pipeline (OpenClaw-inspired):
          1. Normalize  — clean/classify input
          2. Route      — check slash commands, rate limits
          3. Plugin hook — pre_gateway_dispatch
          4. Assemble context — per-channel memory
          5. Infer      — run orchestrator
          6. ReAct      — tool execution (inside orchestrator)
          7. Persist    — save to memory + session
        """
        # 1. Normalize
        text = evt.text.strip()
        if not text:
            return ""

        # 2. Route — slash command check
        from core.command_registry import resolve_command
        cmd_result = resolve_command(text)
        if cmd_result:
            cmd, args = cmd_result
            if not cmd.cli_only:
                if hasattr(self.orch, 'dispatcher') and self.orch.dispatcher:
                    return self.orch.dispatcher.dispatch(cmd, args)

        # 3. Plugin hook
        if self.plugins:
            hook_result = self.plugins.invoke_hook_first(
                "pre_gateway_dispatch", event=evt, gateway=self,
            )
            if isinstance(hook_result, dict):
                action = hook_result.get("action")
                if action == "skip":
                    return ""
                elif action == "rewrite":
                    text = hook_result.get("text", text)

        # 4. Assemble per-channel context
        channel_key = f"{evt.platform}:{evt.channel_id}"
        if channel_key not in self._per_channel_memory:
            self._per_channel_memory[channel_key] = ChannelMemory()
        chan_mem = self._per_channel_memory[channel_key]
        chan_mem.add(evt.user_name, text)

        # Add platform context to user message
        platform_hint = f"[{evt.platform} from {evt.user_name}] "
        full_text = platform_hint + text

        # 5-6. Infer + ReAct (orchestrator handles tool calling loop)
        self.memory.add_message("user", full_text)
        try:
            response = self.orch.process(full_text)
        except Exception as e:
            log.error("Gateway process error: %s", e)
            response = f"Sorry, I encountered an error: {e}"

        # 7. Persist
        if self.session:
            self.session.add_message("user", full_text)
            self.session.add_message("assistant", response)

        chan_mem.add("cogman", response)
        return response

    def broadcast(self, text: str):
        """Send a message to all connected channels."""
        for adapter in self._adapters:
            if adapter.is_configured():
                try:
                    # We'd need to track active channels — simplified version
                    log.info("Broadcast via %s: %s", adapter.platform, text[:80])
                except Exception as e:
                    log.error("Broadcast error (%s): %s", adapter.platform, e)


class ChannelMemory:
    """Minimal per-channel conversation buffer for gateways."""

    def __init__(self, max_size: int = 10):
        self._history = []
        self._max = max_size

    def add(self, name: str, text: str):
        self._history.append({"name": name, "text": text})
        if len(self._history) > self._max:
            self._history = self._history[-self._max:]

    def format(self) -> str:
        return "\n".join(f"{m['name']}: {m['text']}" for m in self._history)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _split_message(text: str, max_len: int) -> List[str]:
    """Split a long message into chunks under max_len."""
    if len(text) <= max_len:
        return [text]
    chunks = []
    while len(text) > max_len:
        # Try to split at newline
        split_at = text.rfind("\n", 0, max_len)
        if split_at == -1:
            split_at = max_len
        chunks.append(text[:split_at])
        text = text[split_at:].lstrip("\n")
    if text:
        chunks.append(text)
    return chunks
