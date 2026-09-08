"""Check repository-local Markdown links without relying on network availability."""
from pathlib import Path
import re
import subprocess
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[2]


def main():
    files = subprocess.check_output(["git", "ls-files", "-z", "*.md"], cwd=ROOT).decode().split("\0")
    failures = []
    for name in filter(None, files):
        path = ROOT / name
        text = re.sub(r"```.*?```", "", path.read_text(encoding="utf-8"), flags=re.S)
        for match in re.finditer(r"\[[^\]\n]*\]\(([^)\n]+)\)", text):
            target = match[1].split(' "')[0].strip("<>")
            url = urlsplit(target)
            if url.scheme or target.startswith(("#", "//")):
                continue
            base = ROOT if target.startswith("/") else path.parent
            destination = base / unquote(url.path).lstrip("/")
            if not destination.exists():
                failures.append(f"{name}: missing target {target}")
    if failures:
        raise SystemExit("\n".join(failures))
    print("Repository-local Markdown link targets: OK")


if __name__ == "__main__":
    main()
