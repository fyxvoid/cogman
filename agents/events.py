"""Agent event types for COGMAN's cognitive loop streaming."""
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional

@dataclass
class AgentEvent:
    type: str

@dataclass
class AgentStartEvent(AgentEvent):
    type: str = field(default="agent_start", init=False)

@dataclass
class TurnStartEvent(AgentEvent):
    type: str = field(default="turn_start", init=False)

@dataclass
class MessageStartEvent(AgentEvent):
    type: str = field(default="message_start", init=False)
    role: str = "assistant"
    content: str = ""

@dataclass
class MessageUpdateEvent(AgentEvent):
    type: str = field(default="message_update", init=False)
    delta: str = ""
    content: str = ""

@dataclass
class MessageEndEvent(AgentEvent):
    type: str = field(default="message_end", init=False)
    role: str = "assistant"
    content: str = ""

@dataclass
class ToolExecutionStartEvent(AgentEvent):
    type: str = field(default="tool_execution_start", init=False)
    tool_call_id: str = ""
    tool_name: str = ""
    args: Dict = field(default_factory=dict)

@dataclass
class ToolExecutionUpdateEvent(AgentEvent):
    type: str = field(default="tool_execution_update", init=False)
    tool_call_id: str = ""
    tool_name: str = ""
    partial_result: str = ""

@dataclass
class ToolExecutionEndEvent(AgentEvent):
    type: str = field(default="tool_execution_end", init=False)
    tool_call_id: str = ""
    tool_name: str = ""
    result: str = ""
    is_error: bool = False

@dataclass
class TurnEndEvent(AgentEvent):
    type: str = field(default="turn_end", init=False)
    tool_calls_made: int = 0

@dataclass
class AgentEndEvent(AgentEvent):
    type: str = field(default="agent_end", init=False)
    final_text: str = ""
    tool_calls_made: int = 0
    error: Optional[str] = None

EventListener = Callable[[AgentEvent], None]
