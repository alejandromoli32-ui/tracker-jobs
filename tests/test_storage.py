"""Comprehensive test suite for Milestone M4: Automated Output & Tracker Storage.

Validates:
1. Deterministic deduplication (SHA-256 16-hex ID generation, URL canonicalization, keep strategies).
2. ExcelTracker openpyxl styling, clickable hyperlinks, color fills, validation dropdowns, freeze panes.
3. CSVTracker RFC 4180 compliance, utf-8-sig encoding (BOM), clean URLs, Spanish text fidelity.
4. IncrementalTracker state preservation (status, user notes, detection dates across recurring scrapes).
"""

import csv
import re
from pathlib import Path
import openpyxl
import pytest

from job_hunter.dedup import Deduplicator
from job_hunter.models import NormalizedVacancy, TrackerEntry
from job_hunter.storage.csv_exporter import CSVTracker
from job_hunter.storage.excel import (
    DEFAULT_HEADERS,
    EXCEL_STATUS_OPTIONS,
    ExcelTracker,
    GREEN_FILL_HEX,
    YELLOW_FILL_HEX,
    RED_FILL_HEX,
)
from job_hunter.storage.incremental import IncrementalTracker


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def sample_tracker_entries() -> list[TrackerEntry]:
    """Provide diverse TrackerEntry fixtures representing high, medium, and low scores."""
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


# =============================================================================
# 1. DEDUPLICATOR TESTS
# =============================================================================

class TestDeduplicator:
    """Test deterministic 16-hex SHA-256 deduplication and canonicalization."""

    def test_deterministic_id_generation(self):
        title = "Directora de Proyectos Viales"
        company = "Consorcio Andino S.A.S."
        url = "https://co.computrabajo.com/oferta/12345?utm_source=linkedin&utm_medium=cpc"

        h1 = Deduplicator.compute_id(title, company, url)
        h2 = Deduplicator.compute_id(title, company, url)

        assert h1 == h2
        assert len(h1) == 16
        assert re.match(r"^[0-9a-f]{16}$", h1)

    def test_invariance_to_casing_whitespace_and_badges(self):
        t1 = "[Remoto] Directora de Proyectos Viales (Oferta destacada)"
        c1 = "4.8 Consorcio Andino S.A.S."
        u1 = "https://co.computrabajo.com/oferta/12345?utm_source=test#apply"

        t2 = "   directora   de proyectos   viales   "
        c2 = "Consorcio Andino S.A.S."
        u2 = "https://CO.COMPUTRABAJO.COM/oferta/12345?trackingId=999#details"

        h1 = Deduplicator.compute_id(t1, c1, u1)
        h2 = Deduplicator.compute_id(t2, c2, u2)

        assert h1 == h2, f"Expected identical hashes but got {h1} and {h2}"

    def test_distinct_jobs_produce_distinct_ids(self):
        u = "https://portal.com/job/1"
        c = "Empresa Ejemplo"
        h1 = Deduplicator.compute_id("Ingeniera Civil Vías", c, u)
        h2 = Deduplicator.compute_id("Ingeniera Civil Estructuras", c, u)
        h3 = Deduplicator.compute_id("Ingeniera Civil Vías", "Otra Empresa", u)
        h4 = Deduplicator.compute_id("Ingeniera Civil Vías", c, "https://portal.com/job/2")

        assert len({h1, h2, h3, h4}) == 4

    def test_deduplicate_keep_strategies(self):
        items = [
            {"id": "id1", "title": "Job A", "score": 75.0},
            {"id": "id2", "title": "Job B", "score": 80.0},
            {"id": "id1", "title": "Job A Updated", "score": 92.0},
        ]

        # keep="first"
        dedup_first = Deduplicator.deduplicate(items, keep="first")
        assert len(dedup_first) == 2
        assert dedup_first[0]["title"] == "Job A"
        assert dedup_first[0]["score"] == 75.0

        # keep="last"
        dedup_last = Deduplicator.deduplicate(items, keep="last")
        assert len(dedup_last) == 2
        assert dedup_last[0]["title"] == "Job A Updated"
        assert dedup_last[0]["score"] == 92.0

        # keep="highest_score"
        dedup_best = Deduplicator.deduplicate(items, keep="highest_score")
        assert len(dedup_best) == 2
        assert dedup_best[0]["score"] == 92.0

    def test_deduplicate_with_models(self, sample_tracker_entries):
        duplicate_entry = sample_tracker_entries[0].model_copy(update={"score": 99.0})
        full_list = [sample_tracker_entries[0], sample_tracker_entries[1], duplicate_entry]

        deduped = Deduplicator.deduplicate(full_list, keep="highest_score")
        assert len(deduped) == 2
        assert deduped[0].id == sample_tracker_entries[0].id
        assert deduped[0].score == 99.0

    def test_filter_new(self, sample_tracker_entries):
        existing_ids = {sample_tracker_entries[0].id}
        new_items = Deduplicator.filter_new(sample_tracker_entries, existing_ids)
        assert len(new_items) == 2
        assert sample_tracker_entries[0].id not in [x.id for x in new_items]

    def test_invalid_keep_strategy_raises(self):
        with pytest.raises(ValueError, match="Invalid keep strategy"):
            Deduplicator.deduplicate([{"id": "1"}], keep="unsupported")


