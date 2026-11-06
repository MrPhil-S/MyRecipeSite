#!/usr/bin/env python3
"""Create dated, verified backups of the live MyRecipeSite asset folders."""

from __future__ import annotations

import datetime as dt
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import uuid


NAS_SHARE = "//192.168.1.14/pi_myRecipes_backup"
CREDENTIALS = Path("/etc/samba/credentials/pi-backup")
MOUNT_POINT = Path("/mnt/myrecipesite_backup")
# A separate snapshot series prevents an old-layout snapshot from satisfying
# today's backup and keeps legacy recovery snapshots outside this retention job.
BACKUP_ROOT = MOUNT_POINT / "MyRecipeSite" / "consolidated-media"
LOCK_FILE = Path("/run/lock/myrecipesite-assets-backup.lock")
MOUNT_OPTIONS = (
    f"credentials={CREDENTIALS},vers=2.0,iocharset=utf8,uid=0,gid=0,"
    "file_mode=0600,dir_mode=0700"
)
SOURCES = {
    "media": Path("/var/lib/myrecipesite-v2/uploads"),
}
DAILY_RE = re.compile(r"\d{4}-\d{2}-\d{2}\Z")
MONTHLY_RE = re.compile(r"\d{4}-\d{2}\Z")


def log(message: str) -> None:
    print(message, flush=True)


def run(args: list[str], *, capture: bool = False, timeout: int = 1800) -> str:
    log("RUN " + " ".join(str(arg) for arg in args))
    result = subprocess.run(
        args,
        check=True,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.STDOUT if capture else None,
        timeout=timeout,
    )
    return result.stdout if capture else ""


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def regular_files(root: Path) -> list[Path]:
    paths = sorted(root.rglob("*"), key=lambda path: path.relative_to(root).as_posix())
    files: list[Path] = []
    for path in paths:
        if path.is_symlink():
            raise RuntimeError(f"Unexpected symlink in asset tree: {path}")
        if path.is_file():
            files.append(path)
    return files


def verify_tree(source: Path, destination: Path) -> list[dict[str, object]]:
    source_files = regular_files(source)
    destination_files = regular_files(destination)
    source_names = [path.relative_to(source).as_posix() for path in source_files]
    destination_names = [
        path.relative_to(destination).as_posix() for path in destination_files
    ]
    if source_names != destination_names:
        raise RuntimeError(f"File list differs between {source} and {destination}")

    records: list[dict[str, object]] = []
    for source_file, destination_file in zip(source_files, destination_files):
        source_hash = sha256(source_file)
        destination_hash = sha256(destination_file)
        if source_hash != destination_hash:
            raise RuntimeError(f"Checksum mismatch for {source_file}")
        records.append(
            {
                "path": source_file.relative_to(source).as_posix(),
                "size": source_file.stat().st_size,
                "sha256": source_hash,
            }
        )
    return records


def verify_mount() -> None:
    result = run(
        ["findmnt", "-n", "-o", "FSTYPE,SOURCE", "--target", str(MOUNT_POINT)],
        capture=True,
    ).strip()
    fields = result.split(maxsplit=1)
    if len(fields) != 2 or fields[0] != "cifs":
        raise RuntimeError(f"Expected a CIFS mount at {MOUNT_POINT}; found {result!r}")
    mounted_share = fields[1].replace("\\", "/").casefold()
    if mounted_share != NAS_SHARE.casefold():
        raise RuntimeError(f"Unexpected share mounted at {MOUNT_POINT}: {fields[1]}")


def mount_share() -> None:
    if os.geteuid() != 0:
        raise RuntimeError("This backup must run as root")
    if not MOUNT_POINT.is_dir() or MOUNT_POINT.is_symlink():
        raise RuntimeError(f"Missing or unsafe mount point: {MOUNT_POINT}")
    credential_stat = CREDENTIALS.stat()
    if credential_stat.st_uid != 0 or credential_stat.st_mode & 0o077:
        raise RuntimeError("SMB credentials must be root-owned and mode 600 or stricter")
    for source in SOURCES.values():
        if not source.is_dir() or source.is_symlink():
            raise RuntimeError(f"Missing or unsafe source folder: {source}")

    if not os.path.ismount(MOUNT_POINT):
        if any(MOUNT_POINT.iterdir()):
            raise RuntimeError(f"Refusing to use non-empty, unmounted path {MOUNT_POINT}")
        run(
            [
                "mount",
                "-t",
                "cifs",
                NAS_SHARE,
                str(MOUNT_POINT),
                "-o",
                MOUNT_OPTIONS,
            ],
            timeout=60,
        )
    verify_mount()


