#!/usr/bin/env bash
set -Eeuo pipefail

site=/etc/nginx/sites-available/myrecipesite_app
incoming=/home/pi/myrecipes-v2/incoming
backup=/home/pi/myrecipesite-deploy-backups/pre-v2-20261024T073741Z
legacy_hash=0088b9521c02513e6a71e490f9ed0260584b3aa683bc7304da4a524d8236d805
candidate_hash=1822fec13ed4c38e0fc5b1c4cc5df3e6a9ff9d95e2e37d1c36bb43a343cf2c8f

[[ -f "$backup/SHA256SUMS" && ! -e "$backup/INCOMPLETE" ]]
printf '%s  %s\n' "$legacy_hash" "$site" "$legacy_hash" "$incoming/myrecipesite_app.legacy" \
    "$candidate_hash" "$incoming/myrecipesite_app.v2" | sha256sum -c
systemctl is-active --quiet uwsgi.service
systemctl is-active --quiet recipe-fastapi-preview.service
systemctl is-active --quiet recipe-fastapi-production.service
RECIPE_SMOKE_BASE=http://127.0.0.1:8012 python3 "$incoming/smoke_candidate.py" >/dev/null

# Leave the original uWSGI app running for immediate routing rollback.
sudo systemctl enable recipe-fastapi-production.service
rollback_required=1
rollback_on_failure() {
    status=$?
    if (( status != 0 && rollback_required )); then
        echo 'Cutover check failed; restoring legacy Nginx routing' >&2
        if ! bash "$incoming/rollback_nginx.sh"; then
            echo 'Automatic routing rollback failed; intervene on Pi immediately' >&2
        fi
    fi
}
trap rollback_on_failure EXIT
sudo install -m 644 "$incoming/myrecipesite_app.v2" "$site"
sudo nginx -t
sudo systemctl reload nginx
RECIPE_SMOKE_BASE=http://192.168.1.13:5000 python3 "$incoming/smoke_candidate.py"
systemctl is-active --quiet uwsgi.service
systemctl is-active --quiet recipe-fastapi-preview.service
printf '%s  %s\n' "$candidate_hash" "$site" | sha256sum -c
rollback_required=0
echo READ_ONLY_CUTOVER_OK
