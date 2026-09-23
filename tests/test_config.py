from pathlib import Path
import pytest
import yaml

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
# 1. Authoritative Loading Tests for All 4 Defined Profiles
# =============================================================================

def test_load_profile_1_civil_vias_sst():
    """Verify Profile 1 (Ingeniera Civil Senior - Vías & SST) loads with full specs."""
    profile = load_profile("profile_1_civil_vias_sst", profiles_dir=PROFILES_DIR)

    assert isinstance(profile, ProfileConfig)
    assert profile.id == "profile_1_civil_vias_sst"
    assert "Ingeniera Civil" in profile.name
    assert profile.min_total_experience_years == 15
    assert profile.experience.min_total_years == 15
    assert profile.experience.seniority_level == "Senior"

    # Specializations check
    assert "vias" in profile.specializations
    assert "sst" in profile.specializations
    assert profile.specializations["vias"].min_years == 5
    assert profile.specializations["sst"].min_years == 5
    assert len(profile.specializations["vias"].keywords) > 5
    assert len(profile.specializations["sst"].keywords) > 5

    # Modality & Remote Verification rules
    assert profile.modality.strictly_remote is True
    assert "remoto" in profile.modality.allowed_modalities
    assert any("campamento" in d.lower() for d in profile.modality.disqualifiers)
    assert any("residente de obra" in d.lower() for d in profile.modality.disqualifiers)

    # Mandatory Credentials
    assert any("copnia" in cred.lower() for cred in profile.required_credentials)
    assert any("licencia" in cred.lower() for cred in profile.required_credentials)

    # Search Queries & Scoring Weights
    assert len(profile.search_queries) >= 3
    assert profile.scoring_weights.modality == 25.0
    assert profile.scoring_weights.seniority == 25.0
    assert profile.scoring_weights.vias == 25.0
    assert profile.scoring_weights.sst == 25.0
    assert profile.scoring_weights.synergy_bonus == 10.0


def test_load_profile_2_gerente_proyectos_viales():
    """Verify Profile 2 (Gerente / Directora de Proyectos Viales) loads correctly."""
    profile = load_profile("profile_2_gerente_proyectos_viales", profiles_dir=PROFILES_DIR)

    assert isinstance(profile, ProfileConfig)
    assert profile.id == "profile_2_gerente_proyectos_viales"
    assert profile.min_total_experience_years == 10
    assert "gerencia_vial" in profile.specializations
    assert profile.specializations["gerencia_vial"].min_years == 5
    assert any("pmp" in kw.lower() for kw in profile.specializations["gerencia_vial"].keywords)
    assert any("secop" in kw.lower() for kw in profile.specializations["gerencia_vial"].keywords)
    assert any("hibrido" in m.lower() for m in profile.modality.allowed_modalities)


def test_load_profile_3_modelador_bim_vias():
    """Verify Profile 3 (Especialista BIM Civil & Infraestructura Vial) loads correctly."""
    profile = load_profile("profile_3_modelador_bim_vias", profiles_dir=PROFILES_DIR)

    assert isinstance(profile, ProfileConfig)
    assert profile.id == "profile_3_modelador_bim_vias"
    assert profile.min_total_experience_years == 5
    assert "bim_vial" in profile.specializations
    assert profile.specializations["bim_vial"].min_years == 4
    assert any("civil 3d" in kw.lower() for kw in profile.specializations["bim_vial"].keywords)
    assert profile.modality.strictly_remote is True


def test_load_profile_4_consultor_hseq_sig():
    """Verify Profile 4 (Consultora Senior HSEQ & Auditora SIG) loads correctly."""
    profile = load_profile("profile_4_consultor_hseq_sig", profiles_dir=PROFILES_DIR)

    assert isinstance(profile, ProfileConfig)
    assert profile.id == "profile_4_consultor_hseq_sig"
    assert profile.min_total_experience_years == 8
    assert "sistemas_gestion" in profile.specializations
    assert profile.specializations["sistemas_gestion"].min_years == 5
    assert any("iso 45001" in kw.lower() for kw in profile.specializations["sistemas_gestion"].keywords)
    assert any("licencia" in cred.lower() for cred in profile.required_credentials)
    assert profile.modality.strictly_remote is True


# =============================================================================
# 2. Path vs ID Resolution and Discovery Tests
# =============================================================================

