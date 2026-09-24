from __future__ import annotations

import logging
import re
import unicodedata
from typing import Dict, List, Optional, Set, Tuple

from job_hunter.models import (
    ModalityEvaluation,
    NormalizedVacancy,
    ProfileConfig,
    ScoreBreakdown,
    SpecializationConfig,
)
from job_hunter.remote_verifier import RemoteVerifier
from job_hunter.summary import ExplanatorySummaryGenerator

logger = logging.getLogger(__name__)


def _strip_accents(text: str) -> str:
    """Normalize text by folding unicode accents to ASCII equivalents."""
    if not text:
        return ""
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(c for c in normalized if not unicodedata.combining(c)).lower()


# Negative disciplines that are completely unrelated to civil engineering / infrastructure / HSEQ
NEGATIVE_DISCIPLINES = [
    r"desarrollador(?:\s*de)?\s*software",
    r"software\s*engineer",
    r"fullstack(?:\s*developer)?",
    r"full\s*stack(?:\s*developer)?",
    r"frontend(?:\s*developer)?",
    r"backend(?:\s*developer)?",
    r"python\s*/\s*react",
    r"programador",
    r"m[eé]dico",
    r"enfermer[ao]",
    r"contador(?:\s*p[uú]blico)?",
    r"abogado",
    r"call\s*center",
    r"asesor\s*comercial\s*de\s*mostrador",
    r"vendedor\s*de\s*mostrador",
    r"dise[nñ]ador\s*gr[aá]fico",
]

# Junior / Entry-level / Trainee markers that warrant seniority penalties
JUNIOR_MARKERS = [
    r"\bjunior\b",
    r"\bjr\b",
    r"\bpracticante\b",
    r"\btrainee\b",
    r"\bpasant[ií]a\b",
    r"\breci[eé]n\s*graduad[oa]\b",
    r"\bsin\s*experiencia\b",
    r"\bm[aá]ximo\s*1\s*a[nñ]o\b",
    r"\b1\s*a[nñ]o\s*de\s*experiencia\b",
    r"\b0\s*-\s*1\s*a[nñ]os\b",
]

# Seniority boost tokens for senior / leadership roles
SENIOR_TOKENS = [
    r"\bsenior\b",
    r"\bsr\b",
    r"\bdirector\b",
    r"\bdirectora\b",
    r"\bgerente\b",
    r"\bl[ií]der\b",
    r"\bespecialista\s*principal\b",
    r"\bamplia\s*trayectoria\b",
    r"\b1[0-9]\s*\+?\s*a[nñ]os\b",
    r"\b20\s*\+?\s*a[nñ]os\b",
]


