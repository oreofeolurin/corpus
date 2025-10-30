from __future__ import annotations

import asyncio
import json
import os
from typing import Any, Dict, Optional
import sys

from .sources import load_source
from .. import __version__


class MCPServer:
    def __init__(self, source_path: str, source_type: str = "auto") -> None:
        self.source_path = source_path
        self.source_type = source_type
        self.source = load_source(source_path, source_type)

    def _tools_spec(self) -> Dict[str, Any]:
        return {
            "tools": [
                {
                    "name": "list_files",
                    "description": "List repository files",
                    "inputSchema": {"type": "object", "properties": {}, "required": []},
                },
                {
                    "name": "get_file",
                    "description": "Get file content (optionally a line range)",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string"},
                            "start": {"type": "integer"},
                            "end": {"type": "integer"},
                        },
                        "required": ["path"],
                    },
                },
                {
                    "name": "search",
                    "description": "Search for a string across files",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string"},
                            "top_k": {"type": "integer"},
                            "case_sensitive": {"type": "boolean"},
                        },
                        "required": ["query"],
                    },
                },
            ]
        }

    def _call_tool(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        if name == "list_files":
            return {"content": [{"type": "text", "text": "\n".join(self.source.list_files())}]}
        if name == "get_file":
            content = self.source.get_file(
                arguments.get("path"), start=arguments.get("start"), end=arguments.get("end")
            )
            return {"content": [{"type": "text", "text": content}]}
        if name == "search":
            hits = self.source.search(
                arguments.get("query"),
                max_results=int(arguments.get("top_k", 50)),
                case_sensitive=bool(arguments.get("case_sensitive", False)),
            )
            text = "\n".join(f"{h.path}:{h.line}: {h.snippet}" for h in hits)
            return {"content": [{"type": "text", "text": text}]}
        raise ValueError(f"Unknown tool: {name}")

    async def handle_request(self, msg: Dict[str, Any]) -> Dict[str, Any]:
        method = msg.get("method")
        params = msg.get("params", {})
        # basic request logging
        try:
            sys.stderr.write(f"[mcp] request method={method} params_keys={list(params.keys())}\n")
            sys.stderr.flush()
        except Exception:
            pass

        # JSON-RPC 2.0 + MCP methods
        if msg.get("jsonrpc") == "2.0":
            if method == "initialize":
                return {
                    "jsonrpc": "2.0",
                    "id": msg.get("id"),
                    "result": {
                        "serverInfo": {"name": "corpus", "version": __version__},
                        "protocolVersion": "2024-11-05",
                        "capabilities": {"tools": {}},
                    },
                }
            if method == "tools/list":
                return {"jsonrpc": "2.0", "id": msg.get("id"), "result": self._tools_spec()}
            if method == "tools/call":
                name = params.get("name")
                args = params.get("arguments", {}) or {}
                out = self._call_tool(name, args)
                return {"jsonrpc": "2.0", "id": msg.get("id"), "result": out}
            if method in {"resources/list", "prompts/list"}:
                return {"jsonrpc": "2.0", "id": msg.get("id"), "result": {"resources": []} if method == "resources/list" else {"prompts": []}}
            # default unknown
            return {"jsonrpc": "2.0", "id": msg.get("id"), "error": {"code": -32601, "message": f"Unknown method: {method}"}}

        # Fallback: simple one-off calls for CLI testing
        if method == "list_files":
            return {"result": {"files": self.source.list_files()}}
        if method == "get_file":
            path = params.get("path")
            start = params.get("start")
            end = params.get("end")
            content = self.source.get_file(path, start=start, end=end)
            return {"result": {"content": content}}
        if method == "search":
            query = params.get("query")
            top_k = int(params.get("top_k", 50))
            cs = bool(params.get("case_sensitive", False))
            hits = self.source.search(query, max_results=top_k, case_sensitive=cs)
            return {"result": {"matches": [hit.__dict__ for hit in hits]}}
        return {"error": {"message": f"Unknown method: {method}"}}


async def run_stdio(server: MCPServer) -> None:
    loop = asyncio.get_event_loop()
    reader = asyncio.StreamReader()
    protocol = asyncio.StreamReaderProtocol(reader)
    await loop.connect_read_pipe(lambda: protocol, os.fdopen(0, "rb", buffering=0))
    writer_transport, writer_protocol = await loop.connect_write_pipe(asyncio.streams.FlowControlMixin, os.fdopen(1, "wb", buffering=0))
    writer = asyncio.StreamWriter(writer_transport, writer_protocol, reader, loop)

    # startup log
    try:
        files_count = len(server.source.list_files())
        sys.stderr.write(
            f"[mcp] stdio server started source={server.source_path} type={server.source_type} files={files_count}\n"
        )
        sys.stderr.flush()
    except Exception:
        pass

    # Send MCP ready notification so clients mark server healthy
    try:
        ready = {"jsonrpc": "2.0", "method": "notifications/server/ready", "params": {"capabilities": {}}}
        writer.write((json.dumps(ready) + "\n").encode("utf-8"))
        await writer.drain()
    except Exception:
        pass

    while True:
        line = await reader.readline()
        if not line:
            break
        try:
            req = json.loads(line.decode("utf-8"))
            resp = await server.handle_request(req)
        except Exception as exc:
            resp = {"error": {"message": str(exc)}}
        writer.write((json.dumps(resp) + "\n").encode("utf-8"))
        await writer.drain()


