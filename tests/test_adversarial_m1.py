import os
import re
import unicodedata
from pathlib import Path
import pytest
import yaml
from pydantic import ValidationError

from job_hunter.config import (
    ProfileError,
    ProfileNotFoundError,
    ProfileParseError,
    ProfileValidationError,
    list_available_profiles,
    load_profile,
    validate_profile_dict,
)
from job_hunter.models import (
    ExperienceRequirement,
    ModalityConfig,
    ModalityEvaluation,
    NormalizedVacancy,
    ProfileConfig,
    ScoreBreakdown,
    ScoringWeights,
    SearchConfig,
    SpecializationConfig,
    TrackerEntry,
)

PROFILES_DIR = Path(__file__).resolve().parent.parent / "profiles"


# =============================================================================
# Adversarial Challenge Suite 1: Corrupted, Truncated, & Malformed Files
# =============================================================================

def test_adversarial_corrupted_syntax_unclosed_quotes(tmp_path):
    """Corrupted YAML with unclosed quotes and illegal indentation."""
    bad_file = tmp_path / "corrupted_syntax.yaml"
    bad_file.write_text("id: 'unclosed_string\n  name: [broken\n    nested: 123", encoding="utf-8")
    with pytest.raises(ProfileParseError) as exc_info:
        load_profile(bad_file)
    assert "YAML parsing error" in str(exc_info.value)
    assert issubclass(ProfileParseError, ProfileError)


def test_adversarial_completely_empty_file(tmp_path):
    """Completely empty file (0 bytes) should raise ProfileValidationError."""
    empty_file = tmp_path / "empty.yaml"
    empty_file.write_text("", encoding="utf-8")
    with pytest.raises(ProfileValidationError) as exc_info:
        load_profile(empty_file)
    assert "must contain a YAML mapping" in str(exc_info.value)


def test_adversarial_whitespace_and_comments_only(tmp_path):
    """File containing only comments and spaces should raise ProfileValidationError."""
    comment_file = tmp_path / "comments.yaml"
    comment_file.write_text("   \n# Just comments\n# Another comment\n  \n", encoding="utf-8")
    with pytest.raises(ProfileValidationError) as exc_info:
        load_profile(comment_file)
    assert "must contain a YAML mapping" in str(exc_info.value)


def test_adversarial_yaml_primitive_scalar(tmp_path):
    """YAML file containing only scalar values (integer, boolean, string) instead of mapping."""
    for scalar in ["42", "true", "'just a string'", "3.14159"]:
        scalar_file = tmp_path / f"scalar_{abs(hash(scalar))}.yaml"
        scalar_file.write_text(scalar, encoding="utf-8")
        with pytest.raises(ProfileValidationError) as exc_info:
            load_profile(scalar_file)
        assert "must contain a YAML mapping" in str(exc_info.value)


def test_adversarial_whitespace_id_lookup():
    """Lookups with whitespace-only or blank paths."""
    with pytest.raises(ProfileValidationError):
        load_profile("")
    with pytest.raises(ProfileNotFoundError):
        load_profile("   ", profiles_dir=PROFILES_DIR)


# =============================================================================
# Adversarial Challenge Suite 2: Boundary Years, Numbers, & Types
# =============================================================================

def test_adversarial_boundary_years_zero():
    """Zero years of experience should be valid (entry level)."""
    valid_data = {
        "id": "junior_remote",
        "name": "Junior Remote Assistant",
        "target_role": "Junior Engineer",
        "min_total_experience_years": 0,
        "specializations": {
            "vias": {"name": "Vias", "min_years": 0, "weight": 0.0}
        },
    }
    profile = validate_profile_dict(valid_data)
    assert profile.min_total_experience_years == 0
    assert profile.specializations["vias"].min_years == 0
    assert profile.specializations["vias"].weight == 0.0


