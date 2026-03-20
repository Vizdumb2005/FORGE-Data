"""Natural language to code generation orchestration."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.llm_provider import LLMProvider
from app.models.dataset import Dataset
from app.models.user import User


@dataclass(slots=True)
class WorkspaceContext:
    workspace_id: str
    db: AsyncSession
    metadata: dict[str, Any] | None = None


class CodeGenerator:
    """
    Generates Python, SQL, and R code from natural language.
    Context-aware: knows the user's datasets, schemas, and workspace history.
    """

    PYTHON_SYSTEM_PROMPT = """You are an expert data scientist assistant inside FORGE Data platform.
You generate Python code for data analysis. You have access to:
- pandas as pd, numpy as np, plotly.express as px, plotly.graph_objects as go
- matplotlib.pyplot as plt, seaborn as sns, scipy, sklearn
- forge_query(sql) function to run SQL against connected datasets
- The following datasets are available as DataFrames if you call forge_query:
  {dataset_schemas}

Rules:
1. ALWAYS return ONLY executable Python code, no markdown fences, no explanation text
2. Print results and display charts using plotly (preferred) or matplotlib
3. For dataframes, print df.to_string() or display a sample
4. If creating a plotly chart, use fig.show() — FORGE will capture it
5. Handle errors gracefully in your code
6. Comment your code clearly
The user's current workspace context: {workspace_context}"""

    SQL_SYSTEM_PROMPT = """You are an expert SQL analyst inside FORGE Data platform.
Available tables: {dataset_schemas}
Rules:
1. Return ONLY valid SQL, no markdown, no explanation
2. Use standard SQL compatible with DuckDB (supports most PostgreSQL syntax)
3. Always include column aliases for computed fields
4. Add LIMIT 1000 unless user specifies differently"""

    R_SYSTEM_PROMPT = """You are an expert R data analyst inside FORGE Data platform.
Available datasets: {dataset_schemas}
Rules:
1. Return ONLY executable R code, no markdown or explanation
2. Prefer tidyverse/data.table idioms where clear
3. Print concise summaries/tables and generate clear plots
4. Handle potential errors in code with informative output
Workspace context: {workspace_context}"""

    def __init__(self, llm_provider: LLMProvider | None = None) -> None:
        self.llm_provider = llm_provider or LLMProvider()

    async def generate_code(
        self,
        user: User,
        prompt: str,
        language: str,
        workspace_context: WorkspaceContext,
        history: list[dict[str, str]] | None = None,
    ) -> AsyncIterator[str]:
        dataset_schemas = await self._dataset_schemas(workspace_context)
        system_prompt = self._system_prompt(language, dataset_schemas, workspace_context)

        messages: list[dict[str, str]] = []
        for message in history or []:
            if "role" in message and "content" in message:
                messages.append({"role": message["role"], "content": message["content"]})
        messages.append({"role": "user", "content": prompt})

        result = await self.llm_provider.complete(
            user=user,
            messages=messages,
            system=system_prompt,
            stream=True,
        )
        if isinstance(result, str):
            yield result
            return
        async for chunk in result:
            yield chunk

    async def fix_error(
        self,
        user: User,
        original_code: str,
        error_output: str,
        language: str,
        workspace_context: WorkspaceContext,
    ) -> AsyncIterator[str]:
        fix_prompt = (
            "This code produced this error. Fix it and return only corrected code.\n\n"
            f"Language: {language}\n\n"
            f"Original code:\n{original_code}\n\n"
            f"Error output:\n{error_output}"
        )
        async for chunk in self.generate_code(
            user=user,
            prompt=fix_prompt,
            language=language,
            workspace_context=workspace_context,
        ):
            yield chunk

    async def explain_output(
        self,
        user: User,
        code: str,
        output: str,
        language: str,
    ) -> AsyncIterator[str]:
        prompt = (
            "Explain what this output means in plain English.\n\n"
            f"Language: {language}\n\n"
            f"Code:\n{code}\n\n"
            f"Output:\n{output}"
        )
        result = await self.llm_provider.complete(
            user=user,
            messages=[{"role": "user", "content": prompt}],
            system="You are a clear and concise data analysis explainer.",
            stream=True,
            max_tokens=1200,
        )
        if isinstance(result, str):
            yield result
            return
        async for chunk in result:
            yield chunk

    async def suggest_next_steps(
        self,
        user: User,
        analysis_history: list[dict[str, str]],
        workspace_context: WorkspaceContext,
    ) -> list[str]:
        dataset_schemas = await self._dataset_schemas(workspace_context)
        prompt = (
            "Given this analysis history and dataset context, suggest exactly 3 concise next-step "
            "analysis actions/questions. Return JSON array of 3 strings only.\n\n"
            f"History:\n{json.dumps(analysis_history)}\n\n"
            f"Dataset schemas:\n{dataset_schemas}"
        )
        result = await self.llm_provider.complete(
            user=user,
            messages=[{"role": "user", "content": prompt}],
            system="You are a senior analytics copilot.",
            stream=False,
            max_tokens=500,
        )
        text = result if isinstance(result, str) else ""
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return [str(item) for item in parsed][:3]
        except json.JSONDecodeError:
            pass

        fallback = [line.strip("- ").strip() for line in text.splitlines() if line.strip()]
        return fallback[:3]

    async def _dataset_schemas(self, workspace_context: WorkspaceContext) -> str:
        result = await workspace_context.db.execute(
            select(Dataset).where(Dataset.workspace_id == workspace_context.workspace_id)
        )
        datasets = result.scalars().all()

        if not datasets:
            return "No datasets available in this workspace."

        lines: list[str] = []
        for dataset in datasets:
            columns = dataset.schema_snapshot or []
            if not columns:
                lines.append(f"- {dataset.name}: schema unavailable")
                continue
            col_defs = ", ".join(
                f"{col.get('name', 'unknown')}:{col.get('dtype', 'unknown')}" for col in columns
            )
            lines.append(f"- {dataset.name}({col_defs})")
        return "\n".join(lines)

    def _system_prompt(
        self,
        language: str,
        dataset_schemas: str,
        workspace_context: WorkspaceContext,
    ) -> str:
        serialized_context = json.dumps(workspace_context.metadata or {})
        if language == "python":
            return self.PYTHON_SYSTEM_PROMPT.format(
                dataset_schemas=dataset_schemas,
                workspace_context=serialized_context,
            )
        if language == "sql":
            return self.SQL_SYSTEM_PROMPT.format(dataset_schemas=dataset_schemas)
        if language == "r":
            return self.R_SYSTEM_PROMPT.format(
                dataset_schemas=dataset_schemas,
                workspace_context=serialized_context,
            )
        return self.PYTHON_SYSTEM_PROMPT.format(
            dataset_schemas=dataset_schemas,
            workspace_context=serialized_context,
        )
