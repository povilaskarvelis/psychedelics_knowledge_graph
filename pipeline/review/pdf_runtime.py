#!/usr/bin/env python3
"""Runtime helpers for PDF-heavy review scripts."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

DEFAULT_PDF_ENV = "psychkg-pdf"
BOOTSTRAP_FLAG = "PSYCHKG_PDF_ENV_BOOTSTRAPPED"
DISABLE_FLAG = "PSYCHKG_DISABLE_PDF_ENV_BOOTSTRAP"
ENV_NAME_VAR = "PSYCHKG_PDF_CONDA_ENV"


def ensure_pdf_runtime() -> None:
    """Re-exec PDF extraction scripts inside the configured conda environment."""

    if os.environ.get(DISABLE_FLAG) == "1":
        return
    if os.environ.get(BOOTSTRAP_FLAG) == "1":
        return

    env_name = os.environ.get(ENV_NAME_VAR, DEFAULT_PDF_ENV)
    if os.environ.get("CONDA_DEFAULT_ENV") == env_name:
        return

    conda = shutil.which("conda")
    if not conda:
        print(
            f"WARNING: conda not found; continuing outside `{env_name}`. "
            f"Set `{DISABLE_FLAG}=1` to silence this bootstrap check.",
            file=sys.stderr,
        )
        return

    script = Path(sys.argv[0])
    script_arg = str(script.resolve()) if script.exists() else sys.argv[0]
    env = dict(os.environ)
    env[BOOTSTRAP_FLAG] = "1"
    print(f"Re-running PDF extraction inside conda env `{env_name}`...", file=sys.stderr)
    os.execvpe(
        conda,
        [
            conda,
            "run",
            "--no-capture-output",
            "-n",
            env_name,
            "python",
            script_arg,
            *sys.argv[1:],
        ],
        env,
    )
