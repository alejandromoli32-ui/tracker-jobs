# Project: Multi-Profile Job Tracker & Hunter Engine (Colombia & Remote)

## Architecture
The system is an automated, modular Python application structured under the package `job_hunter`:
- `job_hunter/models.py`: Strongly-typed domain models (Pydantic / dataclasses) for Profiles, Raw Vacancies, Normalized Vacancies, Scoring Breakdown, and Tracker Entries.
- `job_hunter/config.py`: Declarative profile manager loading and validating YAML/JSON profile specifications across 4+ independent profiles.
- `job_hunter/client.py`: Resilient HTTP client with browser header rotation, jittered rate limiting, retry backoff, and circuit breaking.
- `job_hunter/scrapers/`: Modular portal scrapers (Computrabajo Colombia, ElEmpleo Colombia, LinkedIn Jobs Guest API, Remotive API, Mock Fallback scraper).
- `job_hunter/remote_verifier.py`: Colombian labor modality evaluator (teletrabajo, virtual, remoto) with strict presential/obra/campamento disqualification filters.
- `job_hunter/matcher.py`: Multi-dimensional affinity scoring engine (0 to 100) combining modality, seniority, Vías specialization, SST specialization, and synergy bonuses.
- `job_hunter/summary.py`: Explanatory summary generator detailing match strengths, missing requirements, and regulatory notices (COPNIA, Licencia SST).
- `job_hunter/dedup.py`: Deterministic SHA-256 (16-hex) deduplication hashing based on canonicalized title, company, portal, and URL.
- `job_hunter/storage/`: Excel (`.xlsx`) exporter with openpyxl (styled headers, clickable `=HYPERLINK`, color-coded score cells, status dropdowns) and CSV exporter (RFC 4180, UTF-8-SIG).
- `job_hunter/storage/incremental.py`: State-preserving incremental sync merging fresh search results into existing workbooks while preserving candidate status (`Nueva`, `Por revisar`, `Postulado`, `Descartado`), notes, and initial detection dates.
- `job_hunter/cli.py`: Unified command-line interface orchestrating scraping, filtering, and exporting for any selected profile.

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | Declarative Profile Schema | YAML/JSON schema defining profile title, years experience, keywords, exclusions, search queries | M1 | R1 (ORIGINAL_REQUEST line 14) |
| 2 | Profile 1: Civil Senior Vías & SST | Declarative configuration for 15+ yrs Civil, 5+ yrs Vías, 5+ yrs SST, remote Colombia | M1 | R1 (ORIGINAL_REQUEST line 16) |
| 3 | Profiles 2, 3, 4 Extensibility | Declarative configurations for Infra Project Manager, BIM Specialist, HSEQ Consultant | M1 | R1 / Acceptance (line 47) |
| 4 | Multi-Profile Loader & Validator | Dynamic loading of active profile without modifying source code | M1 | R1 / Acceptance (line 47) |
| 5 | Resilient HTTP Client | User-Agent rotation, 1.5s-2.5s jittered rate limiting, exponential backoff retries, timeouts | M2 | R2 / Acceptance (line 40) |
| 6 | Computrabajo Colombia Scraper | Scraping `co.computrabajo.com` with `-en-remoto` filter, pagination, detail parsing | M2 | R2 / Acceptance (line 39) |
| 7 | ElEmpleo Colombia Scraper | Scraping `elempleo.com/co` with keyword search, pagination, detail block parsing | M2 | R2 / Acceptance (line 39) |
| 8 | LinkedIn Guest & Remotive Ingestion | LinkedIn Guest API (`f_WT=2`) and Remotive remote API ingestion | M2 | R2 / Acceptance (line 39) |
| 9 | Vacancy Normalization & Schema | Transforming heterogeneous portal data into standardized `NormalizedVacancy` | M2 | R2 (ORIGINAL_REQUEST line 19) |
| 10 | Strict Remote/Virtual Verification | Gatekeeper verifying remote/teletrabajo and penalizing 100% on-site obra/campamento jobs | M3 | R3 / Acceptance (line 43) |
| 11 | Multi-Dimensional Affinity Scoring | 0-100 scoring model (Modality 25, Seniority 25, Vías 25, SST 25, Synergy 10, clamped 0-100) | M3 | R3 / Acceptance (line 44) |
| 12 | Explanatory Summary Generator | Concise explanation of match reasons and regulatory observations (COPNIA, Licencia SST) | M3 | R3 (ORIGINAL_REQUEST line 25) |
| 13 | Deterministic Deduplication Hashing | 16-hex SHA-256 hash identifying vacancies idempotently across runs | M4 | R4 (ORIGINAL_REQUEST line 29) |
| 14 | OpenPyXL Excel Output (.xlsx) | Styled workbook with clickable `=HYPERLINK`, color fills (>=70 green), frozen panes | M4 | R4 / Acceptance (line 51) |
| 15 | CSV Export (UTF-8-SIG) | RFC 4180 compliant CSV export for cross-platform data processing | M4 | R4 (ORIGINAL_REQUEST line 28) |
| 16 | Incremental Tracker Synchronization | Merging new vacancies into existing tracker while preserving user application status | M4 | R4 / Acceptance (line 51) |
| 17 | CLI Pipeline Runner | Command-line runner supporting `--profile`, `--sources`, `--min-score`, `--output` | M5 | System Integration |
| 18 | Pytest Automated Test Suite | Comprehensive unit, integration, and acceptance tests covering R1-R4 | M5 | Acceptance (line 50) |
| 19 | 9 Canonical Benchmark Verification | Test fixtures covering 3 ideal (>=70), 3 on-site (0/penalized), 3 non-relevant (<50) | M5 | Verification Resources (line 34) |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | Multi-Profile Configuration Engine | Profile models, YAML validator, 4 profile definitions | none | DONE |
| M2 | Job Scraping & Aggregation Engine | Resilient client, portal scrapers, normalizer, mock fixtures | M1 (models) | DONE |
| M3 | Intelligent Matching & Scoring Engine | Remote verifier, 0-100 scoring rubric, explanatory summary generator | M1 (models) | DONE |
| M4 | Automated Output & Tracker Storage | Deduplicator, Excel openpyxl generator, CSV export, incremental status merger | M1, M3 | DONE |
| M5 | CLI Integration & Comprehensive E2E Verification | CLI runner, pytest suite (Tiers 1-4), 9 benchmark tests, adversarial hardening | M1, M2, M3, M4 | DONE |