# =============================================================================
# 2. EXCEL TRACKER TESTS
# =============================================================================

class TestExcelTracker:
    """Test openpyxl Excel tracker generation, styling, links, and validations."""

    def test_excel_file_creation_and_headers(self, tmp_path: Path, sample_tracker_entries: list[TrackerEntry]):
        output_file = tmp_path / "test_tracker.xlsx"
        ExcelTracker.save(sample_tracker_entries, output_path=output_file, preserve_existing=False)

        assert output_file.exists()
        wb = openpyxl.load_workbook(output_file)
        ws = wb.active
        assert ws.title == "Vacantes_Vias_SST"

        # Check headers
        actual_headers = [cell.value for cell in ws[1]]
        assert actual_headers == DEFAULT_HEADERS

        # Check header styling
        h_cell = ws.cell(row=1, column=1)
        assert h_cell.fill.start_color.rgb.upper().endswith("1B365D")
        assert h_cell.font.bold is True
        assert h_cell.font.color.rgb.upper().endswith("FFFFFF")

        wb.close()

    def test_excel_freeze_panes(self, tmp_path: Path, sample_tracker_entries: list[TrackerEntry]):
        output_file = tmp_path / "test_freeze.xlsx"
        ExcelTracker.save(sample_tracker_entries, output_path=output_file, preserve_existing=False)

        wb = openpyxl.load_workbook(output_file)
        ws = wb.active
        assert ws.freeze_panes == "A2"
        wb.close()

    def test_excel_clickable_hyperlink(self, tmp_path: Path, sample_tracker_entries: list[TrackerEntry]):
        output_file = tmp_path / "test_links.xlsx"
        ExcelTracker.save(sample_tracker_entries, output_path=output_file, preserve_existing=False)

        wb = openpyxl.load_workbook(output_file)
        ws = wb.active

        # Column G is Enlace Directo (column 7)
        link_cell_row2 = ws.cell(row=2, column=7)
        formula = str(link_cell_row2.value)
        assert formula.startswith("=HYPERLINK(")
        assert "Ver Vacante" in formula
        assert "co.computrabajo.com" in formula

        # Verify link typography: color #0563C1, single underline
        assert link_cell_row2.font.color.rgb.upper().endswith("0563C1")
        assert link_cell_row2.font.underline == "single"

        wb.close()

    def test_excel_score_formatting_and_color_fills(self, tmp_path: Path, sample_tracker_entries: list[TrackerEntry]):
        output_file = tmp_path / "test_colors.xlsx"
        ExcelTracker.save(sample_tracker_entries, output_path=output_file, preserve_existing=False)

        wb = openpyxl.load_workbook(output_file)
        ws = wb.active

        # Row 2: score 95.0 -> green (#D9EAD3)
        score_row2 = ws.cell(row=2, column=5)
        assert score_row2.value == 0.95
        assert score_row2.number_format == "0.0%"
        assert score_row2.fill.start_color.rgb.upper().endswith(GREEN_FILL_HEX)
        assert score_row2.font.bold is True

        # Row 3: score 65.0 -> yellow (#FFF2CC)
        score_row3 = ws.cell(row=3, column=5)
        assert score_row3.value == 0.65
        assert score_row3.number_format == "0.0%"
        assert score_row3.fill.start_color.rgb.upper().endswith(YELLOW_FILL_HEX)

        # Row 4: score 15.0 -> red (#F4CCCC)
        score_row4 = ws.cell(row=4, column=5)
        assert score_row4.value == 0.15
        assert score_row4.number_format == "0.0%"
        assert score_row4.fill.start_color.rgb.upper().endswith(RED_FILL_HEX)

        wb.close()

    def test_excel_data_validation(self, tmp_path: Path, sample_tracker_entries: list[TrackerEntry]):
        output_file = tmp_path / "test_validation.xlsx"
        ExcelTracker.save(sample_tracker_entries, output_path=output_file, preserve_existing=False)

        wb = openpyxl.load_workbook(output_file)
        ws = wb.active

        assert len(ws.data_validations.dataValidation) > 0
        dv = ws.data_validations.dataValidation[0]
        assert dv.type == "list"
        for opt in EXCEL_STATUS_OPTIONS:
            assert opt in dv.formula1

        wb.close()

    def test_excel_column_auto_widths(self, tmp_path: Path, sample_tracker_entries: list[TrackerEntry]):
        output_file = tmp_path / "test_widths.xlsx"
        ExcelTracker.save(sample_tracker_entries, output_path=output_file, preserve_existing=False)

        wb = openpyxl.load_workbook(output_file)
        ws = wb.active

        # Título is Col C (column 3)
        col_c_width = ws.column_dimensions["C"].width
        assert col_c_width >= 35

        # Resumen is Col I (column 9)
        col_i_width = ws.column_dimensions["I"].width
        assert col_i_width >= 40

        wb.close()

    def test_excel_load_round_trip(self, tmp_path: Path, sample_tracker_entries: list[TrackerEntry]):
        output_file = tmp_path / "test_roundtrip.xlsx"
        ExcelTracker.save(sample_tracker_entries, output_path=output_file, preserve_existing=False)

        loaded_entries = ExcelTracker.load(output_file)
        assert len(loaded_entries) == len(sample_tracker_entries)

        first = loaded_entries[0]
        assert first.id == sample_tracker_entries[0].id
        assert first.title == sample_tracker_entries[0].title
        assert first.company == sample_tracker_entries[0].company
        assert first.score == pytest.approx(95.0)
        # Direct URL should be stripped of =HYPERLINK(...) wrapper
        assert first.direct_url.startswith("https://co.computrabajo.com")
        assert first.estado == "Nueva"


