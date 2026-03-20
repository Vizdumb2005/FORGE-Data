"""Data quality engine — Great Expectations-style rule-based validation."""

import io
import logging
import re
from dataclasses import dataclass, field
from typing import Any

import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.exceptions import NotFoundException, ServiceUnavailableException
from app.models.data_quality import DataQualityReport, DataQualityRuleset
from app.models.dataset import Dataset
from app.models.dataset_version import DatasetVersion

logger = logging.getLogger(__name__)

# Built-in rule descriptions (for documentation / UI display)
BUILT_IN_RULES = {
    "not_null": "Column {col} should have no nulls",
    "unique": "Column {col} should be unique",
    "min_value": "Column {col} minimum should be >= {threshold}",
    "max_value": "Column {col} maximum should be <= {threshold}",
    "regex_match": "Column {col} should match pattern {pattern}",
    "accepted_values": "Column {col} should only contain {values}",
    "row_count_gte": "Dataset should have at least {threshold} rows",
}

_MAX_FAILING_SAMPLES = 5


@dataclass
class CheckResult:
    """Result of a single quality check."""

    rule_type: str
    column: str | None
    status: str  # "passed" | "failed"
    message: str
    failing_rows_sample: list[Any] = field(default_factory=list)


class DataQualityEngine:
    """Runs data quality checks using rule definitions stored as JSON."""

    # ── Run checks ────────────────────────────────────────────────────────

    async def run_checks(
        self,
        db: AsyncSession,
        workspace_id: str,
        dataset_id: str,
        user_id: str,
        rules: list[dict[str, Any]],
        ruleset_id: str | None = None,
    ) -> DataQualityReport:
        """Load the latest dataset version and run all rules against it."""
        df = await self._load_latest_dataframe(db, workspace_id, dataset_id)
        version_number = await self._get_latest_version_number(db, dataset_id)

        results: list[dict[str, Any]] = []
        passed = 0
        failed = 0

        for rule in rules:
            check = self._execute_rule(df, rule)
            if check.status == "passed":
                passed += 1
            else:
                failed += 1
            results.append(
                {
                    "rule_type": check.rule_type,
                    "column": check.column,
                    "status": check.status,
                    "message": check.message,
                    "failing_rows_sample": check.failing_rows_sample,
                }
            )

        # Persist the report
        report = DataQualityReport(
            dataset_id=dataset_id,
            version_number=version_number,
            passed=passed,
            failed=failed,
            results=results,
            ruleset_id=ruleset_id,
            created_by=user_id,
        )
        db.add(report)
        await db.flush()

        logger.info(
            "Quality check on dataset %s: %d passed, %d failed",
            dataset_id,
            passed,
            failed,
        )
        return report

    # ── Ruleset management ────────────────────────────────────────────────

    async def save_ruleset(
        self,
        db: AsyncSession,
        workspace_id: str,
        dataset_id: str,
        user_id: str,
        name: str,
        rules: list[dict[str, Any]],
    ) -> DataQualityRuleset:
        """Create or update a named ruleset for a dataset."""
        # Verify dataset exists
        await self._get_dataset(db, workspace_id, dataset_id)

        # Check if a ruleset with this name already exists
        result = await db.execute(
            select(DataQualityRuleset).where(
                DataQualityRuleset.dataset_id == dataset_id,
                DataQualityRuleset.name == name,
            )
        )
        existing = result.scalar_one_or_none()

        if existing:
            existing.rules = rules
            await db.flush()
            return existing

        ruleset = DataQualityRuleset(
            dataset_id=dataset_id,
            name=name,
            rules=rules,
            created_by=user_id,
        )
        db.add(ruleset)
        await db.flush()
        return ruleset

    async def get_ruleset(
        self,
        db: AsyncSession,
        workspace_id: str,
        dataset_id: str,
        ruleset_id: str,
    ) -> DataQualityRuleset:
        """Fetch a specific ruleset."""
        await self._get_dataset(db, workspace_id, dataset_id)
        result = await db.execute(
            select(DataQualityRuleset).where(
                DataQualityRuleset.id == ruleset_id,
                DataQualityRuleset.dataset_id == dataset_id,
            )
        )
        ruleset = result.scalar_one_or_none()
        if ruleset is None:
            raise NotFoundException("DataQualityRuleset", ruleset_id)
        return ruleset

    async def get_report_history(
        self,
        db: AsyncSession,
        workspace_id: str,
        dataset_id: str,
        limit: int = 20,
    ) -> list[DataQualityReport]:
        """Return the most recent quality reports for a dataset."""
        await self._get_dataset(db, workspace_id, dataset_id)
        result = await db.execute(
            select(DataQualityReport)
            .where(DataQualityReport.dataset_id == dataset_id)
            .order_by(DataQualityReport.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    # ── Rule execution dispatcher ─────────────────────────────────────────

    def _execute_rule(self, df: pd.DataFrame, rule: dict[str, Any]) -> CheckResult:
        rule_type = rule.get("type", "")
        column = rule.get("column")

        dispatch = {
            "not_null": self._check_not_null,
            "unique": self._check_unique,
            "min_value": self._check_min_value,
            "max_value": self._check_max_value,
            "regex_match": self._check_regex_match,
            "accepted_values": self._check_accepted_values,
            "row_count_gte": self._check_row_count_gte,
        }

        check_fn = dispatch.get(rule_type)
        if check_fn is None:
            return CheckResult(
                rule_type=rule_type,
                column=column,
                status="failed",
                message=f"Unknown rule type: {rule_type}",
            )

        try:
            return check_fn(df, rule)
        except Exception as exc:
            return CheckResult(
                rule_type=rule_type,
                column=column,
                status="failed",
                message=f"Rule execution error: {exc}",
            )

    # ── Individual check implementations ──────────────────────────────────

    def _check_not_null(self, df: pd.DataFrame, rule: dict) -> CheckResult:
        col = rule["column"]
        if col not in df.columns:
            return CheckResult("not_null", col, "failed", f"Column '{col}' not found")
        null_mask = df[col].isna()
        null_count = int(null_mask.sum())
        if null_count == 0:
            return CheckResult("not_null", col, "passed", f"Column '{col}' has no nulls")
        samples = df[null_mask].head(_MAX_FAILING_SAMPLES).index.tolist()
        return CheckResult(
            "not_null",
            col,
            "failed",
            f"Column '{col}' has {null_count} null values",
            failing_rows_sample=[f"row {i}" for i in samples],
        )

    def _check_unique(self, df: pd.DataFrame, rule: dict) -> CheckResult:
        col = rule["column"]
        if col not in df.columns:
            return CheckResult("unique", col, "failed", f"Column '{col}' not found")
        dupes = df[col].duplicated(keep=False)
        dupe_count = int(dupes.sum())
        if dupe_count == 0:
            return CheckResult("unique", col, "passed", f"Column '{col}' is unique")
        sample_vals = df.loc[dupes, col].head(_MAX_FAILING_SAMPLES).tolist()
        return CheckResult(
            "unique",
            col,
            "failed",
            f"Column '{col}' has {dupe_count} duplicate values",
            failing_rows_sample=[_to_json_safe(v) for v in sample_vals],
        )

    def _check_min_value(self, df: pd.DataFrame, rule: dict) -> CheckResult:
        col = rule["column"]
        threshold = rule.get("threshold", 0)
        if col not in df.columns:
            return CheckResult("min_value", col, "failed", f"Column '{col}' not found")
        violations = df[df[col] < threshold]
        if violations.empty:
            return CheckResult(
                "min_value",
                col,
                "passed",
                f"Column '{col}' min >= {threshold}",
            )
        sample_vals = violations[col].head(_MAX_FAILING_SAMPLES).tolist()
        return CheckResult(
            "min_value",
            col,
            "failed",
            f"Column '{col}' has {len(violations)} values below {threshold}",
            failing_rows_sample=[_to_json_safe(v) for v in sample_vals],
        )

    def _check_max_value(self, df: pd.DataFrame, rule: dict) -> CheckResult:
        col = rule["column"]
        threshold = rule.get("threshold", 0)
        if col not in df.columns:
            return CheckResult("max_value", col, "failed", f"Column '{col}' not found")
        violations = df[df[col] > threshold]
        if violations.empty:
            return CheckResult(
                "max_value",
                col,
                "passed",
                f"Column '{col}' max <= {threshold}",
            )
        sample_vals = violations[col].head(_MAX_FAILING_SAMPLES).tolist()
        return CheckResult(
            "max_value",
            col,
            "failed",
            f"Column '{col}' has {len(violations)} values above {threshold}",
            failing_rows_sample=[_to_json_safe(v) for v in sample_vals],
        )

    def _check_regex_match(self, df: pd.DataFrame, rule: dict) -> CheckResult:
        col = rule["column"]
        pattern = rule.get("pattern", "")
        if col not in df.columns:
            return CheckResult("regex_match", col, "failed", f"Column '{col}' not found")
        series = df[col].dropna().astype(str)
        compiled = re.compile(pattern)
        non_matching = series[~series.map(lambda v: bool(compiled.fullmatch(v)))]
        if non_matching.empty:
            return CheckResult(
                "regex_match",
                col,
                "passed",
                f"Column '{col}' matches pattern '{pattern}'",
            )
        sample_vals = non_matching.head(_MAX_FAILING_SAMPLES).tolist()
        return CheckResult(
            "regex_match",
            col,
            "failed",
            f"Column '{col}' has {len(non_matching)} values not matching '{pattern}'",
            failing_rows_sample=sample_vals,
        )

    def _check_accepted_values(self, df: pd.DataFrame, rule: dict) -> CheckResult:
        col = rule["column"]
        accepted = set(rule.get("values", []))
        if col not in df.columns:
            return CheckResult("accepted_values", col, "failed", f"Column '{col}' not found")
        series = df[col].dropna()
        invalid = series[~series.isin(accepted)]
        if invalid.empty:
            return CheckResult(
                "accepted_values",
                col,
                "passed",
                f"Column '{col}' only contains accepted values",
            )
        sample_vals = invalid.head(_MAX_FAILING_SAMPLES).tolist()
        return CheckResult(
            "accepted_values",
            col,
            "failed",
            f"Column '{col}' has {len(invalid)} values not in accepted set",
            failing_rows_sample=[_to_json_safe(v) for v in sample_vals],
        )

    def _check_row_count_gte(self, df: pd.DataFrame, rule: dict) -> CheckResult:
        threshold = rule.get("threshold", 0)
        actual = len(df)
        if actual >= threshold:
            return CheckResult(
                "row_count_gte",
                None,
                "passed",
                f"Row count {actual} >= {threshold}",
            )
        return CheckResult(
            "row_count_gte",
            None,
            "failed",
            f"Row count {actual} < {threshold}",
        )

    # ── Data loading helpers ──────────────────────────────────────────────

    async def _load_latest_dataframe(
        self, db: AsyncSession, workspace_id: str, dataset_id: str
    ) -> pd.DataFrame:
        """Load the latest version of the dataset as a DataFrame.

        Tries versioned Parquet first, then falls back to the dataset's
        storage_path in MinIO.
        """
        dataset = await self._get_dataset(db, workspace_id, dataset_id)

        # Try latest version first
        result = await db.execute(
            select(DatasetVersion)
            .where(DatasetVersion.dataset_id == dataset_id)
            .order_by(DatasetVersion.version_number.desc())
            .limit(1)
        )
        latest_version = result.scalar_one_or_none()

        if latest_version:
            data = await _download_from_minio(latest_version.parquet_path)
            return pd.read_parquet(io.BytesIO(data))

        # Fallback to dataset's own storage_path
        if dataset.storage_path:
            data = await _download_from_minio(dataset.storage_path)
            return pd.read_parquet(io.BytesIO(data))

        raise NotFoundException("Dataset data", dataset_id)

    async def _get_latest_version_number(self, db: AsyncSession, dataset_id: str) -> int | None:
        result = await db.execute(
            select(DatasetVersion.version_number)
            .where(DatasetVersion.dataset_id == dataset_id)
            .order_by(DatasetVersion.version_number.desc())
            .limit(1)
        )
        row = result.scalar_one_or_none()
        return row if row is not None else None

    async def _get_dataset(self, db: AsyncSession, workspace_id: str, dataset_id: str) -> Dataset:
        result = await db.execute(
            select(Dataset).where(
                Dataset.id == dataset_id,
                Dataset.workspace_id == workspace_id,
            )
        )
        dataset = result.scalar_one_or_none()
        if dataset is None:
            raise NotFoundException("Dataset", dataset_id)
        return dataset


# ── Private helpers ───────────────────────────────────────────────────────────


def _to_json_safe(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, int | float | str | bool):
        return value
    return str(value)


async def _download_from_minio(object_name: str) -> bytes:
    try:
        from minio import Minio

        client = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_use_ssl,
        )
        response = client.get_object(settings.minio_bucket, object_name)
        return response.read()
    except Exception as exc:
        raise ServiceUnavailableException("MinIO storage") from exc
