"""Job vacancy normalization, sanitization, hashing, and modality classification.

Provides deterministic cleaning and transformation of heterogeneous portal listings
into strongly-typed NormalizedVacancy instances.
"""

from __future__ import annotations

import hashlib
import html
import re
from typing import Any, Dict, Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from job_hunter.models import NormalizedVacancy


TRACKING_PARAM_PREFIXES = ("utm_",)
TRACKING_PARAM_EXACT = {
    "position",
    "pagenum",
    "refid",
    "trackingid",
    "fbclid",
    "gclid",
    "trk",
    "ref",
    "origin",
    "f_wt",
    "f_tpr",
    "geoid",
    "currentjobid",
    "trabajo",
}

PRESENTIAL_MARKERS = [
    "100% presencial",
    "presencial en obra",
    "residente de obra",
    "campamento",
    "en campamento",
    "frente de obra",
    "planta industrial",
    "cantera",
    "turnos rotativos",
    "en sitio",
    "en mina",
    "jefe de patio",
    "inspector sst presencial",
    "inspeccion diaria en sitio",
    "trabajo 100% presencial",
    "labor presencial",
    "jornada presencial",
    "abstenerse personas interesadas en trabajo remoto",
]

HYBRID_MARKERS = [
    "híbrido",
    "hibrido",
    "hybrid",
    "semipresencial",
    "semi-presencial",
    "parcialmente presencial",
    "alternancia",
    "días en oficina",
    "dias en oficina",
    "días presenciales",
    "dias presenciales",
    "esquema mixto",
]

REMOTE_MARKERS = [
    "remoto",
    "remote",
    "teletrabajo",
    "virtual",
    "home office",
    "trabajo remoto",
    "100% remoto",
    "100% teletrabajo",
    "100% virtual",
    "remoto colombia",
    "remote colombia",
    "teletrabajo nacional",
    "completamente remoto",
]


def clean_text(text: Optional[str]) -> str:
    """Strip HTML tags, unescape entities, and normalize whitespace."""
    if not text or not isinstance(text, str):
        return ""
    # Strip script and style blocks entirely
    cleaned = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", text, flags=re.DOTALL | re.IGNORECASE)
    # Remove HTML tags
    cleaned = re.sub(r"<[^>]+>", " ", cleaned)
    # Unescape HTML entities (&aacute;, &nbsp;, etc.)
    cleaned = html.unescape(cleaned)
    # Replace non-breaking spaces and other special spaces
    cleaned = cleaned.replace("\xa0", " ").replace("\u200b", "")
    # Collapse multiple whitespace to single space
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def clean_title(title: Optional[str]) -> str:
    """Clean job title by stripping badge markers and extra spaces."""
    cleaned = clean_text(title)
    if not cleaned:
        return "Vacante Sin Título"

    # Strip bracketed prefixes or suffixes like [Remoto], (Teletrabajo), etc.
    cleaned = re.sub(r"^\s*\[[^\]]+\]\s*", "", cleaned)
    cleaned = re.sub(r"\s*\[[^\]]+\]\s*$", "", cleaned)
    cleaned = re.sub(r"^\s*\([^\)]+\)\s*", "", cleaned)
    cleaned = re.sub(r"\s*\([^\)]+\)\s*$", "", cleaned)

    # Strip common badge text like 'Oferta destacada', 'Postulado', 'Vista', etc.
    for badge in ["Oferta destacada", "Postulado", "Vista", "Urgente", "Destacada"]:
        pattern = re.compile(rf"\b{re.escape(badge)}\b", flags=re.IGNORECASE)
        cleaned = pattern.sub("", cleaned)

    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned if cleaned else (title.strip() if title else "Vacante Sin Título")


def clean_company(company: Optional[str]) -> str:
    """Clean company name by removing rating prefixes and trimming."""
    cleaned = clean_text(company)
    if not cleaned:
        return "Confidencial"

    # Strip rating numbers at start like '4,8 ' or '3.5 '
    cleaned = re.sub(r"^[0-9]+[.,][0-9]+\s*", "", cleaned).strip()

    if not cleaned or cleaned.lower() in ("empresa confidencial", "confidencial", "importante empresa"):
        return "Confidencial"

    return cleaned


def clean_url(url: Optional[str]) -> str:
    """Canonicalize URL and strip tracking, UTM, and UI parameters."""
    if not url or not isinstance(url, str):
        return ""

    raw_url = url.strip()
    split = urlsplit(raw_url)

    # Parse and filter query parameters
    query_params = parse_qsl(split.query, keep_blank_values=False)
    filtered_params = []
    for k, v in query_params:
        lower_k = k.lower()
        if any(lower_k.startswith(p) for p in TRACKING_PARAM_PREFIXES):
            continue
        if lower_k in TRACKING_PARAM_EXACT:
            continue
        filtered_params.append((k, v))

    clean_query = urlencode(filtered_params)
    # Discard fragment
    clean_split = (split.scheme, split.netloc, split.path, clean_query, "")
    return urlunsplit(clean_split)


