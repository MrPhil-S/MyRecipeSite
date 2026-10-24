"""Atomically toggle the Pi's production write flag without printing secrets."""

import os
import stat
import sys
from pathlib import Path


PATH = Path("/home/pi/myrecipes-v2/production.env")


def main():
    if sys.argv[1:] not in (["0"], ["1"]):
        raise SystemExit("Usage: set_prod_write_flag.py 0|1")
    mode = stat.S_IMODE(PATH.stat().st_mode)
    if mode != 0o600 or PATH.is_symlink():
        raise RuntimeError("Unexpected production environment permissions.")
    original = PATH.read_text(encoding="ascii")
    if original.count("RECIPE_PROD_WRITES=") != 1:
        raise RuntimeError("Expected exactly one production write flag.")
    lines = original.splitlines(keepends=True)
    matches = [line for line in lines if line.startswith("RECIPE_PROD_WRITES=")]
    if matches not in (["RECIPE_PROD_WRITES=0\n"], ["RECIPE_PROD_WRITES=1\n"]):
        raise RuntimeError("Unexpected production write flag value.")
    updated = original.replace(matches[0], "RECIPE_PROD_WRITES=" + sys.argv[1] + "\n")
    pending = PATH.with_suffix(".env.pending")
    if pending.exists() or pending.is_symlink():
        raise RuntimeError("A pending environment update already exists.")
    old_umask = os.umask(0o077)
    try:
        with pending.open("x", encoding="ascii") as output:
            output.write(updated)
            output.flush()
            os.fsync(output.fileno())
        os.chmod(pending, 0o600)
        os.replace(pending, PATH)
    except Exception:
        pending.unlink(missing_ok=True)
        raise
    finally:
        os.umask(old_umask)
    print("PRODUCTION_WRITES=" + sys.argv[1])


if __name__ == "__main__":
    main()
