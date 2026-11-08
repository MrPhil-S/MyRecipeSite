#!/usr/bin/env python3
"""Copy one verified Pi release snapshot to the NAS without replacing older copies."""

import hashlib
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import uuid

SOURCE_ROOT = Path("/home/pi/myrecipesite-deploy-backups")
MOUNT = Path("/mnt/myrecipesite_release_backup")
SHARE = "//192.168.1.14/pi_myRecipes_backup"
DEST_ROOT = MOUNT / "MyRecipeSite" / "release-backups"
FILES = frozenset({"MyRecipes.sql.gz", "MyRecipes_DEV.sql.gz", "pi-files.tar.gz", "SHA256SUMS", "MANIFEST.txt"})
HASHED = frozenset({"MyRecipes.sql.gz", "MyRecipes_DEV.sql.gz", "pi-files.tar.gz"})
SNAPSHOT_RE = re.compile(r"snapshot-\d{8}T\d{6}Z\Z")
RELEASE_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z")


def run(*args):
    subprocess.run(args, check=True)


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def file_hashes(folder):
    if folder.is_symlink() or not folder.is_dir():
        raise RuntimeError(f"Missing or unsafe snapshot folder: {folder}")
    entries = {entry.name for entry in folder.iterdir()}
    if entries != FILES:
        raise RuntimeError(f"Unexpected snapshot files in {folder}: {sorted(entries)}")
    for name in FILES:
        path = folder / name
        if path.is_symlink() or not path.is_file() or path.stat().st_size == 0:
            raise RuntimeError(f"Missing or unsafe snapshot file: {path}")
    actual = {name: sha256(folder / name) for name in FILES}
    checksums = {}
    for line in (folder / "SHA256SUMS").read_text(encoding="ascii").splitlines():
        match = re.fullmatch(r"([0-9a-fA-F]{64})  (MyRecipes\.sql\.gz|MyRecipes_DEV\.sql\.gz|pi-files\.tar\.gz)", line)
        if not match or match.group(2) in checksums:
            raise RuntimeError("Invalid snapshot checksum list")
        checksums[match.group(2)] = match.group(1).lower()
    if set(checksums) != HASHED or any(actual[name] != checksums[name] for name in HASHED):
        raise RuntimeError("Pi snapshot checksums did not verify")
    return actual


def main(snapshot_arg, release):
    if os.geteuid() != 0:
        raise RuntimeError("Run as root")
    if not RELEASE_RE.fullmatch(release):
        raise RuntimeError("Invalid release name")
    snapshot = Path(snapshot_arg)
    if snapshot.parent != SOURCE_ROOT or not SNAPSHOT_RE.fullmatch(snapshot.name):
        raise RuntimeError("Snapshot must be an exact dated folder under the Pi backup root")
    source_hashes = file_hashes(snapshot)
    if MOUNT.is_symlink() or (MOUNT.exists() and (not MOUNT.is_dir() or any(MOUNT.iterdir()))):
        raise RuntimeError("NAS mount point is unsafe or already in use")
    MOUNT.mkdir(mode=0o700, exist_ok=True)
    if MOUNT.is_mount():
        raise RuntimeError("NAS mount point is already mounted")
    run(
        "mount", "-t", "cifs", SHARE, str(MOUNT), "-o",
        "credentials=/etc/samba/credentials/pi-backup,vers=2.0,iocharset=utf8,uid=0,gid=0,file_mode=0600,dir_mode=0700",
    )
    stage = None
    try:
        if not MOUNT.is_mount() or not (MOUNT / "MyRecipeSite").is_dir():
            raise RuntimeError("Expected MyRecipeSite folder on the mounted NAS share")
        if DEST_ROOT.is_symlink():
            raise RuntimeError("Release backup root cannot be a symlink")
        DEST_ROOT.mkdir(mode=0o700, exist_ok=True)
        release_dir = DEST_ROOT / release
        if release_dir.is_symlink():
            raise RuntimeError("Release folder cannot be a symlink")
        release_dir.mkdir(mode=0o700, exist_ok=True)
        final = release_dir / snapshot.name
        if final.exists() or final.is_symlink():
            raise RuntimeError(f"Refusing to overwrite existing NAS snapshot: {final}")
        stage = release_dir / f".partial-{snapshot.name}-{uuid.uuid4().hex}"
        stage.mkdir(mode=0o700)
        run("rsync", "-rt", "--no-perms", "--no-owner", "--no-group", f"{snapshot}/", f"{stage}/")
        if file_hashes(stage) != source_hashes:
            raise RuntimeError("NAS copy differs from the Pi snapshot")
        os.rename(stage, final)
        stage = None
        if file_hashes(final) != source_hashes:
            raise RuntimeError("NAS snapshot changed after final rename")
        print(f"NAS_BACKUP_READY={SHARE}/MyRecipeSite/release-backups/{release}/{snapshot.name}", flush=True)
    finally:
        try:
            if stage is not None and stage.exists() and stage.parent == DEST_ROOT / release and stage.name.startswith(".partial-"):
                shutil.rmtree(stage)
        finally:
            run("umount", str(MOUNT))


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("Usage: copy_release_snapshot_to_nas.py SNAPSHOT_PATH RELEASE_NAME")
    main(sys.argv[1], sys.argv[2])
