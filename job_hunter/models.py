from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field, field_validator, model_validator, ConfigDict


class SpecializationConfig(BaseModel):
    """Configuration for a specific domain specialization within a profile."""
    model_config = ConfigDict(extra="allow")

    name: str = Field(..., description="Specialization name (e.g. 'Vías e Infraestructura Vial')")
    min_years: int = Field(default=0, ge=0, description="Minimum years of specific experience required")
    weight: float = Field(default=25.0, ge=0.0, description="Scoring weight for this specialization")
    keywords: List[str] = Field(default_factory=list, description="Primary technical keywords")
    boost_keywords: List[str] = Field(default_factory=list, description="High-priority boost keywords")

    @field_validator("min_years")
    @classmethod
    def validate_min_years(cls, v: int) -> int:
        if v < 0:
            raise ValueError("min_years must be non-negative")
        return v

    @field_validator("weight")
    @classmethod
    def validate_weight(cls, v: float) -> float:
        if v < 0.0:
            raise ValueError("weight must be non-negative")
        return v


class ExperienceRequirement(BaseModel):
    """Detailed experience requirements for a profile."""
    model_config = ConfigDict(extra="allow")

    min_total_years: int = Field(default=0, ge=0, description="Minimum general professional experience in years")
    seniority_level: str = Field(default="Senior", description="Seniority classification (e.g. 'Senior', 'Director')")
    primary_discipline: str = Field(default="Ingeniería Civil", description="Primary professional field/degree")
    specialties: Dict[str, SpecializationConfig] = Field(default_factory=dict, description="Domain specialties")

    @field_validator("min_total_years")
    @classmethod
    def validate_min_total_years(cls, v: int) -> int:
        if v < 0:
            raise ValueError("min_total_years must be non-negative")
        return v


class ModalityConfig(BaseModel):
    """Requirements and exclusions regarding work modality (remote, hybrid, on-site)."""
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    strictly_remote: bool = Field(
        default=True,
        alias="strict_remote",
        description="Whether vacancy must be strictly remote/teletrabajo",
    )
    allowed_modalities: List[str] = Field(
        default_factory=lambda: ["remoto", "virtual", "teletrabajo", "home office"],
        description="Allowed work modalities",
    )
    allowed_presencial_cities: List[str] = Field(
        default_factory=lambda: [
            "Barranquilla",
            "Atlántico",
            "Atlantico",
            "Puerto Colombia",
            "Soledad",
            "Galapa",
            "Malambo",
        ],
        description="Cities where presential work is permitted for the candidate",
    )
    disqualifiers: List[str] = Field(
        default_factory=lambda: [
            "100% presencial",
            "presencial en obra",
            "residente de obra",
            "campamento",
            "en campamento",
            "frente de obra",
        ],
        alias="disqualifying_terms",
        description="Expressions that immediately disqualify the vacancy",
    )
    allowed_countries: List[str] = Field(
        default_factory=lambda: ["Colombia", "Remoto", "Global", "Latinoamérica"],
        description="Allowed geographic locations",
    )
    geographic_disqualifiers: List[str] = Field(
        default_factory=lambda: [
            "must reside in usa",
            "us citizens only",
            "w2 only",
            "green card required",
        ],
        description="Geographic exclusion markers",
    )


class ScoringWeights(BaseModel):
    """Weight distribution and thresholds for scoring vacancies."""
    model_config = ConfigDict(extra="allow")

    modality: float = Field(default=25.0, ge=0.0, description="Weight for modality compliance")
    seniority: float = Field(default=25.0, ge=0.0, description="Weight for seniority/experience")
    vias: float = Field(default=25.0, ge=0.0, description="Weight for Vías specialization")
    sst: float = Field(default=25.0, ge=0.0, description="Weight for SST specialization")
    synergy_bonus: float = Field(default=10.0, ge=0.0, description="Bonus when dual specializations match")
    min_score_to_save: float = Field(default=50.0, ge=0.0, description="Minimum score to track")
    high_affinity_threshold: float = Field(default=70.0, ge=0.0, description="Threshold for high affinity")


class SearchConfig(BaseModel):
    """Parameters governing portal scraping queries."""
    model_config = ConfigDict(extra="allow")

    locations: List[str] = Field(
        default_factory=lambda: ["Colombia", "Remoto", "Bogotá"],
        description="Target search locations",
    )
    modalities: List[str] = Field(
        default_factory=lambda: ["remoto", "virtual", "teletrabajo"],
        description="Target modalities",
    )
    portals: List[str] = Field(
        default_factory=lambda: ["computrabajo", "elempleo", "linkedin"],
        description="Target job portals",
    )
    max_pages_per_portal: int = Field(default=3, ge=1, description="Max search result pages per portal")
    date_posted_limit_days: int = Field(default=30, ge=1, description="Max days since publication")
    query_strings: List[str] = Field(default_factory=list, description="Search queries submitted to scrapers")


