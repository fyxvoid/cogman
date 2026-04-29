"""
core/memory.py — backward-compat shim.
The real implementation lives in memory/manager.py.
"""
from memory.manager import Memory, ShortTermMemory, LongTermMemory, MemoryProvider
__all__ = ["Memory", "ShortTermMemory", "LongTermMemory", "MemoryProvider"]
