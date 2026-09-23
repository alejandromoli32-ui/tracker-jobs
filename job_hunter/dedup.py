"""Deterministic job deduplication engine.

Computes canonical 16-hex SHA-256 identifiers across heterogeneous portal postings
and provides idempotent deduplication for vacancy collections.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any, Dict, List, Optional, Sequence, Set, TypeVar, Union

from job_hunter.normalizer import clean_company, clean_title, clean_url

T = TypeVar("T")


class Deduplicator:
    """Deterministic deduplication engine for job vacancies."""

    @classmethod
    def compute_id(cls, title: str, company: str, url: str) -> str:
        """Compute a deterministic 16-hex SHA-256 deduplication ID.

        Normalizes text (case-insensitive, whitespace collapsed, badges removed)
        and canonicalizes the URL (tracking parameters and fragments stripped).

        Formula:
            hashlib.sha256(f"{norm_title}|{norm_company}|{clean_url}".encode('utf-8')).hexdigest()[:16]
        """
        norm_title = clean_title(title).lower().strip()
        norm_company = clean_company(company).lower().strip()
        clean_u = clean_url(url).lower().strip()

        raw_key = f"{norm_title}|{norm_company}|{clean_u}"
        return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()[:16]

    @classmethod
    def normalize_text(cls, text: Optional[str]) -> str:
        """Normalize free text: unescape, strip extra whitespace, and lowercase."""
        if not text:
            return ""
        # Collapse whitespace
        cleaned = re.sub(r"\s+", " ", str(text)).strip().lower()
        return cleaned

    @classmethod
    def canonicalize_url(cls, url: Optional[str]) -> str:
        """Strip tracking parameters, fragments, and normalize URL scheme/netloc."""
        return clean_url(url)

    @classmethod
    def get_item_id(cls, item: Any) -> str:
        """Extract or compute the 16-hex deterministic ID for any vacancy item."""
        if isinstance(item, dict):
            if "id" in item and item["id"]:
                return str(item["id"])
            title = str(item.get("title", ""))
            company = str(item.get("company", ""))
            url = str(item.get("direct_url", item.get("url", "")))
            return cls.compute_id(title, company, url)

        # Object with attributes (TrackerEntry, NormalizedVacancy, etc.)
        item_id = getattr(item, "id", None)
        if item_id:
            return str(item_id)

        title = getattr(item, "title", "")
        company = getattr(item, "company", "")
        url = getattr(item, "direct_url", getattr(item, "url", ""))
        return cls.compute_id(title, company, url)

    @classmethod
    def is_duplicate(cls, item: Any, seen_ids: Set[str]) -> bool:
        """Check if item has already been encountered."""
        item_id = cls.get_item_id(item)
        return item_id in seen_ids

    @classmethod
    def deduplicate(
        cls,
        items: Sequence[T],
        keep: str = "first",
    ) -> List[T]:
        """Deduplicate a sequence of vacancies or tracker entries.

        Parameters
        ----------
        items:
            Sequence of NormalizedVacancy, TrackerEntry, or dict objects.
        keep:
            Strategy when encountering duplicate IDs:
            - 'first': preserve the first encountered instance (default)
            - 'last': preserve the last encountered instance
            - 'highest_score': preserve the instance with highest numeric score
        """
        if not items:
            return []

        if keep not in ("first", "last", "highest_score"):
            raise ValueError(f"Invalid keep strategy '{keep}'. Expected 'first', 'last', or 'highest_score'.")

        if keep == "first":
            seen: Set[str] = set()
            result: List[T] = []
            for it in items:
                i_id = cls.get_item_id(it)
                if i_id not in seen:
                    seen.add(i_id)
                    result.append(it)
            return result

        if keep == "last":
            seen_dict: Dict[str, T] = {}
            # Remember order of first encounter to maintain stable list order
            order: List[str] = []
            for it in items:
                i_id = cls.get_item_id(it)
                if i_id not in seen_dict:
                    order.append(i_id)
                seen_dict[i_id] = it
            return [seen_dict[i_id] for i_id in order]

        # keep == "highest_score"
        best_by_id: Dict[str, T] = {}
        order_list: List[str] = []

        def _get_score(obj: Any) -> float:
            if isinstance(obj, dict):
                val = obj.get("score", 0.0)
            else:
                val = getattr(obj, "score", 0.0)
            try:
                return float(val)
            except (ValueError, TypeError):
                return 0.0

        for it in items:
            i_id = cls.get_item_id(it)
            if i_id not in best_by_id:
                order_list.append(i_id)
                best_by_id[i_id] = it
            else:
                if _get_score(it) > _get_score(best_by_id[i_id]):
                    best_by_id[i_id] = it

        return [best_by_id[i_id] for i_id in order_list]

    @classmethod
    def filter_new(cls, items: Sequence[T], existing_ids: Set[str]) -> List[T]:
        """Filter items returning only those whose ID is NOT in existing_ids."""
        return [it for it in items if cls.get_item_id(it) not in existing_ids]
