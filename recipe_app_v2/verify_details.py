"""Compare container details with legacy models and safely rendered templates."""
import json
import re
import subprocess
from html.parser import HTMLParser

import httpx
from sqlalchemy import func, select

from recipe_app_v2.config import ROOT
from recipe_app_v2.database import get_engine
from recipe_app_v2.models import recipe_view_date


class PageText(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.parts = []
        self.feed(html)

    def handle_data(self, text):
        self.parts.append(text)

    def value(self):
        return ' '.join(' '.join(self.parts).split())


def normalize(text):
    return ' '.join(str(text).split())


def verify():
    legacy = subprocess.run([str(ROOT / 'MyRecipesVenv/Scripts/python.exe'), '-m',
                             'recipe_app_v2.legacy_detail_snapshot'], cwd=ROOT,
                            capture_output=True, text=True, encoding='utf-8', check=True)
    snapshot = json.loads(legacy.stdout)
    assets = set()
    with httpx.Client(timeout=30) as client:
        for recipe in snapshot['recipes']:
            response = client.get(f"http://127.0.0.1:8001/recipes/{recipe['id']}?page=2&sort=name&log_visit=false")
            response.raise_for_status()
            actual = PageText(response.text).value()
            previous = PageText(recipe['legacy_html']).value()
            for field, attribute in [('ingredient_ids', 'ingredient'), ('instruction_ids', 'instruction'),
                                     ('source_note_ids', 'source-note')]:
                ids = [int(n) for n in re.findall(f'data-{attribute}-id="(\\d+)"', response.text)]
                assert ids == recipe[field], f"{recipe['id']}: {field} order differs"
            for value in [recipe['name'], *recipe['texts'], *recipe['collections'], *recipe['facts']]:
                expected = normalize(value)
                assert expected in actual, f"{recipe['id']}: detail content missing"
                assert expected in previous, f"{recipe['id']}: legacy content differs"
            if recipe['notes']:
                assert normalize(recipe['notes']) in actual
            if recipe['cuisine']:
                assert normalize(recipe['cuisine']) in actual
            assert f"Cooked {recipe['cook_count']} times" in actual
            assert f"{recipe['view_count']} recorded views" in actual
            assert '/?page=2&amp;sort=name' in response.text
            assert ('Source recipe PDF' in actual) == recipe['pdf']
            assets.update(re.findall(r'(?:src|href)="(/(?:recipe-images|ingredient-images|source-pdfs)/[^\"]+)"', response.text))
        asset_status = {'ok': 0, 'missing': 0}
        for path in sorted(assets):
            status = client.get('http://127.0.0.1:8001' + path).status_code
            assert status in (200, 404), f"Asset failed: {status}"
            asset_status['ok' if status == 200 else 'missing'] += 1
        assert client.get('http://127.0.0.1:8001/recipes/2147483647').status_code == 404
        assert client.post('http://127.0.0.1:8001/recipes/3674').status_code == 405
    with get_engine().connect() as conn:
        after = conn.scalar(select(func.count()).select_from(recipe_view_date))
    assert after == snapshot['visit_count'], 'Visit history changed during read-only checks'
    print(json.dumps({'details_checked': len(snapshot['recipes']), 'legacy_template_parity': 'ok',
                      'visit_history_unchanged': True, 'back_navigation': 'ok', 'assets': asset_status}, indent=2))


if __name__ == '__main__':
    verify()
