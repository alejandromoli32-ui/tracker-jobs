# E2E Test Infra: Multi-Profile Job Tracker & Hunter Engine

## Test Philosophy
- **Requirement-Driven & Opaque-Box**: Tests are derived directly from `ORIGINAL_REQUEST.md` (R1-R4 and Acceptance Criteria). Tests exercise public entry points, domain schemas, scraping engines, scoring models, and tracker outputs.
- **Methodology**: Multi-Tiered testing:
  - **Tier 1: Feature Coverage (>=5 per feature)**: Isolated happy-path unit & functional tests for every component (Config, Scrapers, RemoteVerifier, Matcher, Dedup, Excel, CSV, Incremental Sync, CLI).
  - **Tier 2: Boundary & Corner Cases (>=5 per feature)**: Corrupted YAML profiles, missing fields in HTML cards, network timeouts, 0-day remote vacancies, ambiguous modality descriptions, edge scores (69 vs 71), duplicate collisions, empty existing Excel workbooks.
  - **Tier 3: Cross-Feature Combinations (Pairwise Coverage)**: Scraper output -> Deduplicator -> Matcher -> Incremental Storage; Multi-profile switching without state leak; Mixed portal data aggregation.
  - **Tier 4: Real-World Application Scenarios**: End-to-end execution on realistic Colombian job postings, specifically validating the 9 Canonical Verification Jobs (3 ideal remote >= 70, 3 on-site disqualified/penalized, 3 non-relevant civil < 50).
  - **Tier 5: Adversarial Hardening**: White-box stress testing, injection resilience, encoding resilience (Windows cp1252 / UTF-8), and forensic integrity audit.

## Feature Inventory & Test Mapping
| # | Feature | Tier 1 (Coverage) | Tier 2 (Boundaries) | Tier 3 (Interactions) | Tier 4 (Workloads) |
|---|---------|:-----------------:|:-------------------:|:---------------------:|:------------------:|
| 1 | Profile Schema & Loading | 5 tests | 5 tests | ✓ | ✓ |
| 2 | Profile 1: Civil Senior Vías & SST | 5 tests | 5 tests | ✓ | ✓ |
| 3 | Profiles 2, 3, 4 Extensibility | 5 tests | 5 tests | ✓ | ✓ |
| 4 | Resilient Scraping Engine | 5 tests | 5 tests | ✓ | ✓ |
| 5 | Normalization & Hashing | 5 tests | 5 tests | ✓ | ✓ |
| 6 | Strict Remote Verification | 5 tests | 5 tests | ✓ | ✓ |
| 7 | 0-100 Affinity Scoring Rubric | 5 tests | 5 tests | ✓ | ✓ |
| 8 | Explanatory Summary Generator | 5 tests | 5 tests | ✓ | ✓ |
| 9 | Excel Output with Styling & Links | 5 tests | 5 tests | ✓ | ✓ |
| 10| Incremental User Status Preservation| 5 tests | 5 tests | ✓ | ✓ |
| 11| CLI Pipeline Runner | 5 tests | 5 tests | ✓ | ✓ |

## Test Architecture
- **Framework**: `pytest >= 8.0` with `pytest-mock` or standard unittest mocks.
- **Execution**: `uv run pytest -v` (runs all unit and integration tests hermetically and fast).
- **Directory Layout**:
  - `tests/conftest.py`: Shared fixtures (loaded profiles, mock client, canonical 9-job benchmark dataset, temp directories).
  - `tests/test_config.py`: Tests for Profile YAML loading, validation, multi-profile switching.
  - `tests/test_scrapers.py`: Tests for Computrabajo, ElEmpleo, LinkedIn, Remotive, rate limiting, error recovery, normalizer.
  - `tests/test_matcher.py`: Tests for RemoteVerifier, AffinityScorer, 0-100 rubric, penalty triggers, summary generation.
  - `tests/test_storage.py`: Tests for Deduplicator, ExcelTracker openpyxl styling/hyperlinks, CSVTracker, and IncrementalTracker state preservation.
  - `tests/test_e2e_integration.py`: Complete pipeline runs (scrape -> score -> filter -> export -> re-scrape -> merge) validating all Acceptance Criteria.

## Canonical 9-Job Benchmark Suite (Tier 4 Acceptance Matrix)
| Job ID | Title | Company | Modality | Category | Expected Score | Expected Action |
|--------|-------|---------|----------|----------|:--------------:|:---------------:|
| V01 | Directora de Interventoría Vías y SST Remota | Concesiones Viales Andinas | 100% Remoto / Teletrabajo | Ideal Vías + SST | 85 - 100 | ACCEPT (Include in Tracker) |
| V02 | Coordinadora SST e Infraestructura Vial Virtual | Infraestructura & Consultoría SAS | Remoto (Colombia) | Ideal Vías + SST | 80 - 95 | ACCEPT (Include in Tracker) |
| V03 | Asesora Técnica Especialista en Pavimentos y HSE | Consorcio Vial Nacional | Teletrabajo | Ideal Vías + SST | 75 - 90 | ACCEPT (Include in Tracker) |
| V04 | Ingeniero Residente de Pavimentación en Obra | Constructora del Sol | Presencial (Campamento 21/7) | Obra / Presencial | 0 - 20 (Disqualified) | REJECT / DISQUALIFY |
| V05 | Inspector SST en Frente de Obra 4G | Vías de la Montaña SAS | 100% Presencial en Sitio | Obra / Presencial | 0 - 20 (Disqualified) | REJECT / DISQUALIFY |
| V06 | Director de Obra Presencial Túneles y Vías | Megaobras Colombia | Presencial en Terreno | Obra / Presencial | 0 - 20 (Disqualified) | REJECT / DISQUALIFY |
| V07 | Ingeniero Calculista Estructural Edificaciones | Diseños & Estructuras Urbanas | Remoto | Non-relevant Civil | 25 - 45 | REJECT (< 70 threshold) |
| V08 | Residente Hidráulico y Redes Sanitarias | Aguas & Proyectos | Remoto | Non-relevant Civil | 20 - 40 | REJECT (< 70 threshold) |
| V09 | Ingeniero Civil Geotécnico de Fundaciones | Geotecnia Avanzada Ltda | Remoto | Non-relevant Civil | 25 - 45 | REJECT (< 70 threshold) |

## Coverage Thresholds
- **Tier 1**: >= 55 unit tests
- **Tier 2**: >= 55 boundary & error tests
- **Tier 3**: >= 15 cross-module interaction tests
- **Tier 4**: >= 9 benchmark scenario tests + full CLI execution test
- **Total Minimum Target**: >= 135 automated test cases passing with exit code 0.
