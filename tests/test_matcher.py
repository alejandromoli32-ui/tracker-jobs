from __future__ import annotations

import json
from pathlib import Path
import pytest

from job_hunter.config import load_profile
from job_hunter.matcher import AffinityScorer
from job_hunter.models import (
    ModalityConfig,
    ModalityEvaluation,
    NormalizedVacancy,
    ProfileConfig,
    ScoreBreakdown,
    SpecializationConfig,
)
from job_hunter.remote_verifier import RemoteVerifier
from job_hunter.summary import ExplanatorySummaryGenerator


# =============================================================================
# Canonical 9-Job Benchmark Dataset (from ORIGINAL_REQUEST.md line 34,
# TEST_INFRA.md line 38, and spec_report.md line 719)
# =============================================================================

CANONICAL_BENCHMARK_JOBS = [
    # Group A: 3 Ideal Remote Roads/SST Vacancies (Expected Score >= 70, Accept)
    {
        "id_ref": "V01",
        "vacancy": NormalizedVacancy(
            id="v01_vias_remota",
            title="Directora / Coordinadora de Diseños Viales e Infraestructura - 100% Remoto Colombia",
            company="Consorcio Vial Andino",
            direct_url="https://www.computrabajo.com.co/ofertas-de-trabajo/oferta-v1",
            location="Colombia (Remoto)",
            modality="remoto",
            source_portal="computrabajo",
            full_description=(
                "Importante firma de consultoría de transporte busca Ingeniera Civil Senior con más de "
                "12 años de experiencia profesional y 6 años específicos en diseño geométrico de vías, "
                "pavimentos y coordinación técnica de proyectos de infraestructura vial (INVIAS y ANI). "
                "Modalidad 100% remota / teletrabajo desde cualquier ciudad de Colombia. "
                "Requiere Tarjeta Profesional COPNIA vigente."
            ),
        ),
        "expected_score_min": 75.0,
        "expected_score_max": 100.0,
        "expected_action": "ACCEPT",
        "expected_disqualified": False,
    },
    {
        "id_ref": "V02",
        "vacancy": NormalizedVacancy(
            id="v02_sst_remota",
            title="Especialista Senior en Seguridad y Salud en el Trabajo (SST) para Proyectos de Infraestructura - Teletrabajo Colombia",
            company="HSEQ Consultores Integrales",
            direct_url="https://www.elempleo.com/co/ofertas-empleo/oferta-v2",
            location="Bogotá / Remoto Nacional",
            modality="remoto",
            source_portal="elempleo",
            full_description=(
                "Buscamos Especialista Senior en Seguridad y Salud en el Trabajo con formación de base en "
                "Ingeniería Civil y experiencia mínima de 8 años liderando el SG-SST en proyectos de construcción "
                "e infraestructura. Indispensable contar con Licencia SST vigente expedida por Secretaría de Salud "
                "y curso de 50 horas de la Resolución 0312. Trabajo 100% virtual / teletrabajo autónomo en Colombia."
            ),
        ),
        "expected_score_min": 75.0,
        "expected_score_max": 100.0,
        "expected_action": "ACCEPT",
        "expected_disqualified": False,
    },
    {
        "id_ref": "V03",
        "vacancy": NormalizedVacancy(
            id="v03_dual_vias_sst",
            title="Gerente de Proyectos de Interventoría Vial y Gestión HSEQ - Remoto Nacional",
            company="Interventorías y Diseños de Colombia S.A.S.",
            direct_url="https://www.linkedin.com/jobs/view/oferta-v3",
            location="Remoto Colombia",
            modality="remoto",
            source_portal="linkedin",
            full_description=(
                "Se requiere Ingeniero/a Civil con 15 años de experiencia general, con especialización tanto en "
                "Vías y Transportes como en Seguridad y Salud en el Trabajo (SST). Estará a cargo de la gerencia "
                "de interventoría documental, seguimiento a especificaciones técnicas INVIAS y auditoría del SG-SST. "
                "Modalidad estrictamente virtual / teletrabajo desde casa en Colombia. Tarjeta COPNIA y Licencia SST requeridas."
            ),
        ),
        "expected_score_min": 85.0,
        "expected_score_max": 100.0,
        "expected_action": "ACCEPT",
        "expected_disqualified": False,
    },
    # Group B: 3 Presential On-Site Obra Vacancies (Expected Score <= 20, Disqualified/Reject)
    {
        "id_ref": "V04",
        "vacancy": NormalizedVacancy(
            id="v04_residente_campamento",
            title="Ingeniero Residente de Obra Vial - 100% Presencial en Campamento (Vía Bogotá-Girardot)",
            company="Constructora Vial del Sol",
            direct_url="https://co.computrabajo.com/ofertas-de-trabajo/oferta-v4",
            location="Fusagasugá / Girardot, Cundinamarca",
            modality="presencial",
            source_portal="computrabajo",
            full_description=(
                "Constructora requiere Ingeniero Civil Residente de Obra para proyecto vial concesionado. "
                "Experiencia mínima 5 años en colocación de mezclas asfálticas y pavimentos. "
                "Modalidad 100% presencial en frente de obra, pernoctando en campamento de obra con disponibilidad 24/7. "
                "Sin posibilidad de teletrabajo."
            ),
        ),
        "expected_score_min": 0.0,
        "expected_score_max": 20.0,
        "expected_action": "REJECT",
        "expected_disqualified": True,
    },
    {
        "id_ref": "V05",
        "vacancy": NormalizedVacancy(
            id="v05_inspector_sst_obra",
            title="Inspector de Seguridad Industrial y SST en Obra de Construcción - Presencial Medellín",
            company="Edificaciones del Valle",
            direct_url="https://www.elempleo.com/co/ofertas-empleo/oferta-v5",
            location="Medellín, Antioquia",
            modality="presencial",
            source_portal="elempleo",
            full_description=(
                "Se busca Inspector SST con Licencia vigente para trabajo continuo en obra civil presencial en Medellín. "
                "Debe realizar rondas de seguridad en campo, control de permisos de trabajo en alturas e inspección física en obra. "
                "Horario presencial de lunes a sábado en sitio de obra. No es remoto."
            ),
        ),
        "expected_score_min": 0.0,
        "expected_score_max": 20.0,
        "expected_action": "REJECT",
        "expected_disqualified": True,
    },
    {
        "id_ref": "V06",
        "vacancy": NormalizedVacancy(
            id="v06_director_pavimentos_campo",
            title="Director de Construcción de Pavimentos y Mezclas Asfálticas - Presencial Campo Puerto Gaitán",
            company="Pavimentos y Asfaltos Petroleros",
            direct_url="https://www.computrabajo.com.co/ofertas-de-trabajo/oferta-v6",
            location="Puerto Gaitán, Meta",
            modality="presencial",
            source_portal="computrabajo",
            full_description=(
                "Se requiere Director de Pavimentación en obra. Ingeniero Civil con 10 años de experiencia en vías. "
                "Lugar de trabajo: Campamento en Puerto Gaitán, Meta. Turno 21/7 en campo 100% presencial. "
                "Manejo de maquinaria pesada y cuadrillas in situ."
            ),
        ),
        "expected_score_min": 0.0,
        "expected_score_max": 20.0,
        "expected_action": "REJECT",
        "expected_disqualified": True,
    },
    # Group C: 3 Non-Relevant Civil Engineering Vacancies (Expected Score < 50, Reject)
    {
        "id_ref": "V07",
        "vacancy": NormalizedVacancy(
            id="v07_civil_junior_hidrosanitario",
            title="Ingeniero Civil Junior - Diseñador Hidrosanitario y Redes de Gas (Remoto)",
            company="HidroDiseños S.A.S.",
            direct_url="https://www.computrabajo.com.co/ofertas-de-trabajo/oferta-v7",
            location="Colombia (Remoto)",
            modality="remoto",
            source_portal="computrabajo",
            full_description=(
                "Empresa busca Ingeniero Civil recién graduado o Junior (1 año de experiencia) para diseño "
                "de redes hidrosanitarias, fontanería y redes contra incendios en edificaciones residenciales. "
                "Manejo de AutoCAD y Revit MEP. Modalidad 100% remoto en Colombia."
            ),
        ),
        "expected_score_min": 10.0,
        "expected_score_max": 45.0,
        "expected_action": "REJECT",
        "expected_disqualified": False,
    },
    {
        "id_ref": "V08",
        "vacancy": NormalizedVacancy(
            id="v08_calculista_estructuras_edificios",
            title="Ingeniero Civil Calculista de Estructuras Metálicas para Edificaciones (Híbrido/Remoto)",
            company="Cálculos Estructurales Ltda.",
            direct_url="https://www.elempleo.com/co/ofertas-empleo/oferta-v8",
            location="Bogotá / Remoto",
            modality="remoto",
            source_portal="elempleo",
            full_description=(
                "Firma de ingeniería requiere Ingeniero Civil Especialista en Estructuras con 5 años de experiencia "
                "en modelación y cálculo de naves industriales, vigas de acero y conexiones empernadas en SAP2000 y ETABS. "
                "Diseño de estructuras para edificios comerciales. Trabajo remoto con reuniones ocasionales."
            ),
        ),
        "expected_score_min": 15.0,
        "expected_score_max": 48.0,
        "expected_action": "REJECT",
        "expected_disqualified": False,
    },
    {
        "id_ref": "V09",
        "vacancy": NormalizedVacancy(
            id="v09_fullstack_python",
            title="Desarrollador Fullstack Python / React - Remoto Colombia",
            company="Tech Innovations Global",
            direct_url="https://www.linkedin.com/jobs/view/oferta-v9",
            location="Colombia (Remoto)",
            modality="remoto",
            source_portal="linkedin",
            full_description=(
                "Startup tecnológica busca Senior Fullstack Developer con experiencia en Python, Django, React "
                "y PostgreSQL. Diseño de APIs REST y microservicios en la nube AWS. "
                "100% remoto desde cualquier lugar de Latinoamérica."
            ),
        ),
        "expected_score_min": 0.0,
        "expected_score_max": 10.0,
        "expected_action": "REJECT",
        "expected_disqualified": False,
    },
]


