"""
Pipeline-only smoke test.
Usage: docker exec forge-data-api-1 python /workspace/test_pipeline_only.py
"""
from __future__ import annotations

import json
import sys

import httpx

BASE = "http://localhost:8000/api/v1"
EMAIL = "ai_tester@example.com"
PASSWORD = "ForgeTest2026!#"
FULL_NAME = "AI Tester"
MODEL = "qwen3:8b"
PROVIDER = "ollama"
PIPELINE_TIMEOUT = 900

PASS = "\033[92m✓\033[0m"
FAIL = "\033[91m✗\033[0m"
INFO = "\033[94m→\033[0m"


def get_token(client: httpx.Client) -> str:
    client.post(f"{BASE}/auth/register", json={"email": EMAIL, "password": PASSWORD, "full_name": FULL_NAME})
    r = client.post(f"{BASE}/auth/login", json={"email": EMAIL, "password": PASSWORD})
    assert r.status_code == 200, f"Login failed: {r.text}"
    return r.json()["access_token"]


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def get_or_create_workspace(client: httpx.Client, token: str) -> str:
    r = client.get(f"{BASE}/workspaces/", headers=auth(token))
    workspaces = r.json()
    if workspaces:
        ws_id = workspaces[0]["id"]
        print(f"{INFO}  Reusing workspace {ws_id[:8]}")
        return ws_id
    r = client.post(f"{BASE}/workspaces/", json={"name": "Pipeline Test WS", "description": "auto"}, headers=auth(token))
    ws_id = r.json()["id"]
    print(f"{INFO}  Created workspace {ws_id[:8]}")
    return ws_id


def collect_sse(client, url, token, body, timeout=PIPELINE_TIMEOUT):
    chunks = []
    error = None
    all_events = []
    with client.stream("POST", url, json=body,
                       headers={**auth(token), "Accept": "text/event-stream"},
                       timeout=timeout) as resp:
        if resp.status_code != 200:
            return "", f"HTTP {resp.status_code}: {resp.read().decode()[:300]}", []
        for line in resp.iter_lines():
            if not line.startswith("data: "):
                continue
            payload = json.loads(line[6:])
            all_events.append(payload)
            if payload.get("type") == "token":
                chunks.append(payload.get("text", ""))
            elif payload.get("type") == "error":
                error = payload.get("text") or payload.get("message", "unknown error")
            elif payload.get("type") == "complete":
                break
    return "".join(chunks), error, all_events


def main():
    print("=" * 60)
    print("  FORGE — Agentic Pipeline Smoke Test")
    print("=" * 60)

    with httpx.Client(base_url="", timeout=30) as client:
        token = get_token(client)
        print(f"{INFO}  Authenticated as {EMAIL}")
        ws_id = get_or_create_workspace(client, token)

        print(f"\n{INFO}  Running pipeline …")
        text, err, events = collect_sse(
            client,
            f"{BASE}/ai/workspaces/{ws_id}/pipelines/run",
            token,
            {"goal": "Analyse the sales dataset: compute revenue by category, identify the top performer, summarise in 2 sentences."},
        )

        print(f"\n  Event types received: {[e.get('type') for e in events]}")
        print(f"  Total text length:  {len(text)} chars")
        if text:
            print(f"  Text preview: {text[:200].replace(chr(10), ' ')}")

        ok = bool(text and not err)
        icon = PASS if ok else FAIL
        print(f"\n  {icon}  Pipeline run  [{'PASS' if ok else 'FAIL'}]")
        if err:
            print(f"  Error: {err}")
        if not ok and not err:
            print("  ← stream returned no token text (0 chars)")

        # List runs
        r = client.get(f"{BASE}/ai/workspaces/{ws_id}/pipelines", headers=auth(token))
        runs = r.json()
        ok2 = r.status_code == 200
        icon2 = PASS if ok2 else FAIL
        print(f"  {icon2}  List pipeline runs  [{len(runs)} runs]")

    print("\n" + "=" * 60)
    passed = sum([ok, ok2])
    print(f"  Results: {passed}/2 passed")
    print("=" * 60)
    sys.exit(0 if passed == 2 else 1)


if __name__ == "__main__":
    main()
