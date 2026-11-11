from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent
COMMON_DIR = PROJECT_DIR.parent / "scraper-common"
EXTRACTED_DIR = PROJECT_DIR / "extracted_content"
sys.path.insert(0, str(COMMON_DIR))

from common.git_sync import sync_repos_before_run  # noqa: E402


def remove_path(path: Path) -> None:
    if not path.exists():
        return
    if path.is_dir():
        shutil.rmtree(path)
        print(f"Deleted folder: {path.name}")
    else:
        path.unlink()
        print(f"Deleted file: {path.name}")


def cleanup() -> None:
    print("Cleaning __pycache__ folders...")
    for path in PROJECT_DIR.rglob("__pycache__"):
        remove_path(path)

    print("Cleaning extracted_content folder...")
    remove_path(EXTRACTED_DIR)
    EXTRACTED_DIR.mkdir(parents=True, exist_ok=True)
    print("Created fresh extracted_content folder")


def scraper_env() -> dict[str, str]:
    env = os.environ.copy()
    existing_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = (
        f"{COMMON_DIR}{os.pathsep}{existing_pythonpath}"
        if existing_pythonpath
        else str(COMMON_DIR)
    )
    env["SCRAPER_NETWORK_GUARD"] = "1"
    return env


def run_step(script_name: str) -> None:
    print(f"\nRunning {script_name} ...", flush=True)
    result = subprocess.run(
        [sys.executable, script_name],
        cwd=PROJECT_DIR,
        env=scraper_env(),
    )
    if result.returncode != 0:
        raise SystemExit(f"{script_name} failed with exit code {result.returncode}")
    print(f"{script_name} completed successfully.", flush=True)


def main() -> int:
    os.chdir(PROJECT_DIR)
    sync_repos_before_run(PROJECT_DIR)
    print("Starting Apollo Pharmacy category extraction...\n", flush=True)
    cleanup()
    run_step("categories.py")
    print("\nApollo Pharmacy category extraction completed.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
