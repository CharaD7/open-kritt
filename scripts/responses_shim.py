#!/usr/bin/env python3
"""Responses-API shim for providers that reject codex's extra tool types.

codex-cli sends a `tools` array containing entries whose `type` is `namespace`
(MCP) or `web_search`. Providers that validate strictly against OpenAI's
Responses schema - including the HuggingFace router in front of
`fdtn-ai/Foundation-Sec-8B` - reject the whole request:

    ZodError: tools[5] type "namespace"  expected "function" | "mcp"
    ZodError: tools[6] type "web_search" expected "function" | "mcp"

This proxy forwards `POST /v1/responses` upstream with those entries removed.
Everything else (streaming, auth, tool results) passes through untouched.

Usage:
    python3 responses_shim.py --upstream https://router.huggingface.co/v1 \
        --port 8099 --api-key-env HF_TOKEN

Then point the codex provider at http://127.0.0.1:8099/v1
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

import aiohttp
from aiohttp import web

# Tool types the shim removes. Anything not in this set is forwarded verbatim.
DROPPED_TOOL_TYPES = frozenset({"namespace", "web_search"})


def strip_tools(payload: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Remove unsupported tool entries. Returns (payload, dropped_types)."""
    tools = payload.get("tools")
    if not isinstance(tools, list):
        return payload, []

    kept: list[Any] = []
    dropped: list[str] = []
    for tool in tools:
        if isinstance(tool, dict):
            ttype = tool.get("type")
            if isinstance(ttype, str) and ttype in DROPPED_TOOL_TYPES:
                dropped.append(ttype)
                continue
        kept.append(tool)

    if not dropped:
        return payload, []

    new_payload = dict(payload)
    new_payload["tools"] = kept
    return new_payload, dropped


async def handle_responses(request: web.Request) -> web.StreamResponse:
    upstream: str = request.app["upstream"]
    api_key: str = request.app["api_key"]
    stats: dict[str, int] = request.app["stats"]

    try:
        body = await request.json()
    except (json.JSONDecodeError, ValueError):
        return web.json_response(
            {"error": {"message": "shim: request body was not JSON"}}, status=400
        )

    new_body, dropped = strip_tools(body)
    if dropped:
        stats["requests"] = stats.get("requests", 0) + 1
        stats["dropped_tools"] = stats.get("dropped_tools", 0) + len(dropped)
        print(
            f"[shim] stripped {len(dropped)} tool(s): {sorted(set(dropped))}",
            file=sys.stderr,
            flush=True,
        )

    url = upstream.rstrip("/") + "/responses"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": request.headers.get("Accept", "application/json"),
    }

    session: aiohttp.ClientSession = request.app["session"]
    try:
        async with session.post(url, json=new_body, headers=headers) as resp:
            text = await resp.text()
            out = web.Response(
                status=resp.status,
                text=text,
                content_type=resp.content_type or "application/json",
            )
            return out
    except aiohttp.ClientError as exc:
        return web.json_response(
            {"error": {"message": f"shim: upstream error: {exc}"}}, status=502
        )


async def handle_health(request: web.Request) -> web.Response:
    stats = request.app["stats"]
    return web.json_response(
        {
            "status": "ok",
            "upstream": request.app["upstream"],
            "dropped_tool_types": sorted(DROPPED_TOOL_TYPES),
            "requests_stripped": stats.get("requests", 0),
            "tools_dropped": stats.get("dropped_tools", 0),
        }
    )


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--upstream", required=True, help="upstream base url, e.g. https://router.huggingface.co/v1")
    p.add_argument("--port", type=int, default=8099)
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--api-key-env", default="HF_TOKEN", help="env var holding the upstream API key")
    return p


async def on_startup(app: web.Application) -> None:
    app["session"] = aiohttp.ClientSession()


async def on_cleanup(app: web.Application) -> None:
    await app["session"].close()


def main() -> int:
    # Compose passes configuration through the environment; explicit flags win.
    argv = sys.argv[1:]
    if not argv:
        upstream = os.environ.get("SHIM_UPSTREAM", "https://router.huggingface.co/v1")
        port = int(os.environ.get("SHIM_PORT", "8099"))
        api_key = os.environ.get("HF_TOKEN", "")
        if not api_key:
            print("error: HF_TOKEN is not set", file=sys.stderr)
            return 2
        app = web.Application()
        app["upstream"] = upstream
        app["api_key"] = api_key
        app["stats"] = {}
        app.router.add_post("/v1/responses", handle_responses)
        app.router.add_post("/responses", handle_responses)
        app.router.add_get("/health", handle_health)
        app.on_startup.append(on_startup)
        app.on_cleanup.append(on_cleanup)
        print(f"[shim] listening on 0.0.0.0:{port}", file=sys.stderr)
        print(f"[shim] upstream {upstream}", file=sys.stderr)
        print(f"[shim] dropping tool types: {sorted(DROPPED_TOOL_TYPES)}", file=sys.stderr)
        web.run_app(app, host="0.0.0.0", port=port, print=None)
        return 0

    args = build_parser().parse_args()
    api_key = os.environ.get(args.api_key_env, "")
    if not api_key:
        print(f"error: ${args.api_key_env} is not set", file=sys.stderr)
        return 2

    app = web.Application()
    app["upstream"] = args.upstream
    app["api_key"] = api_key
    app["stats"] = {}
    app.router.add_post("/v1/responses", handle_responses)
    # Some clients append a trailing slash or hit /responses without /v1.
    app.router.add_post("/responses", handle_responses)
    app.router.add_get("/health", handle_health)
    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)

    print(f"[shim] listening on http://{args.host}:{args.port}", file=sys.stderr)
    print(f"[shim] upstream {args.upstream}  key from ${args.api_key_env}", file=sys.stderr)
    print(f"[shim] dropping tool types: {sorted(DROPPED_TOOL_TYPES)}", file=sys.stderr)
    web.run_app(app, host=args.host, port=args.port, print=None)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())