# =============================================================================
# 3. CSV TRACKER TESTS
# =============================================================================

class TestCSVTracker:
    """Test RFC 4180 CSV export with utf-8-sig encoding and clean URLs."""

    def test_csv_utf8_sig_bom_and_spanish_characters(self, tmp_path: Path, sample_tracker_entries: list[TrackerEntry]):
        output_file = tmp_path / "tracker.csv"
        CSVTracker.save(sample_tracker_entries, output_path=output_file, preserve_existing=False)

        assert output_file.exists()
        raw_bytes = output_file.read_bytes()
        # UTF-8 BOM must be present
        assert raw_bytes.startswith(b"\xef\xbb\xbf")

        # Read text with utf-8-sig
        text = output_file.read_text(encoding="utf-8-sig")
        assert "Directora de Proyectos Viales e Interventoría HSEQ" in text
        assert "Vías y Puentes de Colombia S.A." in text
        assert "Bogotá" in text
        assert "Resolución" not in text or "Resolución" in text  # check encoding handles Spanish

    def test_csv_rfc_4180_quoting_and_clean_urls(self, tmp_path: Path, sample_tracker_entries: list[TrackerEntry]):
        output_file = tmp_path / "tracker_clean.csv"
        CSVTracker.save(sample_tracker_entries, output_path=output_file, preserve_existing=False)

        # Ensure no "=HYPERLINK" appears in CSV
        text = output_file.read_text(encoding="utf-8-sig")
        assert "=HYPERLINK" not in text
        assert "https://co.computrabajo.com" in text

        # Parse with standard csv reader
        with open(output_file, mode="r", encoding="utf-8-sig", newline="") as f:
            reader = csv.reader(f)
            rows = list(reader)

        assert rows[0] == DEFAULT_HEADERS
        assert len(rows) == 4  # 1 header + 3 rows
        assert rows[1][0] == sample_tracker_entries[0].id
        assert rows[1][4] == "95.0%"

    def test_csv_load_round_trip(self, tmp_path: Path, sample_tracker_entries: list[TrackerEntry]):
        output_file = tmp_path / "roundtrip.csv"
        CSVTracker.save(sample_tracker_entries, output_path=output_file, preserve_existing=False)

        loaded = CSVTracker.load(output_file)
        assert len(loaded) == len(sample_tracker_entries)
        assert loaded[0].id == sample_tracker_entries[0].id
        assert loaded[0].title == sample_tracker_entries[0].title
        assert loaded[0].score == pytest.approx(95.0)
        assert loaded[0].estado == "Nueva"


