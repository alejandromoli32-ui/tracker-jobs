from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
import yaml
from pydantic import ValidationError

from job_hunter.models import ProfileConfig

logger = logging.getLogger(__name__)


class ProfileError(Exception):
    """Base exception for profile-related operations."""
    pass


class ProfileNotFoundError(ProfileError, FileNotFoundError):
    """Raised when a profile file or identifier cannot be located."""
    pass


class ProfileValidationError(ProfileError, ValueError):
    """Raised when profile configuration fails schema validation."""
    pass


class ProfileParseError(ProfileError, ValueError):
    """Raised when profile file contains malformed YAML syntax."""
    pass


def validate_profile_dict(data: Dict[str, Any]) -> ProfileConfig:
    """Validate a raw dictionary against the ProfileConfig schema.

    Args:
        data: Raw profile dictionary.

    Returns:
        Validated ProfileConfig instance.

    Raises:
        ProfileValidationError: If validation fails or input is not a dictionary.
    """
    if not isinstance(data, dict):
        raise ProfileValidationError(f"Profile data must be a dictionary, got {type(data).__name__}")

    try:
        return ProfileConfig.model_validate(data)
    except ValidationError as e:
        raise ProfileValidationError(f"Profile configuration validation failed: {e}") from e


def _resolve_profiles_dirs(custom_dir: Optional[Union[str, Path]] = None) -> List[Path]:
    """Resolve candidate directories containing profile YAML files."""
    if custom_dir is not None:
        p = Path(custom_dir).resolve()
        return [p]

    candidates = [
        Path.cwd() / "profiles",
        Path("profiles").resolve(),
        Path(__file__).resolve().parent.parent / "profiles",
    ]
    seen = set()
    result = []
    for c in candidates:
        resolved = c.resolve()
        if resolved not in seen:
            seen.add(resolved)
            result.append(resolved)
    return result


def load_profile(
    path_or_id: Union[str, Path],
    profiles_dir: Optional[Union[str, Path]] = None,
) -> ProfileConfig:
    """Load and validate a ProfileConfig from a file path or profile identifier.

    Args:
        path_or_id: Relative/absolute path to YAML file, or profile ID slug.
        profiles_dir: Optional directory to search when path_or_id is a profile ID.

    Returns:
        Validated ProfileConfig instance.

    Raises:
        ProfileNotFoundError: If profile file cannot be found.
        ProfileParseError: If YAML syntax is malformed.
        ProfileValidationError: If schema validation fails.
    """
    if not path_or_id:
        raise ProfileValidationError("Profile path or ID must not be empty")

    target_path: Optional[Path] = None
    input_path = Path(path_or_id)

    # 1. Direct path check
    if input_path.is_file():
        target_path = input_path.resolve()
    else:
        # 2. Search in candidate directories
        candidate_dirs = _resolve_profiles_dirs(profiles_dir)
        str_id = str(path_or_id).strip()

        # Try common filename patterns
        file_patterns = [
            str_id if str_id.endswith((".yaml", ".yml")) else f"{str_id}.yaml",
            f"{str_id}.yml",
            f"profile_{str_id}.yaml" if not str_id.startswith("profile_") else f"{str_id}.yaml",
            f"profile_{str_id}.yml" if not str_id.startswith("profile_") else f"{str_id}.yml",
        ]

        for c_dir in candidate_dirs:
            if not c_dir.is_dir():
                continue
            for pattern in file_patterns:
                candidate_file = c_dir / pattern
                if candidate_file.is_file():
                    target_path = candidate_file.resolve()
                    break
            if target_path:
                break

        # 3. Fallback: inspect profile YAML IDs in candidate directories
        if target_path is None:
            for c_dir in candidate_dirs:
                if not c_dir.is_dir():
                    continue
                for f in sorted(list(c_dir.glob("*.yaml")) + list(c_dir.glob("*.yml"))):
                    try:
                        with open(f, "r", encoding="utf-8") as yf:
                            doc = yaml.safe_load(yf)
                            if isinstance(doc, dict):
                                doc_id = doc.get("id") or doc.get("profile", {}).get("id")
                                if doc_id == str_id:
                                    target_path = f.resolve()
                                    break
                    except Exception:
                        continue
                if target_path:
                    break

    if target_path is None or not target_path.is_file():
        searched = [str(d) for d in _resolve_profiles_dirs(profiles_dir)]
        raise ProfileNotFoundError(
            f"Profile '{path_or_id}' could not be found as a direct file or within search directories: {searched}"
        )

    # Read and parse YAML file
    try:
        with open(target_path, "r", encoding="utf-8") as f:
            raw_content = f.read()
    except OSError as e:
        raise ProfileNotFoundError(f"Failed to read profile file '{target_path}': {e}") from e

    try:
        parsed_data = yaml.safe_load(raw_content)
    except yaml.YAMLError as e:
        raise ProfileParseError(f"YAML parsing error in '{target_path}': {e}") from e

    if not isinstance(parsed_data, dict):
        raise ProfileValidationError(
            f"Profile file '{target_path}' must contain a YAML mapping (dictionary), got {type(parsed_data).__name__}"
        )

    return validate_profile_dict(parsed_data)


def list_available_profiles(
    profiles_dir: Optional[Union[str, Path]] = None,
) -> List[ProfileConfig]:
    """Discover and load all valid profiles from the profiles directory.

    Args:
        profiles_dir: Optional path to profiles directory. Defaults to standard locations.

    Returns:
        List of validated ProfileConfig instances.
    """
    candidate_dirs = _resolve_profiles_dirs(profiles_dir)
    target_dir: Optional[Path] = None

    for d in candidate_dirs:
        if d.is_dir():
            target_dir = d
            break

    if target_dir is None:
        logger.warning("No valid profiles directory found in candidates: %s", candidate_dirs)
        return []

    profile_files = sorted(list(target_dir.glob("*.yaml")) + list(target_dir.glob("*.yml")))
    profiles: List[ProfileConfig] = []
    seen_ids = set()

    for pf in profile_files:
        try:
            profile = load_profile(pf, profiles_dir=target_dir)
            if profile.id not in seen_ids:
                seen_ids.add(profile.id)
                profiles.append(profile)
        except Exception as e:
            logger.warning("Skipping invalid profile file '%s': %s", pf, e)

    return profiles
