#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main() -> int:
    script = Path(__file__).with_name("run_latest_failure_focused_validation.py")
    return subprocess.call([sys.executable, str(script), "--skip-wi-local"])


if __name__ == "__main__":
    raise SystemExit(main())