@pytest.fixture
def profile_1() -> ProfileConfig:
    """Load default Profile 1 (Ingeniera Civil Senior - Vías & SST)."""
    return load_profile("profile_1_civil_vias_sst")


@pytest.fixture
def profile_2() -> ProfileConfig:
    """Load Profile 2 (Gerente de Proyectos de Infraestructura)."""
    return load_profile("profile_2_gerente_proyectos_viales")


@pytest.fixture
def profile_3() -> ProfileConfig:
    """Load Profile 3 (Modelador BIM Vías)."""
    return load_profile("profile_3_modelador_bim_vias")


@pytest.fixture
def profile_4() -> ProfileConfig:
    """Load Profile 4 (Consultor HSEQ SIG)."""
    return load_profile("profile_4_consultor_hseq_sig")


@pytest.fixture
def verifier() -> RemoteVerifier:
    return RemoteVerifier()


@pytest.fixture
def scorer(verifier) -> AffinityScorer:
    return AffinityScorer(remote_verifier=verifier)


# =============================================================================
# TIER 1 & 2: RemoteVerifier Unit & Edge Case Tests
# =============================================================================

class TestRemoteVerifier:
    """Unit and boundary tests for Colombian labor modality evaluation."""

    def test_positive_remote_explicit_tokens(self, verifier, profile_1):
        tokens = [
            "100% remoto en Colombia",
            "Modalidad de teletrabajo autónomo",
            "Trabajo desde casa con conexión a internet",
            "Posición virtual para residentes en Colombia",
            "100% teletrabajo nacional",
            "Home office permanente",
        ]
        for token in tokens:
            vac = NormalizedVacancy(
                id="test_pos",
                title="Ingeniera Civil",
                company="Consultores",
                direct_url="https://example.com/job",
                full_description=f"Se busca profesional. {token}.",
                source_portal="computrabajo",
            )
            result = verifier.evaluate(vac, profile_1)
            assert result.is_strictly_remote is True
            assert result.is_disqualified is False
            assert result.modality_score == 25.0
            assert result.detected_modality == "remoto"

    def test_disqualifier_presential_obra_tokens(self, verifier, profile_1):
        disqualifiers = [
            "100% presencial en frente de obra",
            "Residente de obra para colocación de asfalto",
            "Disponibilidad para pernoctar en campamento",
            "Turnos 21x7 en campo",
            "Inspección física en obra diaria",
            "Labor 100% presencial en cantera",
            "Abstenerse candidatos que busquen trabajo remoto",
        ]
        for term in disqualifiers:
            vac = NormalizedVacancy(
                id="test_disq",
                title="Ingeniero de Vías",
                company="Constructora",
                direct_url="https://example.com/job",
                full_description=f"Oferta laboral. {term}.",
                source_portal="computrabajo",
            )
            result = verifier.evaluate(vac, profile_1)
            assert result.is_strictly_remote is False
            assert result.is_disqualified is True
            assert result.modality_score == 0.0
            assert result.disqualification_reason is not None

    def test_precedence_disqualifier_overrides_remote_keyword(self, verifier, profile_1):
        """When a job mentions remote historically but requires on-site campamento now."""
        vac = NormalizedVacancy(
            id="test_precedence",
            title="Ingeniero Residente Vial",
            company="Constructora",
            direct_url="https://example.com/job",
            full_description=(
                "Fue 100% remoto durante la emergencia sanitaria, pero actualmente es "
                "100% presencial en campamento de obra en el Magdalena Medio."
            ),
            source_portal="computrabajo",
        )
        result = verifier.evaluate(vac, profile_1)
        assert result.is_disqualified is True
        assert result.is_strictly_remote is False
        assert result.modality_score == 0.0

    def test_hybrid_modality_receives_partial_score(self, verifier, profile_1):
        vac = NormalizedVacancy(
            id="test_hybrid",
            title="Coordinador de Proyectos",
            company="Constructora",
            direct_url="https://example.com/job",
            full_description="Esquema híbrido con 3 días remoto y 2 días en oficina Bogotá. Reuniones ocasionales.",
            source_portal="elempleo",
        )
        result = verifier.evaluate(vac, profile_1)
        assert result.is_disqualified is False
        assert result.is_strictly_remote is False
        assert result.modality_score == 10.0
        assert result.detected_modality == "hibrido"

    def test_geographic_restriction_disqualifies(self, verifier, profile_1):
        vac = NormalizedVacancy(
            id="test_geo",
            title="Senior Civil Engineer",
            company="US Infrastructure Firm",
            direct_url="https://remotive.com/job",
            full_description="Highway engineer. Must reside in USA. US Citizens or Green Card holders only (W2 only).",
            source_portal="remotive",
        )
        result = verifier.evaluate(vac, profile_1)
        assert result.is_disqualified is True
        assert result.modality_score == 0.0
        assert "EE.UU" in result.disqualification_reason or "geográfica" in result.disqualification_reason

    def test_unstated_modality_receives_baseline_score(self, verifier, profile_1):
        vac = NormalizedVacancy(
            id="test_unstated",
            title="Ingeniero Civil Consultor",
            company="Firma",
            direct_url="https://example.com/job",
            full_description="Revisión de estudios y diseños hidrológicos. Enviar hoja de vida.",
            modality="desconocido",
            source_portal="elempleo",
        )
        result = verifier.evaluate(vac, profile_1)
        assert result.is_disqualified is False
        assert result.is_strictly_remote is False
        assert result.modality_score == 5.0
        assert result.detected_modality == "desconocido"


