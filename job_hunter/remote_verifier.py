from __future__ import annotations

import logging
import re
import unicodedata
from typing import List, Optional, Tuple

from job_hunter.models import ModalityConfig, ModalityEvaluation, NormalizedVacancy, ProfileConfig

logger = logging.getLogger(__name__)


def _strip_accents(text: str) -> str:
    """Normalize text by folding unicode accents to ASCII equivalents."""
    if not text:
        return ""
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(c for c in normalized if not unicodedata.combining(c)).lower()


# Built-in strict Colombian presential / construction site markers that immediately disqualify
DEFAULT_PRESENTIAL_OBRA_DISQUALIFIERS = [
    r"100%\s*presencial",
    r"totalmente\s*presencial",
    r"presencial\s*en\s*obra",
    r"residente\s*(?:tecnico\s*)?de\s*obra",
    r"residente\s*en\s*obra",
    r"residente\s*tecnico\s*de\s*obra",
    r"director\s*(?:tecnico\s*)?de\s*obra",
    r"director\s*de\s*construccion",
    r"en\s*campamento",
    r"campamento\s*de\s*obra",
    r"vivir\s*en\s*campamento",
    r"pernoctando\s*en\s*campamento",
    r"campamento",
    r"frente\s*de\s*obra",
    r"frentes\s*de\s*obra",
    r"en\s*campo\s*100%",
    r"trabajo\s*en\s*campo",
    r"100%\s*en\s*campo",
    r"disponibilidad\s*para\s*trasladarse\s*a\s*obra",
    r"inspeccion\s*fisica\s*en\s*obra",
    r"inspeccion\s*en\s*campo",
    r"rondas\s*de\s*seguridad\s*en\s*campo",
    r"planta\s*fisica",
    r"planta\s*industrial",
    r"obra\s*vial\s*in\s*situ",
    r"en\s*sitio\s*de\s*obra",
    r"en\s*sitio",
    r"en\s*terreno",
    r"cuadrillas\s*in\s*situ",
    r"jefe\s*de\s*patio",
    r"cantera",
    r"turnos?\s*rotativos?\s*en\s*sitio",
    r"turnos?\s*14x7",
    r"turnos?\s*21x7",
    r"turnos?\s*21/7",
    r"turno\s*21\s*dias",
    r"no\s*es\s*remoto",
    r"sin\s*posibilidad\s*de\s*teletrabajo",
    r"abstenerse\s*.*(?:remoto|virtual|teletrabajo)",
    r"labor\s*100%\s*presencial",
    r"horario\s*presencial",
    r"jornada\s*presencial",
]

# Built-in Colombian positive remote / teletrabajo markers
DEFAULT_POSITIVE_REMOTE_MARKERS = [
    r"100%\s*remoto",
    r"100%\s*virtual",
    r"totalmente\s*remoto",
    r"completamente\s*remoto",
    r"remoto\s*en\s*colombia",
    r"remoto\s*colombia",
    r"remoto\s*nacional",
    r"teletrabajo\s*autonomo",
    r"teletrabajo\s*total",
    r"teletrabajo\s*completo",
    r"teletrabajo\s*colombia",
    r"teletrabajo\s*nacional",
    r"teletrabajo",
    r"trabajo\s*remoto",
    r"trabajo\s*desde\s*casa",
    r"trabajo\s*en\s*casa",
    r"home\s*office",
    r"virtual",
    r"remoto",
    r"a\s*distancia",
    r"modalidad\s*remota",
    r"modalidad\s*virtual",
    r"desde\s*cualquier\s*ciudad\s*(?:de\s*colombia)?",
    r"cualquier\s*lugar\s*de\s*colombia",
    r"cualquier\s*lugar\s*de\s*latinoamerica",
    r"wfh",
]

# Built-in hybrid / partial remote markers
DEFAULT_HYBRID_MARKERS = [
    r"hibrido",
    r"semipresencial",
    r"alternancia",
    r"parcialmente\s*remoto",
    r"esquema\s*mixto",
    r"\d+\s*dias\s*remoto",
    r"\d+\s*dias\s*en\s*casa",
    r"\d+\s*dias\s*en\s*oficina",
    r"reuniones\s*ocasionales",
    r"asistencia\s*parcial",
]

# Geographic disqualifiers for vacancies restricted outside Colombia
DEFAULT_GEOGRAPHIC_DISQUALIFIERS = [
    r"must\s*reside\s*in\s*(?:the\s*)?(?:us|usa|united\s*states)",
    r"us\s*citizens?\s*(?:or\s*green\s*card)?\s*only",
    r"w2\s*only",
    r"green\s*card\s*(?:holder\s*)?required",
    r"florida\s*pe\s*license",
    r"not\s*open\s*to\s*international\s*applicants",
    r"residiendo\s*en\s*estados\s*unidos",
    r"residencia\s*obligatoria\s*en\s*espana",
    r"residir\s*en\s*espana",
    r"residir\s*en\s*santiago\s*de\s*chile",
    r"residir\s*en\s*mexico",
]