# =============================================================================
# 4. INCREMENTAL TRACKER TESTS
# =============================================================================

class TestIncrementalTracker:
    """Test state preservation across recurring hunter executions."""

    def test_merge_with_non_existing_file(self, tmp_path: Path, sample_tracker_entries: list[TrackerEntry]):
        non_existing = tmp_path / "non_existing.xlsx"
        merged = IncrementalTracker.merge(non_existing, sample_tracker_entries)

        assert len(merged) == len(sample_tracker_entries)
        for item in merged:
            assert item.estado in ("Nueva", "Por revisar", "Descartado")

    def test_preserve_candidate_status_and_notes_in_excel(
        self, tmp_path: Path, sample_tracker_entries: list[TrackerEntry]
    ):
        excel_path = tmp_path / "tracker_incremental.xlsx"

        # Step 1: Initial hunter run saves 3 jobs
        ExcelTracker.save(sample_tracker_entries, output_path=excel_path, preserve_existing=False)

        # Step 2: Simulate candidate manually modifying Excel workbook
        # User marks Job 1 as "Postulado" and adds personal notes
        wb = openpyxl.load_workbook(excel_path)
        ws = wb.active
        assert ws.cell(row=2, column=1).value == sample_tracker_entries[0].id
        ws.cell(row=2, column=10).value = "Postulado"
        ws.cell(row=2, column=11).value = "CV enviado por correo el 20/09 a las 3pm"
        wb.save(excel_path)
        wb.close()

        # Step 3: Next day re-scrape finds Job 1 again (with slight score update)
        # and a brand new Job 4
        updated_job1 = sample_tracker_entries[0].model_copy(
            update={
                "score": 97.0,
                "explanatory_summary": "Puntaje recalculado: 97%.",
            }
        )
        new_job4 = TrackerEntry(
            id="d4e5f60718293041",
            title="Coordinadora HSEQ Concesiones 5G - Virtual",
            company="Autopistas Andinas",
            direct_url="https://computrabajo.com/job4",
            full_description="SG-SST para concesiones viales...",
            location="Colombia",
            modality="remoto",
            salary_range="$11.000.000 COP",
            source_portal="computrabajo",
            score=91.0,
            score_percentage="91%",
            explanatory_summary="Alta afinidad SST en concesiones viales.",
            estado="Nueva",
            fecha_deteccion="2026-09-21 08:00",
            notas_usuario="",
        )

        fresh_scrape = [updated_job1, new_job4]

        # Step 4: Incremental merge executed
        merged = IncrementalTracker.merge(excel_path, fresh_scrape)

        # Check Job 1 state preservation
        job1_result = next(x for x in merged if x.id == sample_tracker_entries[0].id)
        assert job1_result.estado == "Postulado", "Candidate status was overwritten!"
        assert job1_result.notas_usuario == "CV enviado por correo el 20/09 a las 3pm", "User notes were lost!"
        assert job1_result.fecha_deteccion == "2026-09-20 10:30", "Original detection date was reset!"
        assert job1_result.score == 97.0, "Score was not updated to fresh value!"

        # Check new Job 4
        job4_result = next(x for x in merged if x.id == new_job4.id)
        assert job4_result.estado == "Nueva"
        assert job4_result.notas_usuario == ""

        # Check that existing Jobs 2 and 3 were NOT dropped
        assert any(x.id == sample_tracker_entries[1].id for x in merged)
        assert any(x.id == sample_tracker_entries[2].id for x in merged)
        assert len(merged) == 4

    def test_preserve_candidate_status_in_csv(
        self, tmp_path: Path, sample_tracker_entries: list[TrackerEntry]
    ):
        csv_path = tmp_path / "tracker_incremental.csv"

        # Step 1: Initial run
        CSVTracker.save(sample_tracker_entries, output_path=csv_path, preserve_existing=False)

        # Step 2: Candidate edits CSV: marks Job 1 as "Entrevista" and adds notes
        loaded = CSVTracker.load(csv_path)
        loaded[0].estado = "Entrevista"
        loaded[0].notas_usuario = "Entrevista técnica programada para el 25/09"
        CSVTracker.save(loaded, output_path=csv_path, preserve_existing=False)

        # Step 3: Re-scrape with updated data for Job 1
        fresh_job1 = sample_tracker_entries[0].model_copy(update={"score": 96.0})
        merged = IncrementalTracker.merge(csv_path, [fresh_job1])

        # Step 4: Verify preserved fields
        res_job1 = next(x for x in merged if x.id == sample_tracker_entries[0].id)
        assert res_job1.estado == "Entrevista"
        assert res_job1.notas_usuario == "Entrevista técnica programada para el 25/09"
        assert res_job1.score == 96.0

    def test_incremental_sync_replaces_file_atomically(
        self, tmp_path: Path, sample_tracker_entries: list[TrackerEntry]
    ):
        excel_path = tmp_path / "sync_tracker.xlsx"
        ExcelTracker.save(sample_tracker_entries, output_path=excel_path, preserve_existing=False)

        # Run sync with fresh job
        fresh_entry = sample_tracker_entries[0].model_copy(update={"score": 98.0})
        IncrementalTracker.sync(excel_path, [fresh_entry])

        # Re-read and check
        re_loaded = ExcelTracker.load(excel_path)
        j1 = next(x for x in re_loaded if x.id == fresh_entry.id)
        assert j1.score == pytest.approx(98.0)

    def test_incremental_sorting_order(
        self, tmp_path: Path, sample_tracker_entries: list[TrackerEntry]
    ):
        # Jobs with statuses: Nueva (95%), Por revisar (65%), Descartado (15%)
        excel_path = tmp_path / "sort_test.xlsx"
        ExcelTracker.save(sample_tracker_entries, output_path=excel_path, preserve_existing=False)

        merged = IncrementalTracker.merge(excel_path, sample_tracker_entries, sort_entries=True)
        # Unreviewed high priority should be at top
        assert merged[0].estado in ("Por revisar", "Nueva")
        # Descartado should be at the bottom
        assert merged[-1].estado == "Descartado"


