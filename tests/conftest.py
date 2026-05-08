# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Velascat
"""Pytest conftest with venv guard.

Refuses to run unless invoked from inside this project's `.venv` —
prevents accidental test runs against the global interpreter.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_EXPECTED_VENV = _REPO / ".venv"


def _running_in_venv() -> bool:
    return Path(sys.prefix).resolve() == _EXPECTED_VENV.resolve()


if not _running_in_venv() and not os.environ.get("CUSTODIAN_SKIP_VENV_GUARD"):
    sys.stderr.write(
        f"ERROR: Tests must be run inside this project's virtual environment.\n"
        f"Expected: {_EXPECTED_VENV}\n"
        f"Active:   {sys.prefix}\n\n"
        f"Activate it first:\n"
        f"  source .venv/bin/activate\n"
        f"Or invoke pytest through the venv directly:\n"
        f"  .venv/bin/pytest\n"
    )
    sys.exit(2)
