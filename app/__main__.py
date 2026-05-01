"""
CLI entrypoint for the mock MCP server framework.

    uv run mock-mcp --config monthly-report
    python -m app --config monthly-report

`--config` takes a profile name (e.g. `monthly-report`), resolved against
the `configs/` directory as `<name>.yaml` (or `.yml`). The chosen config's
`x-mock-port` is the default bind port; `--port` overrides.

Hard-errors with a non-zero exit if the profile cannot be resolved or
fails validation. There is no implicit default config.
"""

from __future__ import annotations

import argparse
import sys

import uvicorn

from app.loader import build_app, load_config


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mock-mcp", description=__doc__)
    parser.add_argument(
        "--config",
        required=True,
        metavar="PROFILE",
        help="config profile name (e.g. 'monthly-report' → configs/monthly-report.yaml)",
    )
    parser.add_argument("--host", default="0.0.0.0", help="bind host (default: 0.0.0.0)")
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="bind port (overrides x-mock-port from the config)",
    )
    parser.add_argument("--reload", action="store_true", help="uvicorn auto-reload")
    args = parser.parse_args(argv)

    try:
        config = load_config(args.config)
    except (FileNotFoundError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    app = build_app(config)
    port = args.port if args.port is not None else config.get("x-mock-port", 8000)

    uvicorn.run(app, host=args.host, port=port, access_log=True, loop="asyncio", reload=args.reload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