class RemoteVerifier:
    """Evaluates job vacancy work modality against candidate profile requirements.

    Implements strict Colombian labor modality verification (Ley 1221 de 2008,
    Ley 2088 de 2021, Ley 2121 de 2021) and acts as gatekeeper against presential
    construction sites (obra/campamento/frente de obra) and geographic exclusions.
    """

    def __init__(self, custom_disqualifiers: Optional[List[str]] = None) -> None:
        self.custom_disqualifiers = custom_disqualifiers or []

    def evaluate(self, vacancy: NormalizedVacancy, profile: ProfileConfig) -> ModalityEvaluation:
        """Evaluate the modality of a vacancy against profile constraints.

        Args:
            vacancy: Normalized vacancy data model.
            profile: Profile configuration specifying modality preferences and disqualifiers.

        Returns:
            ModalityEvaluation with strict remote status, disqualification flags,
            detected modality, and modality score (0.0 to 25.0).
        """
        # Combine all relevant vacancy texts for comprehensive inspection
        fields_to_inspect = [
            vacancy.title or "",
            vacancy.full_description or "",
            vacancy.location or "",
            vacancy.raw_snippet or "",
            vacancy.modality or "",
        ]
        raw_combined = " ".join(fields_to_inspect)
        clean_text = _strip_accents(raw_combined)

        # ---------------------------------------------------------------------
        # STAGE 1: Geographic Disqualification Gate
        # ---------------------------------------------------------------------
        geo_disqualifier_hit = self._check_geographic_disqualifiers(clean_text, vacancy, profile.modality)
        if geo_disqualifier_hit:
            return ModalityEvaluation(
                is_strictly_remote=False,
                is_disqualified=True,
                modality_score=0.0,
                disqualification_reason=f"Restricción geográfica incompatible con Colombia: '{geo_disqualifier_hit}'",
                detected_modality="presencial",
            )

        # Check if presential work is explicitly permitted for this specific location (e.g. Barranquilla)
        allowed_presencial_cities = getattr(profile.modality, "allowed_presencial_cities", None) if profile.modality else None
        is_allowed_presencial = False
        if allowed_presencial_cities:
            is_allowed_presencial = any(
                _strip_accents(c) in clean_text for c in allowed_presencial_cities
            )

        # ---------------------------------------------------------------------
        # STAGE 2: Presential / Obra / Campamento Disqualification Gate
        # ---------------------------------------------------------------------
        presential_disqualifier_hit = self._check_presential_disqualifiers(clean_text, vacancy, profile.modality)
        if presential_disqualifier_hit:
            if is_allowed_presencial:
                max_score = profile.scoring_weights.modality if profile.scoring_weights else 25.0
                return ModalityEvaluation(
                    is_strictly_remote=False,
                    is_disqualified=False,
                    modality_score=float(max_score),
                    disqualification_reason=None,
                    detected_modality="presencial_permitida",
                )
            return ModalityEvaluation(
                is_strictly_remote=False,
                is_disqualified=True,
                modality_score=0.0,
                disqualification_reason=f"Modalidad presencial no permitida: detectado '{presential_disqualifier_hit}'",
                detected_modality="presencial",
            )

        # Explicit declared presential check
        decl_modality = _strip_accents(vacancy.modality or "")
        if decl_modality in ("presencial", "onsite", "on-site", "presential"):
            if is_allowed_presencial:
                max_score = profile.scoring_weights.modality if profile.scoring_weights else 25.0
                return ModalityEvaluation(
                    is_strictly_remote=False,
                    is_disqualified=False,
                    modality_score=float(max_score),
                    disqualification_reason=None,
                    detected_modality="presencial_permitida",
                )
            return ModalityEvaluation(
                is_strictly_remote=False,
                is_disqualified=True,
                modality_score=0.0,
                disqualification_reason="Vacante declarada como 100% presencial",
                detected_modality="presencial",
            )

        # ---------------------------------------------------------------------
        # STAGE 3: Hybrid / Partial Remote Matching
        # ---------------------------------------------------------------------
        is_hybrid, hybrid_hit = self._check_hybrid(clean_text, vacancy)
        if is_hybrid:
            # If profile requires strictly remote, hybrid is allowed but receives partial points (10/25)
            # If profile allows hybrid explicitly, receives higher partial score (18/25)
            if profile.modality and not profile.modality.strictly_remote:
                hybrid_score = 18.0
            else:
                hybrid_score = 10.0

            return ModalityEvaluation(
                is_strictly_remote=False,
                is_disqualified=False,
                modality_score=hybrid_score,
                disqualification_reason=None,
                detected_modality="hibrido",
            )

        # ---------------------------------------------------------------------
        # STAGE 4: Positive Remote / Teletrabajo Matching
        # ---------------------------------------------------------------------
        is_remote, remote_hit = self._check_positive_remote(clean_text, vacancy, profile.modality)
        if is_remote:
            max_score = profile.scoring_weights.modality if profile.scoring_weights else 25.0
            return ModalityEvaluation(
                is_strictly_remote=True,
                is_disqualified=False,
                modality_score=float(max_score),
                disqualification_reason=None,
                detected_modality="remoto",
            )

        # ---------------------------------------------------------------------
        # STAGE 5: Ambiguous / Unstated Modality (Desconocido)
        # ---------------------------------------------------------------------
        # If no explicit markers found, award baseline points (5 pts) and flag as desconocido
        return ModalityEvaluation(
            is_strictly_remote=False,
            is_disqualified=False,
            modality_score=5.0,
            disqualification_reason=None,
            detected_modality="desconocido",
        )

    def _check_geographic_disqualifiers(
        self, clean_text: str, vacancy: NormalizedVacancy, modality_cfg: Optional[ModalityConfig]
    ) -> Optional[str]:
        """Check for geographic constraints that exclude Colombian applicants."""
        # 1. Profile-defined geographic disqualifiers
        if modality_cfg and modality_cfg.geographic_disqualifiers:
            for term in modality_cfg.geographic_disqualifiers:
                clean_term = _strip_accents(term)
                if re.search(r"\b" + re.escape(clean_term) + r"\b", clean_text, flags=re.IGNORECASE):
                    return term

        # 2. Built-in geographic disqualifiers
        for pattern in DEFAULT_GEOGRAPHIC_DISQUALIFIERS:
            match = re.search(pattern, clean_text, flags=re.IGNORECASE)
            if match:
                return match.group(0)

        # 3. Vacancy extra_metadata flags
        if vacancy.extra_metadata:
            if vacancy.extra_metadata.get("us_only"):
                return "Restringido a residentes en EE.UU."
            if vacancy.extra_metadata.get("legal_restriction"):
                return "Restricción legal territorial"

        return None

    def _check_presential_disqualifiers(
        self, clean_text: str, vacancy: NormalizedVacancy, modality_cfg: Optional[ModalityConfig]
    ) -> Optional[str]:
        """Check for on-site, campamento, frente de obra, and presential keywords."""
        # 1. Metadata check
        if vacancy.extra_metadata and vacancy.extra_metadata.get("presential_strict"):
            return "Requerimiento presencial estricto en metadatos"

        # 2. Profile-defined disqualifiers
        if modality_cfg and modality_cfg.disqualifiers:
            for term in modality_cfg.disqualifiers:
                clean_term = _strip_accents(term)
                if re.search(r"\b" + re.escape(clean_term) + r"\b", clean_text, flags=re.IGNORECASE):
                    return term

        # 3. Custom verifier disqualifiers
        for term in self.custom_disqualifiers:
            clean_term = _strip_accents(term)
            if re.search(r"\b" + re.escape(clean_term) + r"\b", clean_text, flags=re.IGNORECASE):
                return term

        # 4. Built-in presential & obra patterns
        for pattern in DEFAULT_PRESENTIAL_OBRA_DISQUALIFIERS:
            match = re.search(pattern, clean_text, flags=re.IGNORECASE)
            if match:
                return match.group(0)

        return None

    def _check_positive_remote(
        self, clean_text: str, vacancy: NormalizedVacancy, modality_cfg: Optional[ModalityConfig]
    ) -> Tuple[bool, Optional[str]]:
        """Check for Colombian remote, teletrabajo, or virtual markers."""
        # Declared modality in normalized vacancy
        decl_modality = _strip_accents(vacancy.modality or "")
        if decl_modality in ("remoto", "remote", "teletrabajo", "virtual"):
            return True, decl_modality

        # Profile allowed modalities matching
        if modality_cfg and modality_cfg.allowed_modalities:
            for term in modality_cfg.allowed_modalities:
                clean_term = _strip_accents(term)
                if re.search(r"\b" + re.escape(clean_term) + r"\b", clean_text, flags=re.IGNORECASE):
                    return True, term

        # Built-in positive remote patterns
        for pattern in DEFAULT_POSITIVE_REMOTE_MARKERS:
            match = re.search(pattern, clean_text, flags=re.IGNORECASE)
            if match:
                return True, match.group(0)

        return False, None

    def _check_hybrid(self, clean_text: str, vacancy: NormalizedVacancy) -> Tuple[bool, Optional[str]]:
        """Check for hybrid or partial remote work indicators."""
        decl_modality = _strip_accents(vacancy.modality or "")
        if decl_modality in ("hibrido", "hybrid", "semipresencial"):
            return True, decl_modality

        for pattern in DEFAULT_HYBRID_MARKERS:
            match = re.search(pattern, clean_text, flags=re.IGNORECASE)
            if match:
                return True, match.group(0)

        return False, None
