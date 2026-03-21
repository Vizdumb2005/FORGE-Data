"""forge_helpers — Python module injected into every FORGE Jupyter kernel.

This module is executed silently when a kernel starts to set up a convenient
environment for data exploration: common imports, the ``forge_query()``
shortcut for querying registered data sources, and a matplotlib backend
suitable for non-interactive rendering.
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

# ── forge_query: run SQL against the FORGE query engine ────────────────────
import httpx as _httpx

_FORGE_API_BASE = "__FORGE_API_BASE__"
_FORGE_AUTH_TOKEN = "__FORGE_AUTH_TOKEN__"
_FORGE_WORKSPACE_ID = "__FORGE_WORKSPACE_ID__"

def forge_query(sql: str) -> pd.DataFrame:
    """Execute *sql* against all registered data sources and return a DataFrame.

    Example::

        df = forge_query("SELECT * FROM my_dataset LIMIT 100")
        df.head()
    """
    url = f"{_FORGE_API_BASE}/api/v1/connectors/workspaces/{_FORGE_WORKSPACE_ID}/query"
    headers = {"Authorization": f"Bearer {_FORGE_AUTH_TOKEN}"}
    r = _httpx.post(url, json={"sql": sql}, headers=headers, timeout=60)
    r.raise_for_status()
    data = r.json()
    if "error" in data:
        raise RuntimeError(f"Query error: {data['error']}")
    return pd.DataFrame(data["rows"], columns=data["columns"])


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

print("\U0001f525 FORGE kernel ready. Use forge_query(sql) to query your data sources.")
'''


def build_bootstrap_code(
    api_base: str,
    auth_token: str,
    workspace_id: str,
) -> str:
    """Return the bootstrap source with runtime values substituted in.

    Values are embedded using repr() to ensure correct Python string escaping
    regardless of special characters in the token or workspace ID.
    """
    return (
        BOOTSTRAP_CODE
        .replace("\"__FORGE_API_BASE__\"", repr(api_base))
        .replace("\"__FORGE_AUTH_TOKEN__\"", repr(auth_token))
        .replace("\"__FORGE_WORKSPACE_ID__\"", repr(workspace_id))
    )
