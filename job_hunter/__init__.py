"""Multi-Profile Job Tracker & Hunter Engine (Colombia & Remote)."""

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
from job_hunter.config import (
    ProfileError,
    ProfileNotFoundError,
    ProfileParseError,
    ProfileValidationError,
    list_available_profiles,
    load_profile,
    validate_profile_dict,
)
from job_hunter.remote_verifier import RemoteVerifier
from job_hunter.matcher import AffinityScorer
from job_hunter.summary import ExplanatorySummaryGenerator
from job_hunter.dedup import Deduplicator
from job_hunter.storage import (
    CSVTracker,
    DEFAULT_HEADERS,
    EXCEL_STATUS_OPTIONS,
    ExcelTracker,
    IncrementalTracker,
)

__version__ = "0.1.0"

__all__ = [
    "ProfileConfig",
    "ExperienceRequirement",
    "SpecializationConfig",
    "ModalityConfig",
    "ScoringWeights",
    "SearchConfig",
    "NormalizedVacancy",
    "ModalityEvaluation",
    "ScoreBreakdown",
    "TrackerEntry",
    "RemoteVerifier",
    "AffinityScorer",
    "ExplanatorySummaryGenerator",
    "Deduplicator",
    "ExcelTracker",
    "CSVTracker",
    "IncrementalTracker",
    "DEFAULT_HEADERS",
    "EXCEL_STATUS_OPTIONS",
    "load_profile",
    "list_available_profiles",
    "validate_profile_dict",
    "ProfileError",
    "ProfileNotFoundError",
    "ProfileValidationError",
    "ProfileParseError",
]

