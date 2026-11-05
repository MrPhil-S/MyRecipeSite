import os
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from recipe_app_v2.image_aliases import (Matcher, catalogue_path, image_url, load_catalogue,
                                        normalize, revision, save_entry)
from recipe_app_v2.main import app


class ImageAliasTests(unittest.TestCase):
    def test_preparation_and_reviewed_identities(self):
        matcher = Matcher()
        cases = [
            ('3 cloves garlic', 'minced', 'minced_garlic'),
            ('1 tablespoon fresh ginger root', 'minced', 'minced_ginger'),
            ('1 piece fresh ginger root', 'chopped', 'ginger'),
            ('pepper', 'to taste', 'ground_black_pepper'),
            ('1 tsp Chinese five-spice powder', '', 'five_spice_mix'),
            ('2 green bell peppers', 'halved and seeded', 'green_capsicum'),
            ('Pickled turnip', '', 'turnip'),
            ('tahini paste', '', 'tahini_sauce'),
            ('tzatziki sauce', '', 'tzatziki'),
            ('pancetta bacon', 'thinly sliced, chopped', 'diced_pancetta'),
            ('12 toasted corn or flour tortillas', '', 'corn_tortilla'),
            ('plain or Greek yogurt', '', 'plain_yogurt'),
            ('1 lime', 'zested and juiced', 'lime'),
            ('Grated zest and juice of 1 lime', '', 'lime'),
            ('1 lb boneless', 'skinless chicken thighs', 'boneless_chicken_thigh'),
            ('Toasted', 'chopped cashews', 'cashew'),
            ('2 tablespoons heavy cream', '', 'heavy_whipping_cream'),
            ('Thai basil', 'leaves roughly torn', 'thai_basil'),
            ('romaine lettuce', 'leaves separated', 'romaine_lettuce'),
            ('1 can pineapple rings', 'juice drained and reserved', 'canned_pineapple_slices'),
            ('4 oz feta or goat cheese', 'crumbled', 'crumbled_feta_cheese'),
            ('fresh thyme leaves', '', 'thyme_leaves'),
            ('12 ounces grated full-fat', 'low moisture mozzarella cheese', 'shredded_mozzarella_cheese'),
        ]
        for ingredient, note, expected in cases:
            with self.subTest(ingredient=ingredient, note=note):
                self.assertEqual(matcher.match(ingredient, note), expected)

    def test_preparation_does_not_borrow_alternatives_or_components(self):
        matcher = Matcher()
        for text, note, expected in [
            ('ginger', 'or minced garlic', 'ginger'),
            ('ginger', 'serve with garlic sauce', 'ginger'),
            ('3 cloves garlic', 'minced, plus chili sauce for serving', 'minced_garlic'),
            ('fresh basil', 'or dried oregano', 'basil'),
            ('2 peppers', '', 'default_ingredient'),
            ('white pepper', '', 'white_pepper'),
            ('chili pepper sauce', '', 'default_ingredient'),
        ]:
            with self.subTest(text=text, note=note):
                self.assertEqual(matcher.match(text, note), expected)
        self.assertEqual(Matcher({'water': []}).match('water chestnuts'), 'default_ingredient')
        self.assertEqual(Matcher({'flour': []}).match('corn or flour tortillas'), 'default_ingredient')
        self.assertEqual(Matcher({'a': ['red herb'], 'b': ['red herb']}).match('red herb'), 'default_ingredient')

    def test_alias_preview_accepts_and_preserves_preparation_note(self):
        response = self.client.get('/image-aliases', params={'sample': '2 cloves garlic', 'sample_note': 'minced'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['matched'], 'minced_garlic')
        self.assertIn('name="sample_note" value="minced"', response.text)
        self.assertIn('sample_note=minced', response.context['query_string'])

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {'RECIPE_UPLOADS': self.folder.name, 'RECIPE_DEV_WRITES': '1'})
        self.env.start()
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        self.env.stop()
        self.folder.cleanup()

    def test_normalization_aliases_variants_and_alternative_priority(self):
        matcher = Matcher()
        cases = {
            '2 bunches scallions': 'spring_onion',
            '1 fresh jalapeño': 'jalapeno_pepper',
            '7 oz extra-firm tofu': 'extra_firm_tofu',
            '½ cup cilantro leaves &amp;amp; tender stems': 'cilantro_(coriander_herb)',
            '1 teaspoon ground coriander': 'ground_coriander_seed',
            '2 cilantro roots': 'coriander_root',
            '1/2 teaspoon cayenne pepper (or 1 teaspoon Thai chile sauce)': 'ground_cayenne_pepper',
            '1 teaspoon smoked paprika': 'smoked_paprika_powder',
            '2 tablespoons red miso': 'red_miso_paste',
            '2 tablespoons white miso': 'white_miso_paste',
            '0.75 pounds lean ground beef': 'lean_beef_mince',
            '1 pound ground beef': 'beef_mince',
            '225g lasagna sheets': 'lasagne_noodle',
        }
        for text, expected in cases.items():
            self.assertEqual(matcher.match(text), expected, text)
        self.assertEqual(normalize('JALAPEÑO  peppers'), 'jalapeno pepper')
        self.assertEqual(Matcher({'butter': []}).match('butternut squash'), 'default_ingredient')
        self.assertEqual(Matcher({'gin': [], 'ham': []}).match('ginger champagne'), 'default_ingredient')
        self.assertEqual(Matcher({'a': ['scallion'], 'b': ['scallions']}).match('2 scallions'), 'default_ingredient')
        self.assertEqual(Matcher({'dried_basil': ['basil']}).match('fresh basil'), 'default_ingredient')
        self.assertEqual(Matcher({'chili_pepper': []}).match('asian chile pepper sauce'), 'default_ingredient')

    def test_reviewed_compounds_cuts_and_plural_forms_do_not_match_components(self):
        matcher = Matcher()
        cases = {
            'lemon wedges': 'lemon_wedge',
            'fresh lime wedges': 'lime_wedge',
            '1 tablespoon lemon grass': 'lemongrass',
            '4 chicken breasts': 'chicken_breast',
            '6 chicken thighs': 'chicken_thigh',
            '3 pounds chicken wings': 'chicken_wing',
            '3 cloves garlic': 'garlic_clove',
            '2 or 3 large garlic cloves': 'garlic_clove',
            '4 pork chops': 'pork_chop',
            '2 eggs': 'egg',
            '2 tablespoons cornstarch': 'corn_starch',
            '1 piece fresh ginger root': 'ginger',
        }
        for text, expected in cases.items():
            self.assertEqual(matcher.match(text), expected, text)
        blocked = {
            '6 flour tortillas': {'flour': []},
            '12 corn tortillas': {'corn': []},
            '1 can water chestnuts': {'water': []},
            '1 tablespoon lemon grass': {'lemon': []},
            '1 pound chicken breasts': {'chicken': []},
            '1 pound ground turkey breast': {'turkey': []},
            '1 cup jumbo pasta shells': {'pasta': []},
            '227g semi sweet chocolate chips': {'semi_sweet_chocolate': []},
            '1 tsp kombu dashi powder (can substitute for mushroom stock powder)': {'mushroom_stock': []},
            '1 tsp kombu dashi powder': {'kombu': []},
            '1 medium red kuri (or butternut) squash': {'butternut_squash': [], 'butter': []},
        }
        for text, entries in blocked.items():
            self.assertEqual(Matcher(entries).match(text), 'default_ingredient', text)

    def test_fallback_is_safe_and_keeps_existing_images(self):
        folder = Path(self.folder.name) / 'ingredient_images'
        folder.mkdir(parents=True)
        (folder / 'mint.jpg').write_bytes(b'test image file')
        for value in (None, '', '../gin', 'not_a_real_ingredient', 'gin'):
            self.assertEqual(image_url(value), '/ingredient-images/default_ingredient.jpg')
        self.assertEqual(image_url('mint'), '/ingredient-images/mint.jpg')

    def test_table_sorting_applies_before_pagination_and_preserves_filters(self):
        entries = {f'ingredient_{i:02d}': [f'alias {59-i:02d}'] for i in range(60)}
        with patch('recipe_app_v2.image_alias_routes.load_catalogue', return_value=entries):
            response = self.client.get('/image-aliases?sort=name&direction=desc&q=ingredient')
            self.assertEqual(response.context['rows'][0]['name'], 'ingredient_59')
            self.assertIn('aria-sort="descending"', response.text)
            self.assertIn('sort=name', response.text)
            self.assertIn('direction=desc', response.text)
            self.assertEqual(self.client.get('/image-aliases?sort=name&direction=desc&page=2').context['rows'][0]['name'], 'ingredient_09')
            self.assertEqual(self.client.get('/image-aliases?sort=aliases&direction=asc').context['rows'][0]['name'], 'ingredient_59')
            with patch('recipe_app_v2.image_alias_routes.image_url', side_effect=lambda n:
                       '/ingredient-images/mint.jpg' if n == 'ingredient_59' else '/ingredient-images/default_ingredient.jpg'):
                self.assertEqual(self.client.get('/image-aliases?sort=image&direction=asc').context['rows'][0]['name'], 'ingredient_59')

    def test_atomic_catalogue_edits_conflicts_and_stale_versions(self):
        start = load_catalogue()
        version = revision(start)
        save_entry('alias_test_image', ['unique test herb'], version)
        self.assertTrue(catalogue_path().is_file())
        self.assertEqual(Matcher().match('2 unique test herbs'), 'default_ingredient')
        self.assertEqual(Matcher().match('2 unique test herb'), 'alias_test_image')
        with self.assertRaises(RuntimeError):
            save_entry('second_test', [], version)
        updated = load_catalogue()
        with self.assertRaises(ValueError):
            save_entry('second_test', ['unique test herb'], revision(updated))
        with self.assertRaises(ValueError):
            save_entry('../unsafe', [], revision(updated))
        save_entry('alias_test_image', [], revision(updated), 'alias_test_image', 'delete')
        self.assertEqual(load_catalogue(), start)

    def test_management_csrf_preview_edit_delete_and_readonly_mode(self):
        body = self.client.get('/image-aliases/edit').text
        fields = {key: re.search(f'name="{key}" value="([^"]*)"', body)[1]
                  for key in ('csrf_token', 'version', 'original')}
        data = dict(fields, name='test_alias_image', aliases='unique test ingredient', action='save')
        self.assertEqual(self.client.post('/image-aliases/edit', data=dict(data, csrf_token='bad')).status_code, 403)
        self.assertEqual(self.client.post('/image-aliases/edit', data=data, follow_redirects=False).status_code, 303)
        body = self.client.get('/image-aliases?sample=unique+test+ingredient').text
        self.assertIn('test_alias_image', body)
        body = self.client.get('/image-aliases/edit?name=test_alias_image').text
        fields = {key: re.search(f'name="{key}" value="([^"]*)"', body)[1]
                  for key in ('csrf_token', 'version', 'original')}
        data = dict(fields, name='test_alias_image', aliases='unique test ingredient', action='delete')
        self.assertEqual(self.client.post('/image-aliases/edit', data=data).status_code, 422)
        self.assertEqual(self.client.post('/image-aliases/edit', data=dict(data, confirm_delete='yes'), follow_redirects=False).status_code, 303)
        with patch.dict(os.environ, {'RECIPE_DEV_WRITES': '0'}):
            data.update(action='save', name='readonly_test', original='', version=revision(load_catalogue()))
            self.assertEqual(self.client.post('/image-aliases/edit', data=data).status_code, 403)
