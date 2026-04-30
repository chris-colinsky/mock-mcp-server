"""
Load an OAS-3.1 + x-mock-* YAML config and build a runnable FastAPI app
with an MCP server attached at /mcp.

Top-level extensions consumed:
  x-mock-port:    int (used by the CLI; the loader just exposes it)
  x-mock-auth:    {type: bearer, token_env, default}
  x-mock-mcp:     {exclude_tags?, mount_path?, forward_headers?}

Per-operation extensions consumed:
  x-mock-static:    response object returned verbatim
  x-mock-dynamic:   {seed_from, response, derived}  — see app/mock/engine.py
  x-mock-validate:  list of {field, type, message?} — extra request validators

The MCP tool schema is built directly from the authored OAS (see
app/mcp_server.py), not from FastAPI route introspection — the contract
you author IS what tools see.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import yaml
from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app import auth as auth_mod
from app import mcp_server as mcp_attach_mod
from app import validators as validators_mod
from app.mock import engine as engine_mod


CONFIG_DIR = Path(__file__).parent.parent / "configs"


# ---------------------------------------------------------------------------
# entry points


def load_config(profile: str) -> dict:
    """Resolve a profile name (e.g. 'monthly-report') to a parsed config dict."""
    path = CONFIG_DIR / f"{profile}.yaml"
    if not path.exists():
        path = CONFIG_DIR / f"{profile}.yml"
    if not path.exists():
        raise FileNotFoundError(
            f"config profile not found: {profile!r} "
            f"(looked in {CONFIG_DIR} for {profile}.yaml or {profile}.yml)"
        )
    with path.open() as f:
        config = yaml.safe_load(f)
    _validate(config, str(path))
    return config


def build_app(config: dict) -> FastAPI:
    """Build a FastAPI app + FastApiMCP from a parsed config dict."""
    info = config.get("info", {})
    app = FastAPI(
        title=info.get("title", "Mock MCP Server"),
        description=info.get("description", ""),
        version=info.get("version", "1.0.0"),
        exception_handlers=_exception_handlers(),
    )

    auth_dep = auth_mod.build_dependency(config.get("x-mock-auth"))

    router = APIRouter()
    for path, path_item in (config.get("paths") or {}).items():
        for method, operation in path_item.items():
            if method not in ("get", "post", "put", "delete", "patch"):
                continue
            _register_route(router, path, method, operation, auth_dep)
    app.include_router(router)

    _add_health_routes(app)

    oas_for_mcp = _strip_x_mock(config)
    app.openapi_schema = oas_for_mcp  # so /openapi.json reflects the authored contract

    mcp_opts = config.get("x-mock-mcp") or {}
    mcp_attach_mod.attach(
        app,
        oas_for_mcp,
        mount_path=mcp_opts.get("mount_path", "/mcp"),
        exclude_tags=mcp_opts.get("exclude_tags", ["root", "health"]),
        forward_headers=mcp_opts.get("forward_headers", ["authorization"]),
    )
    return app


# ---------------------------------------------------------------------------
# config validation


def _validate(config: Any, source: str) -> None:
    if not isinstance(config, dict):
        raise ValueError(f"{source}: top-level config must be a mapping")
    if "openapi" not in config:
        raise ValueError(f"{source}: missing 'openapi' version field")
    if "paths" not in config:
        raise ValueError(f"{source}: missing 'paths'")
    for path, path_item in (config.get("paths") or {}).items():
        for method, operation in path_item.items():
            if method not in ("get", "post", "put", "delete", "patch"):
                continue
            has_static = "x-mock-static" in operation
            has_dynamic = "x-mock-dynamic" in operation
            if has_static == has_dynamic:
                raise ValueError(
                    f"{source}: {method.upper()} {path} must define exactly one of "
                    "x-mock-static or x-mock-dynamic"
                )


# ---------------------------------------------------------------------------
# route registration


def _register_route(
    router: APIRouter,
    path: str,
    method: str,
    operation: dict,
    auth_dep: Any | None,
) -> None:
    parameters = operation.get("parameters", [])
    query_params = [p for p in parameters if p.get("in") == "query"]
    path_params = [p for p in parameters if p.get("in") == "path"]

    static = operation.get("x-mock-static")
    dynamic = operation.get("x-mock-dynamic")
    custom_validators = operation.get("x-mock-validate", [])

    async def handler(request: Request) -> Any:
        # Build {query, path} dict, coercing per OAS schema. We don't reuse
        # FastAPI's parameter-decoded handler signature because the parameter
        # set is config-driven and varies per route.
        query: dict = {}
        for p in query_params:
            name = p["name"]
            schema = p.get("schema") or {}
            raw = request.query_params.get(name)
            if raw is None:
                if p.get("required"):
                    raise HTTPException(
                        status_code=422,
                        detail=[{"loc": ["query", name], "msg": "field required", "type": "missing"}],
                    )
                if "default" in schema:
                    query[name] = schema["default"]
                continue
            query[name] = _coerce(raw, schema, ["query", name])

        path_values = {
            p["name"]: _coerce(request.path_params.get(p["name"]), p.get("schema") or {}, ["path", p["name"]])
            for p in path_params
        }

        for v in custom_validators:
            field_name = v["field"]
            value = query.get(field_name, path_values.get(field_name))
            try:
                validators_mod.get(v["type"])(value)
            except ValueError as exc:
                # Prefer the validator's own message; fall back to the YAML
                # override only if the exception didn't carry one.
                msg = str(exc) or v.get("message") or "validation failed"
                raise HTTPException(
                    status_code=422,
                    detail=[{"loc": ["query", field_name], "msg": msg, "type": "value_error"}],
                ) from exc

        request_data = {"query": query, "path": path_values}
        if static is not None:
            return engine_mod.generate_static(static)
        return engine_mod.generate(dynamic, request_data)

    # Build a FastAPI-decorated handler whose signature reflects the OAS
    # parameters, so the standard OpenAPI page (and request validation) work.
    handler.__name__ = operation.get("operationId") or f"{method}_{path.strip('/').replace('/', '_')}"

    dependencies = [auth_dep] if auth_dep else []
    router.add_api_route(
        path,
        handler,
        methods=[method.upper()],
        tags=operation.get("tags") or [],
        summary=operation.get("summary"),
        description=operation.get("description"),
        operation_id=operation.get("operationId"),
        dependencies=dependencies,
    )


def _coerce(value: Any, schema: dict, loc: list) -> Any:
    """Coerce a raw query-string value to the type declared in its OAS schema."""
    if value is None:
        return None
    type_ = schema.get("type")
    pattern = schema.get("pattern")
    try:
        if type_ == "integer":
            value = int(value)
        elif type_ == "number":
            value = float(value)
        elif type_ == "boolean":
            value = str(value).lower() in ("1", "true", "yes", "on")
        # type == "string" or absent: leave as-is
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=422,
            detail=[{"loc": loc, "msg": f"could not parse as {type_}: {value!r}", "type": "type_error"}],
        ) from exc

    if pattern and isinstance(value, str):
        import re

        if not re.match(pattern, value):
            raise HTTPException(
                status_code=422,
                detail=[
                    {
                        "loc": loc,
                        "msg": f"string does not match pattern {pattern!r}",
                        "type": "value_error.pattern",
                    }
                ],
            )

    if "enum" in schema and value not in schema["enum"]:
        raise HTTPException(
            status_code=422,
            detail=[{"loc": loc, "msg": f"value must be one of {schema['enum']}", "type": "value_error.enum"}],
        )

    return value


# ---------------------------------------------------------------------------
# health/root built-ins (excluded from MCP via `exclude_tags`)


def _add_health_routes(app: FastAPI) -> None:
    @app.get("/", tags=["root"], summary="Root", include_in_schema=True)
    async def _root() -> dict:
        return {
            "message": f"Welcome to {app.title} (Mock)",
            "version": app.version,
            "docs": "/docs",
            "health": "/health",
        }

    @app.get("/health", tags=["health"], summary="Health Check", include_in_schema=True)
    async def _health() -> dict:
        from datetime import datetime, timezone

        return {
            "status": "healthy",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "version": app.version,
            "database_connections": {"mock": "ok"},
        }


def _strip_x_mock(config: dict) -> dict:
    """Return a deep copy of `config` with all x-mock-* keys removed."""
    import copy

    clone = copy.deepcopy(config)

    def scrub(node: Any) -> None:
        if isinstance(node, dict):
            for k in [k for k in node if isinstance(k, str) and k.startswith("x-mock-")]:
                del node[k]
            for v in node.values():
                scrub(v)
        elif isinstance(node, list):
            for v in node:
                scrub(v)

    scrub(clone)
    return clone


# ---------------------------------------------------------------------------
# error handlers


def _exception_handlers() -> dict:
    async def validation(_req: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": exc.errors()})

    async def http_exc(_req: Request, exc: HTTPException) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    async def timeout(_req: Request, _exc: asyncio.TimeoutError) -> JSONResponse:
        return JSONResponse(status_code=408, content={"detail": "Tool execution timed out."})

    async def general(_req: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(status_code=500, content={"detail": f"Internal Tool Error: {exc!s}"})

    return {
        RequestValidationError: validation,
        HTTPException: http_exc,
        asyncio.TimeoutError: timeout,
        Exception: general,
    }
