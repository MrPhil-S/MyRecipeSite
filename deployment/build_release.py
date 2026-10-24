"""Build a reviewed FastAPI source archive without local data or credentials."""

import argparse
import hashlib
import io
import subprocess
import tarfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
EXCLUDED = (
    "recipe_app_v2/migrations/versions/0002_cooked_recorded_dt.py",
)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    if ROOT not in output.parents:
        parser.error("Write the release archive inside the project workspace.")
    if output.exists():
        parser.error("Release archive already exists; choose a new path.")

    paths = subprocess.check_output(
        ["git", "ls-files", "-z", "--", "recipe_app_v2"], cwd=ROOT
    ).decode("utf-8").rstrip("\0").split("\0")
    if not paths or not paths[0]:
        parser.error("No tracked v2 files found.")
    for path in EXCLUDED:
        if path in paths or (ROOT / path).exists():
            parser.error("Deferred cooked-date migration is present; release blocked.")

    source = {}
    for relative in paths:
        if ".." in Path(relative).parts or not relative.startswith("recipe_app_v2/"):
            parser.error("Unexpected source path from Git.")
        file = ROOT / relative
        if not file.is_file() or file.is_symlink():
            parser.error("Tracked source is missing or is a symlink: " + relative)
        data = file.read_bytes()
        if b"recorded_dt" in data:
            parser.error("Deferred recorded_dt feature found in: " + relative)
        source[relative] = data

    revision = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    manifest = ["git_head=" + revision, "source=working tree, tracked v2 files only"]
    manifest.extend(
        f"{hashlib.sha256(data).hexdigest()}  {path}" for path, data in sorted(source.items())
    )
    source["RELEASE_MANIFEST.txt"] = ("\n".join(manifest) + "\n").encode()

    output.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(output, "w:gz") as archive:
        for relative, data in sorted(source.items()):
            info = tarfile.TarInfo(relative)
            info.size = len(data)
            info.mode = 0o644
            archive.addfile(info, io.BytesIO(data))
    print(f"archive={output}")
    print(f"files={len(source)}")
    print(f"sha256={hashlib.sha256(output.read_bytes()).hexdigest()}")


if __name__ == "__main__":
    main()
