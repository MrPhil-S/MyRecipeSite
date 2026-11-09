"""Build a pinned FastAPI runtime archive with explicit provenance."""

import argparse
import hashlib
import io
import json
import subprocess
import tarfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
APP = "recipe_app_v2/"
PYTHON = """__init__.py activity.py collections.py config.py cooked_history.py database.py
editor.py editor_routes.py image_alias_routes.py image_aliases.py ingredient_rematch.py
main.py models.py recipe_book.py recipe_saves.py recipes.py search.py search_history.py
sorting.py tags.py uploads.py""".split()
TEMPLATES = """_brand_image.html _detail_fragment.html _editor.html _ingredient_row.html
_library_floating_actions.html _library_results.html _library_sidebar.html
_meal_plan.html _plan_fragment.html _recipe_detail.html _recipe_photo.html
_recipes.html _search_history.html _table_headers.html _tag_delete.html
_tag_form.html app_header.html base.html delete_recipe.html detail.html editor.html
image_alias_form.html image_aliases.html image_rematches.html index.html
not_found.html plan.html recipe_book.html shared/icons.html tag_form.html
tags.html""".split()
STATIC = """app.css app-pages.css brand/brand.css brand/my-recipes.png
design-home.css design-recipe.css favicon.svg fonts/dm-sans.ttf
fonts/DM-Sans-LICENSE.txt image-upload.js live-app.css recipe-controls.js
search-controls.js vendor/alpine.min.js vendor/ALPINE-LICENSE.txt
vendor/htmx.min.js vendor/HTMX-LICENSE.txt""".split()
RUNTIME = tuple(sorted(
    [APP + name for name in PYTHON]
    + [APP + "templates/" + name for name in TEMPLATES]
    + [APP + "static/" + name for name in STATIC]
    + [APP + "image_alias_seed.json", APP + "requirements.txt"]
))


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT)


def fail(message):
    raise ValueError(message)


def build(output, mode):
    output = (ROOT / output).resolve() if not output.is_absolute() else output.resolve()
    if ROOT not in output.parents or output.exists():
        fail("Output must be a new file inside the project workspace.")
    if not output.is_relative_to(ROOT / "tmp"):
        fail("Write review/build artifacts under the ignored tmp directory.")

    commit = git("rev-parse", "HEAD").decode().strip()
    tracked = set(git("ls-files", "-z", "--", "recipe_app_v2").decode().strip("\0").split("\0"))
    dirty = bool(git("status", "--porcelain", "--untracked-files=all"))
    committed = set(git("ls-tree", "-r", "--name-only", "-z", commit, "--", "recipe_app_v2").decode().strip("\0").split("\0"))
    if mode == "release" and dirty:
        fail("Committed release requires a clean working tree.")

    source = {}
    provenance = {}
    for path in RUNTIME:
        file = ROOT / path
        if mode == "release":
            if path not in committed:
                fail("Required committed runtime input is missing: " + path)
            data = git("show", f"{commit}:{path}")
            provenance[path] = "commit:" + commit
        else:
            if not file.is_file() or file.is_symlink():
                fail("Required runtime input is missing or linked: " + path)
            data = file.read_bytes()
            provenance[path] = "tracked-working-tree" if path in tracked else "untracked-working-tree"
        if not data:
            fail("Empty runtime input: " + path)
        source[path] = data

    # A newly added template or asset must receive an explicit runtime review.
    for folder in ("templates", "static"):
        actual = {
            p.relative_to(ROOT).as_posix() for p in (ROOT / APP / folder).rglob("*")
            if p.is_file() and "__pycache__" not in p.parts
        }
        unexpected = actual - set(RUNTIME)
        if unexpected:
            fail("Unreviewed runtime tree input: " + sorted(unexpected)[0])

    manifest = {
        "format": 2,
        "kind": "non-deployable-working-tree-preview" if mode == "preview" else "committed-runtime-release",
        "source_commit": commit,
        "working_tree_dirty": dirty,
        "members": [
            {"path": path, "sha256": hashlib.sha256(data).hexdigest(),
             "bytes": len(data), "provenance": provenance[path]}
            for path, data in sorted(source.items())
        ],
        "persistent_media": "external; not included in source archive",
    }
    source["RELEASE_MANIFEST.json"] = (json.dumps(manifest, indent=2) + "\n").encode()
    output.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(output, "w:gz") as archive:
        for path, data in sorted(source.items()):
            info = tarfile.TarInfo(path)
            info.size = len(data)
            info.mode = 0o644
            archive.addfile(info, io.BytesIO(data))
    print(f"kind={manifest['kind']}")
    print(f"commit={commit}")
    print(f"archive={output}")
    print(f"files={len(source)}")
    print(f"sha256={hashlib.sha256(output.read_bytes()).hexdigest()}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("preview", "release"))
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    try:
        build(args.output, args.mode)
    except (ValueError, subprocess.CalledProcessError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
