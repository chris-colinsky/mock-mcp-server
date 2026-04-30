"""
MCP server, mounted at /mcp on the FastAPI app.

Builds the MCP tool list directly from the authored OAS dict and dispatches
tool calls back through the FastAPI app via an httpx ASGI transport.
This is intentionally a small, owned shim — the previous version delegated
to fastapi-mcp, but that required either monkey-patching get_openapi or
generating Pydantic models from JSON Schema; both were worse than ~150
lines of focused code here.

What we use from upstream:
  - `mcp.server.lowlevel.Server`         — protocol implementation
  - `mcp.server.streamable_http_manager` — HTTP transport
  - `mcp.types`                          — wire types

What we own:
  - OAS → MCP tool list (`build_tools`)
  - tool dispatch (call our own FastAPI route, return body as TextContent)
"""
from __future__ import annotations

import contextlib
import json
import logging
from typing import Any
from urllib.parse import urlencode

import httpx
import mcp.types as mcp_types
from fastapi import FastAPI, Request
from mcp.server.lowlevel import Server as MCPServer
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager


logger = logging.getLogger(__name__)

# Path-template parameters look like /items/{id}; matched per OAS 3.x.
_PARAM_PATTERN = "{}"


# ---------------------------------------------------------------------------
# OAS → MCP tool list


def build_tools(oas: dict, exclude_tags: list[str] | None = None) -> tuple[list[mcp_types.Tool], dict]:
    """
    Convert an OAS dict into (tools, operation_map).

    operation_map: { operationId: {"method": str, "path": str, "params": [...]} }
    Used by the call dispatcher to know how to translate tool args into HTTP.
    """
    excluded = set(exclude_tags or [])
    tools: list[mcp_types.Tool] = []
    op_map: dict[str, dict] = {}

    schemas = (oas.get("components") or {}).get("schemas") or {}

    for path, path_item in (oas.get("paths") or {}).items():
        for method, op in path_item.items():
            if method not in ("get", "post", "put", "delete", "patch"):
                continue
            tags = op.get("tags") or []
            if any(t in excluded for t in tags):
                continue

            op_id = op.get("operationId") or _default_op_id(method, path)
            description = _format_description(op)
            input_schema, params = _build_input_schema(op, schemas)

            tools.append(
                mcp_types.Tool(
                    name=op_id,
                    description=description,
                    inputSchema=input_schema,
                )
            )
            op_map[op_id] = {"method": method.upper(), "path": path, "params": params}

    return tools, op_map


def _default_op_id(method: str, path: str) -> str:
    return f"{method}_{path.strip('/').replace('/', '_').replace('{', '').replace('}', '')}"


def _format_description(op: dict) -> str:
    parts = []
    summary = op.get("summary")
    description = op.get("description")
    if summary:
        parts.append(summary)
    if description and description != summary:
        parts.append(description)
    return "\n\n".join(parts) or ""


def _build_input_schema(op: dict, schemas: dict) -> tuple[dict, list[dict]]:
    """
    Build a single inputSchema for the tool from query/path parameters and
    (optionally) requestBody. Returns (schema, parameter-list-for-dispatch).
    """
    properties: dict = {}
    required: list[str] = []
    params: list[dict] = []

    for p in op.get("parameters") or []:
        location = p.get("in")
        if location not in ("query", "path"):
            continue
        name = p["name"]
        prop = dict(p.get("schema") or {})
        if p.get("description") and "description" not in prop:
            prop["description"] = p["description"]
        properties[name] = prop
        if p.get("required"):
            required.append(name)
        params.append({"name": name, "in": location})

    body = op.get("requestBody")
    if body:
        # Inline the request body schema as a single named property "body".
        content = (body.get("content") or {}).get("application/json")
        if content and content.get("schema"):
            properties["body"] = _resolve_refs(content["schema"], schemas)
            if body.get("required"):
                required.append("body")
            params.append({"name": "body", "in": "body"})

    schema: dict = {"type": "object", "properties": properties}
    if required:
        schema["required"] = required
    return schema, params


def _resolve_refs(node: Any, schemas: dict, seen: set | None = None) -> Any:
    """Inline $refs to components/schemas. Cycle-safe."""
    seen = seen or set()
    if isinstance(node, dict):
        if "$ref" in node:
            ref = node["$ref"]
            if not ref.startswith("#/components/schemas/"):
                return node
            name = ref.removeprefix("#/components/schemas/")
            if name in seen:
                return {"$ref": ref}
            target = schemas.get(name)
            if target is None:
                return node
            return _resolve_refs(target, schemas, seen | {name})
        return {k: _resolve_refs(v, schemas, seen) for k, v in node.items()}
    if isinstance(node, list):
        return [_resolve_refs(v, schemas, seen) for v in node]
    return node


