from typing import Literal
from urllib.parse import urlencode

SortOrder = Literal['recent', 'recent_asc', 'name', 'name_desc',
                    'cooked', 'cooked_asc', 'visited', 'visited_asc']
SORT_CHOICES = (
    ('recent', 'Newest added first'), ('recent_asc', 'Oldest added first'),
    ('name', 'A to Z'), ('name_desc', 'Z to A'),
    ('cooked', 'Most recently cooked first'), ('cooked_asc', 'Least recently cooked first'),
    ('visited', 'Most recently visited first'), ('visited_asc', 'Least recently visited first'),
)


def table_headers(path, columns, sort, direction, parameters):
    return [{'key': key, 'label': label,
             'aria_sort': ('ascending' if direction == 'asc' else 'descending') if sort == key else 'none',
             'url': path + '?' + urlencode(dict(parameters, sort=key,
                 direction='desc' if sort == key and direction == 'asc' else 'asc'))}
            for key, label in columns]
