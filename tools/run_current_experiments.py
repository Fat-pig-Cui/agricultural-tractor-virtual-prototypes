"""Run a small, source-only reproduction in an external workspace.

The public archive intentionally ships no historical result files. This
launcher copies the current source tree to a new workspace and runs the
selected calculation there.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def prepare(work: Path) -> Path:
    work = work.expanduser().resolve()
    if work.is_relative_to(ROOT):
        raise ValueError("The workspace must be outside the public checkout.")
    if work.exists():
        raise FileExistsError(f"Refusing to overwrite existing workspace: {work}")
    work.mkdir(parents=True)
    for folder in ("code", "tools"):
        shutil.copytree(ROOT / folder, work / folder,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    (work / "results").mkdir()
    return work


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("experiment", choices=("paper1", "paper2", "smoke"))
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--duration", type=float, default=None)
    args = parser.parse_args()
    work = prepare(args.workspace)
    if args.experiment == "smoke":
        for name in ("reproduce_paper1.py", "reproduce_paper2.py"):
            subprocess.run([sys.executable, str(work / "tools" / name),
                            "--workspace", str(work), "--duration", "12"],
                           cwd=work, check=True)
    else:
        name = f"reproduce_{args.experiment}.py"
        command = [sys.executable, str(work / "tools" / name),
                   "--workspace", str(work)]
        if args.duration is not None:
            command += ["--duration", str(args.duration)]
        subprocess.run(command, cwd=work, check=True)
    print(f"Results workspace: {work}")


if __name__ == "__main__":
    main()
