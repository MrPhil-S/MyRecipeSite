"""Release provenance and input checks in an isolated Git repository."""

import hashlib
import json
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

from deployment.build_release import ROOT, RUNTIME


class ReleaseBuilderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "deployment").mkdir()
        shutil.copy2(ROOT / "deployment/build_release.py", self.root / "deployment/build_release.py")
        for name in RUNTIME:
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / name, target)
        self.git("init", "-q")
        self.git("add", ".")
        self.git("-c", "user.name=Test", "-c", "user.email=test@example.invalid",
                 "commit", "-qm", "approved runtime fixture")

    def git(self, *args):
        return subprocess.run(["git", *args], cwd=self.root, check=True,
                              capture_output=True, text=True).stdout.strip()

    def build(self, mode, name):
        return subprocess.run([sys.executable, "deployment/build_release.py",
                               mode, "tmp/" + name], cwd=self.root,
                              capture_output=True, text=True)

    def test_committed_release_and_dirty_preview_have_distinct_provenance(self):
        released = self.build("release", "release.tar.gz")
        self.assertEqual(released.returncode, 0, released.stderr)
        with tarfile.open(self.root / "tmp/release.tar.gz") as archive:
            manifest = json.load(archive.extractfile("RELEASE_MANIFEST.json"))
            self.assertEqual(manifest["kind"], "committed-runtime-release")
            self.assertFalse(manifest["working_tree_dirty"])
            self.assertEqual({m["path"] for m in manifest["members"]}, set(RUNTIME))
            for member in manifest["members"]:
                data = archive.extractfile(member["path"]).read()
                self.assertEqual(hashlib.sha256(data).hexdigest(), member["sha256"])
                self.assertEqual(member["provenance"], "commit:" + manifest["source_commit"])

        icon = self.root / "recipe_app_v2/templates/shared/icons.html"
        icon.write_bytes(icon.read_bytes() + b"\n<!-- reviewed preview edit -->\n")
        self.assertNotEqual(self.build("release", "dirty.tar.gz").returncode, 0)
        preview = self.build("preview", "preview.tar.gz")
        self.assertEqual(preview.returncode, 0, preview.stderr)
        with tarfile.open(self.root / "tmp/preview.tar.gz") as archive:
            manifest = json.load(archive.extractfile("RELEASE_MANIFEST.json"))
            self.assertEqual(manifest["kind"], "non-deployable-working-tree-preview")
            self.assertTrue(manifest["working_tree_dirty"])
            self.assertIn(b"reviewed preview edit",
                          archive.extractfile("recipe_app_v2/templates/shared/icons.html").read())

    def test_missing_runtime_input_is_rejected(self):
        (self.root / "recipe_app_v2/templates/shared/icons.html").unlink()
        result = self.build("preview", "missing.tar.gz")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Required runtime input is missing", result.stderr)

    def test_migration_source_does_not_block_release_or_enter_runtime_archive(self):
        migration = self.root / "recipe_app_v2/migrations/versions/0002_cooked_recorded_dt.py"
        migration.parent.mkdir(parents=True)
        migration.write_text("revision = '0002'\n")
        runtime = self.root / "recipe_app_v2/main.py"
        runtime.write_bytes(runtime.read_bytes() + b"\n# recorded_dt custom_date\n")
        self.git("add", ".")
        self.git("-c", "user.name=Test", "-c", "user.email=test@example.invalid",
                 "commit", "-qm", "add migration source")
        result = self.build("release", "with-migration.tar.gz")
        self.assertEqual(result.returncode, 0, result.stderr)
        with tarfile.open(self.root / "tmp/with-migration.tar.gz") as archive:
            self.assertNotIn("recipe_app_v2/migrations/versions/0002_cooked_recorded_dt.py",
                             archive.getnames())
            self.assertIn(b"recorded_dt custom_date",
                          archive.extractfile("recipe_app_v2/main.py").read())

    def test_release_requires_required_input_in_the_commit(self):
        icon = self.root / "recipe_app_v2/templates/shared/icons.html"
        icon.unlink()
        self.git("add", "-u")
        self.git("-c", "user.name=Test", "-c", "user.email=test@example.invalid",
                 "commit", "-qm", "omit required icon")
        result = self.build("release", "missing-committed.tar.gz")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Required committed runtime input is missing", result.stderr)

    def test_unreviewed_asset_is_rejected(self):
        extra = self.root / "recipe_app_v2/static/unreviewed.js"
        extra.write_text("alert(1)")
        result = self.build("preview", "asset.tar.gz")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Unreviewed runtime tree input", result.stderr)


if __name__ == "__main__":
    unittest.main()
