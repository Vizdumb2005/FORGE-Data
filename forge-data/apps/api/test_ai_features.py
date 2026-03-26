"""
Comprehensive AI feature test — runs inside the Docker API container.
Tests: code-gen, fix-error, explain, suggest, stat-advisor, chat, semantic-layer, pipeline.
Usage:  docker exec forge-data-api-1 python /workspace/test_ai_features.py
        OR run from host:  python forge-data/test_ai_features.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import httpx

# ── Config ────────────────────────────────────────────────────────────────────
BASE = "http://localhost:8000/api/v1"
EMAIL = "ai_tester@example.com"
PASSWORD = "ForgeTest2026!#"
FULL_NAME = "AI Tester"
DATASET_CSV = Path(__file__).parent / "synthetic_sales_data.csv"
MODEL = "qwen3:8b"          # lightest installed model — fastest for tests
PROVIDER = "ollama"
TIMEOUT = 300               # seconds per streaming call — CPU inference is slow
MAX_TOKENS = 150            # keep responses short to reduce wait time on CPU
PIPELINE_TIMEOUT = 900      # pipeline makes multiple LLM calls — needs more time

PASS = "\033[92m✓\033[0m"
FAIL = "\033[91m✗\033[0m"
INFO = "\033[94m→\033[0m"

results: list[tuple[str, bool, str]] = []


def log(label: str, ok: bool, detail: str = "") -> None:
    icon = PASS if ok else FAIL
    print(f"  {icon}  {label}" + (f"  [{detail}]" if detail else ""))
    results.append((label, ok, detail))


# ── Auth helpers ──────────────────────────────────────────────────────────────
def get_token(client: httpx.Client) -> str:
    # Register (ignore if already exists)
    client.post(f"{BASE}/auth/register",
                json={"email": EMAIL, "password": PASSWORD, "full_name": FULL_NAME})
    r = client.post(f"{BASE}/auth/login", json={"email": EMAIL, "password": PASSWORD})
    assert r.status_code == 200, f"Login failed: {r.text}"
    return r.json()["access_token"]


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ── SSE helpers ───────────────────────────────────────────────────────────────
def collect_sse(client: httpx.Client, method: str, url: str,
                token: str, body: dict, timeout: int = TIMEOUT) -> tuple[str, str | None]:
    """Stream an SSE endpoint and return (full_text, error_text|None)."""
    chunks: list[str] = []
    error: str | None = None
    with client.stream(method, url, json=body,
                       headers={**auth(token), "Accept": "text/event-stream"},
                       timeout=timeout) as resp:
        if resp.status_code != 200:
            return "", f"HTTP {resp.status_code}: {resp.read().decode()[:300]}"
        for line in resp.iter_lines():
            if not line.startswith("data: "):
                continue
            payload = json.loads(line[6:])
            if payload.get("type") == "token":
                chunks.append(payload.get("text", ""))
            elif payload.get("type") == "error":
                error = payload.get("text") or payload.get("message", "unknown error")
            elif payload.get("type") == "complete":
                break
    return "".join(chunks), error


# ── Setup: workspace + dataset ────────────────────────────────────────────────
def setup(client: httpx.Client, token: str) -> tuple[str, str]:
    print(f"\n{INFO}  Setup: workspace + dataset")

    # Workspace
    r = client.post(f"{BASE}/workspaces/",
                    json={"name": "AI Test Workspace", "description": "auto"},
                    headers=auth(token))
    if r.status_code == 201:
        ws_id = r.json()["id"]
        log("Create workspace", True, ws_id[:8])
    else:
        # Reuse first existing workspace
        r2 = client.get(f"{BASE}/workspaces/", headers=auth(token))
        ws_id = r2.json()[0]["id"]
        log("Reuse workspace", True, ws_id[:8])

    # Configure Ollama provider for this user
    r = client.patch(f"{BASE}/auth/me/api-keys",
                     json={
                         "provider_api_keys": {},
                         "provider_settings": {
                             "ollama": {
                                 "base_url": "http://host.docker.internal:11434",
                                 "default_model": MODEL,
                             }
                         },
                     },
                     headers=auth(token))
    log("Configure Ollama provider", r.status_code == 200, f"HTTP {r.status_code}")

    r = client.patch(f"{BASE}/auth/me",
                     json={"preferred_llm_provider": PROVIDER},
                     headers=auth(token))
    log("Set preferred provider → ollama", r.status_code == 200)

    # Dataset
    r = client.post(f"{BASE}/workspaces/{ws_id}/datasets",
                    json={"name": "Synthetic Sales", "description": "5k row sales dataset"},
                    headers=auth(token))
    assert r.status_code == 201, f"Dataset create failed: {r.text}"
    ds_id = r.json()["id"]
    log("Create dataset record", True, ds_id[:8])

    with open(DATASET_CSV, "rb") as f:
        r = client.post(
            f"{BASE}/workspaces/{ws_id}/datasets/{ds_id}/upload",
            files={"file": ("synthetic_sales_data.csv", f, "text/csv")},
            headers=auth(token),
            timeout=60,
        )
    log("Upload CSV (5 000 rows)", r.status_code == 200, f"HTTP {r.status_code}")
    if r.status_code == 200:
        meta = r.json()
        log("  row_count", meta.get("row_count", 0) > 0, str(meta.get("row_count")))
        log("  schema captured", bool(meta.get("schema_snapshot")),
            f"{len(meta.get('schema_snapshot') or [])} cols")

    return ws_id, ds_id


# ── Feature tests ─────────────────────────────────────────────────────────────
def test_providers(client: httpx.Client, token: str) -> None:
    print(f"\n{INFO}  Providers")
    r = client.get(f"{BASE}/ai/providers", headers=auth(token))
    log("GET /ai/providers", r.status_code == 200)
    providers = r.json()
    ollama = next((p for p in providers if p["id"] == "ollama"), None)
    log("Ollama in provider list", ollama is not None)
    log("Ollama configured", bool(ollama and ollama.get("configured")))

    r2 = client.get(f"{BASE}/ai/providers/ollama/models", headers=auth(token))
    log("GET /ai/providers/ollama/models", r2.status_code == 200)
    models = r2.json().get("models", [])
    log("Live models returned", len(models) > 0, str(models))


def test_code_generate(client: httpx.Client, token: str, ws_id: str) -> None:
    print(f"\n{INFO}  Code generation")
    text, err = collect_sse(client, "POST",
                            f"{BASE}/ai/workspaces/{ws_id}/generate",
                            token,
                            {"prompt": "Calculate monthly revenue totals and plot a bar chart",
                             "language": "python", "provider": PROVIDER, "model": MODEL,
                             "max_tokens": MAX_TOKENS})
    ok = bool(text and not err)
    log("Generate Python code", ok, err or f"{len(text)} chars")
    if text:
        log("  Contains code", any(kw in text for kw in ["df", "import", "revenue", "plot"]),
            text[:80].replace("\n", " "))

    text_sql, err_sql = collect_sse(client, "POST",
                                    f"{BASE}/ai/workspaces/{ws_id}/generate",
                                    token,
                                    {"prompt": "Top 5 categories by total revenue",
                                     "language": "sql", "provider": PROVIDER, "model": MODEL,
                                     "max_tokens": MAX_TOKENS})
    ok_sql = bool(text_sql and not err_sql)
    log("Generate SQL code", ok_sql, err_sql or f"{len(text_sql)} chars")
    if text_sql:
        log("  Contains SELECT", "SELECT" in text_sql.upper(),
            text_sql[:80].replace("\n", " "))


def test_fix_error(client: httpx.Client, token: str, ws_id: str) -> None:
    print(f"\n{INFO}  Fix error")
    broken_code = "df = forge_query('SELECT * FROM sales')\nprint(df.groupby('Categry').sum())"
    error_msg = "KeyError: 'Categry'"
    text, err = collect_sse(client, "POST",
                            f"{BASE}/ai/workspaces/{ws_id}/fix-error",
                            token,
                            {"code": broken_code, "error_output": error_msg,
                             "language": "python", "provider": PROVIDER, "model": MODEL,
                             "max_tokens": MAX_TOKENS})
    ok = bool(text and not err)
    log("Fix error in code", ok, err or f"{len(text)} chars")
    if text:
        log("  Typo corrected", "Category" in text or "categor" in text.lower(),
            text[:80].replace("\n", " "))


def test_explain(client: httpx.Client, token: str, ws_id: str) -> None:
    print(f"\n{INFO}  Explain output")
    code = "df.groupby('Category')['Revenue'].sum().sort_values(ascending=False)"
    output = "Category\nElectronics    482310.5\nHome           371204.2\nClothing       298441.8"
    text, err = collect_sse(client, "POST",
                            f"{BASE}/ai/workspaces/{ws_id}/explain",
                            token,
                            {"code": code, "output": output,
                             "language": "python", "provider": PROVIDER, "model": MODEL,
                             "max_tokens": MAX_TOKENS})
    ok = bool(text and not err)
    log("Explain output", ok, err or f"{len(text)} chars")
    if text:
        log("  Mentions revenue/category", any(w in text.lower() for w in ["revenue", "category", "electronics"]),
            text[:100].replace("\n", " "))


def test_suggest(client: httpx.Client, token: str, ws_id: str) -> None:
    print(f"\n{INFO}  Suggest next steps")
    history = [
        {"role": "user", "content": "Load sales data"},
        {"role": "assistant", "content": "df = forge_query('SELECT * FROM sales_data')"},
    ]
    r = client.post(f"{BASE}/ai/workspaces/{ws_id}/suggest",
                    json={"history": history},
                    headers=auth(token), timeout=TIMEOUT)
    ok = r.status_code == 200 and isinstance(r.json(), list) and len(r.json()) > 0
    log("Suggest next steps", ok, str(r.json()[:2]) if ok else f"HTTP {r.status_code}")


def test_stat_advisor(client: httpx.Client, token: str, ws_id: str, ds_id: str) -> None:
    print(f"\n{INFO}  Statistical advisor")
    r = client.post(f"{BASE}/ai/workspaces/{ws_id}/stat-advisor",
                    json={"dataset_id": ds_id,
                          "question": "Is there a significant difference in revenue across regions?"},
                    headers=auth(token), timeout=TIMEOUT)
    ok = r.status_code == 200
    log("Stat advisor response", ok, f"HTTP {r.status_code}")
    if ok:
        data = r.json()
        log("  Has recommendation", bool(data.get("recommendation") or data.get("test") or data.get("result") or data.get("test_name")),
            str(list(data.keys())))


def test_chat(client: httpx.Client, token: str, ws_id: str) -> None:
    print(f"\n{INFO}  Conversational chat")
    text, err = collect_sse(client, "POST",
                            f"{BASE}/ai/chat",
                            token,
                            {"workspace_id": ws_id,
                             "message": "What columns does the sales dataset have and what insights can you give me?",
                             "history": [],
                             "provider": PROVIDER,
                             "model": MODEL,
                             "max_tokens": MAX_TOKENS})
    ok = bool(text and not err)
    log("Chat response", ok, err or f"{len(text)} chars")
    if text:
        log("  Non-empty answer", len(text) > 20, text[:120].replace("\n", " "))

    # Multi-turn
    text2, err2 = collect_sse(client, "POST",
                              f"{BASE}/ai/chat",
                              token,
                              {"workspace_id": ws_id,
                               "message": "Which category has the highest average satisfaction score?",
                               "history": [{"role": "user", "content": "Tell me about the sales data"},
                                           {"role": "assistant", "content": text[:200]}],
                               "provider": PROVIDER,
                               "model": MODEL,
                               "max_tokens": MAX_TOKENS})
    log("Multi-turn chat", bool(text2 and not err2), err2 or f"{len(text2)} chars")


def test_semantic_layer(client: httpx.Client, token: str, ws_id: str) -> None:
    print(f"\n{INFO}  Semantic layer (metrics)")
    metric = {
        "name": "total_revenue",
        "definition": "Sum of all transaction revenues",
        "formula_sql": "SELECT SUM(Revenue) AS total_revenue FROM sales_data",
        "depends_on": [],
    }
    r = client.post(f"{BASE}/ai/workspaces/{ws_id}/semantic-layer/metrics",
                    json=metric, headers=auth(token))
    ok = r.status_code == 201
    log("Create metric", ok, f"HTTP {r.status_code}")
    metric_id = r.json().get("id") if ok else None

    r2 = client.get(f"{BASE}/ai/workspaces/{ws_id}/semantic-layer/metrics",
                    headers=auth(token))
    log("List metrics", r2.status_code == 200 and len(r2.json()) > 0,
        f"{len(r2.json())} metrics")

    if metric_id:
        r3 = client.delete(f"{BASE}/ai/workspaces/{ws_id}/semantic-layer/metrics/{metric_id}",
                           headers=auth(token))
        log("Delete metric", r3.status_code == 204)


def test_pipeline(client: httpx.Client, token: str, ws_id: str) -> None:
    print(f"\n{INFO}  Agentic pipeline")
    try:
        text, err = collect_sse(client, "POST",
                                f"{BASE}/ai/workspaces/{ws_id}/pipelines/run",
                                token,
                                {"goal": "Analyse the sales dataset: compute revenue by category, identify the top performer, summarise in 2 sentences."},
                                timeout=PIPELINE_TIMEOUT)
        ok = bool(text and not err)
        log("Pipeline run", ok, err or f"{len(text)} chars")
        if text:
            log("  Report non-empty", len(text) > 30, text[:120].replace("\n", " "))
    except Exception as exc:
        log("Pipeline run", False, str(exc)[:120])

    r = client.get(f"{BASE}/ai/workspaces/{ws_id}/pipelines", headers=auth(token))
    log("List pipeline runs", r.status_code == 200, f"{len(r.json())} runs")


# ── Main ──────────────────────────────────────────────────────────────────────
def main() -> None:
    print("=" * 60)
    print("  FORGE Data — AI Feature Test Suite")
    print(f"  Model: {PROVIDER}/{MODEL}")
    print("=" * 60)

    with httpx.Client(base_url="", timeout=30) as client:
        token = get_token(client)
        print(f"{INFO}  Authenticated as {EMAIL}")

        ws_id, ds_id = setup(client, token)

        test_providers(client, token)
        test_code_generate(client, token, ws_id)
        test_fix_error(client, token, ws_id)
        test_explain(client, token, ws_id)
        test_suggest(client, token, ws_id)
        test_stat_advisor(client, token, ws_id, ds_id)
        test_chat(client, token, ws_id)
        test_semantic_layer(client, token, ws_id)
        test_pipeline(client, token, ws_id)

    # ── Summary ───────────────────────────────────────────────────────────────
    passed = sum(1 for _, ok, _ in results if ok)
    failed = sum(1 for _, ok, _ in results if not ok)
    print("\n" + "=" * 60)
    print(f"  Results: {passed} passed  {failed} failed  ({len(results)} total)")
    print("=" * 60)
    if failed:
        print("\nFailed checks:")
        for name, ok, detail in results:
            if not ok:
                print(f"  {FAIL}  {name}  {detail}")
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