# =============================================================================
# TIER 1 & 2: ExplanatorySummaryGenerator Tests
# =============================================================================

class TestExplanatorySummaryGenerator:
    """Tests for regulatory alerts, credential checks, and summary synthesis."""

    def test_copnia_detection(self):
        vac = NormalizedVacancy(
            id="test_copnia",
            title="Ingeniero Civil",
            company="Consultores",
            direct_url="https://example.com/job",
            full_description="Indispensable contar con matrícula profesional COPNIA vigente para firma de planos.",
            source_portal="computrabajo",
        )
        regs = ExplanatorySummaryGenerator.check_regulatory_requirements(vac)
        assert regs["copnia_required"] is True
        assert regs["sst_license_required"] is False

    def test_sst_license_and_resolution_0312_detection(self):
        vac = NormalizedVacancy(
            id="test_sst_lic",
            title="Especialista SST",
            company="Consultores",
            direct_url="https://example.com/job",
            full_description="Se requiere Licencia SST vigente expedida por Secretaría de Salud y certificación curso de 50 horas Resolución 0312.",
            source_portal="elempleo",
        )
        regs = ExplanatorySummaryGenerator.check_regulatory_requirements(vac)
        assert regs["sst_license_required"] is True
        assert regs["res_0312_course"] is True

    def test_summary_format_and_tier_labels(self, profile_1):
        vac = NormalizedVacancy(
            id="test_summ_high",
            title="Directora de Vías y SST",
            company="Consultores",
            direct_url="https://example.com/job",
            full_description="Interventoría vial y SST. Requiere tarjeta profesional COPNIA y licencia SST vigente.",
            modality="remoto",
            source_portal="computrabajo",
        )
        breakdown = ScoreBreakdown(
            total_score=92.0,
            modality_score=25.0,
            seniority_score=25.0,
            vias_score=25.0,
            sst_score=25.0,
            synergy_bonus=10.0,
            penalties=0.0,
            is_disqualified=False,
        )
        summary = ExplanatorySummaryGenerator.generate(vac, profile_1, breakdown)
        assert "[Afinidad: 92/100 - Alta Afinidad]" in summary
        assert "100% Remoto en Colombia confirmado" in summary
        assert "COPNIA" in summary
        assert "Licencia en Seguridad y Salud en el Trabajo (SST) vigente" in summary

    def test_disqualified_summary_format(self, profile_1):
        vac = NormalizedVacancy(
            id="test_summ_disq",
            title="Residente de Obra en Campamento",
            company="Constructora",
            direct_url="https://example.com/job",
            full_description="Presencial en campamento 21x7.",
            modality="presencial",
            source_portal="computrabajo",
        )
        breakdown = ScoreBreakdown(
            total_score=0.0,
            modality_score=0.0,
            seniority_score=0.0,
            vias_score=0.0,
            sst_score=0.0,
            synergy_bonus=0.0,
            penalties=100.0,
            is_disqualified=True,
        )
        summary = ExplanatorySummaryGenerator.generate(vac, profile_1, breakdown)
        assert "[Afinidad: 0/100 - Descartada]" in summary
        assert "Presencial / No permitida" in summary


