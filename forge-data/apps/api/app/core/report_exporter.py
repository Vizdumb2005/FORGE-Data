"""Workspace report export and scheduling service."""

from __future__ import annotations

import io
from datetime import UTC, datetime
from uuid import UUID

import nbformat
from nbformat.v4 import new_code_cell, new_markdown_cell, new_notebook, new_output
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ValidationError
from app.models.cell import Cell
from app.models.publishing import ScheduledReport
from app.workers.celery_app import celery_app


class ReportExporter:
    """Exports workspace content in various formats."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def _get_cells(
        self, workspace_id: UUID, cell_ids: list[UUID]
    ) -> list[Cell]:
        result = await self._db.execute(
            select(Cell).where(
                Cell.workspace_id == str(workspace_id),
                Cell.id.in_([str(cell_id) for cell_id in cell_ids]),
            )
        )
        cells = list(result.scalars().all())
        if len(cells) != len(cell_ids):
            raise ValidationError("One or more cell_ids were not found in workspace")
        order_map = {str(cid): i for i, cid in enumerate(cell_ids)}
        cells.sort(key=lambda c: order_map.get(c.id, 0))
        return cells

    async def export_jupyter(self, workspace_id: UUID, cell_ids: list[UUID]) -> bytes:
        cells = await self._get_cells(workspace_id, cell_ids)
        notebook_cells = []
        for cell in cells:
            if cell.cell_type == "markdown" or cell.language == "markdown":
                notebook_cells.append(new_markdown_cell(source=cell.content))
                continue
            nb_cell = new_code_cell(source=cell.content)
            outputs = []
            output = cell.output or {}
            for event in output.get("outputs", []):
                event_type = event.get("type")
                if event_type == "stream":
                    outputs.append(
                        new_output(
                            output_type="stream",
                            name=event.get("name", "stdout"),
                            text=event.get("text", ""),
                        )
                    )
                elif event_type in {"execute_result", "result", "image"}:
                    outputs.append(
                        new_output(
                            output_type="execute_result",
                            data=event.get("data", {"text/plain": ""}),
                            metadata={},
                            execution_count=output.get("execution_count"),
                        )
                    )
                elif event_type == "error":
                    outputs.append(
                        new_output(
                            output_type="error",
                            ename=event.get("ename", "Error"),
                            evalue=event.get("evalue", ""),
                            traceback=event.get("traceback", []),
                        )
                    )
            nb_cell["outputs"] = outputs
            nb_cell["execution_count"] = output.get("execution_count")
            notebook_cells.append(nb_cell)

        nb = new_notebook(cells=notebook_cells, metadata={"forge_workspace_id": str(workspace_id)})
        return nbformat.writes(nb).encode("utf-8")

    async def export_html(self, workspace_id: UUID, cell_ids: list[UUID]) -> bytes:
        cells = await self._get_cells(workspace_id, cell_ids)
        html_parts = [
            "<!doctype html><html><head><meta charset='utf-8'/>",
            "<meta name='viewport' content='width=device-width, initial-scale=1'/>",
            "<script src='https://cdn.plot.ly/plotly-2.35.2.min.js'></script>",
            "<style>body{font-family:Arial,sans-serif;padding:24px;background:#0b0f16;color:#e6edf3}"
            ".cell{border:1px solid #273244;border-radius:8px;padding:12px;margin-bottom:12px}"
            "pre{background:#111827;padding:10px;border-radius:6px;overflow:auto}"
            ".footer{margin-top:32px;color:#8b949e;font-size:12px}</style></head><body>",
            f"<h1>FORGE Report - Workspace {workspace_id}</h1>",
        ]
        for cell in cells:
            html_parts.append("<div class='cell'>")
            html_parts.append(f"<h3>{cell.cell_type.upper()} ({cell.language})</h3>")
            html_parts.append(f"<pre><code>{cell.content}</code></pre>")
            output = cell.output or {}
            outputs = output.get("outputs", [])
            if outputs:
                html_parts.append("<h4>Output</h4>")
            for event in outputs:
                data = event.get("data", {})
                if "text/html" in data:
                    html_parts.append(str(data["text/html"]))
                elif "image/png" in data:
                    html_parts.append(
                        f"<img alt='output' style='max-width:100%' src='data:image/png;base64,{data['image/png']}'/>"
                    )
                elif "text/plain" in data:
                    html_parts.append(f"<pre>{data['text/plain']}</pre>")
                elif event.get("text"):
                    html_parts.append(f"<pre>{event.get('text')}</pre>")
            html_parts.append("</div>")
        html_parts.append("<div class='footer'>Published by FORGE Data</div></body></html>")
        return "".join(html_parts).encode("utf-8")

    async def export_pdf(self, workspace_id: UUID, cell_ids: list[UUID]) -> bytes:
        html_bytes = await self.export_html(workspace_id, cell_ids)
        html_preview = html_bytes.decode("utf-8", errors="ignore")
        buffer = io.BytesIO()
        pdf = canvas.Canvas(buffer, pagesize=A4)
        pdf.setTitle(f"FORGE Report {workspace_id}")
        _, height = A4
        y = height - 40
        pdf.setFont("Helvetica-Bold", 14)
        pdf.drawString(40, y, "FORGE Data Report")
        y -= 24
        pdf.setFont("Helvetica", 9)
        for line in html_preview[:8000].splitlines():
            if y < 40:
                pdf.showPage()
                y = height - 40
                pdf.setFont("Helvetica", 9)
            pdf.drawString(40, y, line[:140])
            y -= 12
        pdf.showPage()
        pdf.save()
        buffer.seek(0)
        return buffer.read()

    async def schedule_report(
        self,
        workspace_id: UUID,
        created_by: UUID,
        cell_ids: list[UUID],
        report_format: str,
        schedule: str,
        delivery: dict,
    ) -> ScheduledReport:
        fmt = report_format.lower()
        if fmt not in {"html", "pdf"}:
            raise ValidationError("format must be 'html' or 'pdf'")
        if not schedule.strip():
            raise ValidationError("schedule must be a cron expression")
        if not isinstance(delivery, dict) or "type" not in delivery:
            raise ValidationError("delivery must include a 'type'")

        await self._get_cells(workspace_id, cell_ids)
        report = ScheduledReport(
            workspace_id=str(workspace_id),
            created_by=str(created_by),
            cell_ids=[str(cell_id) for cell_id in cell_ids],
            format=fmt,
            cron_expression=schedule,
            delivery=delivery,
            celery_task_name=f"report_{workspace_id}_{datetime.now(UTC).timestamp()}",
            is_active=True,
            title=f"Scheduled {fmt.upper()} report",
        )
        self._db.add(report)
        await self._db.flush()
        celery_app.send_task("app.workers.publish.run_scheduled_report", args=[report.id])
        return report

