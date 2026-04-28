"""FastAPI REST interface for cogman."""
import logging
from typing import Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

log = logging.getLogger("cogman.api")

app = FastAPI(title="cogman", version="1.0.0", description="Linux AI Assistant API")

_orchestrator = None
_memory = None


def init(orchestrator, memory):
    global _orchestrator, _memory
    _orchestrator = orchestrator
    _memory = memory


class QueryRequest(BaseModel):
    text: str
    save_to_memory: bool = False


class QueryResponse(BaseModel):
    response: str
    tool_used: Optional[str] = None


class MemoryRequest(BaseModel):
    content: str
    category: str = "general"


@app.get("/health")
def health():
    return {"status": "ok", "assistant": "cogman"}


@app.post("/query", response_model=QueryResponse)
def query(req: QueryRequest):
    if not _orchestrator:
        raise HTTPException(500, "Orchestrator not initialized")
    result = _orchestrator.process(req.text)
    if req.save_to_memory:
        _memory.remember(f"User asked: {req.text}\nAnswer: {result}")
    return QueryResponse(response=result)


@app.post("/memory")
def remember(req: MemoryRequest):
    if not _memory:
        raise HTTPException(500, "Memory not initialized")
    _memory.remember(req.content, category=req.category)
    return {"saved": True}


@app.get("/memory/search")
def search_memory(q: str, top_k: int = 5):
    if not _memory:
        raise HTTPException(500, "Memory not initialized")
    results = _memory.recall(q)
    return {"query": q, "results": results}


@app.get("/tools")
def list_tools():
    from core.tool_registry import ToolRegistry
    # Lazy import to avoid circular dep
    return {"tools": _orchestrator.registry.list_names() if _orchestrator else []}
