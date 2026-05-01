"""Tests for app/mcp_server.py — OAS → MCP tool list conversion."""

from __future__ import annotations

from app.mcp_server import _resolve_refs, build_tools

# ---- $ref resolution --------------------------------------------------------


def test_resolve_refs_inlines_components():
    schemas = {"User": {"type": "object", "properties": {"id": {"type": "string"}}}}
    node = {"$ref": "#/components/schemas/User"}
    out = _resolve_refs(node, schemas)
    assert out == schemas["User"]


def test_resolve_refs_handles_nested():
    schemas = {
        "Item": {"type": "object", "properties": {"name": {"type": "string"}}},
        "Bag": {"type": "object", "properties": {"item": {"$ref": "#/components/schemas/Item"}}},
    }
    out = _resolve_refs({"$ref": "#/components/schemas/Bag"}, schemas)
    assert out["properties"]["item"] == schemas["Item"]


def test_resolve_refs_breaks_cycles():
    schemas = {
        "Node": {"type": "object", "properties": {"next": {"$ref": "#/components/schemas/Node"}}}
    }
    out = _resolve_refs({"$ref": "#/components/schemas/Node"}, schemas)
    # cycle should produce a $ref leaf rather than infinite recursion
    assert out["properties"]["next"] == {"$ref": "#/components/schemas/Node"}


def test_resolve_refs_passes_through_non_components_refs():
    node = {"$ref": "external.yaml#/foo"}
    assert _resolve_refs(node, {}) == node


# ---- build_tools ------------------------------------------------------------


def _minimal_oas(extra_paths=None):
    return {
        "openapi": "3.1.0",
        "info": {"title": "Test", "version": "0"},
        "paths": extra_paths or {},
        "components": {"schemas": {}},
    }


def test_build_tools_returns_one_tool_per_operation():
    oas = _minimal_oas(
        {
            "/foo": {"get": {"operationId": "get_foo", "summary": "Foo"}},
            "/bar": {"post": {"operationId": "post_bar", "summary": "Bar"}},
        }
    )
    tools, op_map = build_tools(oas)
    assert {t.name for t in tools} == {"get_foo", "post_bar"}
    assert op_map["get_foo"] == {"method": "GET", "path": "/foo", "params": []}
    assert op_map["post_bar"] == {"method": "POST", "path": "/bar", "params": []}


def test_build_tools_excludes_tagged_operations():
    oas = _minimal_oas(
        {
            "/api": {"get": {"operationId": "get_api", "tags": ["api"]}},
            "/health": {"get": {"operationId": "health", "tags": ["health"]}},
        }
    )
    tools, _ = build_tools(oas, exclude_tags=["health"])
    assert {t.name for t in tools} == {"get_api"}


def test_build_tools_input_schema_from_query_params():
    oas = _minimal_oas(
        {
            "/q": {
                "get": {
                    "operationId": "q",
                    "parameters": [
                        {
                            "name": "month",
                            "in": "query",
                            "required": True,
                            "schema": {"type": "string", "pattern": "^.+$"},
                            "description": "the month",
                        },
                        {
                            "name": "preview",
                            "in": "query",
                            "required": False,
                            "schema": {"type": "boolean", "default": False},
                        },
                    ],
                }
            }
        }
    )
    tools, op_map = build_tools(oas)
    schema = tools[0].inputSchema
    assert schema["type"] == "object"
    assert "month" in schema["properties"]
    assert schema["required"] == ["month"]
    assert schema["properties"]["month"]["pattern"] == "^.+$"
    # description from parameter falls through to property when schema doesn't have one
    assert schema["properties"]["month"]["description"] == "the month"
    assert op_map["q"]["params"] == [
        {"name": "month", "in": "query"},
        {"name": "preview", "in": "query"},
    ]


def test_build_tools_inlines_request_body_ref():
    oas = _minimal_oas(
        {
            "/p": {
                "post": {
                    "operationId": "p",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {"schema": {"$ref": "#/components/schemas/Payload"}}
                        },
                    },
                }
            }
        }
    )
    oas["components"]["schemas"]["Payload"] = {
        "type": "object",
        "properties": {"x": {"type": "integer"}},
    }
    tools, op_map = build_tools(oas)
    schema = tools[0].inputSchema
    assert "body" in schema["properties"]
    assert schema["properties"]["body"]["properties"]["x"]["type"] == "integer"
    assert "body" in schema["required"]
    assert {"name": "body", "in": "body"} in op_map["p"]["params"]


def test_build_tools_default_op_id_when_missing():
    oas = _minimal_oas({"/items/{id}": {"get": {}}})
    tools, _ = build_tools(oas)
    assert tools[0].name  # generated, non-empty