# ---------------------------------------------------------------------------
# tool dispatch


async def _call_via_http(
    client: httpx.AsyncClient,
    op: dict,
    arguments: dict,
    forward_headers: dict[str, str],
) -> str:
    """Translate an MCP tool call into an HTTP call against the FastAPI app."""
    method, path = op["method"], op["path"]
    params = op["params"]

    query: dict[str, Any] = {}
    body: Any = None
    url_path = path

    for p in params:
        name = p["name"]
        if name not in arguments:
            continue
        value = arguments[name]
        if p["in"] == "query":
            query[name] = _to_query_value(value)
        elif p["in"] == "path":
            url_path = url_path.replace("{" + name + "}", str(value))
        elif p["in"] == "body":
            body = value

    url = url_path
    if query:
        url = f"{url}?{urlencode(query, doseq=True)}"

    request_kwargs: dict[str, Any] = {"headers": forward_headers}
    if body is not None:
        request_kwargs["json"] = body

    response = await client.request(method, url, **request_kwargs)
    text = response.text
    if response.status_code >= 400:
        return json.dumps({"status": response.status_code, "error": _safe_json(text)})
    return text


def _to_query_value(value: Any) -> Any:
    if isinstance(value, bool):
        return "true" if value else "false"
    return value


def _safe_json(text: str) -> Any:
    try:
        return json.loads(text)
    except (ValueError, TypeError):
        return text


# ---------------------------------------------------------------------------
# server attachment


def attach(
    app: FastAPI,
    oas: dict,
    *,
    name: str | None = None,
    version: str | None = None,
    mount_path: str = "/mcp",
    exclude_tags: list[str] | None = None,
    forward_headers: list[str] | None = None,
) -> None:
    """
    Attach an MCP server at `mount_path` on the given FastAPI app.

    The server reads tool definitions from the authored `oas` dict (NOT
    from FastAPI route introspection) and dispatches calls back through
    the same FastAPI app via an in-process httpx ASGI transport.
    """
    tools, op_map = build_tools(oas, exclude_tags=exclude_tags)

    info = oas.get("info") or {}
    server_name = name or info.get("title", "Mock MCP Server")
    server_version = version or info.get("version", "1.0.0")

    mcp_server: MCPServer = MCPServer(server_name, version=server_version)

    # In-process httpx client speaks ASGI directly to our FastAPI app.
    http_client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://mock-mcp",
        timeout=10.0,
    )
    forward_set = {h.lower() for h in (forward_headers or ["authorization"])}

    @mcp_server.list_tools()
    async def _list_tools() -> list[mcp_types.Tool]:
        return tools

    @mcp_server.call_tool()
    async def _call_tool(
        tool_name: str, arguments: dict[str, Any]
    ) -> list[mcp_types.TextContent | mcp_types.ImageContent | mcp_types.EmbeddedResource]:
        op = op_map.get(tool_name)
        if op is None:
            return [mcp_types.TextContent(type="text", text=f"unknown tool: {tool_name}")]

        # Forward allowlisted headers from the original MCP client request
        # so things like Authorization reach the FastAPI route.
        headers: dict[str, str] = {}
        try:
            ctx = mcp_server.request_context
            if ctx and hasattr(ctx, "request") and ctx.request is not None:
                for k, v in ctx.request.headers.items():
                    if k.lower() in forward_set:
                        headers[k] = v
        except (LookupError, AttributeError):
            pass

        text = await _call_via_http(http_client, op, arguments, headers)
        return [mcp_types.TextContent(type="text", text=text)]

    session_manager = StreamableHTTPSessionManager(app=mcp_server, stateless=True)

    @app.api_route(mount_path, methods=["GET", "POST", "DELETE"], include_in_schema=False)
    async def _mcp_endpoint(request: Request):
        await session_manager.handle_request(request.scope, request.receive, request._send)

    # The session manager needs to run as part of the FastAPI lifespan.
    @contextlib.asynccontextmanager
    async def _lifespan(_app: FastAPI):
        async with session_manager.run():
            yield
        await http_client.aclose()

    # Compose with whatever lifespan FastAPI already has (currently none, but
    # be polite to future additions).
    existing = app.router.lifespan_context

    @contextlib.asynccontextmanager
    async def _composed(_app: FastAPI):
        async with _lifespan(_app):
            async with existing(_app):
                yield

    app.router.lifespan_context = _composed
