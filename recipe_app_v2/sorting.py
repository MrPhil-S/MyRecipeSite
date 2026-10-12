from typing import Literal

SortOrder = Literal['recent', 'recent_asc', 'name', 'name_desc',
                    'cooked', 'cooked_asc', 'visited', 'visited_asc']
SORT_CHOICES = (
    ('recent', 'Newest added first'), ('recent_asc', 'Oldest added first'),
    ('name', 'A to Z'), ('name_desc', 'Z to A'),
    ('cooked', 'Most recently cooked first'), ('cooked_asc', 'Least recently cooked first'),
    ('visited', 'Most recently visited first'), ('visited_asc', 'Least recently visited first'),
)