class ProfileConfig(BaseModel):
    """Complete declarative configuration for an active candidate profile."""
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    id: str = Field(..., min_length=1, description="Unique profile identifier (slug)")
    name: str = Field(..., min_length=1, description="Human-readable profile name")
    target_role: str = Field(..., min_length=1, description="Target professional role")
    min_total_experience_years: int = Field(
        default=0,
        ge=0,
        description="Minimum total professional experience required",
    )
    specializations: Dict[str, SpecializationConfig] = Field(
        default_factory=dict,
        description="Dictionary of domain specializations",
    )
    modality: ModalityConfig = Field(
        default_factory=ModalityConfig,
        description="Modality requirements and disqualification filters",
    )
    required_credentials: List[str] = Field(
        default_factory=list,
        description="Mandatory credentials (e.g. COPNIA, Licencia SST)",
    )
    search_queries: List[str] = Field(
        default_factory=list,
        description="Search query strings for scraper engines",
    )
    scoring_weights: ScoringWeights = Field(
        default_factory=ScoringWeights,
        description="Scoring weights and thresholds",
    )
    experience: Optional[ExperienceRequirement] = Field(
        default=None,
        description="Detailed experience specification",
    )
    search_config: Optional[SearchConfig] = Field(
        default=None,
        description="Detailed scraper search configuration",
    )
    scoring_thresholds: Dict[str, float] = Field(
        default_factory=dict,
        description="Additional scoring thresholds",
    )
    active: bool = Field(default=True, description="Whether the profile is active")
    version: str = Field(default="1.0.0", description="Configuration version")

    @field_validator("min_total_experience_years")
    @classmethod
    def validate_min_experience_years(cls, v: int) -> int:
        if v < 0:
            raise ValueError("min_total_experience_years must be non-negative")
        return v

    @model_validator(mode="before")
    @classmethod
    def normalize_profile_input(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        d = dict(data)

        # 1. Unnest top-level "profile" block if present
        if "profile" in d and isinstance(d["profile"], dict):
            sub_prof = d["profile"]
            for k in ["id", "name", "version", "active"]:
                if k in sub_prof and k not in d:
                    d[k] = sub_prof[k]

        # 2. Unnest "candidate" block if present
        if "candidate" in d and isinstance(d["candidate"], dict):
            cand = d["candidate"]
            if "total_experience_years" in cand and "min_total_experience_years" not in d:
                d["min_total_experience_years"] = cand["total_experience_years"]
            if "mandatory_credentials" in cand and "required_credentials" not in d:
                d["required_credentials"] = cand["mandatory_credentials"]
            if "discipline" in cand and "target_role" not in d:
                d["target_role"] = cand["discipline"]

        # 3. Canonical target_role unwrap if dict
        if isinstance(d.get("target_role"), dict):
            d["target_role"] = d["target_role"].get("canonical_title", "")

        # 4. Normalize experience block
        if "experience" in d and isinstance(d["experience"], dict):
            exp = d["experience"]
            if "min_total_years" in exp and "min_total_experience_years" not in d:
                d["min_total_experience_years"] = exp["min_total_years"]

        # 5. Normalize modality block alias
        if "modality_requirements" in d and "modality" not in d:
            d["modality"] = d["modality_requirements"]

        # 6. Normalize search queries / search parameters
        if "search_parameters" in d and isinstance(d["search_parameters"], dict):
            sp = d["search_parameters"]
            if "query_strings" in sp and "search_queries" not in d:
                d["search_queries"] = sp["query_strings"]
        elif "search_queries" in d and isinstance(d["search_queries"], dict):
            sq = d["search_queries"]
            if "terms" in sq:
                d["search_queries"] = sq["terms"]

        # 7. Normalize specializations if provided as list
        if "specializations" in d and isinstance(d["specializations"], list):
            import unicodedata
            spec_dict = {}
            for item in d["specializations"]:
                if isinstance(item, dict):
                    raw_name = item.get("name", "spec")
                    clean_name = unicodedata.normalize("NFKD", raw_name).encode("ascii", "ignore").decode("utf-8")
                    slug = re.sub(r"[^a-zA-Z0-9_]+", "_", clean_name).strip("_").lower()
                    spec_dict[slug] = item
            d["specializations"] = spec_dict

        # 8. Normalize certifications block
        if "certifications" in d and isinstance(d["certifications"], dict):
            certs = d["certifications"]
            if "mandatory" in certs and "required_credentials" not in d:
                d["required_credentials"] = certs["mandatory"]

        return d

    @model_validator(mode="after")
    def sync_nested_components(self) -> "ProfileConfig":
        # Synchronize experience model
        if self.experience is None:
            self.experience = ExperienceRequirement(
                min_total_years=self.min_total_experience_years,
                seniority_level="Senior",
                primary_discipline=self.target_role,
            )
        else:
            if self.min_total_experience_years > 0 and self.experience.min_total_years == 0:
                self.experience.min_total_years = self.min_total_experience_years
            elif self.experience.min_total_years > 0 and self.min_total_experience_years == 0:
                self.min_total_experience_years = self.experience.min_total_years

        # Synchronize search_config model
        if self.search_config is None and self.search_queries:
            self.search_config = SearchConfig(query_strings=self.search_queries)

        return self


class NormalizedVacancy(BaseModel):
    """Standardized representation of a scraped job opportunity."""
    model_config = ConfigDict(extra="allow")

    id: str = Field(..., description="Deterministic 16-hex SHA-256 hash")
    title: str = Field(..., min_length=1, description="Job title")
    company: str = Field(default="Confidencial", description="Company or hiring entity")
    direct_url: str = Field(..., description="Direct URL to job offer")
    full_description: str = Field(..., description="Full text description of the vacancy")
    publication_date: Optional[str] = Field(default=None, description="Publication date (ISO or portal string)")
    location: str = Field(default="Colombia", description="Location declared by employer")
    modality: str = Field(default="remoto", description="Modality: remoto, hibrido, presencial, desconocido")
    salary_range: Optional[str] = Field(default=None, description="Salary range or text")
    source_portal: str = Field(..., description="Job portal: computrabajo, elempleo, linkedin, etc.")
    raw_snippet: Optional[str] = Field(default=None, description="Brief card snippet")
    detection_date: Optional[str] = Field(
        default_factory=lambda: datetime.now().isoformat(),
        description="Timestamp when the vacancy was first detected",
    )
    extra_metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional scraper metadata")


class ModalityEvaluation(BaseModel):
    """Result of evaluating the work modality of a job vacancy against profile rules."""
    model_config = ConfigDict(extra="allow")

    is_strictly_remote: bool = Field(..., description="Whether vacancy meets remote criteria")
    is_disqualified: bool = Field(default=False, description="Whether vacancy is disqualified due to presential markers")
    modality_score: float = Field(default=0.0, ge=0.0, le=25.0, description="Modality score (0-25)")
    disqualification_reason: Optional[str] = Field(default=None, description="Reason if disqualified")
    detected_modality: str = Field(default="remoto", description="Detected modality (remoto, hibrido, presencial)")


class ScoreBreakdown(BaseModel):
    """Multi-dimensional scoring breakdown and explanatory findings for a vacancy."""
    model_config = ConfigDict(extra="allow")

    total_score: float = Field(default=0.0, ge=0.0, le=100.0, description="Composite affinity score (0-100)")
    modality_score: float = Field(default=0.0, ge=0.0, le=25.0, description="Modality score (0-25)")
    seniority_score: float = Field(default=0.0, ge=0.0, le=25.0, description="Seniority score (0-25)")
    vias_score: float = Field(default=0.0, ge=0.0, le=25.0, description="Vías specialization score (0-25)")
    sst_score: float = Field(default=0.0, ge=0.0, le=25.0, description="SST specialization score (0-25)")
    synergy_bonus: float = Field(default=0.0, ge=0.0, le=10.0, description="Dual specialization synergy bonus (0-10)")
    penalties: float = Field(default=0.0, ge=0.0, description="Applied penalties")
    is_disqualified: bool = Field(default=False, description="Whether vacancy was disqualified")
    explanatory_summary: str = Field(default="", description="Explanatory summary of evaluation")
    matched_keywords: List[str] = Field(default_factory=list, description="Keywords matched in text")
    missing_requirements: List[str] = Field(default_factory=list, description="Requirements identified as missing")


class TrackerEntry(NormalizedVacancy):
    """A scored and tracked vacancy entry ready for Excel and CSV persistence."""
    score: float = Field(default=0.0, ge=0.0, le=100.0, description="Affinity score (0-100)")
    score_percentage: str = Field(default="0%", description="Formatted percentage string (e.g. '92%')")
    explanatory_summary: str = Field(default="", description="Summary explaining why it matched or disqualified")
    estado: str = Field(
        default="Nueva",
        description="Tracking status: Nueva, Por revisar, Postulado, En proceso, Entrevista, Oferta, Descartado",
    )
    fecha_deteccion: str = Field(
        default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M"),
        description="Formatted detection date string",
    )
    notas_usuario: str = Field(default="", description="User notes or remarks")
    fecha_postulacion: Optional[str] = Field(default=None, description="Date candidate applied")
    perfil_id: Optional[str] = Field(default=None, description="Profile ID under which vacancy was evaluated")

    @model_validator(mode="after")
    def compute_percentage(self) -> "TrackerEntry":
        if not self.score_percentage or self.score_percentage == "0%":
            self.score_percentage = f"{int(round(self.score))}%"
        return self
