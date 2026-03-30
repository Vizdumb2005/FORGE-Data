"""PII detection and masking helpers for uploaded datasets."""

from __future__ import annotations

import re
from typing import Any, ClassVar

import pandas as pd


class PIIDetector:
    """
    Detect common PII patterns in dataset columns.

    Detection is sample-based (up to 1000 non-null values per column).
    """

    PATTERNS: ClassVar[dict[str, re.Pattern[str]]] = {
        "email": re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"),
        "phone": re.compile(r"(?:\+?1[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)?\d{3}[-.\s]?\d{4}"),
        "ssn": re.compile(r"\d{3}-\d{2}-\d{4}"),
        "credit_card": re.compile(r"\b(?:\d{4}[-\s]?){3}\d{4}\b"),
        "ip_address": re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b"),
    }

    async def scan_dataframe(self, df: pd.DataFrame) -> dict[str, list[str]]:
        detected: dict[str, list[str]] = {}

        for col in df.columns:
            series = df[col].dropna()
            if series.empty:
                continue

            sampled = series.head(1000).astype(str)
            col_hits: list[str] = []
            for pii_type, pattern in self.PATTERNS.items():
                if sampled.str.contains(pattern, regex=True, na=False).any():
                    col_hits.append(pii_type)

            if col_hits:
                detected[str(col)] = col_hits

        return detected

    async def mask_column(self, df: pd.DataFrame, column: str, pii_type: str) -> pd.DataFrame:
        if column not in df.columns:
            return df

        masked_df = df.copy()
        series = masked_df[column]
        if pii_type == "email":
            masked_df[column] = series.map(_mask_email)
        elif pii_type == "phone":
            masked_df[column] = series.map(lambda v: _mask_with_last4(v, "***-***-"))
        elif pii_type == "ssn":
            masked_df[column] = series.map(lambda v: _mask_with_last4(v, "***-**-"))
        elif pii_type == "credit_card":
            masked_df[column] = series.map(lambda v: _mask_with_last4(v, "****-****-****-"))
        return masked_df


def _mask_email(value: Any) -> Any:
    if value is None:
        return value
    text = str(value)
    if "@" not in text:
        return value
    local, domain = text.split("@", 1)
    if not local:
        return f"***@{domain}"
    return f"{local[0]}***@{domain}"


def _mask_with_last4(value: Any, prefix: str) -> Any:
    if value is None:
        return value
    digits = "".join(ch for ch in str(value) if ch.isdigit())
    if len(digits) < 4:
        return value
    return f"{prefix}{digits[-4:]}"