# =============================================================================
# TIER 1 & 2: AffinityScorer Rubric, Bonuses, and Penalties
# =============================================================================

class TestAffinityScorerRubric:
    """Tests for multi-dimensional subscores, synergy bonuses, and penalty triggers."""

    def test_synergy_bonus_applied_when_both_vias_and_sst_match(self, scorer, profile_1):
        vac = NormalizedVacancy(
            id="test_synergy",
            title="Directora de Interventoría Vial y SG-SST Remota",
            company="Consorcio Vial",
            direct_url="https://example.com/job",
            full_description=(
                "Ingeniera Civil con 15 años de experiencia. Coordinación de diseños geométricos, "
                "pavimentos e infraestructura vial. Además liderar auditorías del SG-SST y prevención de riesgos. "
                "100% remoto Colombia."
            ),
            modality="remoto",
            source_portal="computrabajo",
        )
        res = scorer.evaluate(vac, profile_1)
        assert res.vias_score >= 18.0
        assert res.sst_score >= 18.0
        assert res.synergy_bonus == 10.0
        assert res.total_score >= 85.0

    def test_synergy_bonus_not_applied_when_single_specialization_matches(self, scorer, profile_1):
        vac = NormalizedVacancy(
            id="test_no_synergy",
            title="Especialista en Pavimentos y Carreteras Remota",
            company="Consorcio Vial",
            direct_url="https://example.com/job",
            full_description=(
                "Ingeniera Civil con 15 años de experiencia en diseño geométrico, pavimentos y carreteras. "
                "100% remoto Colombia."
            ),
            modality="remoto",
            source_portal="computrabajo",
        )
        res = scorer.evaluate(vac, profile_1)
        assert res.vias_score >= 18.0
        assert res.sst_score == 0.0
        assert res.synergy_bonus == 0.0

    def test_junior_penalty_reduces_score(self, scorer, profile_1):
        vac_junior = NormalizedVacancy(
            id="test_junior",
            title="Ingeniero Civil Junior - Vías",
            company="Consultores",
            direct_url="https://example.com/job",
            full_description="Ingeniero recién graduado con 1 año de experiencia para apoyo en vías. 100% remoto.",
            modality="remoto",
            source_portal="computrabajo",
        )
        res_junior = scorer.evaluate(vac_junior, profile_1)
        assert res_junior.penalties >= 10.0
        assert res_junior.total_score < 50.0

    def test_unrelated_profession_penalty(self, scorer, profile_1):
        vac_unrelated = NormalizedVacancy(
            id="test_dev",
            title="Desarrollador Fullstack Python / React - Remoto",
            company="Tech Corp",
            direct_url="https://example.com/job",
            full_description="Senior Software Engineer con 10 años en Python y Django. 100% remoto.",
            modality="remoto",
            source_portal="linkedin",
        )
        res = scorer.evaluate(vac_unrelated, profile_1)
        assert res.penalties >= 60.0
        assert res.total_score <= 10.0

    def test_score_clamped_strictly_between_0_and_100(self, scorer, profile_1):
        # Vacancy with maximum everything
        vac_max = NormalizedVacancy(
            id="test_max",
            title="Directora de Interventoría Vial y SG-SST - Ingeniera Civil Senior",
            company="Consorcio Nacional",
            direct_url="https://example.com/job",
            full_description=(
                "Ingeniera Civil con 20 años de experiencia general. Especialista en vías, pavimentos, carreteras, "
                "diseño geométrico, tránsito y transporte, invias, ani. "
                "Especialista en seguridad y salud en el trabajo, sst, sg-sst, hseq, licencia sst, resolución 0312, copasst. "
                "100% remoto teletrabajo en Colombia."
            ),
            modality="remoto",
            source_portal="computrabajo",
        )
        res_max = scorer.evaluate(vac_max, profile_1)
        assert res_max.total_score <= 100.0
        assert res_max.total_score == 100.0

        # Disqualified vacancy
        vac_disq = NormalizedVacancy(
            id="test_min",
            title="Residente de Obra en Campamento",
            company="Constructora",
            direct_url="https://example.com/job",
            full_description="Turno 21x7 en campamento 100% presencial.",
            modality="presencial",
            source_portal="computrabajo",
        )
        res_min = scorer.evaluate(vac_disq, profile_1)
        assert res_min.total_score == 0.0