def copy_tree(source: Path, destination: Path) -> list[dict[str, object]]:
    destination.mkdir(parents=True, exist_ok=False)
    run(
        [
            "rsync",
            "-rt",
            "--no-perms",
            "--no-owner",
            "--no-group",
            f"{source}/",
            f"{destination}/",
        ]
    )
    return verify_tree(source, destination)


def make_daily_snapshot(day: str) -> Path:
    daily_root = BACKUP_ROOT / "daily"
    daily_root.mkdir(parents=True, exist_ok=True)
    final = daily_root / day
    if final.exists():
        if not final.is_dir() or not (final / "MANIFEST.json").is_file():
            raise RuntimeError(f"Refusing to overwrite incomplete snapshot {final}")
        log(f"Daily snapshot already exists; keeping it: {final}")
        return final

    stage = daily_root / f".partial-{day}-{uuid.uuid4().hex}"
    stage.mkdir(mode=0o700)
    try:
        folder_records: dict[str, list[dict[str, object]]] = {}
        total_size = 0
        total_files = 0
        for name, source in SOURCES.items():
            target = stage / name
            records = copy_tree(source, target)
            folder_records[name] = records
            total_files += len(records)
            total_size += sum(int(record["size"]) for record in records)

        manifest = {
            "snapshot_date": day,
            "created_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "host": socket.gethostname(),
            "sources": {name: str(path) for name, path in SOURCES.items()},
            "file_count": total_files,
            "total_bytes": total_size,
            "folders": folder_records,
        }
        manifest_path = stage / "MANIFEST.json"
        with manifest_path.open("x", encoding="utf-8") as output:
            json.dump(manifest, output, indent=2, ensure_ascii=False)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.rename(stage, final)
        log(f"Created verified daily snapshot: {final} ({total_files} files)")
        return final
    except Exception:
        if stage.exists():
            shutil.rmtree(stage)
        raise


def make_monthly_snapshot(day: str, daily_snapshot: Path) -> None:
    month = day[:7]
    monthly_root = BACKUP_ROOT / "monthly"
    monthly_root.mkdir(parents=True, exist_ok=True)
    final = monthly_root / month
    if final.exists():
        if not final.is_dir() or not (final / "MANIFEST.json").is_file():
            raise RuntimeError(f"Refusing to overwrite incomplete snapshot {final}")
        log(f"Monthly snapshot already exists; keeping it: {final}")
        return

    stage = monthly_root / f".partial-{month}-{uuid.uuid4().hex}"
    stage.mkdir(mode=0o700)
    try:
        run(
            [
                "rsync",
                "-rt",
                "--no-perms",
                "--no-owner",
                "--no-group",
                f"{daily_snapshot}/",
                f"{stage}/",
            ]
        )
        verify_tree(daily_snapshot, stage)
        os.rename(stage, final)
        log(f"Created verified monthly snapshot: {final}")
    except Exception:
        if stage.exists():
            shutil.rmtree(stage)
        raise


def prune(root: Path, pattern: re.Pattern[str], keep: int) -> None:
    snapshots = [
        path
        for path in root.iterdir()
        if pattern.fullmatch(path.name)
        and path.is_dir()
        and not path.is_symlink()
        and (path / "MANIFEST.json").is_file()
    ]
    snapshots.sort(key=lambda path: path.name, reverse=True)
    for expired in snapshots[keep:]:
        log(f"Removing expired snapshot: {expired}")
        shutil.rmtree(expired)


def perform_backup() -> None:
    now = dt.datetime.now().astimezone()
    day = now.date().isoformat()
    log(f"Starting backup for {day}")
    try:
        mount_share()
        BACKUP_ROOT.mkdir(parents=True, exist_ok=True)
        daily_snapshot = make_daily_snapshot(day)
        make_monthly_snapshot(day, daily_snapshot)
        prune(BACKUP_ROOT / "daily", DAILY_RE, 30)
        prune(BACKUP_ROOT / "monthly", MONTHLY_RE, 12)
        log("BACKUP_COMPLETE")
    finally:
        if os.path.ismount(MOUNT_POINT):
            run(["umount", str(MOUNT_POINT)], timeout=60)


def main() -> int:
    try:
        LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
        with LOCK_FILE.open("w", encoding="ascii") as lock:
            try:
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                log("Another backup run holds the lock; exiting")
                return 0
            perform_backup()
        return 0
    except Exception as error:
        log(f"BACKUP_FAILED: {error}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