def test_adversarial_negative_experience_boundaries():
    """Negative values at -1, -0.01, -999999 must strictly fail."""
    base_data = {
        "id": "boundary_test",
        "name": "Boundary Test",
        "target_role": "Engineer",
    }

    for bad_years in [-1, -999999]:
        data = {**base_data, "min_total_experience_years": bad_years}
        with pytest.raises(ProfileValidationError):
            validate_profile_dict(data)

    for bad_weight in [-0.01, -50.0]:
        data = {
            **base_data,
            "specializations": {"spec": {"name": "Spec", "weight": bad_weight}},
        }
        with pytest.raises(ProfileValidationError):
            validate_profile_dict(data)


def test_adversarial_extreme_numbers():
    """Very large experience numbers (e.g. 100 years) validate without crash."""
    data = {
        "id": "centenarian_profile",
        "name": "Centenarian Master",
        "target_role": "Master Engineer",
        "min_total_experience_years": 100,
        "specializations": {
            "ancient": {"name": "Ancient Roads", "min_years": 80, "weight": 1000.0}
        },
    }
    profile = validate_profile_dict(data)
    assert profile.min_total_experience_years == 100
    assert profile.specializations["ancient"].min_years == 80
    assert profile.specializations["ancient"].weight == 1000.0


def test_adversarial_type_mismatches():
    """Passing invalid types into schema fields."""
    # min_total_experience_years as non-numeric string
    with pytest.raises(ProfileValidationError):
        validate_profile_dict({
            "id": "bad_type",
            "name": "Bad Type",
            "target_role": "Engineer",
            "min_total_experience_years": "fifteen",
        })

    # modality as integer instead of dict or model
    with pytest.raises(ProfileValidationError):
        validate_profile_dict({
            "id": "bad_modality",
            "name": "Bad Modality",
            "target_role": "Engineer",
            "modality": 12345,
        })

    # scoring_weights as list instead of dict
    with pytest.raises(ProfileValidationError):
        validate_profile_dict({
            "id": "bad_weights",
            "name": "Bad Weights",
            "target_role": "Engineer",
            "scoring_weights": ["not", "a", "dict"],
        })


# =============================================================================
# Adversarial Challenge Suite 3: Special Characters, Diacritics, & Unicode
# =============================================================================

def test_adversarial_spanish_diacritics_and_symbols():
    """Specialization names with complex Spanish accents, tildes, and symbols."""
    data = {
        "id": "perfil_acento_n_o",
        "name": "Ingeniería de Vías, Tránsito & Señalización Vial (SST)",
        "target_role": "Especialista en Diseños Geométricos & Pavimentos Rígidos",
        "min_total_experience_years": 15,
        "specializations": [
            {
                "name": "Vias e Infraestructura Vial",
                "min_years": 5,
                "weight": 35.0,
                "keywords": ["tránsito", "señalización", "año de diseño", "interventoría"],
            },
            {
                "name": "Seguridad y Salud en el Trabajo SST",
                "min_years": 5,
                "weight": 35.0,
                "keywords": ["copasst", "ergonomía", "matriz de riesgos"],
            },
            {
                "name": "Vías & Pavimentación Asfáltica (Invías)",
                "min_years": 5,
                "weight": 30.0,
                "keywords": ["asfalto", "invías"],
            },
        ],
    }
    profile = validate_profile_dict(data)
    assert profile.id == "perfil_acento_n_o"
    assert "vias_e_infraestructura_vial" in profile.specializations
    assert "seguridad_y_salud_en_el_trabajo_sst" in profile.specializations
    assert "vias_pavimentacion_asfaltica_invias" in profile.specializations

    spec1 = profile.specializations["vias_e_infraestructura_vial"]
    assert "tránsito" in spec1.keywords
    assert "año de diseño" in spec1.keywords
    spec3 = profile.specializations["vias_pavimentacion_asfaltica_invias"]
    assert "asfalto" in spec3.keywords



def test_adversarial_specialization_missing_or_none_name():
    """Handling specializations with empty or unusual name values."""
    # List of specializations where item is empty dict (defaults should apply)
    data = {
        "id": "empty_spec_dict",
        "name": "Empty Spec Profile",
        "target_role": "Civil Engineer",
        "specializations": [
            {"name": "Especialidad Vial", "min_years": 3}
        ],
    }
    profile = validate_profile_dict(data)
    assert "especialidad_vial" in profile.specializations


