#!/usr/bin/env python3
"""Copy legacy Pi media into the existing per-environment upload root.

The default is read-only. --apply copies missing files without overwriting
anything, then compares SHA256 for every source and destination file. Old
source directories are never modified by this script.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil


ROOTS = {
    "staging": Path("/home/pi/fastapi-preview-data/uploads"),
    "production": Path("/var/lib/myrecipesite-v2/uploads"),
}
SOURCES = {
    "images": Path("/var/lib/myrecipesite/recipe_images"),
    "pdfs": Path("/var/lib/myrecipesite/custom_prints"),
    "ingredient_images": Path("/var/www/MyRecipeSite/myrecipes/static/ingredient_images"),
}


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def files_under(directory):
    if not directory.is_dir() or directory.is_symlink():
        raise RuntimeError(f"Missing or linked source directory: {directory}")
    for path in directory.rglob("*"):
        if path.is_symlink():
            raise RuntimeError(f"Linked source entry: {path}")
        if path.is_file():
            yield path


def copy_missing(source, target, expected):
    temporary = target.with_name(target.name + ".copy-" + secrets.token_hex(8))
    try:
        shutil.copy2(source, temporary)
        if sha256(temporary) != expected or sha256(source) != expected:
            raise RuntimeError(f"Source changed during copy: {source}")
        try:
            os.link(temporary, target)
        except FileExistsError:
            if sha256(target) != expected:
                raise RuntimeError(f"Destination conflict: {target}")
    finally:
        temporary.unlink(missing_ok=True)


def run(environment, apply):
    root = ROOTS[environment]
    if not root.is_dir() or root.is_symlink():
        raise RuntimeError(f"Missing or linked destination root: {root}")
    summary = {}
    for folder, source_root in SOURCES.items():
        destination_root = root / folder
        source_files = list(files_under(source_root))
        if destination_root.is_symlink():
            raise RuntimeError(f"Linked destination directory: {destination_root}")
        if apply:
            destination_root.mkdir(mode=0o700, exist_ok=True)
        elif not destination_root.is_dir():
            summary[folder] = {"source_files": len(source_files),
                               "missing_files_before": len(source_files),
                               "verified_files": None}
            continue
        missing = 0
        for source in source_files:
            relative = source.relative_to(source_root)
            target = destination_root / relative
            if target.parent.is_symlink():
                raise RuntimeError(f"Linked destination parent: {target.parent}")
            expected = sha256(source)
            if target.exists() or target.is_symlink():
                if not target.is_file() or target.is_symlink() or sha256(target) != expected:
                    raise RuntimeError(f"Destination conflict: {target}")
            else:
                missing += 1
                if apply:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    copy_missing(source, target, expected)
            if apply and sha256(target) != expected:
                raise RuntimeError(f"Verification failed: {target}")
        summary[folder] = {"source_files": len(source_files),
                           "missing_files_before": missing,
                           "verified_files": len(source_files) if apply else None}
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("environment", choices=ROOTS)
    parser.add_argument("--apply", action="store_true", help="copy missing files and verify hashes")
    args = parser.parse_args()
    print(json.dumps({"environment": args.environment, "apply": args.apply,
                      "folders": run(args.environment, args.apply)}, indent=2))


if __name__ == "__main__":
    main()
