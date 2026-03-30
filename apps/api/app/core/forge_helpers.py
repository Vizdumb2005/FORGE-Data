"""forge_helpers — Python module injected into every FORGE Jupyter kernel.

This module is executed silently when a kernel starts to set up a convenient
environment for data exploration: common imports, query/tracking helper
functions, and a matplotlib backend suitable for non-interactive rendering.
"""

# The source below is stored as a Python string so the KernelManager can
# inject it verbatim into a fresh kernel via ``execute_request``.

BOOTSTRAP_CODE = r'''
# ── FORGE kernel bootstrap ─────────────────────────────────────────────────
import warnings as _w
_w.filterwarnings("ignore", category=DeprecationWarning)

import pandas as pd
import numpy as np

# Matplotlib — use Agg backend for non-interactive (base64 PNG) output
import matplotlib as _mpl
_mpl.use("Agg")
import matplotlib.pyplot as plt
import seaborn as sns

# Plotly (optional, warn if missing)
try:
    import plotly.express as px
    import plotly.graph_objects as go
except ImportError:
    pass

# ── forge_query + ML tracking helpers ──────────────────────────────────────
import requests as _forge_requests
import base64 as _forge_base64

FORGE_API_URL = "__FORGE_API_URL__"
_FORGE_WORKSPACE_ID = "__FORGE_WORKSPACE_ID__"
kernel_token = "__FORGE_KERNEL_TOKEN__"
workspace_id = _FORGE_WORKSPACE_ID

def forge_query(sql: str) -> pd.DataFrame:
    """Execute *sql* against all registered data sources and return a DataFrame.

    Example::

        df = forge_query("SELECT * FROM my_dataset LIMIT 100")
        df.head()
    """
    url = f"{FORGE_API_URL}/api/v1/connectors/workspaces/{_FORGE_WORKSPACE_ID}/query"
    r = _forge_requests.post(
        url,
        json={"sql": sql},
        timeout=60,
        headers={"Authorization": f"Bearer {kernel_token}"},
    )
    r.raise_for_status()
    data = r.json()
    if "error" in data:
        raise RuntimeError(f"Query error: {data['error']}")
    return pd.DataFrame(data["rows"], columns=data["columns"])

def forge_start_run(experiment_name, run_name, tags={}):
    resp = _forge_requests.post(
        f"{FORGE_API_URL}/api/v1/experiments/{workspace_id}/runs/start",
        json={"experiment_name": experiment_name, "run_name": run_name, "tags": tags},
        headers={"Authorization": f"Bearer {kernel_token}"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["run_id"]

def forge_log(run_id, params=None, metrics=None, step=None):
    """Log params and/or metrics to current experiment run."""
    payload = {}
    if params is not None:
        payload["params"] = params
    if metrics is not None:
        payload["metrics"] = metrics
    if step is not None:
        payload["step"] = step
    resp = _forge_requests.post(
        f"{FORGE_API_URL}/api/v1/experiments/{workspace_id}/runs/{run_id}/log",
        json=payload,
        headers={"Authorization": f"Bearer {kernel_token}"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()

def forge_log_model(run_id, model, model_name):
    """Log a trained sklearn/xgboost model."""
    import cloudpickle as _forge_cloudpickle
    model_bytes = _forge_cloudpickle.dumps(model)
    payload = {
        "model_name": model_name,
        "model_pickle_b64": _forge_base64.b64encode(model_bytes).decode("utf-8"),
    }
    resp = _forge_requests.post(
        f"{FORGE_API_URL}/api/v1/experiments/{workspace_id}/runs/{run_id}/model",
        json=payload,
        headers={"Authorization": f"Bearer {kernel_token}"},
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()

def forge_end_run(run_id, status="FINISHED"):
    resp = _forge_requests.post(
        f"{FORGE_API_URL}/api/v1/experiments/{workspace_id}/runs/{run_id}/end",
        json={"status": status},
        headers={"Authorization": f"Bearer {kernel_token}"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def forge_profile(df: pd.DataFrame) -> None:
    """Print an auto-generated profile summary of *df*."""
    print(f"Shape: {df.shape[0]:,} rows x {df.shape[1]} columns")
    print()
    print("── Dtypes ──")
    print(df.dtypes.to_string())
    print()
    print("── Null counts ──")
    nulls = df.isnull().sum()
    if nulls.any():
        print(nulls[nulls > 0].to_string())
    else:
        print("No null values")
    print()
    print("── Describe ──")
    print(df.describe(include="all").to_string())
    print()
    print("── Sample (5 rows) ──")
    print(df.head(5).to_string())

print(
    "\U0001f525 FORGE kernel ready. "
    "Use forge_query(sql), forge_start_run(), forge_log(), forge_log_model(), forge_end_run()."
)
'''


def build_bootstrap_code(
    api_url: str,
    workspace_id: str,
    kernel_token: str,
) -> str:
    """Return the bootstrap source with runtime values substituted in.

    Values are embedded using repr() to ensure correct Python string escaping.
    """
    return (
        BOOTSTRAP_CODE.replace('"__FORGE_API_URL__"', repr(api_url))
        .replace('"__FORGE_WORKSPACE_ID__"', repr(workspace_id))
        .replace('"__FORGE_KERNEL_TOKEN__"', repr(kernel_token))
    )
