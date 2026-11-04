import tempfile
import os
import unittest
from pathlib import Path
from unittest.mock import patch

from deployment.form_parser import FormParser
from tools.download_vendor import ASSETS, download
from tools.verify_dev import expected_local_recorded_dt_extra, verify


class FormParserTests(unittest.TestCase):
    def test_collects_controls_repeats_selects_textareas_and_entities(self):
        html = (
            '<input name="q" value="a&amp;b">'
            '<input type="file" name="upload">'
            '<input type="checkbox" name="flag" value="yes">'
            '<input type="checkbox" name="flag" value="ok" checked>'
            '<select name="one"><option value="first">1</option>'
            '<option value="second" selected>2</option></select>'
            '<select name="many" multiple><option value="a" selected>A</option>'
            '<option value="b" selected>B</option></select>'
            '<textarea name="notes">A &amp; B</textarea>'
        )
        self.assertEqual(FormParser(html).fields, [
            ('q', 'a&b'), ('flag', 'ok'), ('one', 'second'),
            ('many', 'a'), ('many', 'b'), ('notes', 'A & B'),
        ])

    def test_unselected_single_select_uses_first_option(self):
        self.assertEqual(FormParser(
            '<select name="choice"><option value="x">X</option></select>'
        ).fields, [('choice', 'x')])


class ToolTests(unittest.TestCase):
    def test_dev_audit_rejects_production_before_getting_an_engine(self):
        with patch.dict(os.environ, {'RECIPE_APP_ENV': 'production'}), patch(
            'tools.verify_dev.get_engine'
        ) as get_engine:
            with self.assertRaisesRegex(RuntimeError, 'development environment'):
                verify()
            get_engine.assert_not_called()

    def test_only_expected_recorded_dt_shape_is_exempt(self):
        column = {'type': 'DATETIME', 'nullable': False, 'default': 'CURRENT_TIMESTAMP()'}
        self.assertTrue(expected_local_recorded_dt_extra('recipe_cooked_date', 'recorded_dt', column))
        self.assertFalse(expected_local_recorded_dt_extra('recipe_cooked_date', 'other', column))
        self.assertFalse(expected_local_recorded_dt_extra('recipe', 'recorded_dt', column))
        self.assertFalse(expected_local_recorded_dt_extra(
            'recipe_cooked_date', 'recorded_dt', {**column, 'nullable': True}))

    def test_recorded_dt_exception_rejects_changed_expressions_and_types(self):
        column = {'type': 'DATETIME', 'nullable': False, 'default': 'CURRENT_TIMESTAMP()'}
        for default in ['CURRENT_TIMESTAMP() + INTERVAL 1 DAY',
                        "'CURRENT_TIMESTAMP'", 'CURRENT_TIMESTAMP(6)', None]:
            with self.subTest(default=default):
                self.assertFalse(expected_local_recorded_dt_extra(
                    'recipe_cooked_date', 'recorded_dt', {**column, 'default': default}))
        for kind in ['DATETIME(6)', 'TIMESTAMP_INVALID', 'VARCHAR(100)']:
            with self.subTest(kind=kind):
                self.assertFalse(expected_local_recorded_dt_extra(
                    'recipe_cooked_date', 'recorded_dt', {**column, 'type': kind}))
        for default in ['current_timestamp', ' current_timestamp() ']:
            with self.subTest(default=default):
                self.assertTrue(expected_local_recorded_dt_extra(
                    'recipe_cooked_date', 'recorded_dt', {**column, 'default': default}))

    def test_vendor_download_uses_injected_target_and_pinned_names(self):
        class Response:
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False
            def read(self):
                return b'x' * 120

        with tempfile.TemporaryDirectory() as folder, patch(
            'tools.download_vendor.urlopen', return_value=Response()
        ) as urlopen:
            download(folder)
            self.assertEqual({p.name for p in Path(folder).iterdir()}, set(ASSETS))
            self.assertEqual(urlopen.call_count, len(ASSETS))
            self.assertTrue(all((Path(folder) / name).stat().st_size == 120 for name in ASSETS))


if __name__ == '__main__':
    unittest.main()