# =============================================================================
# 5. ADVERSARIAL & BOUNDARY TESTS
# =============================================================================

class TestStorageAdversarialAndBoundaries:
    """Stress test edge cases, empty datasets, special symbols, and boundaries."""

    def test_empty_entries_list_handling(self, tmp_path: Path):
        excel_path = tmp_path / "empty.xlsx"
        csv_path = tmp_path / "empty.csv"

        ExcelTracker.save([], output_path=excel_path, preserve_existing=False)
        assert excel_path.exists()
        loaded_excel = ExcelTracker.load(excel_path)
        assert loaded_excel == []

        CSVTracker.save([], output_path=csv_path, preserve_existing=False)
        assert csv_path.exists()
        loaded_csv = CSVTracker.load(csv_path)
        assert loaded_csv == []

    def test_special_characters_in_urls_and_titles(self, tmp_path: Path):
        entry = TrackerEntry(
            id="spec010203040506",
            title="Ingeniera & Coordinadora de Vías \"Senior\" <SST> / Especialista",
            company="Construcciones O'Connor & Cía. S.A.S.",
            direct_url="https://portal.com/job/search?q=vias&city=Bogot%C3%A1&ref=\"quote\"#top",
            full_description="Descripción con saltos\nde línea y comillas \"dobles\" y 'simples'.",
            location="Bogotá D.C.",
            modality="remoto",
            salary_range="$10.000.000 COP",
            source_portal="custom",
            score=70.0,
            score_percentage="70%",
            explanatory_summary="Cumple con vías (INVIAS) & SST.",
            estado="Nueva",
            fecha_deteccion="2026-09-21 12:00",
            notas_usuario="Notas con caracteres especiales: ñ, á, é, í, ó, ú, ¿?",
        )

        excel_path = tmp_path / "special.xlsx"
        csv_path = tmp_path / "special.csv"

        ExcelTracker.save([entry], output_path=excel_path, preserve_existing=False)
        CSVTracker.save([entry], output_path=csv_path, preserve_existing=False)

        # Verify Excel
        loaded_x = ExcelTracker.load(excel_path)
        assert len(loaded_x) == 1
        assert "O'Connor" in loaded_x[0].company
        assert "ñ, á, é" in loaded_x[0].notas_usuario

        # Verify CSV
        loaded_c = CSVTracker.load(csv_path)
        assert len(loaded_c) == 1
        assert "O'Connor" in loaded_c[0].company
        assert "ñ, á, é" in loaded_c[0].notas_usuario

    def test_score_color_boundaries(self, tmp_path: Path):
        b70 = TrackerEntry(
            id="b700000000000000",
            title="Boundary 70",
            company="C",
            direct_url="https://x.com",
            full_description="D",
            source_portal="p",
            score=70.0,
        )
        b69 = TrackerEntry(
            id="b690000000000000",
            title="Boundary 69.9",
            company="C",
            direct_url="https://x.com",
            full_description="D",
            source_portal="p",
            score=69.9,
        )
        b50 = TrackerEntry(
            id="b500000000000000",
            title="Boundary 50",
            company="C",
            direct_url="https://x.com",
            full_description="D",
            source_portal="p",
            score=50.0,
        )
        b49 = TrackerEntry(
            id="b490000000000000",
            title="Boundary 49.9",
            company="C",
            direct_url="https://x.com",
            full_description="D",
            source_portal="p",
            score=49.9,
        )

        excel_path = tmp_path / "boundaries.xlsx"
        ExcelTracker.save([b70, b69, b50, b49], output_path=excel_path, preserve_existing=False)

        wb = openpyxl.load_workbook(excel_path)
        ws = wb.active

        # Row 2 (b70) -> green
        assert ws.cell(row=2, column=5).fill.start_color.rgb.upper().endswith(GREEN_FILL_HEX)
        # Row 3 (b69.9) -> yellow
        assert ws.cell(row=3, column=5).fill.start_color.rgb.upper().endswith(YELLOW_FILL_HEX)
        # Row 4 (b50) -> yellow
        assert ws.cell(row=4, column=5).fill.start_color.rgb.upper().endswith(YELLOW_FILL_HEX)
        # Row 5 (b49.9) -> red
        assert ws.cell(row=5, column=5).fill.start_color.rgb.upper().endswith(RED_FILL_HEX)

        wb.close()

    def test_incremental_merge_empty_fresh_entries_preserves_all(self, tmp_path: Path, sample_tracker_entries: list[TrackerEntry]):
        excel_path = tmp_path / "preserve_all.xlsx"
        ExcelTracker.save(sample_tracker_entries, output_path=excel_path, preserve_existing=False)

        # Merge with empty fresh list
        merged = IncrementalTracker.merge(excel_path, [])
        assert len(merged) == len(sample_tracker_entries)

    def test_save_with_preserve_existing_true_merges_in_place(
        self, tmp_path: Path, sample_tracker_entries: list[TrackerEntry]
    ):
        excel_path = tmp_path / "in_place.xlsx"
        # Initial save
        ExcelTracker.save(sample_tracker_entries[:2], output_path=excel_path, preserve_existing=False)

        # User modifies status of first job
        loaded = ExcelTracker.load(excel_path)
        loaded[0].estado = "Postulado"
        loaded[0].notas_usuario = "Postulación enviada"
        ExcelTracker.save(loaded, output_path=excel_path, preserve_existing=False)

        # Now save with preserve_existing=True and new entry
        ExcelTracker.save([sample_tracker_entries[2]], output_path=excel_path, preserve_existing=True)

        final_loaded = ExcelTracker.load(excel_path)
        assert len(final_loaded) == 3
        j1 = next(x for x in final_loaded if x.id == sample_tracker_entries[0].id)
        assert j1.estado == "Postulado"
        assert j1.notas_usuario == "Postulación enviada"

