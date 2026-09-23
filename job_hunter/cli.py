"""Command-line interface and pipeline execution runner for Job Hunter Engine.

Provides unified CLI for searching, scoring, filtering, and persisting
remote job opportunities across 4+ declarative profiles.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Union

from job_hunter.config import (
    ProfileError,
    list_available_profiles,
    load_profile,
)
from job_hunter.matcher import AffinityScorer
from job_hunter.models import ProfileConfig, TrackerEntry
from job_hunter.remote_verifier import RemoteVerifier
from job_hunter.scrapers.engine import JobAggregationEngine
from job_hunter.storage.incremental import IncrementalTracker

logger = logging.getLogger("job_hunter.cli")


def build_parser() -> argparse.ArgumentParser:
    """Construct and configure the argument parser for Job Hunter CLI."""
    parser = argparse.ArgumentParser(
        prog="job-hunter",
        description="Multi-Profile Job Tracker & Hunter Engine (Colombia & Remote)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run default Profile 1 (Civil Vías & SST) in offline mode:
  job-hunter --offline

  # Run specific profile with custom min score and CSV format:
  job-hunter --profile profile_2_gerente_proyectos_viales --min-score 65 --format csv

  # List all available profiles:
  job-hunter --list-profiles

  # Run with specific portals and output directory:
  job-hunter --portals computrabajo,elempleo --output-dir ./my_results --offline
        """,
    )

    parser.add_argument(
        "--profile",
        "-p",
        type=str,
        default="profile_1_civil_vias_sst",
        help="Profile identifier or path to YAML config (default: profile_1_civil_vias_sst)",
    )

    parser.add_argument(
        "--portals",
        "--sources",
        "-s",
        dest="portals",
        type=str,
        default="all",
        help="Comma-separated list of portals to search (default: all)",
    )

    parser.add_argument(
        "--min-score",
        "-m",
        type=float,
        default=None,
        help="Minimum affinity score threshold (default: from profile or 70.0)",
    )

    parser.add_argument(
        "--output-dir",
        "--output",
        "-o",
        dest="output_dir",
        type=str,
        default="output",
        help="Target directory for tracker files (default: output)",
    )

    parser.add_argument(
        "--format",
        "-f",
        type=str,
        choices=["xlsx", "csv", "both"],
        default="both",
        help="Output file format: xlsx, csv, or both (default: both)",
    )

    parser.add_argument(
        "--offline",
        action="store_true",
        default=False,
        help="Use offline mock fixtures for fast deterministic execution without network calls",
    )

    parser.add_argument(
        "--max-pages",
        type=int,
        default=2,
        help="Maximum pages to scrape per portal and search query (default: 2)",
    )

    parser.add_argument(
        "--list-profiles",
        "-l",
        action="store_true",
        default=False,
        help="List available job hunter profiles and exit",
    )

    parser.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        default=False,
        help="Suppress progress output and print only final summary",
    )

    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        default=False,
        help="Enable detailed debug logging",
    )

    return parser


