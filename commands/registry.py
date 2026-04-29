"""Slash command registry — moved from core/command_registry.py."""
from core.command_registry import (
    CommandDef, COMMAND_REGISTRY, resolve_command,
    gateway_help_lines, cli_help_text,
)
__all__ = ["CommandDef", "COMMAND_REGISTRY", "resolve_command", "gateway_help_lines", "cli_help_text"]