def test_adversarial_special_punctuation_in_queries():
    """Search queries with SQL injection strings, HTML tags, or quotes."""
    adversarial_queries = [
        "Ingeniero Civil'; DROP TABLE jobs; --",
        "<script>alert('xss')</script>",
        "\"Vías\" AND ('SST' OR 'HSEQ') AND NOT 'presencial'",
        "Role with emoji 🚀 🏢 💻",
    ]
    data = {
        "id": "adversarial_queries_profile",
        "name": "Adversarial Queries Profile",
        "target_role": "Civil Engineer",
        "search_queries": adversarial_queries,
    }
    profile = validate_profile_dict(data)
    assert profile.search_queries == adversarial_queries
    assert profile.search_config is not None
    assert profile.search_config.query_strings == adversarial_queries


# =============================================================================
# Adversarial Challenge Suite 4: Multi-Profile Loading & Extensibility
# =============================================================================

def test_adversarial_verify_all_four_profiles_authoritative():
    """Verify all 4 production profiles strictly fulfill domain constraints."""
    profiles = list_available_profiles(profiles_dir=PROFILES_DIR)
    assert len(profiles) >= 4

    p1 = load_profile("profile_1_civil_vias_sst", profiles_dir=PROFILES_DIR)
    assert p1.min_total_experience_years == 15
    assert p1.experience.min_total_years == 15
    assert p1.modality.strictly_remote is True
    assert "vias" in p1.specializations and p1.specializations["vias"].min_years >= 5
    assert "sst" in p1.specializations and p1.specializations["sst"].min_years >= 5
    assert any("copnia" in c.lower() for c in p1.required_credentials)
    assert any("licencia" in c.lower() for c in p1.required_credentials)

    p2 = load_profile("profile_2_gerente_proyectos_viales", profiles_dir=PROFILES_DIR)
    assert p2.min_total_experience_years == 10
    assert "gerencia_vial" in p2.specializations

    p3 = load_profile("profile_3_modelador_bim_vias", profiles_dir=PROFILES_DIR)
    assert p3.min_total_experience_years == 5
    assert "bim_vial" in p3.specializations
    assert p3.modality.strictly_remote is True

    p4 = load_profile("profile_4_consultor_hseq_sig", profiles_dir=PROFILES_DIR)
    assert p4.min_total_experience_years == 8
    assert "sistemas_gestion" in p4.specializations
    assert p4.modality.strictly_remote is True


def test_adversarial_dynamically_injected_5th_profile_in_custom_catalog(tmp_path):
    """Verify isolated custom directory containing 5 dynamic profiles loads and filters."""
    custom_dir = tmp_path / "custom_profiles"
    custom_dir.mkdir()

    # Write 5 distinct profiles
    for i in range(1, 6):
        p_data = {
            "id": f"dynamic_profile_{i}",
            "name": f"Dynamic Specialist Role {i}",
            "target_role": f"Specialist Discipline {i}",
            "min_total_experience_years": i * 3,
            "specializations": {
                f"spec_{i}": {
                    "name": f"Domain Specialization {i}",
                    "min_years": i,
                    "weight": 20.0 + i,
                    "keywords": [f"keyword_{i}_a", f"keyword_{i}_b"],
                }
            },
            "modality": {
                "strictly_remote": (i % 2 == 1),
                "allowed_modalities": ["remoto"],
            },
        }
        with open(custom_dir / f"dynamic_{i}.yaml", "w", encoding="utf-8") as f:
            yaml.safe_dump(p_data, f)

    discovered = list_available_profiles(profiles_dir=custom_dir)
    assert len(discovered) == 5
    discovered_ids = {p.id for p in discovered}
    assert discovered_ids == {f"dynamic_profile_{i}" for i in range(1, 6)}

    # Direct retrieval by ID within custom directory
    p5 = load_profile("dynamic_profile_5", profiles_dir=custom_dir)
    assert p5.id == "dynamic_profile_5"
    assert p5.min_total_experience_years == 15
    assert p5.specializations["spec_5"].weight == 25.0


