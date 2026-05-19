"""
Multi-channel gateway — connects cogman to messaging platforms.

Supported channels:
  - Telegram   (python-telegram-bot)
  - WhatsApp   (Green API — free REST tier, no Node.js needed)
  - Matrix     (matrix-nio)
  - Discord    (discord.py)
  - Slack      (slack-bolt, socket mode)
  - IRC        (built-in socket, zero deps)
  - Webhook    (FastAPI/uvicorn)

Run with: python main.py --gateway

Config via env:
  COGMAN_TELEGRAM_TOKEN          → Telegram bot token
  COGMAN_WHATSAPP_INSTANCE       → Green API instance ID
  COGMAN_WHATSAPP_TOKEN          → Green API API token
  COGMAN_WHATSAPP_WEBHOOK_PORT   → incoming webhook port (default 7779)
  COGMAN_MATRIX_HOMESERVER       → e.g. https://matrix.org
  COGMAN_MATRIX_USER             → @cogman:matrix.org
  COGMAN_MATRIX_PASSWORD         → password  (or TOKEN)
  COGMAN_MATRIX_TOKEN            → access token
  COGMAN_DISCORD_TOKEN           → Discord bot token
  COGMAN_SLACK_BOT_TOKEN         → Slack bot token
  COGMAN_SLACK_APP_TOKEN         → Slack socket mode token
  COGMAN_IRC_HOST                → IRC server host
  COGMAN_IRC_CHANNEL             → IRC channel (default #cogman)
  COGMAN_WEBHOOK_PORT            → Webhook port (default 7778)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
import time
import urllib.request
import urllib.parse
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

log = logging.getLogger("cogman.gateway")

# ── Message event ─────────────────────────────────────────────────────────────

@dataclass
class MessageEvent:
    platform:    str
    channel_id:  str
    user_id:     str
    user_name:   str
    text:        str
    timestamp:   float = field(default_factory=time.time)
    is_direct:   bool  = True
    attachments: List[str] = field(default_factory=list)
    raw:         Any   = None

@dataclass
class GatewayResponse:
    text:       str
    channel_id: str
    platform:   str
    reply_to:   Optional[str] = None


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

    def __init__(self):
        self._token  = os.getenv("COGMAN_TELEGRAM_TOKEN", "")
        self._app    = None
        self._thread = None

    def is_configured(self) -> bool:
        if not self._token:
            return False
        try:
            from telegram.ext import Application  # noqa
            return True
        except ImportError:
            return False

    def start(self, on_message: Callable[[MessageEvent], str]):
        if not self.is_configured():
            log.warning("Telegram: not configured")
            return
        from telegram import Update
        from telegram.ext import Application, MessageHandler, CommandHandler, filters

        app = Application.builder().token(self._token).build()
        self._app = app

        async def _handle(update: Update, context):
            if not update.message or not update.message.text:
                return
            evt = MessageEvent(
                platform   = "telegram",
                channel_id = str(update.message.chat_id),
                user_id    = str(update.message.from_user.id),
                user_name  = update.message.from_user.first_name or "User",
                text       = update.message.text,
                is_direct  = update.message.chat.type == "private",
                raw        = update,
            )
            log.info("[Telegram] %s: %s", evt.user_name, evt.text[:80])
            try:
                response = on_message(evt)
                for chunk in _split(response or "", 4096):
                    await update.message.reply_text(chunk)
            except Exception as e:
                log.error("Telegram error: %s", e)
                await update.message.reply_text(f"Error: {e}")

        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, _handle))
        app.add_handler(CommandHandler("start", lambda u, c: u.message.reply_text(
            "COGMAN online. Ask me anything.")))
        app.add_handler(CommandHandler("status", lambda u, c: u.message.reply_text(
            "COGMAN is running. Use /help for commands.")))

        self._thread = threading.Thread(
            target=lambda: app.run_polling(drop_pending_updates=True),
            daemon=True,
        )
        self._thread.start()
        log.info("Telegram gateway started")

    def stop(self):
        if self._app:
            asyncio.run(self._app.shutdown())

    def send(self, channel_id: str, text: str):
        if not self._app:
            return
        async def _s():
            await self._app.bot.send_message(chat_id=channel_id, text=text)
        asyncio.run(_s())


# ── WhatsApp (Green API) ──────────────────────────────────────────────────────

class WhatsAppAdapter(GatewayAdapter):
    """
    WhatsApp via Green API (https://green-api.com) — free REST tier.

    Setup:
      1. Register at green-api.com
      2. Create an instance, scan QR with your phone
      3. Set COGMAN_WHATSAPP_INSTANCE and COGMAN_WHATSAPP_TOKEN
      4. Optionally set COGMAN_WHATSAPP_WEBHOOK_PORT for incoming messages

    Incoming messages are polled (no webhook required) or received via webhook.
    """
    platform = "whatsapp"

    _BASE = "https://api.green-api.com"

    def __init__(self):
        self._instance = os.getenv("COGMAN_WHATSAPP_INSTANCE", "")
        self._token    = os.getenv("COGMAN_WHATSAPP_TOKEN", "")
        self._wport    = int(os.getenv("COGMAN_WHATSAPP_WEBHOOK_PORT", "7779"))
        self._thread: Optional[threading.Thread] = None
        self._running  = False
        self._on_message: Optional[Callable] = None

    def is_configured(self) -> bool:
        return bool(self._instance and self._token)

    def _url(self, method: str) -> str:
        return f"{self._BASE}/waInstance{self._instance}/{method}/{self._token}"

    def _get(self, method: str) -> Optional[dict]:
        try:
            with urllib.request.urlopen(self._url(method), timeout=10) as r:
                return json.loads(r.read())
        except Exception as e:
            log.debug("WhatsApp GET %s: %s", method, e)
            return None

    def _post(self, method: str, data: dict) -> Optional[dict]:
        try:
            payload = json.dumps(data).encode()
            req = urllib.request.Request(
                self._url(method), data=payload,
                headers={"Content-Type": "application/json"}, method="POST",
            )
            with urllib.request.urlopen(req, timeout=15) as r:
                return json.loads(r.read())
        except Exception as e:
            log.error("WhatsApp POST %s: %s", method, e)
            return None

    def start(self, on_message: Callable[[MessageEvent], str]):
        if not self.is_configured():
            log.warning("WhatsApp: not configured (set COGMAN_WHATSAPP_INSTANCE + COGMAN_WHATSAPP_TOKEN)")
            return

        # Check instance state
        state = self._get("getStateInstance")
        if state and state.get("stateInstance") not in ("authorized", "notAuthorized"):
            log.warning("WhatsApp instance state: %s", state)

        self._on_message = on_message
        self._running    = True

        # Start webhook receiver + polling
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()
        log.info("WhatsApp gateway started (instance=%s)", self._instance)

    def _poll_loop(self):
        """Poll Green API for incoming messages via receiveNotification."""
        while self._running:
            try:
                notif = self._get("receiveNotification")
                if not notif or "body" not in notif:
                    time.sleep(1)
                    continue

                receipt_id = notif.get("receiptId")
                body       = notif.get("body", {})

                self._process_notification(body)

                # Acknowledge (delete) the notification
                if receipt_id:
                    self._post(f"deleteNotification/{receipt_id}", {})

            except Exception as e:
                log.error("WhatsApp poll error: %s", e)
                time.sleep(3)

    def _process_notification(self, body: dict):
        if body.get("typeWebhook") not in ("incomingMessageReceived",):
            return
        msg = body.get("messageData", {})
        if msg.get("typeMessage") != "textMessage":
            return  # skip non-text (images, voice, etc.)

        text = msg.get("textMessageData", {}).get("textMessage", "").strip()
        if not text:
            return

        sender = body.get("senderData", {})
        chat_id   = sender.get("chatId", "")
        sender_id = sender.get("sender", "")
        name      = sender.get("senderName", sender_id.split("@")[0])

        evt = MessageEvent(
            platform   = "whatsapp",
            channel_id = chat_id,
            user_id    = sender_id,
            user_name  = name,
            text       = text,
            is_direct  = "@g.us" not in chat_id,
            raw        = body,
        )
        log.info("[WhatsApp] %s: %s", name, text[:80])

        if self._on_message:
            try:
                response = self._on_message(evt)
                if response:
                    self.send(chat_id, response)
            except Exception as e:
                log.error("WhatsApp handler error: %s", e)
                self.send(chat_id, f"Error: {e}")

    def stop(self):
        self._running = False

    def send(self, channel_id: str, text: str):
        if not self.is_configured():
            return
        for chunk in _split(text, 4096):
            self._post("sendMessage", {
                "chatId":  channel_id,
                "message": chunk,
            })


# ── Matrix ────────────────────────────────────────────────────────────────────

class MatrixAdapter(GatewayAdapter):
    """
    Matrix protocol via matrix-nio.

    Config:
      COGMAN_MATRIX_HOMESERVER  → https://matrix.org
      COGMAN_MATRIX_USER        → @cogman:matrix.org
      COGMAN_MATRIX_PASSWORD    → password
      COGMAN_MATRIX_TOKEN       → access token (alternative)
      COGMAN_MATRIX_ROOMS       → comma-separated room IDs to join
    """
    platform = "matrix"

    def __init__(self):
        self._homeserver = os.getenv("COGMAN_MATRIX_HOMESERVER", "")
        self._user       = os.getenv("COGMAN_MATRIX_USER", "")
        self._password   = os.getenv("COGMAN_MATRIX_PASSWORD", "")
        self._token      = os.getenv("COGMAN_MATRIX_TOKEN", "")
        self._rooms_env  = os.getenv("COGMAN_MATRIX_ROOMS", "")
        self._client     = None
        self._thread: Optional[threading.Thread] = None
        self._on_message: Optional[Callable] = None

    def is_configured(self) -> bool:
        return bool(self._homeserver and self._user and
                    (self._password or self._token))

    def start(self, on_message: Callable[[MessageEvent], str]):
        if not self.is_configured():
            log.warning("Matrix: not configured")
            return
        self._on_message = on_message
        self._thread     = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        log.info("Matrix gateway started (%s)", self._homeserver)

    def _run(self):
        try:
            import asyncio
            asyncio.run(self._async_run())
        except Exception as e:
            log.error("Matrix run error: %s", e)

    async def _async_run(self):
        try:
            from nio import AsyncClient, MatrixRoom, RoomMessageText, LoginResponse
        except ImportError:
            log.error("Matrix: install matrix-nio")
            return

        client = AsyncClient(self._homeserver, self._user)
        self._client = client

        if self._token:
            client.access_token = self._token
            client.user_id      = self._user
        else:
            resp = await client.login(self._password)
            if not isinstance(resp, LoginResponse):
                log.error("Matrix login failed: %s", resp)
                return

        # Join configured rooms
        if self._rooms_env:
            for room_id in self._rooms_env.split(","):
                room_id = room_id.strip()
                if room_id:
                    await client.join(room_id)

        def _on_room_message(room: MatrixRoom, event: RoomMessageText):
            # Ignore our own messages
            if event.sender == client.user_id:
                return
            text = event.body.strip()
            if not text:
                return
            evt = MessageEvent(
                platform   = "matrix",
                channel_id = room.room_id,
                user_id    = event.sender,
                user_name  = room.user_name(event.sender) or event.sender,
                text       = text,
                is_direct  = room.member_count == 2,
                raw        = event,
            )
            log.info("[Matrix] %s: %s", evt.user_name, evt.text[:80])
            if self._on_message:
                response = self._on_message(evt)
                if response:
                    asyncio.ensure_future(client.room_send(
                        room_id     = room.room_id,
                        message_type= "m.room.message",
                        content     = {"msgtype": "m.text", "body": response},
                    ))

        client.add_event_callback(_on_room_message, RoomMessageText)

        log.info("Matrix: syncing as %s", client.user_id)
        await client.sync_forever(timeout=30000)

    def stop(self):
        if self._client:
            asyncio.run(self._client.close())

    def send(self, channel_id: str, text: str):
        if not self._client:
            return
        async def _s():
            await self._client.room_send(
                room_id=channel_id,
                message_type="m.room.message",
                content={"msgtype": "m.text", "body": text},
            )
        asyncio.run(_s())


# ── Discord ───────────────────────────────────────────────────────────────────

class DiscordAdapter(GatewayAdapter):
    platform = "discord"

    def __init__(self):
        self._token  = os.getenv("COGMAN_DISCORD_TOKEN", "")
        self._client = None
        self._thread = None

    def is_configured(self) -> bool:
        if not self._token:
            return False
        try:
            import discord  # noqa
            return True
        except ImportError:
            return False

    def start(self, on_message: Callable[[MessageEvent], str]):
        if not self.is_configured():
            log.warning("Discord: not configured")
            return
        import discord
        intents = discord.Intents.default()
        intents.message_content = True
        client = discord.Client(intents=intents)
        self._client = client
        _handler = on_message

        @client.event
        async def on_ready():
            log.info("Discord ready as %s", client.user)

        @client.event
        async def on_message(message):
            if message.author == client.user:
                return
            is_dm      = isinstance(message.channel, discord.DMChannel)
            is_mention = client.user in message.mentions
            if not (is_dm or is_mention):
                return
            text = message.content
            if is_mention:
                text = text.replace(f"<@{client.user.id}>", "").strip()
            evt = MessageEvent(
                platform   = "discord",
                channel_id = str(message.channel.id),
                user_id    = str(message.author.id),
                user_name  = message.author.display_name,
                text       = text,
                is_direct  = is_dm,
                raw        = message,
            )
            log.info("[Discord] %s: %s", evt.user_name, evt.text[:80])
            try:
                async with message.channel.typing():
                    response = _handler(evt)
                for chunk in _split(response or "", 2000):
                    await message.channel.send(chunk)
            except Exception as e:
                log.error("Discord error: %s", e)
                await message.channel.send(f"Error: {e}")

        self._thread = threading.Thread(target=lambda: client.run(self._token), daemon=True)
        self._thread.start()

    def stop(self):
        if self._client:
            asyncio.run(self._client.close())

    def send(self, channel_id: str, text: str):
        if self._client:
            ch = self._client.get_channel(int(channel_id))
            if ch:
                asyncio.run(ch.send(text))


# ── Slack ─────────────────────────────────────────────────────────────────────

class SlackAdapter(GatewayAdapter):
    platform = "slack"

    def __init__(self):
        self._bot_token = os.getenv("COGMAN_SLACK_BOT_TOKEN", "")
        self._app_token = os.getenv("COGMAN_SLACK_APP_TOKEN", "")
        self._app    = None
        self._thread = None

    def is_configured(self) -> bool:
        if not (self._bot_token and self._app_token):
            return False
        try:
            from slack_bolt import App  # noqa
            return True
        except ImportError:
            return False

    def start(self, on_message: Callable[[MessageEvent], str]):
        if not self.is_configured():
            log.warning("Slack: not configured")
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
                platform   = "slack",
                channel_id = event.get("channel", ""),
                user_id    = event.get("user", ""),
                user_name  = event.get("user", "user"),
                text       = text,
                is_direct  = event.get("channel_type") == "im",
                raw        = event,
            )
            log.info("[Slack] %s: %s", evt.user_name, evt.text[:80])
            try:
                response = on_message(evt)
                for chunk in _split(response or "", 3000):
                    say(chunk)
            except Exception as e:
                log.error("Slack error: %s", e)
                say(f"Error: {e}")

        handler = SocketModeHandler(app, self._app_token)
        self._thread = threading.Thread(target=handler.start, daemon=True)
        self._thread.start()

    def stop(self):
        pass

    def send(self, channel_id: str, text: str):
        if self._app:
            self._app.client.chat_postMessage(channel=channel_id, text=text)


# ── IRC ───────────────────────────────────────────────────────────────────────

class IRCAdapter(GatewayAdapter):
    """Native IRC adapter — zero extra deps, uses built-in socket."""
    platform = "irc"

    def __init__(self):
        self._host     = os.getenv("COGMAN_IRC_HOST", "")
        self._port     = int(os.getenv("COGMAN_IRC_PORT", "6667"))
        self._nick     = os.getenv("COGMAN_IRC_NICK", "cogman")
        self._channel  = os.getenv("COGMAN_IRC_CHANNEL", "#cogman")
        self._password = os.getenv("COGMAN_IRC_PASSWORD", "")
        self._tls      = os.getenv("COGMAN_IRC_TLS", "false").lower() == "true"
        self._sock     = None
        self._thread: Optional[threading.Thread] = None
        self._on_message: Optional[Callable] = None
        self._running  = False

    def is_configured(self) -> bool:
        return bool(self._host)

    def start(self, on_message: Callable[[MessageEvent], str]):
        if not self.is_configured():
            log.warning("IRC: COGMAN_IRC_HOST not set")
            return
        self._on_message = on_message
        self._running    = True
        self._thread     = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        log.info("IRC gateway started (%s:%d%s)", self._host, self._port, "/TLS" if self._tls else "")

    def _run(self):
        import socket
        import ssl as _ssl
        raw = socket.create_connection((self._host, self._port), timeout=30)
        if self._tls:
            ctx = _ssl.create_default_context()
            raw = ctx.wrap_socket(raw, server_hostname=self._host)
        self._sock = raw

        def send_raw(line: str):
            raw.sendall((line + "\r\n").encode("utf-8", errors="replace"))

        if self._password:
            send_raw(f"PASS {self._password}")
        send_raw(f"NICK {self._nick}")
        send_raw(f"USER {self._nick} 0 * :COGMAN AI assistant")

        buf = ""
        while self._running:
            try:
                data = raw.recv(4096).decode("utf-8", errors="replace")
            except OSError:
                break
            if not data:
                break
            buf += data
            while "\r\n" in buf:
                line, buf = buf.split("\r\n", 1)
                self._handle(line, send_raw)

    def _handle(self, line: str, send_raw: Callable):
        log.debug("[IRC] %s", line)
        if line.startswith("PING"):
            send_raw("PONG" + line[4:])
            return
        if " 001 " in line:
            send_raw(f"JOIN {self._channel}")
            return
        if " PRIVMSG " not in line:
            return
        try:
            prefix, rest = line.split(" PRIVMSG ", 1)
            nick   = prefix.lstrip(":").split("!")[0]
            target, msg = rest.split(" :", 1)
            target = target.strip()
            is_dm  = target == self._nick
            if not is_dm and self._nick.lower() not in msg.lower():
                return
            evt = MessageEvent(
                platform   = "irc",
                channel_id = target if not is_dm else nick,
                user_id    = nick,
                user_name  = nick,
                text       = msg.strip(),
                is_direct  = is_dm,
            )
            if self._on_message:
                response  = self._on_message(evt)
                reply_to  = nick if is_dm else target
                for chunk in _split(response or "", 400):
                    send_raw(f"PRIVMSG {reply_to} :{chunk}")
        except Exception as e:
            log.error("IRC parse error: %s — %s", e, line)

    def stop(self):
        self._running = False
        if self._sock:
            try:
                self._sock.close()
            except OSError:
                pass

    def send(self, channel_id: str, text: str):
        if self._sock:
            for chunk in _split(text, 400):
                try:
                    self._sock.sendall(f"PRIVMSG {channel_id} :{chunk}\r\n".encode())
                except OSError:
                    break


# ── Webhook ───────────────────────────────────────────────────────────────────

class WebhookAdapter(GatewayAdapter):
    platform = "webhook"

    def __init__(self):
        self._port   = int(os.getenv("COGMAN_WEBHOOK_PORT", "7778"))
        self._host   = "0.0.0.0"
        self._server = None
        self._thread = None
        self._on_message: Optional[Callable] = None

    def is_configured(self) -> bool:
        try:
            import fastapi, uvicorn  # noqa
            return True
        except ImportError:
            return False

    def start(self, on_message: Callable[[MessageEvent], str]):
        if not self.is_configured():
            log.warning("Webhook: fastapi/uvicorn not installed")
            return
        self._on_message = on_message
        import fastapi, uvicorn
        from fastapi import FastAPI, Header
        from pydantic import BaseModel

        app = FastAPI(title="cogman webhook")

        class Payload(BaseModel):
            text:       str
            channel_id: str  = "webhook"
            user_id:    str  = "user"
            user_name:  str  = "user"
            platform:   str  = "webhook"

        @app.post("/chat")
        def chat(p: Payload):
            evt = MessageEvent(
                platform=p.platform, channel_id=p.channel_id,
                user_id=p.user_id,   user_name=p.user_name, text=p.text,
            )
            return {"response": self._on_message(evt)}

        @app.get("/health")
        def health():
            return {"status": "ok", "service": "cogman"}

        # WhatsApp Green API incoming webhook
        @app.post("/wa")
        async def wa_webhook(request: fastapi.Request):
            body = await request.json()
            # Parse and dispatch WhatsApp notification
            if body.get("typeWebhook") == "incomingMessageReceived":
                msg    = body.get("messageData", {})
                sender = body.get("senderData", {})
                text   = msg.get("textMessageData", {}).get("textMessage", "").strip()
                if text and self._on_message:
                    chat_id = sender.get("chatId", "")
                    name    = sender.get("senderName", "")
                    evt = MessageEvent(
                        platform="whatsapp", channel_id=chat_id,
                        user_id=sender.get("sender",""), user_name=name, text=text,
                    )
                    resp = self._on_message(evt)
                    return {"response": resp}
            return {"status": "ignored"}

        config       = uvicorn.Config(app, host=self._host, port=self._port, log_level="warning")
        self._server = uvicorn.Server(config)
        self._thread = threading.Thread(target=self._server.run, daemon=True)
        self._thread.start()
        log.info("Webhook gateway on http://%s:%d", self._host, self._port)

    def stop(self):
        if self._server:
            self._server.should_exit = True

    def send(self, channel_id: str, text: str):
        pass


# ── Gateway Runner ────────────────────────────────────────────────────────────

class GatewayRunner:
    """
    Manages all gateway adapters.

    Per-message pipeline:
      normalize → route → plugin hook → assemble context → infer → ReAct → persist
    """

    def __init__(self, orchestrator, memory, session_mgr=None, plugin_engine=None):
        self.orch    = orchestrator
        self.memory  = memory
        self.session = session_mgr
        self.plugins = plugin_engine
        self._adapters: List[GatewayAdapter] = []
        self._running  = False
        self._per_channel_memory: Dict[str, ChannelMemory] = {}
        self._setup_adapters()

    def _setup_adapters(self):
        self._adapters = [
            TelegramAdapter(),
            WhatsAppAdapter(),
            MatrixAdapter(),
            DiscordAdapter(),
            SlackAdapter(),
            WebhookAdapter(),
            IRCAdapter(),
        ]
        configured = [a.platform for a in self._adapters if a.is_configured()]
        log.info("Configured adapters: %s", configured or ["none"])

    def start(self):
        started = []
        for adapter in self._adapters:
            if adapter.is_configured():
                try:
                    adapter.start(self._handle_message)
                    started.append(adapter.platform)
                    log.info("Started adapter: %s", adapter.platform)
                except Exception as e:
                    log.error("Failed to start %s: %s", adapter.platform, e)

        if not started:
            print("\n[gateway] No adapters configured. Set one of:")
            print("  COGMAN_TELEGRAM_TOKEN                                 — Telegram")
            print("  COGMAN_WHATSAPP_INSTANCE + COGMAN_WHATSAPP_TOKEN      — WhatsApp")
            print("  COGMAN_MATRIX_HOMESERVER + COGMAN_MATRIX_USER + …    — Matrix")
            print("  COGMAN_DISCORD_TOKEN                                  — Discord")
            print("  COGMAN_SLACK_BOT_TOKEN + COGMAN_SLACK_APP_TOKEN       — Slack")
            print("  COGMAN_IRC_HOST [+ COGMAN_IRC_CHANNEL]                — IRC")
            print("  (Webhook always on :7778 if fastapi+uvicorn installed)")
            # Try webhook fallback
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
        print("\n[gateway] stopped.")

    def _handle_message(self, evt: MessageEvent) -> str:
        text = evt.text.strip()
        if not text:
            return ""

        # Route slash commands
        from core.command_registry import resolve_command
        cmd_result = resolve_command(text)
        if cmd_result:
            cmd, args = cmd_result
            if not cmd.cli_only and hasattr(self.orch, "dispatcher") and self.orch.dispatcher:
                return self.orch.dispatcher.dispatch(cmd, args)

        # Plugin hook
        if self.plugins:
            hook = self.plugins.invoke_hook_first("pre_gateway_dispatch", event=evt, gateway=self)
            if isinstance(hook, dict):
                action = hook.get("action")
                if action == "skip":
                    return ""
                elif action == "rewrite":
                    text = hook.get("text", text)

        # Per-channel context
        key = f"{evt.platform}:{evt.channel_id}"
        if key not in self._per_channel_memory:
            self._per_channel_memory[key] = ChannelMemory()
        self._per_channel_memory[key].add(evt.user_name, text)

        platform_hint = f"[{evt.platform} from {evt.user_name}] "
        full_text     = platform_hint + text

        self.memory.add_message("user", full_text)
        try:
            response = self.orch.process(full_text)
        except Exception as e:
            log.error("Gateway process error: %s", e)
            response = f"Sorry, I encountered an error: {e}"

        if self.session:
            self.session.add_message("user", full_text)
            self.session.add_message("assistant", response)

        self._per_channel_memory[key].add("cogman", response)
        return response

    def broadcast(self, text: str, platforms: Optional[List[str]] = None):
        """Send a message to all configured adapters."""
        for adapter in self._adapters:
            if platforms and adapter.platform not in platforms:
                continue
            if adapter.is_configured():
                log.info("Broadcast via %s: %s", adapter.platform, text[:60])


class ChannelMemory:
    def __init__(self, max_size: int = 20):
        self._history = []
        self._max     = max_size

    def add(self, name: str, text: str):
        self._history.append({"name": name, "text": text})
        if len(self._history) > self._max:
            self._history = self._history[-self._max:]

    def format(self) -> str:
        return "\n".join(f"{m['name']}: {m['text']}" for m in self._history)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _split(text: str, max_len: int) -> List[str]:
    if len(text) <= max_len:
        return [text]
    chunks = []
    while len(text) > max_len:
        split_at = text.rfind("\n", 0, max_len)
        if split_at == -1:
            split_at = max_len
        chunks.append(text[:split_at])
        text = text[split_at:].lstrip("\n")
    if text:
        chunks.append(text)
    return chunks
