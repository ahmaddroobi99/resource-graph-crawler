from pathlib import Path

IMPORTANT = {
    "crawler", "processors", "scripts", "tests", "docs", "output_arch",
    "config.py", "main.py", "passwords.txt", "README.md", "requirements.txt", ".gitignore"
}

OUTPUT = "project_clean_dump_important.txt"
root = Path(".")

with open(OUTPUT, "w", encoding="utf-8") as out:
    out.write("CLEAN PROJECT DUMP\n" + "="*60 + "\n")

    for item in sorted(IMPORTANT):
        path = root / item
        if not path.exists():
            continue

        if path.is_file():
            out.write(f"\n\n========== {item} ==========\n")
            out.write(path.read_text(encoding="utf-8", errors="replace"))
        else:
            for f in sorted(path.rglob("*")):
                if f.is_file() and f.suffix in {".py", ".md", ".txt", ".json", ".yml", ".yaml"} and f.stat().st_size < 300_000:
                    rel = f.relative_to(root)
                    out.write(f"\n\n========== {rel} ==========\n")
                    out.write(f.read_text(encoding="utf-8", errors="replace"))

print(f"Done → {OUTPUT}")