class AffinityScorer:
    """Multi-dimensional affinity scoring engine for job vacancies.

    Computes composite affinity score (0 to 100) combining:
    - Modality score (0-25 pts): from RemoteVerifier with strict Colombian teletrabajo rules.
    - Core domain & seniority score (0-25 pts): title alignment and professional experience.
    - Specialization 1 score (0-25 pts): primary specialization keyword match.
    - Specialization 2 score (0-25 pts): secondary specialization keyword match.
    - Synergy bonus (+10 pts): awarded when dual specializations are matched.
    - Penalties: disqualifications (-100 pts), unrelated professions (-60 pts), junior roles (-10 pts).
    """

    def __init__(self, remote_verifier: Optional[RemoteVerifier] = None) -> None:
        self.remote_verifier = remote_verifier or RemoteVerifier()

    def evaluate(self, vacancy: NormalizedVacancy, profile: ProfileConfig) -> ScoreBreakdown:
        """Evaluate a normalized vacancy against the active profile configuration.

        Args:
            vacancy: Normalized vacancy data model.
            profile: Declarative ProfileConfig instance.

        Returns:
            ScoreBreakdown containing subscores, total clamped score, explanatory summary,
            matched keywords, and missing requirements.
        """
        combined_text = (
            f"{vacancy.title or ''} {vacancy.full_description or ''} "
            f"{vacancy.location or ''} {vacancy.raw_snippet or ''}"
        )
        clean_text = _strip_accents(combined_text)
        title_clean = _strip_accents(vacancy.title or "")

        penalties = 0.0
        is_disqualified = False
        all_matched_keywords: List[str] = []

        # ---------------------------------------------------------------------
        # 1. Modality Evaluation (0 to 25 pts)
        # ---------------------------------------------------------------------
        modality_eval = self.remote_verifier.evaluate(vacancy, profile)
        modality_score = float(modality_eval.modality_score)

        if modality_eval.is_disqualified:
            is_disqualified = True
            penalties += 100.0

        # ---------------------------------------------------------------------
        # 2. Core Domain & Seniority Evaluation (0 to 25 pts)
        # ---------------------------------------------------------------------
        seniority_score, seniority_penalty, is_unrelated = self._evaluate_seniority(
            title_clean, clean_text, vacancy, profile
        )
        penalties += seniority_penalty
        if is_unrelated:
            penalties += 60.0

        # ---------------------------------------------------------------------
        # 3. Specializations Evaluation (0 to 25 pts each)
        # ---------------------------------------------------------------------
        spec_scores: Dict[str, float] = {}
        for spec_key, spec_cfg in profile.specializations.items():
            score, matched = self._evaluate_specialization(clean_text, spec_cfg)
            spec_scores[spec_key] = score
            all_matched_keywords.extend(matched)

        # Map to vias_score and sst_score for backwards compatibility with ScoreBreakdown schema
        # Note: ScoreBreakdown enforces le=25.0 on vias_score and sst_score
        vias_score = 0.0
        sst_score = 0.0

        if "vias" in spec_scores:
            vias_score = min(25.0, spec_scores["vias"])
        elif spec_scores:
            vias_score = min(25.0, list(spec_scores.values())[0])

        if "sst" in spec_scores:
            sst_score = min(25.0, spec_scores["sst"])
        elif len(spec_scores) > 1:
            sst_score = min(25.0, list(spec_scores.values())[1])

        # ---------------------------------------------------------------------
        # 4. Synergy Bonus (+10 pts)
        # ---------------------------------------------------------------------
        synergy_bonus = 0.0
        bonus_val = (
            profile.scoring_weights.synergy_bonus
            if profile.scoring_weights
            else 10.0
        )

        # Check if at least two specializations have significant match (>= 10 pts)
        qualifying_specs = [s for s in spec_scores.values() if s >= 10.0]
        if len(qualifying_specs) >= 2 or (vias_score >= 10.0 and sst_score >= 10.0):
            synergy_bonus = float(bonus_val)

        # ---------------------------------------------------------------------
        # 5. Composite Score Calculation & Clamping
        # ---------------------------------------------------------------------
        if is_disqualified:
            total_score = 0.0
        else:
            raw_sum = (
                modality_score
                + seniority_score
                + vias_score
                + sst_score
                + synergy_bonus
                - penalties
            )
            total_score = max(0.0, min(100.0, float(raw_sum)))

        # Deduplicate matched keywords
        unique_matched_keywords = sorted(list(dict.fromkeys(all_matched_keywords)))

        # ---------------------------------------------------------------------
        # 6. Preliminary Breakdown & Summary Generation
        # ---------------------------------------------------------------------
        breakdown = ScoreBreakdown(
            total_score=round(total_score, 1),
            modality_score=round(modality_score, 1),
            seniority_score=round(seniority_score, 1),
            vias_score=round(vias_score, 1),
            sst_score=round(sst_score, 1),
            synergy_bonus=round(synergy_bonus, 1),
            penalties=round(penalties, 1),
            is_disqualified=is_disqualified,
            matched_keywords=unique_matched_keywords,
            missing_requirements=[],
            explanatory_summary="",
        )

        # Generate explanatory summary and identify missing credentials
        summary_text = ExplanatorySummaryGenerator.generate(vacancy, profile, breakdown)
        missing_reqs = ExplanatorySummaryGenerator.identify_missing_requirements(vacancy, profile)

        breakdown.explanatory_summary = summary_text
        breakdown.missing_requirements = missing_reqs

        return breakdown

    def _evaluate_seniority(
        self,
        title_clean: str,
        clean_text: str,
        vacancy: NormalizedVacancy,
        profile: ProfileConfig,
    ) -> Tuple[float, float, bool]:
        """Evaluate title match and experience years against profile requirements.

        Returns:
            Tuple of (seniority_score [0-25], penalty, is_unrelated_discipline).
        """
        penalty = 0.0

        # 1. Check negative disciplines and domain context
        primary_disc = _strip_accents(
            (profile.experience.primary_discipline if profile.experience else profile.target_role)
            or ""
        )
        target_role = _strip_accents(profile.target_role or "")
        combined_profile_desc = f"{primary_disc} {target_role} {profile.name}".lower()

        is_tech_profile = any(
            k in combined_profile_desc
            for k in (
                "sistem",
                "software",
                "program",
                "desarroll",
                "tecnolog",
                "informatic",
                "soporte",
                "comput",
                "ti",
                "it",
                "helpdesk",
                "redes",
            )
        )

        software_negative_patterns = {
            r"desarrollador(?:\s*de)?\s*software",
            r"software\s*engineer",
            r"fullstack(?:\s*developer)?",
            r"full\s*stack(?:\s*developer)?",
            r"frontend(?:\s*developer)?",
            r"backend(?:\s*developer)?",
            r"python\s*/\s*react",
            r"programador",
        }

        for neg_pat in NEGATIVE_DISCIPLINES:
            if is_tech_profile and neg_pat in software_negative_patterns:
                continue
            if re.search(neg_pat, title_clean, flags=re.IGNORECASE) or re.search(
                neg_pat, clean_text[:300], flags=re.IGNORECASE
            ):
                return 0.0, 0.0, True

        # 2. Title Match (0 to 15 pts)
        title_score = 0.0
        title_hit = False

        if is_tech_profile:
            tech_tokens = [
                r"t[eé]cnic[oa]\s*(?:en\s*)?sistemas",
                r"soporte\s*t[eé]cnic[oa]",
                r"soporte\s*ti",
                r"it\s*support",
                r"help\s*desk",
                r"mesa\s*de\s*ayuda",
                r"auxiliar\s*(?:de\s*)?sistemas",
                r"asistente\s*(?:de\s*)?sistemas",
                r"analista\s*de\s*soporte",
                r"soporte\s*(?:de\s*)?aplicaciones",
                r"t[eé]cnic[oa]\s*(?:de\s*)?soporte",
                r"t[eé]cnic[oa]\s*inform[aá]tic[oa]",
                r"t[eé]cnic[oa]\s*(?:de\s*)?redes",
                r"desarrollador(?:\s*junior|\s*jr)?",
                r"programador(?:\s*junior|\s*jr)?",
                r"soporte\s*(?:con\s*)?programaci[oó]n",
                r"python",
                r"sql",
            ]
            for token in tech_tokens:
                if re.search(token, title_clean, flags=re.IGNORECASE):
                    title_score = 15.0
                    title_hit = True
                    break
        else:
            # High priority title and role matches for civil / infrastructure
            civil_tokens = [
                r"ingenier[ao]\s*civil",
                r"directora?\s*(?:/\s*coordinadora?\s*)?de\s*(?:dise[nñ]os?\s*viales|interventor[ií]a|proyectos?|infraestructura|obras|v[ií]as)",
                r"coordinadora?\s*(?:de\s*)?(?:dise[nñ]os?\s*viales|interventor[ií]a|proyectos?|infraestructura|obras|v[ií]as|sst)",
                r"gerente\s*(?:de\s*)?(?:proyectos?|interventor[ií]a|infraestructura|concesiones|v[ií]as)",
                r"l[ií]der\s*t[eé]cnico",
                r"interventor\s*vial",
                r"interventor[ií]a\s*vial",
                r"especialista\s*(?:senior\s*)?en\s*(?:v[ií]as|sst|seguridad\s*y\s*salud|infraestructura|pavimentos)",
                r"dise[nñ]os?\s*viales",
                r"infraestructura\s*vial",
                r"especialista\s*vias",
                r"especialista\s*sst",
                r"coordinadora?\s*sst",
            ]
            for token in civil_tokens:
                if re.search(token, title_clean, flags=re.IGNORECASE):
                    title_score = 15.0
                    title_hit = True
                    break

            # Check if description explicitly specifies the target civil profession in opening
            if not title_hit:
                opening_text = clean_text[:350]
                if re.search(r"\b(ingenier[ao]\s*civil|profesional\s*en\s*ingenier[ií]a\s*civil)\b", opening_text, flags=re.IGNORECASE):
                    title_score = 15.0
                    title_hit = True

        if not title_hit:
            # Check target role keywords in title
            if primary_disc and any(word in title_clean for word in primary_disc.split() if len(word) > 3):
                title_score = 15.0
            elif target_role and any(word in title_clean for word in target_role.split() if len(word) > 4):
                title_score = 15.0
            elif any(
                w in title_clean
                for w in [
                    "ingeniero",
                    "ingeniera",
                    "consultor",
                    "consultora",
                    "especialista",
                    "asesor",
                    "asesora",
                    "calculista",
                    "tecnico",
                    "tecnica",
                    "analista",
                    "programador",
                    "programadora",
                    "desarrollador",
                    "desarrolladora",
                ]
            ):
                title_score = 10.0
            elif any(w in title_clean for w in ["coordinador", "coordinadora", "director", "gerente", "jefe", "lider"]):
                title_score = 5.0
            else:
                title_score = 0.0

        # 3. Experience Match (0 to 10 pts)
        exp_score = 0.0
        min_exp = profile.min_total_experience_years if profile.min_total_experience_years is not None else 5
        is_senior_profile = min_exp >= 5

        # Check junior markers
        is_junior = False
        for j_pat in JUNIOR_MARKERS:
            if re.search(j_pat, title_clean, flags=re.IGNORECASE) or re.search(
                j_pat, clean_text[:400], flags=re.IGNORECASE
            ):
                is_junior = True
                break

        if is_junior:
            if is_senior_profile:
                penalty += 10.0
                exp_score = 0.0
            else:
                # Junior/technician profile actively welcomes entry positions
                exp_score = 10.0
        else:
            # Detect numeric years
            detected_years = self._extract_experience_years(clean_text, vacancy)

            if detected_years is not None:
                if is_senior_profile:
                    if detected_years >= 10.0:
                        exp_score = 10.0
                    elif detected_years >= 5.0:
                        exp_score = 7.0
                    elif detected_years >= 2.0:
                        exp_score = 5.0
                    else:
                        # 0-1 years
                        penalty += 10.0
                        exp_score = 0.0
                else:
                    # Technician/Junior profile
                    if detected_years <= 3.0:
                        exp_score = 10.0
                    elif detected_years <= 5.0:
                        exp_score = 8.0
                    else:
                        exp_score = 6.0
            else:
                if is_senior_profile:
                    has_senior_token = any(re.search(pat, clean_text, flags=re.IGNORECASE) for pat in SENIOR_TOKENS)
                    if has_senior_token:
                        exp_score = 10.0
                    else:
                        exp_score = 5.0
                else:
                    exp_score = 8.0

        total_seniority = max(0.0, min(25.0, title_score + exp_score))
        return total_seniority, penalty, False

    def _extract_experience_years(
        self, clean_text: str, vacancy: NormalizedVacancy
    ) -> Optional[float]:
        """Extract declared or required years of professional experience."""
        # 1. From normalized vacancy attribute if populated
        if hasattr(vacancy, "experience_years_detected") and vacancy.experience_years_detected is not None:
            try:
                return float(vacancy.experience_years_detected)
            except (ValueError, TypeError):
                pass

        # 2. Regex search in text
        exp_patterns = [
            r"(?:con\s+)?(?:m[aá]s\s+de\s+|m[ií]nima\s+de\s+|m[ií]nimo\s+)?(\d+)\s*(?:\+|mas|más)?\s*a[nñ]os\s*(?:de\s*)?experiencia",
            r"experiencia\s*(?:profesional\s*)?(?:general\s*)?(?:m[ií]nima\s*(?:de\s*)?)?(\d+)\s*a[nñ]os",
            r"m[ií]nimo\s*(\d+)\s*a[nñ]os\s*(?:de\s*)?ejercicio",
            r"trayectoria\s*(?:de\s*)?(\d+)\s*a[nñ]os",
            r"(\d+)\s*a[nñ]os\s*(?:espec[ií]ficos|general)",
        ]
        for pat in exp_patterns:
            match = re.search(pat, clean_text, flags=re.IGNORECASE)
            if match:
                try:
                    return float(match.group(1))
                except (ValueError, IndexError):
                    pass

        return None

    def _evaluate_specialization(
        self, clean_text: str, spec_cfg: SpecializationConfig
    ) -> Tuple[float, List[str]]:
        """Evaluate a specialization against vacancy text using word-boundary pattern matching.

        Returns:
            Tuple of (specialization_score [0-25], matched_keywords_list).
        """
        matched_set: Set[str] = set()

        all_keywords = list(spec_cfg.keywords or [])
        boost_keywords = list(spec_cfg.boost_keywords or [])

        # Match regular keywords
        for kw in all_keywords:
            clean_kw = _strip_accents(kw.strip())
            if not clean_kw:
                continue

            # Word boundary matching to avoid substrings (e.g. 'lluvias' matching 'vias')
            escaped = re.escape(clean_kw)
            pattern = re.compile(
                rf"(?<![a-z0-9]){escaped}(?![a-z0-9])",
                re.IGNORECASE,
            )
            if pattern.search(clean_text):
                matched_set.add(kw)

        # Match boost keywords
        has_boost = False
        for bkw in boost_keywords:
            clean_bkw = _strip_accents(bkw.strip())
            if not clean_bkw:
                continue
            escaped = re.escape(clean_bkw)
            pattern = re.compile(
                rf"(?<![a-z0-9]){escaped}(?![a-z0-9])",
                re.IGNORECASE,
            )
            if pattern.search(clean_text):
                matched_set.add(bkw)
                has_boost = True

        # If specialization relates to infrastructure / roads, check "infraestructura"
        spec_name_lower = _strip_accents(spec_cfg.name or "")
        if "infraestructura" in spec_name_lower or any("infraestructura" in kw.lower() for kw in all_keywords):
            if re.search(r"(?<![a-z0-9])infraestructura(?![a-z0-9])", clean_text, re.IGNORECASE):
                matched_set.add("infraestructura")

        count = len(matched_set)
        # Cap baseline weight evaluation at 25.0 points per specialization dimension
        target_max_weight = 25.0

        # Score rubric based on distinct keywords count
        if count >= 3 or (count >= 2 and has_boost):
            score = target_max_weight
        elif count == 2:
            score = round(target_max_weight * 0.72, 1)  # 18.0
        elif count == 1:
            score = round(target_max_weight * 0.40, 1)  # 10.0
        else:
            score = 0.0

        return float(min(target_max_weight, score)), sorted(list(matched_set))
