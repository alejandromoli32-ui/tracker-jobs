"""RFC 4180 compliant CSV exporter with utf-8-sig encoding for Spanish text fidelity.

Exports job vacancy tracking rows with clean direct URLs (no formula strings),
guaranteeing proper rendering of accented characters (á, é, í, ó, ú, ñ) in
Microsoft Excel and cross-platform tabular data processors.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Union

from job_hunter.models import TrackerEntry
from job_hunter.storage.excel import DEFAULT_HEADERS

DATE_DETECTION_REGEX = re.compile(r"\bfecha\s*(?:de\s*)?detecci[oó]n\b", re.IGNORECASE)


class CSVTracker:
    """Manages RFC 4180 compliant CSV export with utf-8-sig BOM encoding."""

    def __init__(self, output_path: Optional[Union[str, Path]] = None) -> None:
        self.output_path = Path(output_path) if output_path else None

    @classmethod
    def save(
        cls,
        entries: Sequence[TrackerEntry],
        output_path: Optional[Union[str, Path]] = None,
        preserve_existing: bool = True,
    ) -> Path:
        """Save tracker entries to an RFC 4180 CSV file encoded with utf-8-sig.

        If preserve_existing is True and output_path exists, an incremental merge
        is performed before writing out.
        """
        if output_path is None:
            raise ValueError("output_path must be provided to CSVTracker.save()")

        path = Path(output_path).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)

        merged_entries: List[TrackerEntry] = list(entries)
        if preserve_existing and path.exists() and path.stat().st_size > 0:
            from job_hunter.storage.incremental import IncrementalTracker
            merged_entries = IncrementalTracker.merge(path, entries)

        # RFC 4180 specifies CRLF ("\r\n") line terminators and quote escaping
        with open(path, mode="w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(
                f,
                dialect="excel",
                delimiter=",",
                quoting=csv.QUOTE_MINIMAL,
                lineterminator="\r\n",
            )

            # Write header
            writer.writerow(DEFAULT_HEADERS)

            # Write data rows
            for entry in merged_entries:
                score_str = f"{entry.score:.1f}%" if entry.score is not None else "0.0%"
                clean_url = (entry.direct_url or "").strip()
                # Ensure no Excel formula string leaks into CSV
                if clean_url.startswith("="):
                    m = re.search(r'=HYPERLINK\("([^"]+)"', clean_url)
                    clean_url = m.group(1) if m else clean_url

                row = [
                    entry.id,
                    entry.fecha_deteccion or "",
                    entry.title or "",
                    entry.company or "",
                    score_str,
                    entry.modality.capitalize() if entry.modality else "Remoto",
                    clean_url,
                    entry.salary_range or "",
                    entry.explanatory_summary or "",
                    entry.estado or "Nueva",
                    entry.notas_usuario or "",
                ]
                writer.writerow(row)

        return path

    def write(self, entries: Sequence[TrackerEntry], preserve_existing: bool = True) -> Path:
        """Instance helper to save using instance output path."""
        if not self.output_path:
            raise ValueError("output_path was not set on CSVTracker instance")
        return self.save(
            entries=entries,
            output_path=self.output_path,
            preserve_existing=preserve_existing,
        )

    @classmethod
    def load(cls, file_path: Union[str, Path]) -> List[TrackerEntry]:
        """Load entries from an existing RFC 4180 CSV file."""
        path = Path(file_path).resolve()
        if not path.exists():
            return []

        entries: List[TrackerEntry] = []
        with open(path, mode="r", encoding="utf-8-sig", newline="") as f:
            reader = csv.reader(f, dialect="excel")
            header = next(reader, None)
            if not header:
                return []

            # Map columns
            col_map: Dict[str, int] = {}
            for idx, h in enumerate(header):
                h_lower = h.lower().strip()
                if re.search(r"\b(id|hash)\b", h_lower):
                    col_map["id"] = idx
                elif DATE_DETECTION_REGEX.search(h_lower):
                    col_map["fecha"] = idx
                elif "título" in h_lower or "titulo" in h_lower:
                    col_map["title"] = idx
                elif "empresa" in h_lower or "company" in h_lower:
                    col_map["company"] = idx
                elif "score" in h_lower or "puntaje" in h_lower:
                    col_map["score"] = idx
                elif "modalidad" in h_lower or "modality" in h_lower:
                    col_map["modality"] = idx
                elif "enlace" in h_lower or "url" in h_lower or "link" in h_lower:
                    col_map["url"] = idx
                elif "salario" in h_lower or "salary" in h_lower:
                    col_map["salary"] = idx
                elif "resumen" in h_lower or "afinidad" in h_lower or "summary" in h_lower:
                    col_map["summary"] = idx
                elif "estado" in h_lower or "status" in h_lower:
                    col_map["estado"] = idx
                elif "nota" in h_lower or "note" in h_lower:
                    col_map["notas"] = idx
                elif "fecha" in h_lower and "postula" not in h_lower and "fecha" not in col_map:
                    col_map["fecha"] = idx

            for row in reader:
                if not row or not any(row):
                    continue

                def _get(field_key: str, default: str = "") -> str:
                    idx = col_map.get(field_key)
                    if idx is not None and idx < len(row):
                        return row[idx].strip()
                    return default

                v_id = _get("id")
                if not v_id:
                    continue

                # Parse score
                raw_score = _get("score", "0")
                cleaned_sc = re.sub(r"[^\d.]", "", raw_score)
                try:
                    score_val = float(cleaned_sc)
                    if 0.0 < score_val <= 1.0:
                        score_val = round(score_val * 100.0, 1)
                except ValueError:
                    score_val = 0.0

                score_val = max(0.0, min(100.0, score_val))


                raw_url = _get("url")
                if raw_url.startswith("="):
                    m = re.search(r'=HYPERLINK\("([^"]+)"', raw_url)
                    raw_url = m.group(1) if m else raw_url

                entry = TrackerEntry(
                    id=v_id,
                    title=_get("title", "Vacante"),
                    company=_get("company", "Confidencial"),
                    direct_url=raw_url,
                    full_description=_get("summary", ""),
                    location="Colombia",
                    modality=_get("modality", "remoto").lower(),
                    salary_range=_get("salary") or None,
                    source_portal="csv",
                    score=score_val,
                    explanatory_summary=_get("summary", ""),
                    estado=_get("estado", "Nueva") or "Nueva",
                    fecha_deteccion=_get("fecha", ""),
                    notas_usuario=_get("notas", ""),
                )
                entries.append(entry)

        return entries
