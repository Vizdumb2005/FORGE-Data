"""Built-in Orion workflow templates."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.core.exceptions import ValidationError
from app.models.workflow import WorkflowTriggerType


def get_workflow_templates() -> list[dict[str, Any]]:
    return [
        {
            "key": "daily_dataset_refresh",
            "name": "Daily Dataset Refresh",
            "description": "Refresh a dataset daily, validate rows, then notify.",
            "required_config_keys": ["dataset_id", "refresh_sql", "notify_email"],
            "workflow": {
                "trigger_type": WorkflowTriggerType.schedule.value,
                "schedule_cron": "0 8 * * *",
                "schedule_timezone": "UTC",
                "trigger_config": {},
                "nodes": [
                    {"node_type": "wait", "label": "Trigger (Schedule)", "config": {"seconds": 0}, "position_x": 40, "position_y": 120},
                    {"node_type": "sql_query", "label": "SQL Query", "config": {"dataset_id": "{{dataset_id}}", "sql": "{{refresh_sql}}", "output_table_name": "daily_refresh"}, "position_x": 300, "position_y": 120},
                    {"node_type": "conditional", "label": "Rows > 0?", "config": {"expression": "outputs.get(run_context.get('node_aliases', {}).get('sql_query'), {}).get('row_count', 0) > 0"}, "position_x": 560, "position_y": 120},
                    {"node_type": "email_notify", "label": "Email Success", "config": {"to": ["{{notify_email}}"], "subject": "Daily refresh succeeded", "body_template": "Refresh complete. Rows: {{ outputs.get(run_context.get('node_aliases', {}).get('sql_query'), {}).get('row_count', 0) }}"}, "position_x": 840, "position_y": 70},
                    {"node_type": "email_notify", "label": "Email Failure", "config": {"to": ["{{notify_email}}"], "subject": "Daily refresh produced no rows", "body_template": "Refresh completed but row_count is 0."}, "position_x": 840, "position_y": 190},
                ],
                "edges": [
                    {"from": 0, "to": 1, "condition": "always"},
                    {"from": 1, "to": 2, "condition": "on_success"},
                    {"from": 2, "to": 3, "condition": "on_success"},
                    {"from": 2, "to": 4, "condition": "on_failure"},
                ],
            },
        },
        {
            "key": "ml_retrain_on_new_data",
            "name": "ML Model Retrain on New Data",
            "description": "Retrain a model automatically when sufficient new data arrives.",
            "required_config_keys": ["dataset_id", "experiment_id", "min_training_rows", "notify_email"],
            "workflow": {
                "trigger_type": WorkflowTriggerType.dataset_event.value,
                "schedule_timezone": "UTC",
                "trigger_config": {
                    "event_type": "dataset.version_created",
                    "dataset_id": "{{dataset_id}}",
                },
                "nodes": [
                    {"node_type": "wait", "label": "Trigger (Dataset Event)", "config": {"seconds": 0}, "position_x": 40, "position_y": 120},
                    {"node_type": "sql_query", "label": "Validate Data", "config": {"dataset_id": "{{dataset_id}}", "sql": "SELECT COUNT(*) AS row_count FROM dataset_{{dataset_id}}", "output_table_name": "training_validation"}, "position_x": 300, "position_y": 120},
                    {"node_type": "conditional", "label": "Enough Rows?", "config": {"expression": "outputs.get('{{sql_node_id}}', {}).get('row_count', 0) >= {{min_training_rows}}"}, "position_x": 560, "position_y": 120},
                    {"node_type": "model_retrain", "label": "Retrain Model", "config": {"experiment_id": "{{experiment_id}}", "parameters": {"dataset_id": "{{dataset_id}}"}}, "position_x": 820, "position_y": 70},
                    {"node_type": "email_notify", "label": "Notify Not Enough Data", "config": {"to": ["{{notify_email}}"], "subject": "Retrain skipped", "body_template": "Not enough rows to retrain model. Required: {{ run_context.trigger_payload.get('min_training_rows', 'N/A') }}."}, "position_x": 820, "position_y": 190},
                    {"node_type": "email_notify", "label": "Notify Retrained", "config": {"to": ["{{notify_email}}"], "subject": "Model retrained", "body_template": "Retrain completed for experiment {{ run_context.trigger_payload.get('experiment_id', '') }}."}, "position_x": 1080, "position_y": 70},
                ],
                "edges": [
                    {"from": 0, "to": 1, "condition": "always"},
                    {"from": 1, "to": 2, "condition": "on_success"},
                    {"from": 2, "to": 3, "condition": "on_success"},
                    {"from": 2, "to": 4, "condition": "on_failure"},
                    {"from": 3, "to": 5, "condition": "on_success"},
                ],
            },
        },
        {
            "key": "weekly_dashboard_report",
            "name": "Weekly Dashboard Report",
            "description": "Refresh dashboard weekly and notify via Slack and email.",
            "required_config_keys": ["dashboard_id", "slack_webhook_url", "notify_email"],
            "workflow": {
                "trigger_type": WorkflowTriggerType.schedule.value,
                "schedule_cron": "0 9 * * 1",
                "schedule_timezone": "UTC",
                "trigger_config": {},
                "nodes": [
                    {"node_type": "wait", "label": "Trigger (Schedule)", "config": {"seconds": 0}, "position_x": 40, "position_y": 120},
                    {"node_type": "sql_query", "label": "Compute Weekly Metrics", "config": {"sql": "SELECT CURRENT_DATE AS report_date", "output_table_name": "weekly_report"}, "position_x": 300, "position_y": 120},
                    {"node_type": "dashboard_publish", "label": "Publish Dashboard", "config": {"dashboard_id": "{{dashboard_id}}"}, "position_x": 560, "position_y": 120},
                    {"node_type": "api_call", "label": "Notify Slack", "config": {"method": "POST", "url": "{{slack_webhook_url}}", "headers": {"Content-Type": "application/json"}, "body": {"text": "Weekly dashboard has been published."}}, "position_x": 820, "position_y": 90},
                    {"node_type": "email_notify", "label": "Email Report", "config": {"to": ["{{notify_email}}"], "subject": "Weekly dashboard published", "body_template": "Dashboard {{ run_context.trigger_payload.get('dashboard_id', '') }} was published."}, "position_x": 820, "position_y": 200},
                ],
                "edges": [
                    {"from": 0, "to": 1, "condition": "always"},
                    {"from": 1, "to": 2, "condition": "on_success"},
                    {"from": 2, "to": 3, "condition": "on_success"},
                    {"from": 2, "to": 4, "condition": "on_success"},
                ],
            },
        },
        {
            "key": "data_quality_gate",
            "name": "Data Quality Gate",
            "description": "Run quality checks and promote only when all checks pass.",
            "required_config_keys": ["dataset_id", "quality_sql", "promote_cell_id", "notify_email"],
            "workflow": {
                "trigger_type": WorkflowTriggerType.dataset_event.value,
                "schedule_timezone": "UTC",
                "trigger_config": {
                    "event_type": "dataset.version_created",
                    "dataset_id": "{{dataset_id}}",
                },
                "nodes": [
                    {"node_type": "wait", "label": "Trigger (Dataset Event)", "config": {"seconds": 0}, "position_x": 40, "position_y": 120},
                    {"node_type": "sql_query", "label": "Quality SQL", "config": {"dataset_id": "{{dataset_id}}", "sql": "{{quality_sql}}", "output_table_name": "quality_gate"}, "position_x": 300, "position_y": 120},
                    {"node_type": "conditional", "label": "All Pass?", "config": {"expression": "outputs.get('{{sql_node_id}}', {}).get('row_count', 0) > 0"}, "position_x": 560, "position_y": 120},
                    {"node_type": "code_cell", "label": "Promote Dataset", "config": {"cell_id": "{{promote_cell_id}}"}, "position_x": 820, "position_y": 70},
                    {"node_type": "email_notify", "label": "Email Blocked", "config": {"to": ["{{notify_email}}"], "subject": "Dataset blocked by quality gate", "body_template": "Quality gate failed for dataset {{ run_context.trigger_payload.get('dataset_id', '') }}."}, "position_x": 820, "position_y": 190},
                ],
                "edges": [
                    {"from": 0, "to": 1, "condition": "always"},
                    {"from": 1, "to": 2, "condition": "on_success"},
                    {"from": 2, "to": 3, "condition": "on_success"},
                    {"from": 2, "to": 4, "condition": "on_failure"},
                ],
            },
        },
    ]


def instantiate_template(template_key: str, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    template = {t["key"]: t for t in get_workflow_templates()}.get(template_key)
    if template is None:
        raise ValidationError(f"Unknown template key '{template_key}'")

    merged_overrides = dict(overrides or {})
    missing = [key for key in template["required_config_keys"] if key not in merged_overrides]
    if missing:
        raise ValidationError(f"Missing required template config: {', '.join(missing)}")

    workflow_def = deepcopy(template["workflow"])
    _render_template_placeholders(workflow_def, merged_overrides)
    return {
        "key": template["key"],
        "name": template["name"],
        "description": template["description"],
        "required_config_keys": template["required_config_keys"],
        "workflow": workflow_def,
    }


def _render_template_placeholders(target: Any, overrides: dict[str, Any]) -> Any:
    if isinstance(target, dict):
        for key, value in list(target.items()):
            target[key] = _render_template_placeholders(value, overrides)
        return target
    if isinstance(target, list):
        for index, value in enumerate(target):
            target[index] = _render_template_placeholders(value, overrides)
        return target
    if isinstance(target, str):
        rendered = target
        for key, value in overrides.items():
            rendered = rendered.replace(f"{{{{{key}}}}}", str(value))
        return rendered
    return target