# =============================================================================
# TIER 4: Canonical 9 Benchmark Verification Jobs (Acceptance Criteria lines 42-45)
# =============================================================================

class TestCanonical9BenchmarkSuite:
    """Authoritative test suite validating the 9 canonical verification jobs.

    Directly verifies:
    - 3 Ideal Remote Vías + SST vacancies score >= 70 (ACCEPT).
    - 3 Presential on-site obra/campamento vacancies score <= 20 and are disqualified (REJECT).
    - 3 Non-relevant civil engineering vacancies score < 50 (REJECT).
    """

    @pytest.mark.parametrize(
        "job_spec",
        CANONICAL_BENCHMARK_JOBS,
        ids=[j["id_ref"] for j in CANONICAL_BENCHMARK_JOBS],
    )
    def test_canonical_benchmark_job(self, scorer, profile_1, job_spec):
        vacancy = job_spec["vacancy"]
        score_min = job_spec["expected_score_min"]
        score_max = job_spec["expected_score_max"]
        action = job_spec["expected_action"]
        disqualified = job_spec["expected_disqualified"]

        result = scorer.evaluate(vacancy, profile_1)

        # 1. Verify score is within expected range
        assert score_min <= result.total_score <= score_max, (
            f"Job {job_spec['id_ref']} ({vacancy.title}): score {result.total_score} "
            f"not in expected range [{score_min}, {score_max}]. Breakdown: {result}"
        )

        # 2. Verify disqualification flag
        assert result.is_disqualified == disqualified, (
            f"Job {job_spec['id_ref']} ({vacancy.title}): is_disqualified was "
            f"{result.is_disqualified}, expected {disqualified}"
        )

        # 3. Verify high-affinity acceptance threshold (>= 70)
        if action == "ACCEPT":
            assert result.total_score >= 70.0, (
                f"Ideal job {job_spec['id_ref']} failed acceptance threshold (>= 70): {result.total_score}"
            )
            assert not result.is_disqualified
            assert result.modality_score == 25.0
        else:
            assert result.total_score < 70.0, (
                f"Rejected job {job_spec['id_ref']} improperly passed acceptance threshold (>= 70): {result.total_score}"
            )


