#!/usr/bin/env python3
"""Join the responses-shim container to every per-job scan network.

The engine creates a dedicated docker network per job
(`open-kritt-scan-<id>`, labelled `open-kritt.scan-sandbox=1`) and runs the
codex runner on it. Those networks cannot resolve compose service names, so the
runner cannot reach `responses-shim`.

This watcher polls for networks with that label and connects the shim to each
one. Idempotent: an `already exists` API error counts as success.

Required env:
  SHIM_CONTAINER   container to attach (default open-kritt-responses-shim)

Optional:
  SHIM_ALIASES       comma-separated network aliases (default responses-shim)
  SHIM_POLL_SECONDS  poll interval (default 5)
"""

from __future__ import annotations

import os
import sys
import time

import docker

LABEL = "open-kritt.scan-sandbox"


def log(msg: str) -> None:
    print(f"[network-joiner] {msg}", file=sys.stderr, flush=True)


def main() -> int:
    container_name = os.environ.get("SHIM_CONTAINER", "open-kritt-responses-shim")
    aliases = [
        a.strip()
        for a in os.environ.get("SHIM_ALIASES", "responses-shim").split(",")
        if a.strip()
    ]
    poll = float(os.environ.get("SHIM_POLL_SECONDS", "5"))

    client = docker.from_env()
    try:
        container = client.containers.get(container_name)
    except docker.errors.NotFound:
        log(f"container {container_name!r} not found")
        return 2

    log(f"attaching {container_name} to networks labelled {LABEL} as {aliases}")

    while True:
        try:
            networks = client.networks.list(filters={"label": LABEL})
        except Exception as exc:  # noqa: BLE001
            log(f"list failed: {exc}")
            time.sleep(poll)
            continue

        for net in networks:
            try:
                net.connect(container, aliases=aliases)
                log(f"attached to {net.name}")
            except docker.errors.APIError as exc:
                msg = str(exc).lower()
                if "already exists" in msg or "409" in msg:
                    continue  # already attached, expected
                log(f"could not attach to {net.name}: {exc}")

        time.sleep(poll)


if __name__ == "__main__":
    raise SystemExit(main())