def test_load_profile_by_direct_path():
    """Verify loading by direct Path and relative string path."""
    direct_path = PROFILES_DIR / "profile_1_civil_vias_sst.yaml"
    profile_from_path = load_profile(direct_path)
    assert profile_from_path.id == "profile_1_civil_vias_sst"

    rel_path = f"profiles/profile_1_civil_vias_sst.yaml"
    profile_from_rel = load_profile(rel_path)
    assert profile_from_rel.id == "profile_1_civil_vias_sst"


def test_list_available_profiles():
    """Verify discovery of all available profile definitions."""
    profiles = list_available_profiles(profiles_dir=PROFILES_DIR)
    assert len(profiles) >= 4

    ids = {p.id for p in profiles}
    expected_ids = {
        "profile_1_civil_vias_sst",
        "profile_2_gerente_proyectos_viales",
        "profile_3_modelador_bim_vias",
        "profile_4_consultor_hseq_sig",
    }
    assert expected_ids.issubset(ids)


def test_list_available_profiles_nonexistent_dir(tmp_path):
    """Verify listing profiles in an empty/nonexistent directory returns empty list."""
    empty_dir = tmp_path / "empty_profiles"
    result = list_available_profiles(profiles_dir=empty_dir)
    assert result == []


# =============================================================================
# 3. Schema Validation & Constraints Tests
# =============================================================================

def test_schema_constraints_negative_experience():
    """Reject profile with negative minimum experience years."""
    bad_data = {
        "id": "test_invalid_exp",
        "name": "Invalid Exp Profile",
        "target_role": "Tester",
        "min_total_experience_years": -5,
    }
    with pytest.raises(ProfileValidationError) as excinfo:
        validate_profile_dict(bad_data)
    assert "min_total_experience_years" in str(excinfo.value)


def test_schema_constraints_negative_specialization_years():
    """Reject specialization with negative experience years."""
    bad_data = {
        "id": "test_invalid_spec",
        "name": "Invalid Spec Profile",
        "target_role": "Tester",
        "specializations": {
            "vias": {
                "name": "Vias",
                "min_years": -2,
            }
        },
    }
    with pytest.raises(ProfileValidationError) as excinfo:
        validate_profile_dict(bad_data)
    assert "min_years" in str(excinfo.value)


def test_schema_constraints_missing_required_fields():
    """Reject profile missing essential identity fields (id, name, target_role)."""
    # Missing ID
    with pytest.raises(ProfileValidationError):
        validate_profile_dict({"name": "No ID", "target_role": "Tester"})

    # Empty ID
    with pytest.raises(ProfileValidationError):
        validate_profile_dict({"id": "", "name": "Empty ID", "target_role": "Tester"})

    # Missing name
    with pytest.raises(ProfileValidationError):
        validate_profile_dict({"id": "valid_id", "target_role": "Tester"})

    # Missing target_role
    with pytest.raises(ProfileValidationError):
        validate_profile_dict({"id": "valid_id", "name": "Valid Name"})


def test_validate_profile_dict_non_dict_input():
    """Reject non-dictionary inputs to validate_profile_dict."""
    with pytest.raises(ProfileValidationError):
        validate_profile_dict(["not", "a", "dict"])

    with pytest.raises(ProfileValidationError):
        validate_profile_dict("string_input")


# =============================================================================
# 4. Multi-Profile Extensibility: Dynamic 5th Profile Without Code Change
# =============================================================================