def run_pipeline(
    profile_input: Union[str, Path] = "profile_1_civil_vias_sst",
    portals: Optional[Sequence[str]] = None,
    min_score: Optional[float] = None,
    output_dir: Union[str, Path] = "output",
    export_format: str = "both",
    offline: bool = False,
    max_pages: int = 2,
    quiet: bool = False,
    engine: Optional[JobAggregationEngine] = None,
    scorer: Optional[AffinityScorer] = None,
    verifier: Optional[RemoteVerifier] = None,
) -> Dict[str, Any]:
    """Execute the end-to-end job hunter pipeline programmatically.

    Args:
        profile_input: Profile identifier (slug) or path to profile YAML file.
        portals: List of portal names to query, or None for all available portals.
        min_score: Minimum affinity score to retain; if None, derived from profile or 70.0.
        output_dir: Directory where tracker files will be written.
        export_format: Output format ('xlsx', 'csv', or 'both').
        offline: Whether to bypass live network requests using deterministic fixtures.
        max_pages: Maximum pages to scrape per portal and query.
        quiet: If True, suppress stdout progress prints.
        engine: Optional pre-configured JobAggregationEngine instance.
        scorer: Optional pre-configured AffinityScorer instance.
        verifier: Optional pre-configured RemoteVerifier instance.

    Returns:
        Dictionary containing execution summary, stats, and exported file paths.
    """
    # 1. Discover and load profile
    profile: ProfileConfig = load_profile(profile_input)

    # Resolve threshold
    effective_min_score = min_score
    if effective_min_score is None:
        if profile.scoring_weights and hasattr(profile.scoring_weights, "min_score_to_save"):
            effective_min_score = float(profile.scoring_weights.min_score_to_save)
        else:
            effective_min_score = 70.0

    # Resolve target portals
    target_portals: Optional[List[str]] = None
    if portals:
        cleaned_portals = [p.strip().lower() for p in portals if p.strip()]
        if "all" not in cleaned_portals and "*" not in cleaned_portals:
            target_portals = cleaned_portals

    if not quiet:
        mode_str = "Offline (Mock Fixtures)" if offline else "Live Web Portals"
        portals_str = ", ".join(target_portals) if target_portals else "All available portals"
        print("=" * 80)
        print(" MULTI-PROFILE JOB TRACKER & HUNTER ENGINE (Colombia & Remote)")
        print("=" * 80)
        print(f" Profile:      [{profile.id}] {profile.name}")
        print(f" Target Role:  {profile.target_role} (Min Exp: {profile.min_total_experience_years} yrs)")
        print(f" Search Mode:  {mode_str}")
        print(f" Portals:      {portals_str}")
        print(f" Min Score:    {effective_min_score:.1f}%")
        print(f" Output Dir:   {output_dir}")
        print("-" * 80)

    # 2. Execute scraping & aggregation
    agg_engine = engine or JobAggregationEngine()
    queries = profile.search_queries
    if not queries and profile.search_config:
        queries = profile.search_config.query_strings

    if not quiet:
        print(f"[1/4] Aggregating vacancies for {len(queries)} search queries...")

    vacancies = agg_engine.run(
        queries=queries,
        portals=target_portals,
        max_pages=max_pages,
        offline=offline,
    )

    if not quiet:
        print(f"      Total unique vacancies discovered: {len(vacancies)}")

    # 3. Remote verification and affinity scoring
    if not quiet:
        print("[2/4] Evaluating labor modality and calculating affinity scores...")

    aff_scorer = scorer or AffinityScorer()
    rem_verifier = verifier or RemoteVerifier()

    scored_entries: List[TrackerEntry] = []
    remote_verified_count = 0
    scored_gte_70_count = 0

    for vac in vacancies:
        # Check remote compliance
        mod_eval = rem_verifier.evaluate(vac, profile)
        if mod_eval.is_strictly_remote and not mod_eval.is_disqualified:
            remote_verified_count += 1

        # Calculate composite score
        breakdown = aff_scorer.evaluate(vac, profile)
        if breakdown.total_score >= 70.0:
            scored_gte_70_count += 1

        # Check retention threshold
        if breakdown.total_score >= effective_min_score:
            entry = TrackerEntry(
                id=vac.id,
                title=vac.title,
                company=vac.company,
                direct_url=vac.direct_url,
                full_description=vac.full_description,
                publication_date=vac.publication_date,
                location=vac.location,
                modality=vac.modality,
                salary_range=vac.salary_range,
                source_portal=vac.source_portal,
                raw_snippet=vac.raw_snippet,
                score=breakdown.total_score,
                score_percentage=f"{int(round(breakdown.total_score))}%",
                explanatory_summary=breakdown.explanatory_summary,
                estado="Nueva",
                perfil_id=profile.id,
            )
            scored_entries.append(entry)

    if not quiet:
        print(f"      Remote verified vacancies: {remote_verified_count}")
        print(f"      Vacancies with Score >= 70%: {scored_gte_70_count}")
        print(f"[3/4] Filtered by threshold >= {effective_min_score:.1f}%: {len(scored_entries)} vacancies retained")

    # 4. Storage export and incremental synchronization
    out_path = Path(output_dir).resolve()
    out_path.mkdir(parents=True, exist_ok=True)

    fmt = export_format.strip().lower()
    exported_files: List[Path] = []

    if not quiet:
        print("[4/4] Synchronizing tracker storage...")

    if fmt in ("xlsx", "both"):
        xlsx_file = out_path / f"{profile.id}_tracker.xlsx"
        saved_xlsx = IncrementalTracker.sync(xlsx_file, scored_entries)
        exported_files.append(saved_xlsx)
        if not quiet:
            print(f"      -> Excel Tracker: {saved_xlsx}")

    if fmt in ("csv", "both"):
        csv_file = out_path / f"{profile.id}_tracker.csv"
        saved_csv = IncrementalTracker.sync(csv_file, scored_entries)
        exported_files.append(saved_csv)
        if not quiet:
            print(f"      -> CSV Tracker:   {saved_csv}")

    if not quiet:
        print("-" * 80)
        print(
            f" Complete: {len(vacancies)} scraped | "
            f"{remote_verified_count} remote verified | "
            f"{scored_gte_70_count} score >= 70% | "
            f"{len(scored_entries)} exported"
        )
        print("=" * 80)

    return {
        "profile_id": profile.id,
        "profile_name": profile.name,
        "total_scraped": len(vacancies),
        "remote_verified": remote_verified_count,
        "scored_gte_70": scored_gte_70_count,
        "exported_count": len(scored_entries),
        "min_score": effective_min_score,
        "exported_files": [str(p) for p in exported_files],
        "entries": scored_entries,
        "failures": agg_engine.last_run_stats.get("failures", {}),
    }


def main(argv: Optional[List[str]] = None) -> int:
    """Main CLI entry point for Job Hunter Engine."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG, format="%(levelname)s [%(name)s]: %(message)s")
    else:
        logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    # Handle --list-profiles
    if args.list_profiles:
        try:
            available = list_available_profiles()
            print("=" * 80)
            print(" AVAILABLE PROFILES (Job Hunter Multi-Profile Engine)")
            print("=" * 80)
            if not available:
                print(" No profiles found in profiles directory.")
            else:
                for idx, p in enumerate(available, start=1):
                    print(f" [{idx}] ID:   {p.id}")
                    print(f"     Name: {p.name}")
                    print(f"     Role: {p.target_role}")
                    print(f"     Exp:  {p.min_total_experience_years}+ years total")
                    specialties = list(p.specializations.keys()) if p.specializations else []
                    print(f"     Spec: {', '.join(specialties)}")
                    print("-" * 80)
            return 0
        except Exception as exc:
            print(f"Error listing profiles: {exc}", file=sys.stderr)
            return 1

    # Parse portals argument
    portals_list: Optional[List[str]] = None
    if args.portals and args.portals.strip().lower() not in ("all", "*"):
        portals_list = [p.strip() for p in args.portals.split(",") if p.strip()]

    try:
        run_pipeline(
            profile_input=args.profile,
            portals=portals_list,
            min_score=args.min_score,
            output_dir=args.output_dir,
            export_format=args.format,
            offline=args.offline,
            max_pages=args.max_pages,
            quiet=args.quiet,
        )
        return 0
    except ProfileError as exc:
        print(f"Profile Error: {exc}", file=sys.stderr)
        return 1
    except FileNotFoundError as exc:
        print(f"File Error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Execution Error: {exc}", file=sys.stderr)
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
