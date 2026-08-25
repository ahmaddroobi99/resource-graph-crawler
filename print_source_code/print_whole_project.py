import os
from pathlib import Path

EXCLUDE_DIRS = {'.venv', '.venv-1', '__pycache__', '.pytest_cache', '.git', 'node_modules', '.idea'}
MAX_SIZE = 500_000  # skip files bigger than 500 KB
OUTPUT = "project_full_dump.txt"

root = Path(".")
with open(OUTPUT, "w", encoding="utf-8") as out:
    out.write(f"PROJECT DUMP — {root.resolve()}\n")
    out.write("=" * 80 + "\n\n")

    for path in sorted(root.rglob("*")):
        if any(part in EXCLUDE_DIRS for part in path.parts):
            continue
        if path.is_dir():
            continue
        if path.stat().st_size > MAX_SIZE:
            out.write(f"\n\n========== {path} (SKIPPED - too large) ==========\n")
            continue

        rel = path.relative_to(root)
        out.write(f"\n\n========== {rel} ==========\n")
        try:
            out.write(path.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            out.write("[binary or unreadable file]")

print(f"Done → {OUTPUT}")