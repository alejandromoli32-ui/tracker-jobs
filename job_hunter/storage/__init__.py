"""Storage and persistence package for job tracking.

Provides Excel (.xlsx) styled reports with openpyxl, RFC 4180 CSV export
with utf-8-sig encoding, and state-preserving incremental merging.
"""

from job_hunter.storage.csv_exporter import CSVTracker
from job_hunter.storage.excel import (
    DEFAULT_HEADERS,
    EXCEL_STATUS_OPTIONS,
    ExcelTracker,
)
from job_hunter.storage.incremental import (
    STATUS_PRIORITY,
    IncrementalTracker,
)

__all__ = [
    "ExcelTracker",
    "CSVTracker",
    "IncrementalTracker",
    "DEFAULT_HEADERS",
    "EXCEL_STATUS_OPTIONS",
    "STATUS_PRIORITY",
]
