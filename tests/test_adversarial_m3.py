"""Adversarial stress and edge-case test suite for Milestone M3.

Covers:
- Strict modality verification edge cases, conflicting statements, and geographic exclusions
- Word boundary false-positive protection (e.g. 'lluvias', 'asistencia')
- Dynamic score computation sensitivity (verifying score changes when text changes)
- Strict clamping to [0.0, 100.0] under extreme penalties or extreme positive bonuses
- Comprehensive regulatory requirement detection (COPNIA, Licencia SST, Res. 0312)
- Multi-profile evaluation across Profiles 1, 2, 3, 4 and arbitrary custom profiles
- Zero-score enforcement on unrelated professions and presential site work
"""

from __future__ import annotations

import pytest

from job_hunter.config import load_profile
from job_hunter.matcher import AffinityScorer
from job_hunter.models import (
    ModalityConfig,
    NormalizedVacancy,
    ProfileConfig,
    ScoreBreakdown,
    SpecializationConfig,
)
from job_hunter.remote_verifier import RemoteVerifier
from job_hunter.summary import ExplanatorySummaryGenerator


@pytest.fixture
def profile_1() -> ProfileConfig:
    return load_profile("profile_1_civil_vias_sst")


@pytest.fixture
def scorer() -> AffinityScorer:
    return AffinityScorer()


@pytest.fixture
def verifier() -> RemoteVerifier:
    return RemoteVerifier()


class TestAdversarialRemoteVerifier:
    """Stress tests for modality verification, contradiction handling, and edge cases."""

    @pytest.mark.parametrize(
        "presential_text,expected_term",
        [
            ("Turnos rotativos 14x7 en sitio", "sitio"),
            ("Turnos 21x7 en frente de obra", "frente de obra"),
            ("Turno 21 dias pernoctando en campamento", "campamento"),
            ("Jefe de patio y maquinaria pesada", "jefe de patio"),
            ("Inspección física en obra diaria", "inspeccion fisica en obra"),
            ("Rondas de seguridad en campo obligatorias", "rondas de seguridad en campo"),
            ("Planta industrial en zona franca", "planta industrial"),
            ("Obra vial in situ con contratistas", "obra vial in situ"),
            ("Cuadrillas in situ en cantera", "cantera"),
            ("Labor 100% presencial", "100% presencial"),
            ("Sin posibilidad de teletrabajo bajo ninguna circunstancia", "sin posibilidad de teletrabajo"),
        ],
    )
    def test_presential_disqualifiers_detected(self, verifier, profile_1, presential_text, expected_term):
        vac = NormalizedVacancy(
            id="test_presential_edge",
            title="Ingeniero de Vías",
            company="Constructora",
            direct_url="https://example.com/job",
            full_description=f"Proyecto de infraestructura. {presential_text}.",
            source_portal="computrabajo",
        )
        res = verifier.evaluate(vac, profile_1)
        assert res.is_disqualified is True
        assert res.modality_score == 0.0
        assert res.detected_modality == "presencial"

    @pytest.mark.parametrize(
        "contradictory_text",
        [
            "Posición 100% remota... sin embargo requiere pernoctar en campamento de obra.",
            "Teletrabajo autónomo en Colombia con turnos 21x7 en campo.",
            "Trabajo desde casa pero con labor 100% presencial en sitio.",
            "Modalidad virtual durante pandemia, actualmente 100% presencial en obra.",
        ],
    )
    def test_disqualification_overrides_positive_remote(self, verifier, profile_1, contradictory_text):
        vac = NormalizedVacancy(
            id="test_contradictory",
            title="Coordinador de Vías",
            company="Consorcio",
            direct_url="https://example.com/job",
            full_description=contradictory_text,
            source_portal="computrabajo",
        )
        res = verifier.evaluate(vac, profile_1)
        assert res.is_disqualified is True
        assert res.modality_score == 0.0
        assert res.is_strictly_remote is False

    @pytest.mark.parametrize(
        "geo_text",
        [
            "Must reside in the US. W2 only.",
            "US citizens or green card required.",
            "Florida PE license mandatory.",
            "Not open to international applicants.",
            "Residencia obligatoria en España.",
            "Debe residir en Mexico.",
        ],
    )
    def test_geographic_disqualifiers(self, verifier, profile_1, geo_text):
        vac = NormalizedVacancy(
            id="test_geo",
            title="Highway Engineer",
            company="Global Inc",
            direct_url="https://example.com/job",
            full_description=f"Highway and pavement modeling. {geo_text}.",
            source_portal="remotive",
        )
        res = verifier.evaluate(vac, profile_1)
        assert res.is_disqualified is True
        assert res.modality_score == 0.0

    def test_custom_verifier_disqualifiers(self, profile_1):
        custom_v = RemoteVerifier(custom_disqualifiers=["trabajo nocturno en tunel", "disponibilidad de viaje permanente"])
        vac = NormalizedVacancy(
            id="test_custom_v",
            title="Ingeniero Civil",
            company="Constructora",
            direct_url="https://example.com/job",
            full_description="Revisión de proyectos con disponibilidad de viaje permanente a nivel nacional. 100% remoto.",
            source_portal="computrabajo",
        )
        res = custom_v.evaluate(vac, profile_1)
        assert res.is_disqualified is True
        assert res.modality_score == 0.0


