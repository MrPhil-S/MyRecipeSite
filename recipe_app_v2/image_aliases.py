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
    'eggs': 'egg', 'shallots': 'shallot', 'carrots': 'carrot', 'chives': 'chive',
    'capers': 'caper', 'chops': 'chop', 'thighs': 'thigh', 'breasts': 'breast',
    'wings': 'wing', 'drumsticks': 'drumstick', 'livers': 'liver',
    'wedges': 'wedge', 'tortillas': 'tortilla', 'lemons': 'lemon', 'limes': 'lime',
    'cucumbers': 'cucumber', 'avocados': 'avocado', 'almonds': 'almond',
    'cashews': 'cashew', 'peanuts': 'peanut', 'skewers': 'skewer', 'steaks': 'steak',
    'olives': 'olive', 'lentils': 'lentil', 'oats': 'oat', 'peppercorns': 'peppercorn',
    'artichokes': 'artichoke', 'apples': 'apple', 'chestnuts': 'chestnut',
    'chips': 'chip', 'shells': 'shell', 'juiced': 'juice',
    'stalks': 'stalk', 'sprigs': 'sprig', 'rings': 'ring', 'pieces': 'piece',
    'pickles': 'pickle', 'pistachios': 'pistachio', 'raisins': 'raisin',
    'dates': 'date', 'oranges': 'orange', 'cans': 'can', 'cutlets': 'cutlet',
    'crackers': 'cracker', 'bitters': 'bitter', 'slices': 'slice',
}

# These words identify a different food, cut or product; matching just a
# component (flour in a tortilla, water in water chestnuts) is not sufficient.
IMAGE_HEADS = frozenset(('sauce', 'paste', 'jelly', 'tortilla', 'chestnut',
    'juice', 'zest', 'noodle', 'starch', 'syrup', 'vinegar', 'broth', 'stock',
    'sausage', 'meatball', 'breast', 'thigh', 'wing', 'drumstick', 'liver',
    'tenderloin', 'chop', 'shell', 'chip', 'rind', 'dressing', 'soup', 'powder',
    'yogurt', 'ketchup'))

# Only preparation descriptors may augment an already named ingredient.
# Notes containing serving suggestions or substitutes must not supply another food.
PREPARATION = frozenset('minced crushed chopped crumbled roasted toasted ground cracked '
    'grated shredded sliced diced peeled shelled deveined pitted canned frozen '
    'boneless skinless fresh dried raw unsalted salted light low reduced sodium '
    'seed leaf stalk sprig wedge juice zest whole can inch mexican '
    'center cut piece 10 12'.split())
FORM_WORDS = frozenset('minced crushed chopped crumbled roasted toasted ground cracked '
    'grated shredded sliced diced peeled shelled deveined pitted canned frozen '
    'boneless skinless dried unsalted light'.split())
MEASURES = frozenset('lb lbs pound pounds ounce ounces oz g gm grams kg cup cups '
    'tablespoon tablespoons tbsp teaspoon teaspoons tsp bunch bunches large small '
    'medium x one two a an of fresh raw skin on bone in full fat low moisture '
    'finely coarsely toasted chopped boneless skinless'.split())


def primary_text(text):
    text = re.sub(r'(\d)\s+or\s+(\d)', r'\1 to \2', text, flags=re.I)
    text = re.sub(r'\((?:or|such as|can substitute)\b[^)]*\)', '', text, flags=re.I)
    text = re.sub(r'\bhomemade\s+or\s+store[- ]bought\b', '', text, flags=re.I)
    # Recover shared nouns in these common alternatives, keeping the first option.
    for alternatives, noun in ((r'corn|flour', r'tortillas?'),
                               (r'plain|Greek', 'yogurt'),
                               (r'feta|goat', 'cheese'),
                               (r'light|dark', 'brown sugar'),
                               (r'red|white', 'wine'),
                               (r'white|apple cider', 'vinegar'),
                               (r'rapid rise|instant', 'yeast')):
        text = re.sub(r'\b(' + alternatives + r')\s+or\s+(?:' + alternatives
                      + r')\s+(' + noun + r')\b', r'\1 \2', text, flags=re.I)
    return re.split(r'\bor\b|\bsuch as\b|\bcan substitute\b|//|\+\s*\d',
                    text, maxsplit=1, flags=re.I)[0]


