"""
End-to-end tests against the bundled monthly-report config via FastAPI's
TestClient. Exercises loader + recipes + derived + auth + validators all at
once. Highest leverage tests in the suite.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.loader import build_app, load_config


@pytest.fixture(scope="module")
def client():
    """
    TestClient as a context manager so FastAPI's lifespan fires. The MCP
    session manager registers itself in the lifespan, so /mcp tests fail
    with "Task group is not initialized" without this wrapping.
    """
    config = load_config("monthly-report")
    app = build_app(config)
    with TestClient(app) as c:
        yield c


@pytest.fixture
def auth() -> dict[str, str]:
    return {"Authorization": "Bearer mock-test-token"}


# ---- auth -------------------------------------------------------------------


def test_unauthorized_without_bearer(client: TestClient) -> None:
    r = client.get("/reports/generate?report_month=2024-01")
    assert r.status_code == 401


def test_unauthorized_with_bad_token(client: TestClient) -> None:
    r = client.get(
        "/reports/generate?report_month=2024-01",
        headers={"Authorization": "Bearer wrong"},
    )
    assert r.status_code == 401


def test_authorized_with_correct_token(client: TestClient, auth: dict) -> None:
    r = client.get("/reports/generate?report_month=2024-01", headers=auth)
    assert r.status_code == 200


# ---- validation -------------------------------------------------------------


def test_pattern_validation_rejects_garbage(client: TestClient, auth: dict) -> None:
    r = client.get("/reports/generate?report_month=garbage", headers=auth)
    assert r.status_code == 422
    detail = r.json()["detail"][0]
    assert detail["loc"] == ["query", "report_month"]
    assert "pattern" in detail["msg"].lower()


def test_past_month_validator_rejects_future(client: TestClient, auth: dict) -> None:
    r = client.get("/reports/generate?report_month=2099-01", headers=auth)
    assert r.status_code == 422
    detail = r.json()["detail"][0]
    assert "past month" in detail["msg"].lower()


def test_missing_required_query_param(client: TestClient, auth: dict) -> None:
    r = client.get("/reports/generate", headers=auth)
    assert r.status_code == 422


# ---- response shape & invariants -------------------------------------------


def test_response_shape(client: TestClient, auth: dict) -> None:
    r = client.get("/reports/generate?report_month=2024-06", headers=auth)
    body = r.json()
    assert body["success"] is True
    assert body["report_month"] == "2024-06"
    assert body["output_file_path"].startswith("s3://")
    assert "year=2024" in body["output_file_path"]
    assert "month=06" in body["output_file_path"]
    assert "summary_stats" in body


def test_invariant_total_brands_equals_platform_sum(client: TestClient, auth: dict) -> None:
    r = client.get("/reports/generate?report_month=2024-06", headers=auth)
    s = r.json()["summary_stats"]
    assert s["total_brands"] == sum(s["brands_by_platform"].values())


def test_invariant_invoice_split_sums_to_total(client: TestClient, auth: dict) -> None:
    r = client.get("/reports/generate?report_month=2024-06", headers=auth)
    s = r.json()["summary_stats"]
    assert sum(s["draft_invoice_summary"].values()) == s["total_brands"]


def test_invariant_delta_equals_earnings_minus_adjusted(client: TestClient, auth: dict) -> None:
    r = client.get("/reports/generate?report_month=2024-06", headers=auth)
    s = r.json()["summary_stats"]
    assert s["total_link_delta"] == round(
        s["total_platform_earnings"] - s["total_link_adjusted_spend"], 2
    )


def test_environment_reflects_use_preview_db(client: TestClient, auth: dict) -> None:
    r1 = client.get("/reports/generate?report_month=2024-06&use_preview_db=false", headers=auth)
    r2 = client.get("/reports/generate?report_month=2024-06&use_preview_db=true", headers=auth)
    assert r1.json()["summary_stats"]["environment"] == "prod"
    assert r2.json()["summary_stats"]["environment"] == "preview"
    assert "environment=prod" in r1.json()["output_file_path"]
    assert "environment=preview" in r2.json()["output_file_path"]


# ---- determinism -----------------------------------------------------------


def _stripped(d: dict) -> dict:
    """Drop the one intentionally non-deterministic field."""
    return {k: v for k, v in d.items() if k != "generated_at"}


def test_same_query_same_response(client: TestClient, auth: dict) -> None:
    a = client.get("/reports/generate?report_month=2024-06", headers=auth).json()
    b = client.get("/reports/generate?report_month=2024-06", headers=auth).json()
    assert _stripped(a) == _stripped(b)


def test_different_months_diverge(client: TestClient, auth: dict) -> None:
    a = client.get("/reports/generate?report_month=2024-06", headers=auth).json()
    b = client.get("/reports/generate?report_month=2024-07", headers=auth).json()
    assert _stripped(a) != _stripped(b)


# ---- built-in routes -------------------------------------------------------


def test_root_route(client: TestClient) -> None:
    r = client.get("/")
    assert r.status_code == 200
    assert "version" in r.json()


def test_health_route(client: TestClient) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "healthy"


def test_openapi_schema_reflects_authored_oas(client: TestClient) -> None:
    """The /openapi.json endpoint should reflect the authored OAS, not FastAPI's introspection."""
    schema = client.get("/openapi.json").json()
    assert "/reports/generate" in schema["paths"]
    op = schema["paths"]["/reports/generate"]["get"]
    assert op["operationId"] == "generate_report"
    # Authored schema names are preserved through to /openapi.json
    assert "MonthlyReportResponse" in schema["components"]["schemas"]


# ---- /mcp endpoint: protocol smoke + ASGI hygiene -------------------------


def test_mcp_initialize_returns_200_at_bare_path(client: TestClient) -> None:
    """
    Regression test for the 'Unexpected ASGI message http.response.start sent
    after response already completed' error: hitting /mcp directly (no
    trailing slash, no redirect) must return 200 with the SSE response and
    must not log a RuntimeError. The handler in app/mcp_server.py now
    captures the ASGI messages from StreamableHTTPSessionManager and
    re-emits them via a regular FastAPI Response, which keeps FastAPI's
    routing layer from double-sending response.start.
    """
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "test", "version": "0"},
        },
    }
    r = client.post(
        "/mcp",
        json=payload,
        headers={"Accept": "application/json, text/event-stream"},
    )
    assert r.status_code == 200
    # Response is an SSE event with the initialize result inline.
    assert "result" in r.text
    assert "protocolVersion" in r.text


def test_mcp_endpoint_streams_sse_content_type(client: TestClient) -> None:
    """The MCP endpoint should respond with text/event-stream so SSE-aware clients can parse it."""
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "test", "version": "0"},
        },
    }
    r = client.post(
        "/mcp",
        json=payload,
        headers={"Accept": "application/json, text/event-stream"},
    )
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")