# =============================================================================
# Adversarial Challenge Suite 5: Domain Models Boundary & Integrity
# =============================================================================

def test_adversarial_score_breakdown_boundaries():
    """ScoreBreakdown must validate 0-100 score ranges and individual subscores."""
    # Valid maximum
    valid_max = ScoreBreakdown(
        total_score=100.0,
        modality_score=25.0,
        seniority_score=25.0,
        vias_score=25.0,
        sst_score=25.0,
        synergy_bonus=10.0,
        penalties=0.0,
    )
    assert valid_max.total_score == 100.0

    # Over 100 total score should fail
    with pytest.raises(ValidationError):
        ScoreBreakdown(total_score=105.0)

    # Negative subscores should fail
    with pytest.raises(ValidationError):
        ScoreBreakdown(modality_score=-1.0)

    with pytest.raises(ValidationError):
        ScoreBreakdown(synergy_bonus=15.0)  # max is 10.0


def test_adversarial_tracker_entry_percentages():
    """TrackerEntry percentage calculation boundary conditions."""
    e0 = TrackerEntry(
        id="0123456789abcdef",
        title="Ingeniera Civil",
        direct_url="https://example.com/job",
        full_description="Desc",
        source_portal="computrabajo",
        score=0.0,
    )
    assert e0.score_percentage == "0%"

    e100 = TrackerEntry(
        id="0123456789abcdef",
        title="Ingeniera Civil",
        direct_url="https://example.com/job",
        full_description="Desc",
        source_portal="computrabajo",
        score=100.0,
    )
    assert e100.score_percentage == "100%"

    e_fractional = TrackerEntry(
        id="0123456789abcdef",
        title="Ingeniera Civil",
        direct_url="https://example.com/job",
        full_description="Desc",
        source_portal="computrabajo",
        score=78.4,
    )
    assert e_fractional.score_percentage == "78%"


# =============================================================================
# Adversarial Challenge Suite 6: Empirical Edge Findings & Bug Probing
# =============================================================================

def test_adversarial_binary_non_utf8_file_behavior(tmp_path):
    """Probing behavior on non-UTF8 binary files."""
    bin_file = tmp_path / "binary_profile.yaml"
    bin_file.write_bytes(b"\xff\xfe\x00\x00\xaa\xbb\xcc")
    # Observes whether UnicodeDecodeError or ProfileError is raised
    with pytest.raises((UnicodeDecodeError, ProfileError)):
        load_profile(bin_file)


def test_adversarial_specialization_name_none_raises_type_error():
    """Empirical demonstration: specialization with name=None raises TypeError."""
    bad_data = {
        "id": "spec_none_name",
        "name": "Test",
        "target_role": "Engineer",
        "specializations": [
            {"name": None, "min_years": 3}
        ],
    }
    with pytest.raises((TypeError, ProfileValidationError)):
        validate_profile_dict(bad_data)


def test_adversarial_specializations_list_of_strings_dropped():
    """Empirical demonstration: list of strings in specializations is dropped to empty dict."""
    data = {
        "id": "spec_strings",
        "name": "Test",
        "target_role": "Engineer",
        "specializations": ["vias", "sst"],
    }
    profile = validate_profile_dict(data)
    assert profile.specializations == {}


def test_adversarial_normalized_vacancy_validation():
    """NormalizedVacancy requires deterministic ID, title, url, description, portal."""
    # Missing required fields
    with pytest.raises(ValidationError):
        NormalizedVacancy(title="Valid Title")

    # Empty title violates min_length=1
    with pytest.raises(ValidationError):
        NormalizedVacancy(
            id="1234567890abcdef",
            title="",  # min_length=1
            direct_url="https://test.com",
            full_description="Desc",
            source_portal="computrabajo",
        )