def test_dynamic_5th_profile_extensibility(tmp_path):
    """Verify adding a 5th profile purely via configuration without code changes."""
    profile_5_data = {
        "id": "profile_5_geotecnia_tuneles",
        "name": "Ingeniero Especialista en Geotecnia y Túneles Viales",
        "target_role": "Especialista Geotécnico de Obras Subterráneas",
        "min_total_experience_years": 7,
        "specializations": {
            "geotecnia": {
                "name": "Geotecnia y Mecánica de Rocas",
                "min_years": 4,
                "weight: 30.0": None,  # Will test clean parsing
                "keywords": ["geotecnia", "taludes", "mecánica de rocas", "cálculo de empujes"],
            },
            "tuneles": {
                "name": "Excavación y Soporte de Túneles",
                "min_years": 3,
                "keywords": ["túnel", "perforación y voladura", "concreto lanzado", "natm"],
            },
        },
        "modality": {
            "strictly_remote": True,
            "allowed_modalities": ["remoto", "virtual", "teletrabajo"],
            "disqualifiers": ["residente de frente subterráneo", "campamento minero 14x7"],
        },
        "required_credentials": ["Tarjeta Profesional COPNIA"],
        "search_queries": ["Especialista Geotécnico Remoto", "Consultor Túneles Virtual"],
    }

    # Clean up weight test key
    profile_5_data["specializations"]["geotecnia"]["weight"] = 30.0
    del profile_5_data["specializations"]["geotecnia"]["weight: 30.0"]

    # 1. Validate dictionary directly
    profile_5 = validate_profile_dict(profile_5_data)
    assert profile_5.id == "profile_5_geotecnia_tuneles"
    assert profile_5.min_total_experience_years == 7
    assert "geotecnia" in profile_5.specializations
    assert "tuneles" in profile_5.specializations

    # 2. Write to a new YAML file and load via load_profile
    file_path = tmp_path / "profile_5_geotecnia_tuneles.yaml"
    with open(file_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(profile_5_data, f)

    loaded_5 = load_profile(file_path)
    assert loaded_5.id == "profile_5_geotecnia_tuneles"
    assert loaded_5.target_role == "Especialista Geotécnico de Obras Subterráneas"
    assert loaded_5.modality.strictly_remote is True
    assert "residente de frente subterráneo" in loaded_5.modality.disqualifiers


# =============================================================================
# 5. Error Handling Tests (Corrupted YAML, Missing Files)
# =============================================================================

def test_corrupted_yaml_handling(tmp_path):
    """Verify clear ProfileParseError on malformed YAML syntax."""
    corrupted_file = tmp_path / "corrupted_profile.yaml"
    with open(corrupted_file, "w", encoding="utf-8") as f:
        f.write("id: test\nname: [unclosed list\n  key: value\n")

    with pytest.raises(ProfileParseError) as excinfo:
        load_profile(corrupted_file)
    assert "YAML parsing error" in str(excinfo.value)


def test_nonexistent_profile_handling():
    """Verify ProfileNotFoundError when target file or ID does not exist."""
    with pytest.raises(ProfileNotFoundError):
        load_profile("this_profile_does_not_exist_anywhere", profiles_dir=PROFILES_DIR)


def test_empty_path_or_id_handling():
    """Verify ProfileValidationError when path_or_id is empty string."""
    with pytest.raises(ProfileValidationError):
        load_profile("")


def test_yaml_non_dict_content(tmp_path):
    """Verify ProfileValidationError when YAML contains a list instead of a dict."""
    list_file = tmp_path / "list_profile.yaml"
    with open(list_file, "w", encoding="utf-8") as f:
        f.write("- item1\n- item2\n")

    with pytest.raises(ProfileValidationError) as excinfo:
        load_profile(list_file)
    assert "must contain a YAML mapping" in str(excinfo.value)


# =============================================================================
# 6. Domain Entity Instantiation & Serialization Tests
# =============================================================================

def test_models_instantiation_and_serialization():
    """Verify NormalizedVacancy, ModalityEvaluation, ScoreBreakdown, TrackerEntry."""
    vacancy = NormalizedVacancy(
        id="a1b2c3d4e5f60718",
        title="Directora de Interventoría Vial Remota",
        company="Consorcio Vial Andino",
        direct_url="https://portal.com/oferta/123",
        full_description="Descripción detallada de la oferta...",
        source_portal="computrabajo",
        modality="remoto",
        salary_range="$10.000.000 - $14.000.000 COP",
    )
    assert vacancy.id == "a1b2c3d4e5f60718"
    assert vacancy.company == "Consorcio Vial Andino"

    mod_eval = ModalityEvaluation(
        is_strictly_remote=True,
        is_disqualified=False,
        modality_score=25.0,
        detected_modality="remoto",
    )
    assert mod_eval.is_strictly_remote is True
    assert mod_eval.modality_score == 25.0

    breakdown = ScoreBreakdown(
        total_score=92.5,
        modality_score=25.0,
        seniority_score=25.0,
        vias_score=25.0,
        sst_score=17.5,
        synergy_bonus=10.0,
        is_disqualified=False,
        explanatory_summary="Alta afinidad en Vías y SST.",
    )
    assert breakdown.total_score == 92.5
    assert breakdown.synergy_bonus == 10.0

    entry = TrackerEntry(
        id=vacancy.id,
        title=vacancy.title,
        company=vacancy.company,
        direct_url=vacancy.direct_url,
        full_description=vacancy.full_description,
        source_portal=vacancy.source_portal,
        score=92.5,
        explanatory_summary=breakdown.explanatory_summary,
        estado="Nueva",
    )
    assert entry.score == 92.5
    assert entry.score_percentage == "93%" or entry.score_percentage == "92%"
    assert entry.estado == "Nueva"

    dumped = entry.model_dump()
    assert dumped["id"] == "a1b2c3d4e5f60718"
    assert dumped["score"] == 92.5

    json_str = entry.model_dump_json()
    assert "Directora de Interventoría Vial Remota" in json_str


# =============================================================================
# 7. Additional Boundary & Normalization Tests
# =============================================================================

def test_load_profile_by_id_default_discovery():
    """Verify loading by ID uses default discovery paths when profiles_dir is None."""
    profile = load_profile("profile_1_civil_vias_sst")
    assert profile.id == "profile_1_civil_vias_sst"


def test_load_profile_by_short_id():
    """Verify loading by short ID (without 'profile_' prefix) resolves correctly."""
    profile = load_profile("1_civil_vias_sst", profiles_dir=PROFILES_DIR)
    assert profile.id == "profile_1_civil_vias_sst"


def test_profile_nested_structure_normalization():
    """Verify normalization of nested profile/candidate/certifications structures."""
    nested_data = {
        "profile": {
            "id": "nested_spec_profile",
            "name": "Nested Spec Profile",
            "version": "2.0.0",
            "active": True,
        },
        "candidate": {
            "discipline": "Ingeniería de Transportes",
            "total_experience_years": 12,
            "mandatory_credentials": ["Tarjeta COPNIA", "Licencia SST"],
        },
        "search_parameters": {
            "query_strings": ["Transportes Remoto Colombia"],
        },
        "modality_requirements": {
            "strict_remote": True,
            "disqualifying_terms": ["obra presencial"],
        },
        "specializations": [
            {
                "name": "Tránsito y Movilidad",
                "min_years": 4,
                "weight": 30.0,
                "keywords": ["vissim", "synchro", "aforo"],
            }
        ],
    }

    profile = validate_profile_dict(nested_data)
    assert profile.id == "nested_spec_profile"
    assert profile.name == "Nested Spec Profile"
    assert profile.version == "2.0.0"
    assert profile.target_role == "Ingeniería de Transportes"
    assert profile.min_total_experience_years == 12
    assert profile.experience.min_total_years == 12
    assert "Tarjeta COPNIA" in profile.required_credentials
    assert "Transportes Remoto Colombia" in profile.search_queries
    assert profile.modality.strictly_remote is True
    assert "obra presencial" in profile.modality.disqualifiers
    assert "transito_y_movilidad" in profile.specializations
    assert profile.specializations["transito_y_movilidad"].min_years == 4


def test_tracker_entry_percentage_computation():
    """Verify TrackerEntry correctly formats score_percentage from float score."""
    entry1 = TrackerEntry(
        id="hash000000000001",
        title="Ingeniera Civil Remota",
        direct_url="https://portal.com/job1",
        full_description="Desc",
        source_portal="computrabajo",
        score=78.6,
    )
    assert entry1.score_percentage == "79%"

    entry2 = TrackerEntry(
        id="hash000000000002",
        title="Ingeniera Civil Remota 2",
        direct_url="https://portal.com/job2",
        full_description="Desc",
        source_portal="elempleo",
        score=0.0,
    )
    assert entry2.score_percentage == "0%"


def test_specialization_weight_and_years_validation():
    """Verify SpecializationConfig constraints on weight and min_years."""
    with pytest.raises(ValueError):
        SpecializationConfig(name="Bad Spec", min_years=-1)

    with pytest.raises(ValueError):
        SpecializationConfig(name="Bad Spec", weight=-5.0)

    valid_spec = SpecializationConfig(name="Good Spec", min_years=3, weight=20.0)
    assert valid_spec.min_years == 3
    assert valid_spec.weight == 20.0


def test_experience_requirement_negative_years():
    """Verify ExperienceRequirement rejects negative min_total_years."""
    with pytest.raises(ValueError):
        ExperienceRequirement(min_total_years=-1)


def test_search_config_defaults_and_validation():
    """Verify SearchConfig defaults and bounds."""
    cfg = SearchConfig()
    assert "Colombia" in cfg.locations
    assert cfg.max_pages_per_portal == 3
    assert cfg.date_posted_limit_days == 30

    with pytest.raises(ValueError):
        SearchConfig(max_pages_per_portal=0)