def preparation_context(text, note):
    primary = normalize(primary_text(text))
    # Ignore instructions that introduce other ingredients and removed parts.
    note = re.split(r'\b(?:or|such as|plus|for|with|serve|serving)\b',
                    note or '', maxsplit=1, flags=re.I)[0]
    note = re.sub(r'\b(?:seeds?|stems?|skins?)\s+removed\b', '', note, flags=re.I)
    note = re.sub(r'\bjuice\s+(?:drained|reserved)\b', '', note, flags=re.I)
    note = normalize(note)
    note = re.sub(r'\blite\b', 'light', note)
    # Recover rows split after quantity/modifiers: "1 lb boneless", "skinless chicken thighs".
    identity = {w for w in primary.split() if not any(c.isdigit() for c in w)} - MEASURES - PREPARATION
    if not identity:
        return primary + ' ' + note
    return primary + ' ' + ' '.join(w for w in note.split() if w in PREPARATION)


def normalize(value):
    for _ in range(8):
        decoded = html.unescape(value)
        if decoded == value:
            break
        value = decoded
    value = unicodedata.normalize('NFKD', unquote(value)).casefold()
    value = ''.join(char for char in value if not unicodedata.combining(char))
    tokens = re.findall(r'[a-z0-9]+', value)
    normalized = ' '.join(PLURALS.get(token, token) for token in tokens)
    # Known compound spellings; no unrestricted substring or fuzzy matching.
    normalized = re.sub(r'\blemon grass\b', 'lemongrass', normalized)
    normalized = re.sub(r'\bcornstarch\b', 'corn starch', normalized)
    normalized = re.sub(r'\bclove garlic\b', 'garlic clove', normalized)
    normalized = re.sub(r'\bgingerroot\b', 'ginger root', normalized)
    normalized = re.sub(r'\bzested\b', 'zest', normalized)
    normalized = re.sub(r'\bcan\b', 'canned', normalized)
    return normalized


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
        self.catalogue = load_catalogue() if values is None else values
        self.version = revision(self.catalogue)
        for name, aliases in self.catalogue.items():
            target_words = frozenset(normalize(name).split())
            for term, explicit in [(name, False)] + [(alias, True) for alias in aliases]:
                phrase = normalize(term)
                if phrase:
                    self.entries.append((name, phrase, explicit,
                        re.compile(r'(?<!\w)' + re.escape(phrase) + r'(?!\w)'),
                        frozenset(phrase.split()), target_words))

    def match(self, text, note=''):
        normalized = preparation_context(text, note)
        words = set(normalized.split())
        primary_words = set(normalize(primary_text(text)).split())
        # A fruit providing both juice and zest uses its whole-fruit illustration.
        fruits = words & {'lemon', 'lime', 'orange'}
        if len(fruits) == 1 and {'juice', 'zest'} <= words:
            fruit = next(iter(fruits))
            if fruit in self.catalogue:
                return fruit
        candidates = []
        opposites = [('fresh', 'dried'), ('red', 'white'), ('salted', 'unsalted'),
                     ('sweet', 'hot'), ('ground', 'whole')]
        for name, phrase, explicit, pattern, phrase_words, target in self.entries:
            # Multiword identities and preparation can be reordered (garlic,
            # minced; boneless skinless chicken breast). Never use substrings.
            if not pattern.search(normalized) and not (len(phrase_words) > 1 and phrase_words <= words):
                continue
            # The reviewed "pepper" convention is for unspecified seasoning,
            # not an alias for every vegetable or pepper-containing product.
            if name == 'ground_black_pepper' and phrase == 'pepper':
                seasoning = MEASURES | PREPARATION | {'pepper', 'to', 'taste', 'optional', 'pinch', 'freshly'}
                if (any(w not in seasoning and not any(c.isdigit() for c in w) for w in words)
                        or re.search(r'\bpeppers\b', text, flags=re.I)):
                    continue
            # An explicit full alias can describe a form not present in its
            # image filename (red pepper flakes -> crushed red chili peppers).
            semantic_target = target | (set(phrase.split()) if explicit else set())
            if (words & IMAGE_HEADS) - semantic_target:
                continue
            # A sauce or paste must not become its pepper/vegetable component.
            if not explicit and any(head in words and head not in target for head in ('sauce', 'paste', 'jelly')):
                continue
            if any((a in words and b in target) or (b in words and a in target) for a, b in opposites):
                continue
            if 'bone in' in normalized and 'boneless' in target:
                continue
            # This distinction applies to coriander's leafy image, not every
            # ingredient: fresh ginger root legitimately uses the ginger image.
            if (('root' in words or 'seed' in words)
                    and name in ('cilantro_(coriander_herb)', 'coriander_leaves')):
                continue
            # A longer ingredient phrase remains important; matching explicit
            # preparation breaks ties against unprepared clove/root images.
            score = len(phrase_words) + len(phrase_words & FORM_WORDS)
            primary_identity = len((phrase_words - PREPARATION) & primary_words)
            candidates.append(((score, primary_identity, len(phrase_words), int(explicit)), name))
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
