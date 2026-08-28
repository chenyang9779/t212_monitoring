from __future__ import annotations

import csv
import io
import json
import re
from typing import Any, Iterable

from fastapi.responses import Response

EXPORT_FORMATS = {"csv", "jsonl"}
_DANGEROUS_CSV_PREFIXES = ("=", "+", "-", "@")


def flatten_record(record: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    """Flatten nested broker payloads into stable dotted columns for CSV export."""

    flattened: dict[str, Any] = {}
    for key, value in record.items():
        name = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(value, dict):
            flattened.update(flatten_record(value, name))
        elif isinstance(value, list):
            flattened[name] = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        else:
            flattened[name] = value
    return flattened


def _safe_filename_component(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip())
    return cleaned.strip("._") or "export"


def _csv_cell(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if isinstance(value, str) and value.startswith(_DANGEROUS_CSV_PREFIXES):
        # Avoid spreadsheet formula injection when a CSV is opened interactively.
        return f"'{value}"
    return value


def _ordered_fields(rows: list[dict[str, Any]], preferred: Iterable[str] | None) -> list[str]:
    fields: list[str] = []
    seen: set[str] = set()
    if preferred:
        for field in preferred:
            if field not in seen:
                fields.append(field)
                seen.add(field)
    for row in rows:
        for field in row:
            if field not in seen:
                fields.append(field)
                seen.add(field)
    return fields


def rows_to_csv(
    rows: list[dict[str, Any]],
    preferred_fields: Iterable[str] | None = None,
) -> str:
    fields = _ordered_fields(rows, preferred_fields)
    output = io.StringIO(newline="")
    if not fields:
        return ""
    writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({field: _csv_cell(row.get(field)) for field in fields})
    return output.getvalue()


def rows_to_jsonl(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return ""
    return "".join(
        json.dumps(row, ensure_ascii=False, separators=(",", ":"), default=str) + "\n"
        for row in rows
    )


def export_response(
    rows: list[dict[str, Any]],
    filename_stem: str,
    export_format: str,
    preferred_fields: Iterable[str] | None = None,
) -> Response:
    if export_format not in EXPORT_FORMATS:
        raise ValueError(f"Unsupported export format: {export_format}")

    safe_stem = _safe_filename_component(filename_stem)
    if export_format == "csv":
        content = rows_to_csv(rows, preferred_fields=preferred_fields)
        media_type = "text/csv; charset=utf-8"
        extension = "csv"
    else:
        content = rows_to_jsonl(rows)
        media_type = "application/x-ndjson; charset=utf-8"
        extension = "jsonl"

    return Response(
        content=content,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{safe_stem}.{extension}"',
            "X-Export-Rows": str(len(rows)),
        },
    )