# =============================================================================
# TIER 3: Multi-Profile Extensibility Tests (Profiles 1, 2, 3, 4)
# =============================================================================

class TestMultiProfileMatching:
    """Verifies that the matching engine evaluates arbitrary profiles without code changes."""

    def test_profile_2_gerente_proyectos_viales(self, scorer, profile_2):
        vac = NormalizedVacancy(
            id="p2_test",
            title="Gerente de Proyecto para Concesión Vial 4G (Remoto / Híbrido)",
            company="Consorcio de Infraestructura",
            direct_url="https://example.com/p2",
            location="Bogotá / Remoto",
            modality="remoto",
            source_portal="linkedin",
            full_description=(
                "Buscamos Gerente de Proyectos con certificación PMP y 12 años de experiencia en "
                "contratación estatal (Ley 80 y SECOP II), concesiones 4G y control de cronogramas en Primavera P6. "
                "Supervisión de infraestructura vial y gestión contractual con ANI e INVIAS. "
                "Modalidad 100% remota."
            ),
        )
        res = scorer.evaluate(vac, profile_2)
        assert res.total_score >= 70.0
        assert not res.is_disqualified
        assert "pmp" in [k.lower() for k in res.matched_keywords]

    def test_profile_3_modelador_bim_vias(self, scorer, profile_3):
        vac = NormalizedVacancy(
            id="p3_test",
            title="Especialista en Modelado BIM y Diseño Geométrico Vial Remoto",
            company="Ingeniería & BIM SAS",
            direct_url="https://example.com/p3",
            location="Colombia (Remoto)",
            modality="remoto",
            source_portal="computrabajo",
            full_description=(
                "Ingeniero Civil con 6 años de experiencia en modelado BIM de infraestructura vial, "
                "diseño geométrico de carreteras en Autodesk Civil 3D, Infraworks y Revit. "
                "100% teletrabajo en Colombia."
            ),
        )
        res = scorer.evaluate(vac, profile_3)
        assert res.total_score >= 70.0
        assert not res.is_disqualified

    def test_profile_4_consultor_hseq_sig(self, scorer, profile_4):
        vac = NormalizedVacancy(
            id="p4_test",
            title="Consultor Senior HSEQ y Auditor Líder ISO 45001 / SG-SST (Teletrabajo)",
            company="Sistemas de Gestión Colombia",
            direct_url="https://example.com/p4",
            location="Medellín / Remoto",
            modality="remoto",
            source_portal="elempleo",
            full_description=(
                "Consultora busca Auditor Líder HSEQ con Licencia SST vigente y 10 años de experiencia "
                "en implementación y auditoría de sistemas de gestión integrados (ISO 45001, ISO 9001, ISO 14001, "
                "Decreto 1072 de 2015 y Resolución 0312). Auditorías remotas y diseño de matriz de riesgos. "
                "Trabajo 100% virtual."
            ),
        )
        res = scorer.evaluate(vac, profile_4)
        assert res.total_score >= 70.0
        assert not res.is_disqualified

    def test_fixtures_json_evaluation(self, scorer, profile_1):
        """Evaluate all mock vacancies from mock_vacancies.json to verify stability."""
        fixture_path = Path(__file__).resolve().parent.parent / "job_hunter" / "fixtures" / "mock_vacancies.json"
        if not fixture_path.exists():
            pytest.skip("mock_vacancies.json not found")

        with open(fixture_path, encoding="utf-8") as f:
            vacancies_raw = json.load(f)

        for raw in vacancies_raw:
            vac = NormalizedVacancy(
                id=raw["id"],
                title=raw["title"],
                company=raw.get("company", "Confidencial"),
                direct_url=raw["direct_url"],
                location=raw.get("location", "Colombia"),
                modality=raw.get("modality", "desconocido"),
                source_portal=raw.get("source_portal", "mock"),
                full_description=raw.get("full_description", ""),
                salary_range=raw.get("salary_range"),
                raw_snippet=raw.get("raw_snippet"),
                extra_metadata=raw.get("extra_metadata", {}),
            )
            res = scorer.evaluate(vac, profile_1)
            assert 0.0 <= res.total_score <= 100.0
            assert isinstance(res.explanatory_summary, str)
            assert len(res.explanatory_summary) > 10


