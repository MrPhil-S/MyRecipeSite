import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from recipe_app_v2.config import ROOT
from recipe_app_v2.uploads import upload_root


class UploadConfigTests(unittest.TestCase):
    def test_production_rejects_missing_relative_and_release_paths(self):
        for value in ('', 'uploads', str(ROOT), str(ROOT / 'recipe_app_v2')):
            with self.subTest(value=value), patch.dict(os.environ, {
                'RECIPE_APP_ENV': 'production', 'RECIPE_UPLOADS': value,
            }):
                with self.assertRaises(RuntimeError):
                    upload_root()

    def test_production_requires_existing_external_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {
                'RECIPE_APP_ENV': 'production', 'RECIPE_UPLOADS': directory,
            }):
                self.assertEqual(upload_root(), Path(directory).resolve())
            with patch.dict(os.environ, {
                'RECIPE_APP_ENV': 'production', 'RECIPE_UPLOADS': str(Path(directory) / 'missing'),
            }):
                with self.assertRaises(RuntimeError):
                    upload_root()
