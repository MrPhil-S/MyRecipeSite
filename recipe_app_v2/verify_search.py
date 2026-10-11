"""Verify search using an independent Python reference over real legacy rows."""
import json
import re
import subprocess
from collections import defaultdict
from urllib.parse import parse_qs, urlsplit
from html import unescape

import httpx
from sqlalchemy import func, select

from recipe_app_v2.config import ROOT
from recipe_app_v2.database import get_engine
from recipe_app_v2.models import Query_History, recipe_view_date
from recipe_app_v2.search_cases import CASES


def verify():
    process = subprocess.run([str(ROOT / 'MyRecipesVenv/Scripts/python.exe'), '-m',
                              'recipe_app_v2.legacy_search_snapshot'], cwd=ROOT,
                             capture_output=True, text=True, encoding='utf-8', check=True)
    data = json.loads(process.stdout)
    ingredients, instructions = defaultdict(list), defaultdict(list)
    for row in data['ingredients']:
        ingredients[row['id']].append(row['text'].lower())
    for row in data['instructions']:
        instructions[row['id']].append(row['text'].lower())

    def matches(recipe, term):
        term = term.lower()
        terms = {term}
        for primary, secondary in data['synonyms']:
            if term in primary.lower() or term in secondary.lower():
                terms.update((primary.lower(), secondary.lower()))
        return (term in recipe['name'].lower() or term in recipe['notes'].lower()
                or any(term in text for text in instructions[recipe['id']])
                or any(t in text for t in terms for text in ingredients[recipe['id']]))

    differences = []
    with httpx.Client(base_url='http://127.0.0.1:8001', timeout=30) as client:
        for query, included, excluded in CASES:
            expected = [r['id'] for r in data['recipes']
                        if all(matches(r, t) for t in included) and not any(matches(r, t) for t in excluded)]
            for sort in ('recent', 'name'):
                ordered = expected if sort == 'recent' else [r for r in data['name_order'] if r in set(expected)]
                actual = []
                for page in range(1, max(1, (len(ordered) + 23) // 24) + 1):
                    response = client.get('/', params={'q': query, 'sort': sort, 'page': page}, headers={'HX-Request': 'true'})
                    response.raise_for_status()
                    actual.extend(int(n) for n in re.findall(r'data-recipe-id="(\d+)"', response.text))
                    assert '<!doctype' not in response.text
                    if query:
                        for href in re.findall(r'href="([^\"]+)"', response.text):
                            href = unescape(href)
                            if href.startswith('/recipes/'):
                                assert parse_qs(urlsplit(href).query)['q'] == [query]
                assert actual == ordered, f'Search mismatch for {query!r}, {sort}'
            if query in data['legacy']:
                old, new = set(data['legacy'][query]), set(expected)
                if old != new:
                    differences.append({'query': query, 'additional_valid_matches': len(new - old),
                                        'removed_legacy_matches': len(old - new)})
        assert client.get('/', params={'q': 'x' * 201}).status_code == 422
    with get_engine().connect() as conn:
        assert conn.scalar(select(func.count()).select_from(Query_History)) == data['history_count']
        assert conn.scalar(select(func.count()).select_from(recipe_view_date)) == data['visit_count']
    print(json.dumps({'queries_checked': len(CASES), 'sort_modes': 2, 'reference_parity': 'ok',
                      'history_and_visits_unchanged': True, 'legacy_differences': differences}, indent=2))


if __name__ == '__main__':
    verify()