def clean_salary(salary: Optional[str]) -> Optional[str]:
    """Clean salary string; returns None if empty or uninformative."""
    if not salary or not isinstance(salary, str):
        return None

    cleaned = clean_text(salary)
    if not cleaned:
        return None

    lower = cleaned.lower()
    if any(k in lower for k in ("a convenir", "no especificado", "no definido", "confidencial", "acordar")):
        return None

    return cleaned


def clean_description(description: Optional[str]) -> str:
    """Sanitize description HTML, preserving paragraph breaks while stripping scripts."""
    if not description or not isinstance(description, str):
        return ""

    # Remove script and style tags along with their contents
    desc = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", description, flags=re.DOTALL | re.IGNORECASE)

    # Replace breaks and paragraph closing tags with newline characters
    desc = re.sub(r"<\s*br\s*/?>", "\n", desc, flags=re.IGNORECASE)
    desc = re.sub(r"<\s*/p\s*>", "\n\n", desc, flags=re.IGNORECASE)
    desc = re.sub(r"<\s*/li\s*>", "\n", desc, flags=re.IGNORECASE)
    desc = re.sub(r"<\s*li[^>]*>", "• ", desc, flags=re.IGNORECASE)

    # Remove all other HTML tags
    desc = re.sub(r"<[^>]+>", " ", desc)

    # Unescape entities
    desc = html.unescape(desc)
    desc = desc.replace("\xa0", " ").replace("\u200b", "")

    # Normalize newlines: collapse more than two newlines into two
    desc = re.sub(r"[ \t]+", " ", desc)
    desc = re.sub(r"\n\s*\n\s*\n+", "\n\n", desc)
    lines = [line.strip() for line in desc.splitlines()]
    return "\n".join(lines).strip()


def classify_modality(text: str, declared_modality: Optional[str] = None) -> str:
    """Classify work modality into 'remoto', 'hibrido', 'presencial', or 'desconocido'."""
    text_lower = (text or "").lower()
    decl_lower = (declared_modality or "").lower().strip()

    combined = f"{text_lower} {decl_lower}"

    # 1. Presential check (takes precedence when explicitly on-site / obra / campamento)
    if decl_lower in ("presential", "presencial", "on-site", "onsite"):
        return "presencial"

    for marker in PRESENTIAL_MARKERS:
        if marker in combined:
            return "presencial"

    # 2. Hybrid check
    if decl_lower in ("hybrid", "hibrido", "híbrido"):
        return "hibrido"

    for marker in HYBRID_MARKERS:
        if marker in combined:
            return "hibrido"

    # 3. Remote check
    if decl_lower in ("remote", "remoto", "teletrabajo", "virtual", "home office"):
        return "remoto"

    for marker in REMOTE_MARKERS:
        if marker in combined:
            return "remoto"

    # 4. Fallback check on individual words
    if "remot" in combined or "virtual" in combined or "teletrabaj" in combined:
        return "remoto"
    if "presencial" in combined:
        return "presencial"

    return "desconocido"


def compute_dedup_id(title: str, company: str, clean_url_str: str) -> str:
    """Compute deterministic 16-hex SHA-256 deduplication ID."""
    norm_title = clean_title(title).lower()
    norm_company = clean_company(company).lower()
    clean_u = clean_url(clean_url_str).lower()

    raw_key = f"{norm_title}|{norm_company}|{clean_u}"
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()[:16]


def normalize_vacancy(
    title: str,
    company: Optional[str],
    direct_url: str,
    full_description: str,
    source_portal: str,
    publication_date: Optional[str] = None,
    location: Optional[str] = None,
    modality: Optional[str] = None,
    salary_range: Optional[str] = None,
    raw_snippet: Optional[str] = None,
    extra_metadata: Optional[Dict[str, Any]] = None,
    custom_id: Optional[str] = None,
) -> NormalizedVacancy:
    """Construct a strongly-typed NormalizedVacancy with cleaned fields and deterministic ID."""
    norm_title = clean_title(title)
    norm_company = clean_company(company)
    norm_url = clean_url(direct_url)
    norm_desc = clean_description(full_description)
    norm_salary = clean_salary(salary_range)
    norm_snippet = clean_text(raw_snippet) if raw_snippet else None

    # Determine modality using title, description, snippet and declared modality
    context_text = f"{norm_title} {norm_desc} {norm_snippet or ''}"
    computed_modality = classify_modality(context_text, declared_modality=modality)

    vacancy_id = custom_id or compute_dedup_id(norm_title, norm_company, norm_url)

    loc = clean_text(location) if location else "Colombia"
    if not loc:
        loc = "Colombia"

    return NormalizedVacancy(
        id=vacancy_id,
        title=norm_title,
        company=norm_company,
        direct_url=norm_url,
        full_description=norm_desc,
        publication_date=publication_date.strip() if publication_date else None,
        location=loc,
        modality=computed_modality,
        salary_range=norm_salary,
        source_portal=source_portal.strip().lower() if source_portal else "unknown",
        raw_snippet=norm_snippet,
        extra_metadata=extra_metadata or {},
    )
