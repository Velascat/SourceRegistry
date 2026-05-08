# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Velascat
import json
from pathlib import Path

from source_registry.contracts.verification import VerificationResult


def write_verification_result(path: str, result: VerificationResult) -> None:
    with Path(path).open("w", encoding="utf-8") as handle:
        json.dump(result.model_dump(), handle, indent=2, sort_keys=True, ensure_ascii=False)
        handle.write("\n")
