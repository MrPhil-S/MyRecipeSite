"""Independent image-name catalogue, conservative matching and atomic local edits."""
import hashlib
import html
import json
import os
import re
import tempfile
import threading
import unicodedata
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import quote, unquote

from .config import ROOT
from .database import writes_enabled
from .uploads import upload_root

SEED = Path(__file__).with_name('image_alias_seed.json')
LOCK = threading.RLock()
PLURALS = {
    'onions': 'onion', 'scallions': 'scallion', 'peppers': 'pepper',
    'chilies': 'chili', 'chiles': 'chili', 'chilli': 'chili', 'chillies': 'chili', 'chile': 'chili',
    'leaves': 'leaf', 'roots': 'root', 'stems': 'stem', 'seeds': 'seed',
    'noodles': 'noodle', 'sheets': 'sheet', 'fillets': 'fillet', 'filets': 'fillet', 'filet': 'fillet',
    'beans': 'bean', 'potatoes': 'potato', 'tomatoes': 'tomato', 'mushrooms': 'mushroom',
    'sprouts': 'sprout', 'buns': 'bun', 'rolls': 'roll', 'cloves': 'clove', 'pods': 'pod',
    'walnuts': 'walnut', 'pecans': 'pecan', 'cherries': 'cherry', 'bananas': 'banana',
    'florets': 'floret', 'flakes': 'flake', 'jalapenos': 'jalapeno', 'zucchinis': 'zucchini',
    'tenderloins': 'tenderloin', 'ribs': 'rib', 'chickpeas': 'chickpea',
}


def normalize(value):
    for _ in range(8):
        decoded = html.unescape(value)
        if decoded == value:
            break
        value = decoded
    value = unicodedata.normalize('NFKD', unquote(value)).casefold()
    value = ''.join(char for char in value if not unicodedata.combining(char))
    tokens = re.findall(r'[a-z0-9]+', value)
    return ' '.join(PLURALS.get(token, token) for token in tokens)


def catalogue_path():
    return upload_root() / 'ingredient-image-aliases.json'


def load_catalogue():
    path = catalogue_path()
    values = json.loads((path if path.exists() else SEED).read_text(encoding='utf-8'))
    if not isinstance(values, dict):
        raise ValueError('Invalid image alias catalogue.')
    return values


def revision(values):
    return hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()


def image_url(name):
    folder = ROOT / 'myrecipes/static/ingredient_images'
    valid = bool(name and re.fullmatch(r'[A-Za-z0-9_%() -]{1,100}', name))
    filename = name + '.jpg' if valid and (folder / (name + '.jpg')).is_file() else 'default_ingredient.jpg'
    return '/ingredient-images/' + quote(filename, safe='')


class Matcher:
    def __init__(self, values=None):
        self.entries = []
        for name, aliases in (load_catalogue() if values is None else values).items():
            for term, explicit in [(name, False)] + [(alias, True) for alias in aliases]:
                phrase = normalize(term)
                if phrase:
                    self.entries.append((name, phrase, explicit,
                        re.compile(r'(?<!\w)' + re.escape(phrase) + r'(?!\w)')))

    def match(self, text):
        # Alternatives/examples never outrank the primary ingredient.
        primary = re.split(r'\bor\b|\bsuch as\b', text, maxsplit=1, flags=re.I)[0]
        normalized = normalize(primary)
        words = set(normalized.split())
        candidates = []
        opposites = [('fresh', 'dried'), ('red', 'white'), ('salted', 'unsalted'),
                     ('sweet', 'hot'), ('ground', 'whole')]
        for name, phrase, explicit, pattern in self.entries:
            if not pattern.search(normalized):
                continue
            target = set(normalize(name).split())
            # A sauce or paste must not become its pepper/vegetable component.
            if not explicit and any(head in words and head not in target for head in ('sauce', 'paste', 'jelly')):
                continue
            if any((a in words and b in target) or (b in words and a in target) for a, b in opposites):
                continue
            if 'bone in' in normalized and 'boneless' in target:
                continue
            # Do not turn coriander roots/seeds into the leafy herb through a shorter alias.
            if ('root' in words or 'seed' in words) and not ({'root', 'seed'} & target):
                continue
            candidates.append(((len(phrase.split()), int(explicit)), name))
        if not candidates:
            return 'default_ingredient'
        best = max(score for score, _ in candidates)
        winners = {name for score, name in candidates if score == best}
        return winners.pop() if len(winners) == 1 else 'default_ingredient'


@contextmanager
def catalogue_lock():
    path = catalogue_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with LOCK, path.with_suffix('.lock').open('a+b') as handle:
        if handle.tell() == 0:
            handle.write(b'0')
            handle.flush()
        handle.seek(0)
        if os.name == 'nt':
            import msvcrt
            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl
            fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == 'nt':
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle, fcntl.LOCK_UN)


def save_entry(name, aliases, version, original='', action='save'):
    if not writes_enabled():
        raise PermissionError('Dev saves are disabled.')
    if (not re.fullmatch(r'[A-Za-z0-9_%() -]{1,100}', name) or not normalize(name)
            or name.casefold() == 'default_ingredient'):
        raise ValueError('Use an image name of up to 100 characters without a path or extension.')
    if len(aliases) > 100 or any(not re.search('[a-z]', normalize(alias)) or len(alias) > 100 for alias in aliases):
        raise ValueError('Use up to 100 aliases, one per line, with up to 100 characters each.')
    if len({normalize(alias) for alias in aliases}) != len(aliases):
        raise ValueError('Aliases must be distinct after spelling normalization.')
    with catalogue_lock():
        values = load_catalogue()
        if revision(values) != version:
            raise RuntimeError('The catalogue changed. Reload before saving.')
        if original and (original != name or original not in values):
            raise ValueError('Reload the original entry before editing.')
        if not original and name in values:
            raise ValueError('That image name already exists. Edit its entry instead.')
        if action == 'delete':
            if not original:
                raise ValueError('Choose an existing entry to delete.')
            del values[name]
        else:
            incoming = {normalize(alias) for alias in aliases}
            incoming.add(normalize(name))
            for other, other_aliases in values.items():
                if other != name and incoming & {normalize(term) for term in [other] + other_aliases}:
                    raise ValueError(f'An equivalent name is already assigned to {other}.')
            values[name] = aliases
        path = catalogue_path()
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, delete=False) as handle:
                temporary = Path(handle.name)
                json.dump(values, handle, sort_keys=True, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            if temporary is not None and temporary.exists():
                temporary.unlink()