## Interface Contracts

### M1: Models & Config
- `ProfileConfig`:
  - `id: str`
  - `name: str`
  - `target_role: str`
  - `min_total_experience_years: int`
  - `specializations: Dict[str, SpecializationConfig]` (e.g. `vias`, `sst`)
  - `modality: ModalityConfig` (`strictly_remote: bool`, `allowed_modalities: List[str]`, `disqualifiers: List[str]`)
  - `required_credentials: List[str]` (e.g. `COPNIA`, `Licencia SST`)
  - `search_queries: List[str]`
  - `scoring_weights: ScoringWeights`
- `load_profile(path_or_id: str) -> ProfileConfig`
- `list_available_profiles(profiles_dir: Path) -> List[ProfileConfig]`

### M2: Scraping & Normalization
- `NormalizedVacancy`:
  - `id: str` (16-char SHA-256)
  - `title: str`
  - `company: str`
  - `direct_url: str`
  - `full_description: str`
  - `publication_date: Optional[str]`
  - `location: str`
  - `modality: str` (`remoto`, `hibrido`, `presencial`, `desconocido`)
  - `salary_range: Optional[str]`
  - `source_portal: str`
  - `raw_snippet: Optional[str]`
- `BaseScraper.search(query: str, max_pages: int = 2) -> List[NormalizedVacancy]`
- `JobAggregationEngine.run(queries: List[str], portals: List[str], max_pages: int) -> List[NormalizedVacancy]`

### M3: Remote Verification & Scoring
- `RemoteVerifier.evaluate(vacancy: NormalizedVacancy, profile: ProfileConfig) -> ModalityEvaluation`:
  - `is_strictly_remote: bool`
  - `is_disqualified: bool`
  - `modality_score: float` (0.0 to 25.0)
  - `disqualification_reason: Optional[str]`
- `AffinityScorer.evaluate(vacancy: NormalizedVacancy, profile: ProfileConfig) -> ScoreBreakdown`:
  - `total_score: float` (0.0 to 100.0)
  - `modality_score: float` (0 to 25)
  - `seniority_score: float` (0 to 25)
  - `vias_score: float` (0 to 25)
  - `sst_score: float` (0 to 25)
  - `synergy_bonus: float` (0 to 10)
  - `penalties: float`
  - `is_disqualified: bool`
  - `explanatory_summary: str`
  - `matched_keywords: List[str]`
  - `missing_requirements: List[str]`

### M4: Storage & Deduplication
- `Deduplicator.compute_id(title: str, company: str, url: str) -> str` (16-hex SHA-256)
- `TrackerEntry`:
  - Inherits vacancy data + `score: float`, `score_percentage: str`, `explanatory_summary: str`, `estado: str` (`Nueva`, `Por revisar`, `Postulado`, `Descartado`), `fecha_deteccion: str`, `notas_usuario: str`
- `ExcelTracker.save(entries: List[TrackerEntry], output_path: Path, preserve_existing: bool = True) -> Path`
- `CSVTracker.save(entries: List[TrackerEntry], output_path: Path, preserve_existing: bool = True) -> Path`
- `IncrementalTracker.merge(existing_path: Path, fresh_entries: List[TrackerEntry]) -> List[TrackerEntry]`

### M5: CLI Integration
- `job_hunter.cli`:
  - Arguments: `--profile <id_or_path>`, `--portals <list>`, `--min-score <float>`, `--output <path>`, `--format <xlsx|csv|both>`

## Code Layout
```
c:/Users/Admin/Downloads/TRACKER_JOBS/
├── profiles/
│   ├── profile_1_civil_vias_sst.yaml
│   ├── profile_2_gerente_proyectos_viales.yaml
│   ├── profile_3_modelador_bim_vias.yaml
│   └── profile_4_consultor_hseq_sig.yaml
├── job_hunter/
│   ├── __init__.py
│   ├── models.py
│   ├── config.py
│   ├── client.py
│   ├── normalizer.py
│   ├── dedup.py
│   ├── remote_verifier.py
│   ├── matcher.py
│   ├── summary.py
│   ├── cli.py
│   ├── scrapers/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── computrabajo.py
│   │   ├── elempleo.py
│   │   ├── linkedin.py
│   │   ├── remotive.py
│   │   └── mock_scraper.py
│   └── storage/
│       ├── __init__.py
│       ├── excel.py
│       ├── csv_exporter.py
│       └── incremental.py
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_config.py
│   ├── test_scrapers.py
│   ├── test_matcher.py
│   ├── test_storage.py
│   └── test_e2e_integration.py
├── pyproject.toml
├── ORIGINAL_REQUEST.md
├── PROJECT.md
└── TEST_INFRA.md
```