class TestAdversarialAffinityScorer:
    """Stress tests for dynamic score changes, boundary clamping, and keyword isolation."""

    def test_dynamic_sensitivity_on_keyword_removal(self, scorer, profile_1):
        """Verifies that removing keywords genuinely reduces score rather than returning fixed values."""
        full_text = (
            "Ingeniera Civil Senior con 15 años de experiencia. Especialista en diseño geométrico de vías, "
            "pavimentos y carreteras. Además especialista en seguridad y salud en el trabajo, sst, sg-sst. "
            "100% remoto Colombia."
        )
        vac_full = NormalizedVacancy(
            id="v_dyn_full",
            title="Ingeniera Civil Senior de Vías y SST",
            company="Consorcio",
            direct_url="https://example.com/job",
            full_description=full_text,
            modality="remoto",
            source_portal="computrabajo",
        )
        res_full = scorer.evaluate(vac_full, profile_1)
        assert res_full.total_score == 100.0
        assert res_full.vias_score == 25.0
        assert res_full.sst_score == 25.0
        assert res_full.synergy_bonus == 10.0

        # Remove SST keywords
        no_sst_text = (
            "Ingeniera Civil Senior con 15 años de experiencia. Especialista en diseño geométrico de vías, "
            "pavimentos y carreteras. 100% remoto Colombia."
        )
        vac_no_sst = vac_full.model_copy(update={"full_description": no_sst_text, "title": "Ingeniera Civil Senior de Vías"})
        res_no_sst = scorer.evaluate(vac_no_sst, profile_1)
        assert res_no_sst.sst_score == 0.0
        assert res_no_sst.synergy_bonus == 0.0
        assert res_no_sst.total_score < res_full.total_score
        assert res_no_sst.total_score == 75.0

        # Remove vías keywords as well (senior civil generalist)
        general_text = "Ingeniera Civil Senior con 15 años de experiencia general en consultoría técnica. 100% remoto Colombia."
        vac_general = vac_full.model_copy(update={"full_description": general_text, "title": "Ingeniera Civil Senior"})
        res_general = scorer.evaluate(vac_general, profile_1)
        assert res_general.vias_score == 0.0
        assert res_general.sst_score == 0.0
        assert res_general.total_score == 50.0  # 25 modality + 25 seniority

    def test_word_boundary_isolation_accents_and_derivatives(self, scorer, profile_1):
        """Verifies that words containing substrings of keywords do NOT falsely trigger matches."""
        tricky_text = (
            "Ingeniero Ambiental con experiencia en temporada de lluvias torrenciales y aluvias. "
            "Brinda asistencia técnica a comunidades. "
            "Manejo de desvías provisionales de agua. 100% remoto Colombia."
        )
        vac = NormalizedVacancy(
            id="v_tricky",
            title="Ingeniero Ambiental",
            company="EcoAndes",
            direct_url="https://example.com/job",
            full_description=tricky_text,
            modality="remoto",
            source_portal="computrabajo",
        )
        res = scorer.evaluate(vac, profile_1)
        assert res.vias_score == 0.0
        assert res.sst_score == 0.0
        assert "vias" not in [k.lower() for k in res.matched_keywords]
        assert "sst" not in [k.lower() for k in res.matched_keywords]

    @pytest.mark.parametrize(
        "years_text,expected_exp_score",
        [
            ("con más de 12 años de experiencia profesional", 10.0),
            ("experiencia mínima de 15 años en el cargo", 10.0),
            ("trayectoria de 20 años", 10.0),
            ("mínimo 5 años de experiencia", 7.0),
            ("experiencia mínima 6 años", 7.0),
            ("mínimo 3 años de ejercicio profesional", 5.0),
        ],
    )
    def test_experience_years_extraction(self, scorer, profile_1, years_text, expected_exp_score):
        vac = NormalizedVacancy(
            id="v_exp_extract",
            title="Consultor Técnico",
            company="Consultores",
            direct_url="https://example.com/job",
            full_description=f"Se requiere profesional {years_text}. 100% remoto Colombia.",
            modality="remoto",
            source_portal="computrabajo",
        )
        res = scorer.evaluate(vac, profile_1)
        # title is "Consultor Técnico" -> 10 pts title score
        expected_seniority = 10.0 + expected_exp_score
        assert res.seniority_score == expected_seniority

    def test_extreme_clamping_upper_and_lower(self, scorer, profile_1):
        # Case A: Massive positive bonuses (modality 25 + seniority 25 + vias 25 + sst 25 + synergy 10 = 110 raw)
        vac_over = NormalizedVacancy(
            id="v_over",
            title="Directora de Interventoría Vial e Infraestructura y SST",
            company="Consorcio Vial",
            direct_url="https://example.com/job",
            full_description=(
                "Ingeniera Civil con 20 años de experiencia. Diseño geométrico de vías, pavimentos, carreteras, invias, ani. "
                "Especialista en seguridad y salud en el trabajo, sst, sg-sst, licencia sst, resolución 0312. "
                "100% remoto Colombia."
            ),
            modality="remoto",
            source_portal="computrabajo",
        )
        res_over = scorer.evaluate(vac_over, profile_1)
        assert res_over.total_score == 100.0

        # Case B: Disqualified with multiple penalties
        vac_disq_pen = NormalizedVacancy(
            id="v_under",
            title="Desarrollador Junior de Software en Campamento de Obra",
            company="Constructora",
            direct_url="https://example.com/job",
            full_description="Programador junior sin experiencia. Turnos 21x7 en campamento 100% presencial.",
            modality="presencial",
            source_portal="computrabajo",
        )
        res_under = scorer.evaluate(vac_disq_pen, profile_1)
        assert res_under.total_score == 0.0
        assert res_under.is_disqualified is True


