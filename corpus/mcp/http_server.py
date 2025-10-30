from __future__ import annotations

import sys
from typing import Any, Dict

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel

from .sources import load_source
from .catalog import load_catalog
from .. import __version__


class ToolCall(BaseModel):
    name: str
    arguments: Dict[str, Any] | None = None


def create_app(source_path: str | None = None) -> FastAPI:
    single_source = source_path is not None
    source = load_source(source_path, "auto") if single_source else None
    app = FastAPI()

    @app.get("/healthz")
    def health() -> Dict[str, Any]:
        return {"ok": True}

    @app.get("/mcp")
    def mcp_capabilities() -> Dict[str, Any]:
        try:
            files_count = len(source.list_files()) if single_source and source else 0
            sys.stderr.write(f"[mcp-http] ready files={files_count}\n")
            sys.stderr.flush()
        except Exception:
            pass
        return {
            "serverInfo": {"name": "corpus", "version": __version__},
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "tools": [
                {
                    "name": "list_collections",
                    "description": "List registered collections",
                    "inputSchema": {"type": "object", "properties": {}, "required": []},
                },
                {
                    "name": "list_files",
                    "description": "List repository files",
                    "inputSchema": {
                        "type": "object",
                        "properties": {"collection": {"type": "string"}},
                        "required": [] if single_source else ["collection"],
                    },
                },
                {
                    "name": "get_file",
                    "description": "Get file content (optionally a line range)",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "collection": {"type": "string"},
                            "path": {"type": "string"},
                            "start": {"type": "integer"},
                            "end": {"type": "integer"},
                        },
                        "required": ["path"] if single_source else ["collection", "path"],
                    },
                },
                {
                    "name": "search",
                    "description": "Search for a string across files",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "collection": {"type": "string"},
                            "query": {"type": "string"},
                            "top_k": {"type": "integer"},
                            "case_sensitive": {"type": "boolean"},
                        },
                        "required": ["query"] if single_source else ["collection", "query"],
                    },
                },
            ],
            "resources": [],
            "prompts": [],
        }

    def _tools_spec() -> Dict[str, Any]:
        return {
            "tools": [
                {
                    "name": "list_collections",
                    "description": "List registered collections",
                    "inputSchema": {"type": "object", "properties": {}, "required": []},
                },
                {
                    "name": "list_files",
                    "description": "List repository files",
                    "inputSchema": {
                        "type": "object",
                        "properties": {"collection": {"type": "string"}},
                        "required": [] if single_source else ["collection"],
                    },
                },
                {
                    "name": "get_file",
                    "description": "Get file content (optionally a line range)",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "collection": {"type": "string"},
                            "path": {"type": "string"},
                            "start": {"type": "integer"},
                            "end": {"type": "integer"},
                        },
                        "required": ["path"] if single_source else ["collection", "path"],
                    },
                },
                {
                    "name": "search",
                    "description": "Search for a string across files",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "collection": {"type": "string"},
                            "query": {"type": "string"},
                            "top_k": {"type": "integer"},
                            "case_sensitive": {"type": "boolean"},
                        },
                        "required": ["query"] if single_source else ["collection", "query"],
                    },
                },
            ]
        }

    def _resolve_source(arguments: Dict[str, Any]):
        if single_source:
            return source
        col_id = arguments.get("collection")
        if not col_id:
            raise HTTPException(status_code=400, detail="collection required")
        cat = load_catalog()
        match = next((c for c in cat.collections if c.id == col_id), None)
        if not match:
            raise HTTPException(status_code=404, detail="collection not found")
        return load_source(match.source, match.type)

    def _call_tool(name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        if name == "list_collections":
            cat = load_catalog()
            text = "\n".join(f"{c.id}\t{c.type}\t{c.source}" for c in cat.collections)
            return {"content": [{"type": "text", "text": text}]}
        if name == "list_files":
            src = _resolve_source(arguments)
            return {"content": [{"type": "text", "text": "\n".join(src.list_files())}]}
        if name == "get_file":
            path = arguments.get("path")
            if not path:
                raise HTTPException(status_code=400, detail="path required")
            start = arguments.get("start")
            end = arguments.get("end")
            src = _resolve_source(arguments)
            content = src.get_file(path, start=start, end=end)
            return {"content": [{"type": "text", "text": content}]}
        if name == "search":
            query = arguments.get("query")
            if not query:
                raise HTTPException(status_code=400, detail="query required")
            top_k = int(arguments.get("top_k", 50))
            cs = bool(arguments.get("case_sensitive", False))
            src = _resolve_source(arguments)
            hits = src.search(query, max_results=top_k, case_sensitive=cs)
            text = "\n".join(f"{h.path}:{h.line}: {h.snippet}" for h in hits)
            return {"content": [{"type": "text", "text": text}]}
        raise HTTPException(status_code=404, detail="unknown tool")

    @app.post("/mcp/tools/call")
    def call_tool(body: ToolCall) -> Dict[str, Any]:
        name = body.name
        args = body.arguments or {}
        sys.stderr.write(f"[mcp-http] call tool={name}\n")
        sys.stderr.flush()
        return _call_tool(name, args)

    # JSON-RPC style endpoint (Cursor may POST /mcp)
    @app.post("/mcp")
    async def mcp_rpc(request: Request) -> Dict[str, Any]:
        payload = await request.json()
        method = payload.get("method")
        _id = payload.get("id")
        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": _id,
                "result": {
                    "serverInfo": {"name": "corpus", "version": __version__},
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                },
            }
        if method == "tools/list":
            return {"jsonrpc": "2.0", "id": _id, "result": _tools_spec()}
        if method == "tools/call":
            name = (payload.get("params") or {}).get("name")
            args = (payload.get("params") or {}).get("arguments") or {}
            out = _call_tool(name, args)
            return {"jsonrpc": "2.0", "id": _id, "result": out}
        return {"jsonrpc": "2.0", "id": _id, "error": {"code": -32601, "message": "Unknown method"}}

    return app


