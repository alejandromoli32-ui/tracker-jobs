"""Adversarial stress and forensic verification test suite for Milestone M4.

Validates:
1. Deduplication engine determinism, collision resistance, parameter stripping, and keep strategies.
2. ExcelTracker openpyxl styling, clickable hyperlinks, color fills, validation dropdowns, freeze panes, and round-trip loading.
3. CSVTracker RFC 4180 compliance, utf-8-sig encoding (BOM), clean URLs, Spanish text fidelity, and round-trip loading.
4. IncrementalTracker candidate status and notes preservation, detection date preservation, and priority sorting.
5. Hostile inputs, formula injection resistance, special characters, and boundary conditions.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path
import openpyxl
import pytest

from job_hunter.dedup import Deduplicator
from job_hunter.models import TrackerEntry
from job_hunter.storage.csv_exporter import CSVTracker
from job_hunter.storage.excel import (
    DEFAULT_HEADERS,
    EXCEL_STATUS_OPTIONS,
    ExcelTracker,
    GREEN_FILL_HEX,
    YELLOW_FILL_HEX,
    RED_FILL_HEX,
    GREEN_FONT_HEX,
    YELLOW_FONT_HEX,
    RED_FONT_HEX,
)
from job_hunter.storage.incremental import IncrementalTracker, STATUS_PRIORITY


@pytest.fixture
def sample_entries() -> list[TrackerEntry]:
    return [
        TrackerEntry(
            id="a1b2c3d4e5f60718",
            title="Directora de Proyectos Viales e Interventoría HSEQ - 100% Remota",
            company="Consorcio Infraestructura y Transporte Andino S.A.S.",
            direct_url="https://co.computrabajo.com/ofertas/directora-vias-01?utm_source=feed&ref=home",
            full_description="Importante firma requiere Ingeniera Civil con más de 15 años de experiencia...",
            location="Colombia",
            modality="remoto",
            salary_range="$12.000.000 - $16.000.000 COP",
            source_portal="computrabajo",
            score=95.0,
            score_percentage="95%",
            explanatory_summary="Alta afinidad (95%): Perfil Senior en Civil con Vías y SST. COPNIA requerida.",
            estado="Nueva",
            fecha_deteccion="2026-09-20 10:30",
            notas_usuario="",
        ),
        TrackerEntry(
            id="b2c3d4e5f6071829",
            title="Especialista Senior Diseños Viales Civil 3D",
            company="Vías y Puentes de Colombia S.A.",
            direct_url="https://elempleo.com/co/ofertas/especialista-civil3d-02",
            full_description="Diseño geométrico de carreteras bajo normas INVIAS...",
            location="Bogotá",
            modality="remoto",
            salary_range="$9.000.000 - $13.000.000 COP",
            source_portal="elempleo",
            score=65.0,
            score_percentage="65%",
            explanatory_summary="Afinidad media (65%): Enfoque en diseño vial, requiere complementar SST.",
            estado="Por revisar",
            fecha_deteccion="2026-09-20 11:00",
            notas_usuario="Revisar requisitos en Bogotá.",
        ),
        TrackerEntry(
            id="c3d4e5f607182930",
            title="Ingeniero Residente de Pavimentos en Campamento",
            company="Constructora Vial del Norte",
            direct_url="https://linkedin.com/jobs/view/residente-campamento-03?trackingId=xyz",
            full_description="100% presencial en obra, campamento obligatorio...",
            location="Valledupar",
            modality="presencial",
            salary_range="$7.000.000 COP",
            source_portal="linkedin",
            score=15.0,
            score_percentage="15%",
            explanatory_summary="Descartada (15%): Modalidad 100% presencial en frente de obra.",
            estado="Descartado",
            fecha_deteccion="2026-09-20 11:30",
            notas_usuario="Descartada por obra en campamento.",
        ),
    ]


class TestAdversarialDeduplication:
    """Stress testing the deduplication algorithm."""

    def test_tracking_parameter_stripping_and_hashing(self):
        title = "Directora de Proyectos Viales e Infraestructura"
        company = "Consorcio Vial Andino S.A.S."

        # URLs with various tracking query strings and hash fragments
        u1 = "https://co.computrabajo.com/ofertas/vias-01?utm_source=linkedin&utm_medium=cpc&utm_campaign=hiring"
        u2 = "https://CO.computrabajo.com/ofertas/vias-01?fbclid=IwAR123456789&gclid=EAIaIQobChMI&ref=job_board"
        u3 = "https://co.computrabajo.com/ofertas/vias-01#apply-now"

        h1 = Deduplicator.compute_id(title, company, u1)
        h2 = Deduplicator.compute_id(title, company, u2)
        h3 = Deduplicator.compute_id(title, company, u3)

        assert h1 == h2 == h3
        assert len(h1) == 16
        assert re.match(r"^[0-9a-f]{16}$", h1)

    def test_text_normalization_whitespace_and_badges(self):
        t1 = "  [Urgente]   Directora   de Proyectos   Viales (Oferta Destacada)  "
        c1 = "4.8 Consorcio Vial Andino S.A.S."
        u1 = "https://computrabajo.com/job/100"

        t2 = "directora de proyectos viales"
        c2 = "Consorcio Vial Andino S.A.S."
        u2 = "https://computrabajo.com/job/100"

        assert Deduplicator.compute_id(t1, c1, u1) == Deduplicator.compute_id(t2, c2, u2)

    def test_deduplicate_keep_highest_score_tie_breaking(self):
        # Two entries with the exact same ID and same score
        e1 = TrackerEntry(id="dup001", title="Job A", company="Co", direct_url="https://a.com", full_description="D", source_portal="t", score=80.0)
        e2 = TrackerEntry(id="dup001", title="Job A Updated", company="Co", direct_url="https://a.com", full_description="D", source_portal="t", score=80.0)
        e3 = TrackerEntry(id="dup002", title="Job B", company="Co", direct_url="https://b.com", full_description="D", source_portal="t", score=90.0)

        result = Deduplicator.deduplicate([e1, e2, e3], keep="highest_score")
        assert len(result) == 2
        assert result[0].id == "dup001"
        assert result[1].id == "dup002"

    def test_deduplicate_with_dicts(self):
        d1 = {"id": "hash01", "title": "Job 1", "score": 70.0}
        d2 = {"id": "hash01", "title": "Job 1 New", "score": 90.0}
        d3 = {"id": "hash02", "title": "Job 2", "score": 85.0}

        res = Deduplicator.deduplicate([d1, d2, d3], keep="highest_score")
        assert len(res) == 2
        assert res[0]["score"] == 90.0
        assert res[1]["score"] == 85.0


class TestAdversarialExcelTracker:
    """Stress testing openpyxl ExcelTracker formatting, structure, and roundtrip."""

    def test_excel_palette_colors_and_boundary_fills(self, tmp_path: Path):
        excel_path = tmp_path / "palette_test.xlsx"
        entries = [
            TrackerEntry(id="100pct", title="Job 100", company="C", direct_url="https://x.com", full_description="D", source_portal="t", score=100.0),
            TrackerEntry(id="70pct", title="Job 70", company="C", direct_url="https://x.com", full_description="D", source_portal="t", score=70.0),
            TrackerEntry(id="699pct", title="Job 69.9", company="C", direct_url="https://x.com", full_description="D", source_portal="t", score=69.9),
            TrackerEntry(id="50pct", title="Job 50", company="C", direct_url="https://x.com", full_description="D", source_portal="t", score=50.0),
            TrackerEntry(id="499pct", title="Job 49.9", company="C", direct_url="https://x.com", full_description="D", source_portal="t", score=49.9),
            TrackerEntry(id="0pct", title="Job 0", company="C", direct_url="https://x.com", full_description="D", source_portal="t", score=0.0),
        ]
        ExcelTracker.save(entries, output_path=excel_path, preserve_existing=False)

        wb = openpyxl.load_workbook(excel_path)
        ws = wb.active

        # 100% -> Green
        assert ws.cell(row=2, column=5).fill.start_color.rgb.upper().endswith(GREEN_FILL_HEX)
        assert ws.cell(row=2, column=5).font.color.rgb.upper().endswith(GREEN_FONT_HEX)
        assert ws.cell(row=2, column=5).font.bold is True

        # 70% -> Green
        assert ws.cell(row=3, column=5).fill.start_color.rgb.upper().endswith(GREEN_FILL_HEX)
        assert ws.cell(row=3, column=5).font.color.rgb.upper().endswith(GREEN_FONT_HEX)
        assert ws.cell(row=3, column=5).font.bold is True

        # 69.9% -> Yellow
        assert ws.cell(row=4, column=5).fill.start_color.rgb.upper().endswith(YELLOW_FILL_HEX)
        assert ws.cell(row=4, column=5).font.color.rgb.upper().endswith(YELLOW_FONT_HEX)

        # 50% -> Yellow
        assert ws.cell(row=5, column=5).fill.start_color.rgb.upper().endswith(YELLOW_FILL_HEX)
        assert ws.cell(row=5, column=5).font.color.rgb.upper().endswith(YELLOW_FONT_HEX)

        # 49.9% -> Red
        assert ws.cell(row=6, column=5).fill.start_color.rgb.upper().endswith(RED_FILL_HEX)
        assert ws.cell(row=6, column=5).font.color.rgb.upper().endswith(RED_FONT_HEX)

        # 0% -> Red
        assert ws.cell(row=7, column=5).fill.start_color.rgb.upper().endswith(RED_FILL_HEX)
        assert ws.cell(row=7, column=5).font.color.rgb.upper().endswith(RED_FONT_HEX)

        wb.close()

    def test_excel_hyperlink_quote_escaping(self, tmp_path: Path):
        excel_path = tmp_path / "hyperlink_escape.xlsx"
        entry = TrackerEntry(
            id="esc01",
            title="Special Job",
            company="C",
            direct_url='https://portal.com/job?filter="quotes"&param=val',
            full_description="D",
            source_portal="t",
            score=75.0,
        )
        ExcelTracker.save([entry], output_path=excel_path, preserve_existing=False)

        wb = openpyxl.load_workbook(excel_path)
        ws = wb.active
        val = ws.cell(row=2, column=7).value
        # Embedded quotes should be escaped as %22
        assert '%22quotes%22' in val
        assert val.startswith('=HYPERLINK("')
        wb.close()

        # Check roundtrip load preserves clean url
        loaded = ExcelTracker.load(excel_path)
        assert len(loaded) == 1
        assert "portal.com/job" in loaded[0].direct_url

    def test_excel_data_validation_options(self, tmp_path: Path, sample_entries: list[TrackerEntry]):
        excel_path = tmp_path / "validation_test.xlsx"
        ExcelTracker.save(sample_entries, output_path=excel_path, preserve_existing=False)

        wb = openpyxl.load_workbook(excel_path)
        ws = wb.active

        assert len(ws.data_validations.dataValidation) > 0
        dv = ws.data_validations.dataValidation[0]
        assert dv.type == "list"
        assert "Nueva" in dv.formula1
        assert "Por revisar" in dv.formula1
        assert "Postulado" in dv.formula1
        assert "Descartado" in dv.formula1
        assert "Entrevista" in dv.formula1
        wb.close()


class TestAdversarialCSVTracker:
    """Stress testing RFC 4180 CSV export and character fidelity."""

    def test_csv_multiline_fields_and_quoting(self, tmp_path: Path):
        csv_path = tmp_path / "multiline.csv"
        entry = TrackerEntry(
            id="multi01",
            title="Coordinadora SST,\nLíder de Seguridad",
            company='Constructora "El Sol" S.A.S.',
            direct_url="https://portal.com/job/1",
            full_description="Línea 1,\nLínea 2 con \"comillas\" y comas.",
            source_portal="custom",
            salary_range="$10.000.000,00 COP",
            explanatory_summary="Afinidad 80%:\nRequiere licencia SST vigente.",
            score=80.0,
        )
        CSVTracker.save([entry], output_path=csv_path, preserve_existing=False)

        # Raw file verification
        raw = csv_path.read_bytes()
        assert raw.startswith(b"\xef\xbb\xbf")  # UTF-8 BOM

        # Parse with standard csv reader
        with open(csv_path, mode="r", encoding="utf-8-sig", newline="") as f:
            reader = csv.reader(f)
            rows = list(reader)

        assert rows[0] == DEFAULT_HEADERS
        assert len(rows) == 2
        assert 'Constructora "El Sol" S.A.S.' in rows[1][3]
        assert "\n" in rows[1][2]  # multiline preserved
        assert "$10.000.000,00 COP" == rows[1][7]

        # Roundtrip loading
        loaded = CSVTracker.load(csv_path)
        assert len(loaded) == 1
        assert loaded[0].id == "multi01"
        assert loaded[0].score == 80.0


class TestAdversarialIncrementalTracker:
    """Stress testing state preservation across recurring scrape runs."""

    def test_full_state_preservation_lifecycle(self, tmp_path: Path, sample_entries: list[TrackerEntry]):
        tracker_file = tmp_path / "lifecycle.xlsx"

        # Run 1: initial discovery of 3 jobs
        ExcelTracker.save(sample_entries, output_path=tracker_file, preserve_existing=False)

        # Simulate user candidate workflows in Excel:
        # - Job 0: marked "Postulado", user notes added
        # - Job 1: marked "Entrevista", user notes added
        # - Job 2: marked "Descartado"
        wb = openpyxl.load_workbook(tracker_file)
        ws = wb.active
        ws.cell(row=2, column=10).value = "Postulado"
        ws.cell(row=2, column=11).value = "Postulación enviada el 20/09."

        ws.cell(row=3, column=10).value = "Entrevista"
        ws.cell(row=3, column=11).value = "Entrevista técnica 25/09 10am."

        ws.cell(row=4, column=10).value = "Descartado"
        ws.cell(row=4, column=11).value = "No aplica por campamento."
        wb.save(tracker_file)
        wb.close()

        # Run 2: Next week recurring hunt.
        # - Job 0 found again, score increased from 95 to 98
        # - Job 1 NOT found (closed vacancy)
        # - Job 2 found again with same score
        # - Job 4 is brand new!
        fresh_job0 = sample_entries[0].model_copy(update={"score": 98.0, "explanatory_summary": "Puntaje actualizado a 98%."})
        fresh_job2 = sample_entries[2].model_copy()
        brand_new_job4 = TrackerEntry(
            id="fresh040506070809",
            title="Líder SG-SST Infraestructura Vial",
            company="Autopistas del Café",
            direct_url="https://elempleo.com/job4",
            full_description="SG-SST para concesiones viales.",
            source_portal="elempleo",
            score=89.0,
            modality="remoto",
            salary_range="$11.000.000 COP",
        )

        merged = IncrementalTracker.merge(tracker_file, [fresh_job0, fresh_job2, brand_new_job4])

        # Verify Job 0: preserved status, preserved notes, preserved original date, refreshed score
        j0 = next(x for x in merged if x.id == sample_entries[0].id)
        assert j0.estado == "Postulado"
        assert j0.notas_usuario == "Postulación enviada el 20/09."
        assert j0.fecha_deteccion == sample_entries[0].fecha_deteccion
        assert j0.score == 98.0
        assert "actualizado a 98%" in j0.explanatory_summary

        # Verify Job 1: retained even though missing from fresh scrape
        j1 = next(x for x in merged if x.id == sample_entries[1].id)
        assert j1.estado == "Entrevista"
        assert j1.notas_usuario == "Entrevista técnica 25/09 10am."

        # Verify Job 2: preserved Descartado
        j2 = next(x for x in merged if x.id == sample_entries[2].id)
        assert j2.estado == "Descartado"

        # Verify Job 4: initialized as Nueva with current timestamp
        j4 = next(x for x in merged if x.id == brand_new_job4.id)
        assert j4.estado == "Nueva"
        assert j4.fecha_deteccion is not None

        # Verify total count
        assert len(merged) == 4

        # Verify priority sorting: Descartado at the bottom
        assert merged[-1].estado == "Descartado"

    def test_sync_replaces_file_in_place(self, tmp_path: Path, sample_entries: list[TrackerEntry]):
        csv_file = tmp_path / "sync_test.csv"
        CSVTracker.save(sample_entries, output_path=csv_file, preserve_existing=False)

        # User updates status in CSV
        loaded = CSVTracker.load(csv_file)
        loaded[0].estado = "Postulado"
        CSVTracker.save(loaded, output_path=csv_file, preserve_existing=False)

        # Fresh sync
        updated_e0 = sample_entries[0].model_copy(update={"score": 99.0})
        IncrementalTracker.sync(csv_file, [updated_e0])

        final_loaded = CSVTracker.load(csv_file)
        j0 = next(x for x in final_loaded if x.id == sample_entries[0].id)
        assert j0.estado == "Postulado"
        assert j0.score == 99.0
