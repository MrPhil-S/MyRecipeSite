#!/usr/bin/env bash
# Capture the Pi's existing applications, media, routing, and both recipe databases.
# Run as pi. The database passwords are read from the Pi's existing config.ini.
set -Eeuo pipefail
umask 077

backup_base=/home/pi/myrecipesite-deploy-backups
backup_dir="$backup_base/snapshot-$(date -u +%Y%m%dT%H%M%SZ)"
config_file=/home/pi/myrecipes-v2/database-config.ini
prod_options=
dev_options=

cleanup() {
    if [[ -n "$prod_options" ]]; then rm -f -- "$prod_options"; fi
    if [[ -n "$dev_options" ]]; then rm -f -- "$dev_options"; fi
}
trap cleanup EXIT

for program in mariadb mariadb-dump gzip tar sha256sum python3; do
    command -v "$program" >/dev/null || { echo "Missing backup utility: $program" >&2; exit 1; }
done
[[ -f "$config_file" ]] || { echo "Missing Pi database config" >&2; exit 1; }
[[ ! -L "$backup_base" ]] || { echo "Backup base must be a real directory" >&2; exit 1; }
mkdir -p -m 700 -- "$backup_base"
[[ ! -e "$backup_dir" ]] || { echo "Backup destination already exists" >&2; exit 1; }
mkdir -m 700 -- "$backup_dir"
touch "$backup_dir/INCOMPLETE"

# Keep the temporary client files in memory, outside the archive and process arguments.
prod_options=$(mktemp /dev/shm/myrecipes-prod.XXXXXX)
dev_options=$(mktemp /dev/shm/myrecipes-dev.XXXXXX)
python3 - "$config_file" "$prod_options" "$dev_options" <<'PY'
import configparser
import os
import sys
from urllib.parse import unquote, urlsplit

config = configparser.ConfigParser(interpolation=None)
if not config.read(sys.argv[1]):
    raise SystemExit("Cannot read the Pi database config")

for section, database, destination in (
    ("prod", "MyRecipes", sys.argv[2]),
    ("dev", "MyRecipes_DEV", sys.argv[3]),
):
    url = urlsplit(config[section]["db_uri"])
    if (url.scheme != "mysql+pymysql" or url.hostname != "192.168.1.14"
            or url.port != 3307 or url.path != "/" + database or url.query
            or not url.username or url.password is None):
        raise SystemExit("Unexpected database target; backup stopped")

    values = {
        "host": url.hostname,
        "port": str(url.port),
        "user": unquote(url.username),
        "password": unquote(url.password),
        "protocol": "tcp",
    }
    with open(destination, "w", encoding="utf-8") as output:
        output.write("[client]\n")
        for key, value in values.items():
            if "\n" in value or "\r" in value:
                raise SystemExit("Invalid database credential")
            escaped = value.replace("\\", "\\\\").replace('"', '\\"')
            output.write(f'{key}="{escaped}"\n')
    os.chmod(destination, 0o600)
print("Database targets validated: MyRecipes and MyRecipes_DEV")
PY