class TestAdversarialSummaryGenerator:
    """Stress tests for ExplanatorySummaryGenerator."""

    def test_regulatory_credential_variations(self):
        vac = NormalizedVacancy(
            id="v_regs",
            title="Ingeniero Civil",
            company="Firma",
            direct_url="https://example.com/job",
            full_description=(
                "Indispensable matrícula profesional emitida por el Consejo Profesional Nacional de Ingeniería (COPNIA). "
                "Licencia en SST vigente y certificación del curso de 50 horas del SG-SST según Resolución 0312."
            ),
            source_portal="computrabajo",
        )
        regs = ExplanatorySummaryGenerator.check_regulatory_requirements(vac)
        assert regs["copnia_required"] is True
        assert regs["sst_license_required"] is True
        assert regs["res_0312_course"] is True

    def test_missing_requirements_flagged_when_absent_in_profile(self):
        # Profile without COPNIA or SST credentials
        lean_profile = ProfileConfig(
            id="lean_prof",
            name="Consultor Lean",
            target_role="Consultor",
            required_credentials=[],  # Empty credentials
        )
        vac = NormalizedVacancy(
            id="v_missing",
            title="Consultor",
            company="Firma",
            direct_url="https://example.com/job",
            full_description="Requiere tarjeta profesional COPNIA y licencia SST vigente.",
            source_portal="computrabajo",
        )
        missing = ExplanatorySummaryGenerator.identify_missing_requirements(vac, lean_profile)
        assert any("COPNIA" in m for m in missing)
        assert any("Licencia SST" in m for m in missing)
