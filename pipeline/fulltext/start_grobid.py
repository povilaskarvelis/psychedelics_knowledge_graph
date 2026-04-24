#!/usr/bin/env python3
"""Start a local GROBID Docker service with memory-safe defaults.

The default GROBID Docker config allows a larger engine pool than we need for
this pipeline's sequential conversion runs. On small Colima VMs this can lead to
OOM kills during long batches. This helper generates a project-local config from
the image default, lowers the engine pool and pdfalto memory limit, then starts
the container on port 8070.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_IMAGE = "grobid/grobid:0.9.0-crf"
DEFAULT_CONTAINER = "psychkg-grobid"
DEFAULT_CONFIG = ROOT / "data" / "processed" / "fulltext" / "grobid.safe.yaml"


def run(cmd: list[str], check: bool = True, capture: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=check, text=True, capture_output=capture)


def replace_scalar(text: str, key: str, value: int | str) -> str:
    pattern = re.compile(rf"^(\s*{re.escape(key)}:\s*).*$", re.MULTILINE)
    replacement = rf"\g<1>{value}"
    updated, count = pattern.subn(replacement, text, count=1)
    if count != 1:
        raise ValueError(f"Could not find config key `{key}`")
    return updated


def extract_default_config(image: str, out_path: Path) -> None:
    container = "psychkg-grobid-config-probe"
    run(["docker", "rm", "-f", container], check=False)
    created = run(["docker", "create", "--name", container, image], capture=True)
    if not created.stdout.strip():
        raise RuntimeError("docker create did not return a container id")
    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        run(["docker", "cp", f"{container}:/opt/grobid/grobid-home/config/grobid.yaml", str(out_path)])
    finally:
        run(["docker", "rm", "-f", container], check=False)


def write_safe_config(image: str, out_path: Path, concurrency: int, pdfalto_memory_mb: int) -> None:
    extract_default_config(image, out_path)
    text = out_path.read_text(encoding="utf-8")
    text = replace_scalar(text, "memoryLimitMb", max(256, pdfalto_memory_mb))
    text = replace_scalar(text, "concurrency", max(1, concurrency))
    out_path.write_text(text, encoding="utf-8")


def service_is_alive(url: str = "http://localhost:8070/api/isalive", timeout_sec: int = 2) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout_sec) as response:
            return response.status == 200 and response.read().decode("utf-8", errors="replace").strip() == "true"
    except Exception:
        return False


def wait_until_alive(timeout_sec: int) -> bool:
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        if service_is_alive():
            return True
        time.sleep(1)
    return False


def start_container(args: argparse.Namespace) -> None:
    if args.recreate_config or not args.config.exists():
        write_safe_config(
            image=args.image,
            out_path=args.config,
            concurrency=args.concurrency,
            pdfalto_memory_mb=args.pdfalto_memory_mb,
        )

    run(["docker", "rm", "-f", args.container], check=False)
    cmd = [
        "docker",
        "run",
        "-d",
        "--name",
        args.container,
        "-p",
        "8070:8070",
        "-v",
        f"{args.config}:/opt/grobid/grobid-home/config/grobid.yaml:ro",
    ]
    if args.memory:
        cmd.extend(["--memory", args.memory])
    cmd.append(args.image)
    run(cmd)

    if not wait_until_alive(args.wait_sec):
        run(["docker", "ps", "-a", "--filter", f"name={args.container}"], check=False)
        run(["docker", "logs", "--tail", "120", args.container], check=False)
        raise SystemExit("GROBID did not become healthy")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", default=DEFAULT_IMAGE)
    parser.add_argument("--container", default=DEFAULT_CONTAINER)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--concurrency", type=int, default=1)
    parser.add_argument("--pdfalto-memory-mb", type=int, default=2048)
    parser.add_argument("--memory", default="5g", help="Docker container memory cap, e.g. 5g; empty disables cap")
    parser.add_argument("--wait-sec", type=int, default=90)
    parser.add_argument("--recreate-config", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    args.config = args.config.resolve()
    start_container(args)
    print("GROBID is alive at http://localhost:8070/api/isalive")
    print(f"Config: {args.config}")
    print(f"Container: {args.container}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
