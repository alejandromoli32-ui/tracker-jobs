"""Package entry point for `python -m job_hunter`."""

from __future__ import annotations

import sys
from job_hunter.cli import main

if __name__ == "__main__":
    sys.exit(main())
