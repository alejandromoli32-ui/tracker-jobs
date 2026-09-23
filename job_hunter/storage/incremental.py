"""State-preserving incremental synchronization engine.

Merges freshly scraped and scored vacancies into existing Excel or CSV trackers,
preserving candidate application statuses (e.g. 'Postulado', 'Descartado'),
personal user notes, and initial detection dates across recurring hunter executions.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Union

from job_hunter.models import TrackerEntry

DATE_DETECTION_REGEX = re.compile(r"\bfecha\s*(?:de\s*)?detecci[oó]n\b", re.IGNORECASE)

STATUS_PRIORITY: Dict[str, int] = {
    "por revisar": 1,
    "nueva": 2,
    "entrevista": 3,
    "postulado": 4,
    "en proceso": 5,
    "oferta": 6,
    "descartado": 90,
}



class IncrementalTracker:
    """Synchronizes fresh job listings with existing tracker files while preserving candidate state."""

    @classmethod
    def read_existing(cls, path: Union[str, Path]) -> List[TrackerEntry]:
        """Read existing tracker entries from an Excel or CSV file."""
        file_path = Path(path).resolve()
        if not file_path.exists() or file_path.stat().st_size == 0:
            return []

        suffix = file_path.suffix.lower()
        if suffix == ".xlsx":
            from job_hunter.storage.excel import ExcelTracker
            return ExcelTracker.load(file_path)
        elif suffix in (".csv", ".txt"):
            from job_hunter.storage.csv_exporter import CSVTracker
            return CSVTracker.load(file_path)
        else:
            raise ValueError(f"Unsupported tracker file format '{suffix}'. Expected .xlsx or .csv.")

    @classmethod
    def merge(
        cls,
        existing_path: Union[str, Path],
        fresh_entries: Sequence[TrackerEntry],
        sort_entries: bool = True,
    ) -> List[TrackerEntry]:
        """Merge fresh vacancy entries into existing tracker data.

        Preserves:
            - User-assigned 'estado' (e.g. 'Postulado', 'Descartado')
            - User notes ('notas_usuario')
            - Original detection timestamp ('fecha_deteccion')
            - Existing entries not present in current fresh scrape

        Updates:
            - Score, percentage, summary, salary range, direct link, modality
            - Assigns 'Nueva' and current timestamp to brand new vacancies
        """
        path = Path(existing_path).resolve()
        existing_entries: List[TrackerEntry] = []
        if path.exists() and path.stat().st_size > 0:
            existing_entries = cls.read_existing(path)

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

        if not existing_entries:
            # First run: initialize all fresh entries as 'Nueva' and deduplicate by ID
            seen_by_id: Dict[str, TrackerEntry] = {}
            for entry in fresh_entries:
                if not entry.id:
                    continue
                est = entry.estado or "Nueva"
                dt = entry.fecha_deteccion or now_str
                notes = entry.notas_usuario or ""
                candidate = entry.model_copy(
                    update={
                        "estado": est,
                        "fecha_deteccion": dt,
                        "notas_usuario": notes,
                    }
                )
                if candidate.id in seen_by_id:
                    if (candidate.score or 0.0) > (seen_by_id[candidate.id].score or 0.0):
                        seen_by_id[candidate.id] = candidate
                else:
                    seen_by_id[candidate.id] = candidate

            initialized: List[TrackerEntry] = list(seen_by_id.values())
            if sort_entries:
                initialized.sort(
                    key=lambda e: (
                        STATUS_PRIORITY.get((e.estado or "").strip().lower(), 50),
                        -float(e.score or 0.0),
                    )
                )
            return initialized

        # Build map of existing entries
        existing_by_id: Dict[str, TrackerEntry] = {e.id: e for e in existing_entries if e.id}
        # Remember the order of existing keys
        existing_order: List[str] = [e.id for e in existing_entries if e.id]

        merged_store: Dict[str, TrackerEntry] = dict(existing_by_id)

        for fresh in fresh_entries:
            if not fresh.id:
                continue

            f_id = fresh.id
            if f_id in existing_by_id:
                # Existing job: preserve user status, notes, and original detection date
                old = existing_by_id[f_id]
                preserved_estado = old.estado if old.estado else "Nueva"
                preserved_notas = old.notas_usuario if old.notas_usuario is not None else ""
                preserved_date = old.fecha_deteccion if old.fecha_deteccion else now_str

                merged_entry = fresh.model_copy(
                    update={
                        "estado": preserved_estado,
                        "notas_usuario": preserved_notas,
                        "fecha_deteccion": preserved_date,
                    }
                )
                if f_id in merged_store and (merged_store[f_id].score or 0.0) > (merged_entry.score or 0.0):
                    pass
                else:
                    merged_store[f_id] = merged_entry
            else:
                # Brand new job
                new_entry = fresh.model_copy(
                    update={
                        "estado": "Nueva",
                        "notas_usuario": fresh.notas_usuario or "",
                        "fecha_deteccion": fresh.fecha_deteccion or now_str,
                    }
                )
                if f_id in merged_store and (merged_store[f_id].score or 0.0) > (new_entry.score or 0.0):
                    pass
                else:
                    merged_store[f_id] = new_entry
                if f_id not in existing_order:
                    existing_order.append(f_id)


        merged_list: List[TrackerEntry] = list(merged_store.values())

        if sort_entries:
            merged_list.sort(
                key=lambda e: (
                    STATUS_PRIORITY.get((e.estado or "").strip().lower(), 50),
                    -float(e.score or 0.0),
                )
            )

        return merged_list

    @classmethod
    def sync(
        cls,
        target_path: Union[str, Path],
        fresh_entries: Sequence[TrackerEntry],
        sort_entries: bool = True,
    ) -> Path:
        """Merge fresh entries with existing file and write back formatted results."""
        path = Path(target_path).resolve()
        merged = cls.merge(path, fresh_entries, sort_entries=sort_entries)

        suffix = path.suffix.lower()
        if suffix == ".xlsx":
            from job_hunter.storage.excel import ExcelTracker
            return ExcelTracker.save(merged, path, preserve_existing=False)
        elif suffix in (".csv", ".txt"):
            from job_hunter.storage.csv_exporter import CSVTracker
            return CSVTracker.save(merged, path, preserve_existing=False)
        else:
            raise ValueError(f"Unsupported tracker format '{suffix}'. Must be .xlsx or .csv.")
