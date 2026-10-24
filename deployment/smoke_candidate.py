"""Read-only HTTP smoke check for the Pi's isolated FastAPI candidate."""

import json
import time
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit
from urllib.request import urlopen


BASE = "http://127.0.0.1:8012"


class Images(HTMLParser):
    def __init__(self):
        super().__init__()
        self.sources = []

    def handle_starttag(self, tag, attrs):
        if tag == "img":
            self.sources.extend(value for key, value in attrs if key == "src")


def get(path):
    start = time.monotonic()
    with urlopen(BASE + path, timeout=35) as response:
        body = response.read()
        assert response.status == 200, (path, response.status)
        print(f"{path} status=200 bytes={len(body)} seconds={time.monotonic()-start:.2f}")
        return body


def main():
    health = json.loads(get("/health"))
    assert health["environment"] == "production"
    assert health["database"] == "MyRecipes"
    assert health["read_only"] and not health["saves_enabled"]
    for path in (
        "/", "/plan", "/tags", "/tags/collections", "/tags/cuisines",
        "/tags/synonyms", "/image-aliases", "/recipes/new",
        "/static/brand/my-recipes.png", "/static/favicon.svg",
    ):
        get(path)
    parser = Images()
    parser.feed(get("/recipes/3550?log_visit=false").decode("utf-8"))
    for prefix in ("/recipe-images/", "/ingredient-images/"):
        matches = [urlsplit(urljoin(BASE, src)).path for src in parser.sources
                   if urlsplit(urljoin(BASE, src)).path.startswith(prefix)]
        assert matches, "No image on the recipe page for " + prefix
        get(matches[0])


if __name__ == "__main__":
    main()
