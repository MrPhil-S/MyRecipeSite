"""Fetch pinned browser libraries. Run: ``python -m tools.download_vendor``."""
from pathlib import Path
from urllib.request import urlopen

ASSETS = {
    "htmx.min.js": "https://cdn.jsdelivr.net/npm/htmx.org@2.0.4/dist/htmx.min.js",
    "alpine.min.js": "https://cdn.jsdelivr.net/npm/alpinejs@3.14.9/dist/cdn.min.js",
    "HTMX-LICENSE.txt": "https://cdn.jsdelivr.net/npm/htmx.org@2.0.4/LICENSE",
    "ALPINE-LICENSE.txt": "https://raw.githubusercontent.com/alpinejs/alpine/v3.14.9/LICENSE.md",
}


def download(target=None):
    target = Path(target) if target is not None else (
        Path(__file__).resolve().parents[1] / "recipe_app_v2" / "static" / "vendor"
    )
    target.mkdir(parents=True, exist_ok=True)
    for filename, url in ASSETS.items():
        with urlopen(url, timeout=30) as response:
            content = response.read()
        if len(content) < 100:
            raise RuntimeError("Unexpected empty vendor response")
        (target / filename).write_bytes(content)
        print(filename, len(content), "bytes")


if __name__ == "__main__":
    download()
