from __future__ import annotations

import logging
import re
import unicodedata
from typing import Dict, List, Optional

from job_hunter.models import NormalizedVacancy, ProfileConfig, ScoreBreakdown

logger = logging.getLogger(__name__)


def _strip_accents(text: str) -> str:
    """Normalize text by folding unicode accents to ASCII equivalents."""
    if not text:
        return ""
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(c for c in normalized if not unicodedata.combining(c)).lower()


class ExplanatorySummaryGenerator:
    """Generates concise explanatory summaries for evaluated vacancies.

    Synthesizes affinity tiers, specialization match reasons, modality observations,
    and Colombian regulatory notices (e.g. Tarjeta Profesional COPNIA, Licencia SST).
    """

    @classmethod
    def check_regulatory_requirements(cls, vacancy: NormalizedVacancy) -> Dict[str, bool]:
        """Detect mandatory Colombian regulatory credentials required by the vacancy.

        Returns:
            Dictionary with booleans for:
            - 'copnia_required': Requires Tarjeta Profesional COPNIA
            - 'sst_license_required': Requires Licencia en SST vigente
            - 'res_0312_course': Requires Curso 50h/20h SG-SST (Res. 0312)
        """
        combined = f"{vacancy.title or ''} {vacancy.full_description or ''} {vacancy.raw_snippet or ''}"
        clean_text = _strip_accents(combined)

        # Check explicit metadata if present
        meta = vacancy.extra_metadata or {}
        copnia_in_meta = bool(meta.get("copnia_required"))
        sst_in_meta = bool(meta.get("sst_license_required"))

        # COPNIA / Tarjeta Profesional patterns
        copnia_pattern = re.compile(
            r"\b(copnia|tarjeta\s*profesional|matricula\s*profesional|consejo\s*profesional\s*(?:nacional\s*)?de\s*ingenier[ií]a)\b",
            re.IGNORECASE,
        )
        copnia_detected = copnia_in_meta or bool(copnia_pattern.search(clean_text))

        # Licencia SST patterns
        sst_license_pattern = re.compile(
            r"\b(licencia\s*(?:en\s*)?sst|licencia\s*(?:en\s*)?salud\s*ocupacional|licencia\s*(?:vigente\s*)?expedida\s*por\s*secretar[ií]a|licencia\s*(?:de\s*)?seguridad\s*y\s*salud)\b",
            re.IGNORECASE,
        )
        sst_license_detected = sst_in_meta or bool(sst_license_pattern.search(clean_text))

        # Curso 50h / Res 0312
        res_0312_pattern = re.compile(
            r"\b(resoluci[oó]n\s*0312|curso\s*(?:de\s*)?50\s*horas|curso\s*(?:de\s*)?20\s*horas|50\s*horas\s*sg-sst)\b",
            re.IGNORECASE,
        )
        res_0312_detected = bool(res_0312_pattern.search(clean_text))

        return {
            "copnia_required": copnia_detected,
            "sst_license_required": sst_license_detected,
            "res_0312_course": res_0312_detected,
        }

    @classmethod
    def identify_missing_requirements(
        cls, vacancy: NormalizedVacancy, profile: ProfileConfig
    ) -> List[str]:
        """Identify potential gaps or specific credentials requested by vacancy."""
        regs = cls.check_regulatory_requirements(vacancy)
        missing: List[str] = []

        # If vacancy requires COPNIA and profile does not have it listed in credentials
        profile_creds_str = " ".join(profile.required_credentials or []).lower()
        if regs["copnia_required"] and "copnia" not in profile_creds_str:
            missing.append("Tarjeta Profesional COPNIA requerida por la vacante")

        if regs["sst_license_required"] and "licencia" not in profile_creds_str:
            missing.append("Licencia SST requerida por la vacante")

        return missing

    @classmethod
    def generate(
        cls,
        vacancy: NormalizedVacancy,
        profile: ProfileConfig,
        score_breakdown: ScoreBreakdown,
    ) -> str:
        """Generate a structured, explanatory summary text.

        Conforms to format:
        [Afinidad: {Score}/100 - {Tier}] {Resumen de Coincidencia}. Modalidad: {Modalidad_Texto}. {Observaciones_Y_Requisitos_Legales}.
        """
        score = int(round(score_breakdown.total_score))

        # 1. Determine Tier
        if score_breakdown.is_disqualified:
            tier = "Descartada"
        elif score >= 70:
            tier = "Alta Afinidad"
        elif score >= 50:
            tier = "Afinidad Moderada"
        else:
            tier = "Baja Afinidad"

        # 2. Match explanation / core reason
        reasons: List[str] = []
        if score_breakdown.is_disqualified:
            reasons.append("Descartada por exigencia presencial en obra/campamento o restricción no compatible")
        else:
            # Check match strengths
            high_vias = score_breakdown.vias_score >= 18.0
            high_sst = score_breakdown.sst_score >= 18.0
            moderate_vias = 10.0 <= score_breakdown.vias_score < 18.0
            moderate_sst = 10.0 <= score_breakdown.sst_score < 18.0

            spec_keys = list(profile.specializations.keys()) if profile.specializations else []
            spec_objs = list(profile.specializations.values()) if profile.specializations else []
            is_civil_profile = "vias" in spec_keys or "sst" in spec_keys

            if is_civil_profile:
                if high_vias and high_sst:
                    reasons.append(
                        f"Coincide plenamente con el perfil {profile.name}, integrando infraestructura vial y SG-SST (Sinergia dual)"
                    )
                elif high_vias:
                    reasons.append("Alta coincidencia técnica en infraestructura vial, diseño geométrico y pavimentos")
                elif high_sst:
                    reasons.append("Alta coincidencia en gestión de Seguridad y Salud en el Trabajo (SST)")
                elif moderate_vias and moderate_sst:
                    reasons.append("Afinidad moderada con componentes de vías e infraestructura y seguridad laboral")
                elif moderate_vias:
                    reasons.append("Afinidad parcial en infraestructura vial y transporte")
                elif moderate_sst:
                    reasons.append("Afinidad parcial en seguridad y salud ocupacional")
                elif score_breakdown.seniority_score >= 15.0:
                    reasons.append(f"Afinidad en disciplina base ({profile.target_role}) sin especialidad directa en vías/SST")
                else:
                    reasons.append("Baja correspondencia con las especialidades del perfil activo")
            else:
                s1_name = spec_objs[0].name if len(spec_objs) > 0 else "Soporte de Sistemas"
                s2_name = spec_objs[1].name if len(spec_objs) > 1 else "Programación y Automatización"
                if high_vias and high_sst:
                    reasons.append(f"Alta coincidencia técnica integral ({s1_name} y {s2_name})")
                elif high_vias:
                    reasons.append(f"Alta coincidencia técnica en {s1_name}")
                elif high_sst:
                    reasons.append(f"Alta coincidencia técnica en {s2_name}")
                elif moderate_vias or moderate_sst:
                    reasons.append(f"Afinidad moderada en áreas técnicas del cargo ({profile.target_role})")
                elif score_breakdown.seniority_score >= 15.0:
                    reasons.append(f"Afinidad en rol base ({profile.target_role})")
                else:
                    reasons.append("Baja correspondencia con los requerimientos técnicos del perfil")

        match_text = ". ".join(reasons)

        # 3. Modality description
        if score_breakdown.is_disqualified:
            modality_text = "Presencial / No permitida"
        elif score_breakdown.modality_score >= 20.0:
            modality_text = "100% Remoto en Colombia confirmado"
        elif score_breakdown.modality_score >= 10.0:
            modality_text = "Modalidad híbrida / parcial"
        else:
            modality_text = "Modalidad no declarada o por verificar"

        # 4. Legal / Regulatory and Credential alerts
        observations: List[str] = []
        regs = cls.check_regulatory_requirements(vacancy)

        obs_items: List[str] = []
        if regs["copnia_required"]:
            obs_items.append("tarjeta profesional COPNIA")
        if regs["sst_license_required"]:
            obs_items.append("Licencia en Seguridad y Salud en el Trabajo (SST) vigente")
        if regs["res_0312_course"]:
            obs_items.append("curso SG-SST (Res. 0312)")

        if obs_items:
            observations.append(f"Observación: Requiere {', '.join(obs_items)}.")

        if score_breakdown.modality_score == 10.0 and not score_breakdown.is_disqualified:
            observations.append("Alerta: Modalidad híbrida puede requerir presencia ocasional.")

        obs_text = " ".join(observations).strip()

        # 5. Assemble final string
        prefix = f"[Afinidad: {score}/100 - {tier}]"
        body = f"{match_text}. Modalidad: {modality_text}."
        if obs_text:
            return f"{prefix} {body} {obs_text}"
        return f"{prefix} {body}"