# =============================================================================
# TIER 2 & 5: Adversarial, Boundary & Edge Case Hardening
# =============================================================================

class TestMatcherAdversarialAndBoundaries:
    """Adversarial boundary conditions, false positive avoidance, and encoding tests."""

    def test_false_substring_protection_lluvias_not_vias(self, scorer, profile_1):
        """Ensure 'lluvias' does not trigger 'vias', and 'asistencia' does not trigger 'sst'."""
        vac = NormalizedVacancy(
            id="test_false_pos",
            title="Ingeniero Civil Consultor",
            company="HidroAmbiental",
            direct_url="https://example.com/job",
            full_description=(
                "Evaluación hidrológica de caudales durante temporada de lluvias intensas. "
                "Se requiere asistencia técnica para elaboración de informes. 100% remoto Colombia."
            ),
            modality="remoto",
            source_portal="computrabajo",
        )
        res = scorer.evaluate(vac, profile_1)
        assert res.vias_score == 0.0, f"Expected vias_score 0.0, got {res.vias_score} (matched: {res.matched_keywords})"
        assert res.sst_score == 0.0, f"Expected sst_score 0.0, got {res.sst_score} (matched: {res.matched_keywords})"
        assert "vias" not in [k.lower() for k in res.matched_keywords]
        assert "vías" not in [k.lower() for k in res.matched_keywords]
        assert "sst" not in [k.lower() for k in res.matched_keywords]

    def test_empty_and_whitespace_fields(self, scorer, profile_1):
        """Ensure evaluator handles empty strings and whitespace without exceptions."""
        vac_empty = NormalizedVacancy(
            id="empty_vac",
            title="   ",
            company="",
            direct_url="https://example.com/empty",
            full_description="   \n\t  ",
            location="",
            modality="desconocido",
            source_portal="mock",
        )
        res = scorer.evaluate(vac_empty, profile_1)
        assert res.total_score >= 0.0
        assert not res.is_disqualified
        assert isinstance(res.explanatory_summary, str)

    def test_malformed_html_and_xss_safety(self, scorer, profile_1):
        """Ensure evaluator ignores script tags and malformed HTML in descriptions."""
        vac_xss = NormalizedVacancy(
            id="xss_vac",
            title="Ingeniero Civil <script>alert(1)</script>",
            company="Seguridad <img src=x onerror=alert(1)>",
            direct_url="https://example.com/xss",
            full_description=(
                "Requerimos Ingeniero Civil Senior con 15 años de experiencia. "
                "<script>document.location='http://evil.com'</script> "
                "Especialista en vías y pavimentos. 100% remoto en Colombia."
            ),
            modality="remoto",
            source_portal="mock",
        )
        res = scorer.evaluate(vac_xss, profile_1)
        assert res.total_score >= 70.0
        assert "<script>" not in res.explanatory_summary

    def test_score_boundary_tier_thresholds(self, profile_1):
        """Test exact tier boundaries at 70 and 50 points."""
        vac = NormalizedVacancy(
            id="threshold_vac",
            title="Ingeniero Civil",
            company="Empresa",
            direct_url="https://example.com/thresh",
            full_description="Consultoría técnica remota en Colombia.",
            modality="remoto",
            source_portal="mock",
        )
        # 70.0 -> Alta Afinidad
        b70 = ScoreBreakdown(total_score=70.0, modality_score=25.0, seniority_score=25.0, vias_score=20.0)
        s70 = ExplanatorySummaryGenerator.generate(vac, profile_1, b70)
        assert "Alta Afinidad" in s70

        # 69.0 -> Afinidad Moderada
        b69 = ScoreBreakdown(total_score=69.0, modality_score=25.0, seniority_score=25.0, vias_score=19.0)
        s69 = ExplanatorySummaryGenerator.generate(vac, profile_1, b69)
        assert "Afinidad Moderada" in s69

        # 49.0 -> Baja Afinidad
        b49 = ScoreBreakdown(total_score=49.0, modality_score=25.0, seniority_score=14.0, vias_score=10.0)
        s49 = ExplanatorySummaryGenerator.generate(vac, profile_1, b49)
        assert "Baja Afinidad" in s49

    def test_dynamic_5th_profile_extensibility(self, scorer):
        """Validate an arbitrary custom 5th profile created on the fly."""
        custom_profile = ProfileConfig(
            id="profile_5_geotecnia_tuneles",
            name="Especialista en Geotecnia y Túneles",
            target_role="Ingeniero Geotécnico",
            min_total_experience_years=8,
            specializations={
                "geotecnia": SpecializationConfig(
                    name="Geotecnia y Mecánica de Suelos",
                    min_years=4,
                    weight=25.0,
                    keywords=["geotecnia", "geotecnico", "mecanica de suelos", "estabilidad de taludes", "cimentaciones"],
                    boost_keywords=["geotecnia", "geotecnico"],
                ),
                "tuneles": SpecializationConfig(
                    name="Túneles y Obras Subterráneas",
                    min_years=4,
                    weight=25.0,
                    keywords=["tuneles", "obras subterraneas", "excavacion natm"],
                    boost_keywords=["tuneles"],
                ),
            },
            modality=ModalityConfig(strictly_remote=True),
        )
        vac = NormalizedVacancy(
            id="geo_vac",
            title="Especialista Geotécnico en Modelación de Túneles y Taludes (Remoto)",
            company="Geoconsultores Andinos",
            direct_url="https://example.com/geo",
            full_description=(
                "Ingeniero Civil Geotécnico con 10 años de experiencia en estabilidad de taludes, "
                "mecánica de suelos y modelación numérica de túneles. Trabajo 100% remoto en Colombia."
            ),
            modality="remoto",
            source_portal="computrabajo",
        )
        res = scorer.evaluate(vac, custom_profile)
        assert res.total_score >= 75.0
        assert not res.is_disqualified
        assert any("geotecn" in k.lower() for k in res.matched_keywords)
        assert "tuneles" in [k.lower() for k in res.matched_keywords]

