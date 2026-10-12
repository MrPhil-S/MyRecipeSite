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

    def test_fallback_is_safe_and_keeps_existing_images(self):
        folder = Path(self.folder.name) / 'myrecipes/static/ingredient_images'
        folder.mkdir(parents=True)
        (folder / 'mint.jpg').write_bytes(b'test image file')
        with patch('recipe_app_v2.image_aliases.ROOT', Path(self.folder.name)):
            for value in (None, '', '../gin', 'not_a_real_ingredient', 'gin'):
                self.assertEqual(image_url(value), '/ingredient-images/default_ingredient.jpg')
            self.assertEqual(image_url('mint'), '/ingredient-images/mint.jpg')

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