for section in prod dev; do
    if [[ "$section" == prod ]]; then
        database=MyRecipes
        options=$prod_options
    else
        database=MyRecipes_DEV
        options=$dev_options
    fi

    engines=$(mariadb --defaults-extra-file="$options" --database="$database" \
        --batch --skip-column-names --execute="SELECT DISTINCT ENGINE FROM information_schema.TABLES WHERE TABLE_SCHEMA = DATABASE() AND TABLE_TYPE = 'BASE TABLE'")
    [[ "$engines" == InnoDB ]] || { echo "Unexpected table engine in $database: $engines" >&2; exit 1; }
    table_count=$(mariadb --defaults-extra-file="$options" --database="$database" \
        --batch --skip-column-names --execute="SELECT COUNT(*) FROM information_schema.TABLES WHERE TABLE_SCHEMA = DATABASE() AND TABLE_TYPE = 'BASE TABLE'")
    [[ "$table_count" =~ ^[0-9]+$ && "$table_count" -gt 0 ]] || { echo "No tables found in $database" >&2; exit 1; }

    echo "Dumping $database ($table_count InnoDB tables)"
    mariadb-dump --defaults-extra-file="$options" --default-character-set=utf8mb4 \
        --single-transaction --quick --hex-blob --routines --triggers --events \
        "$database" | gzip -1 > "$backup_dir/$database.sql.gz"
    gzip -t "$backup_dir/$database.sql.gz"
    dumped_tables=$(gzip -cd "$backup_dir/$database.sql.gz" | grep -c '^CREATE TABLE ' || true)
    [[ "$dumped_tables" -eq "$table_count" ]] || {
        echo "Table count mismatch in $database dump ($dumped_tables vs $table_count)" >&2
        exit 1
    }
    printf '%s tables=%s dump_tables=%s\n' "$database" "$table_count" "$dumped_tables" >> "$backup_dir/MANIFEST.txt"
done

required_paths=(
    home/pi/fastapi-preview-data
    home/pi/fastapi-preview-releases
    home/pi/myrecipes-v2
    var/lib/myrecipesite-v2
    etc/systemd/system/recipe-fastapi-production.service
    etc/systemd/system/recipe-fastapi-preview.service
    etc/nginx/sites-available/myrecipesite_app
)
optional_paths=(
    home/pi/fastapi-preview
    home/pi/git/MyRecipeSite
    var/www/MyRecipeSite
    var/lib/myrecipesite
    etc/nginx/sites-available/testapp_proxy
    etc/nginx/sites-enabled/myrecipesite_app
    etc/nginx/sites-enabled/testapp_proxy
    etc/uwsgi/apps-available/myrecipesite.ini
    etc/uwsgi/apps-enabled/myrecipesite.ini
    lib/systemd/system/myrecipessite.service
    etc/systemd/system/recipe-fastapi-production.service.d
    etc/systemd/system/recipe-fastapi-preview.service.d
    etc/systemd/system/myrecipesite-assets-backup.service
    etc/systemd/system/myrecipesite-assets-backup.timer
    usr/local/sbin/myrecipesite-assets-backup.py
    etc/samba/credentials/pi-backup
)
paths=("${required_paths[@]}")
for path in "${required_paths[@]}"; do
    [[ -e "/$path" || -L "/$path" ]] || { echo "Snapshot source missing: /$path" >&2; exit 1; }
done
for path in "${optional_paths[@]}"; do
    if [[ -e "/$path" || -L "/$path" ]]; then
        paths+=("$path")
    else
        printf 'optional_source_absent=/%s\n' "$path" >> "$backup_dir/MANIFEST.txt"
    fi
done
printf 'archive_source=/%s\n' "${paths[@]}" >> "$backup_dir/MANIFEST.txt"

echo "Archiving application trees, live media, and service configuration"
tar --acls --xattrs --numeric-owner \
    --exclude=var/www/MyRecipeSite/MyRecipeSite.sock \
    --exclude='*/__pycache__/*' \
    --exclude='*/myrecipes/logs/*' \
    -C / -czpf "$backup_dir/pi-files.tar.gz" "${paths[@]}"
tar -tzf "$backup_dir/pi-files.tar.gz" >/dev/null

(cd "$backup_dir" && sha256sum MyRecipes.sql.gz MyRecipes_DEV.sql.gz pi-files.tar.gz > SHA256SUMS)
(cd "$backup_dir" && sha256sum -c SHA256SUMS)
printf 'created_utc=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$backup_dir/MANIFEST.txt"
printf 'host=%s\n' "$(hostname)" >> "$backup_dir/MANIFEST.txt"
printf 'source=Pi live files, MyRecipes, MyRecipes_DEV\n' >> "$backup_dir/MANIFEST.txt"
chmod 600 "$backup_dir"/*
rm "$backup_dir/INCOMPLETE"
echo "BACKUP_COMPLETE=$backup_dir"
