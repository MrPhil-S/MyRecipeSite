#!/usr/bin/env bash
set -Eeuo pipefail

base=/home/pi/myrecipes-v2
incoming=$base/incoming
release=$base/current
flag_changed=0
legacy_hash=0088b9521c02513e6a71e490f9ed0260584b3aa683bc7304da4a524d8236d805
candidate_hash=1822fec13ed4c38e0fc5b1c4cc5df3e6a9ff9d95e2e37d1c36bb43a343cf2c8f

rollback_on_failure() {
    status=$?
    if (( status != 0 && flag_changed )); then
        echo 'Production write check failed; disabling v2 writes and restoring legacy routing' >&2
        bash "$incoming/rollback_nginx.sh" || true
        python3 "$incoming/set_prod_write_flag.py" 0 || true
        sudo systemctl restart recipe-fastapi-production.service || true
    fi
}
trap rollback_on_failure EXIT

systemctl is-active --quiet recipe-fastapi-production.service
printf '%s  %s\n' "$legacy_hash" \
    /etc/nginx/sites-available/myrecipesite_app | sha256sum -c
RECIPE_SMOKE_BASE=http://127.0.0.1:8012 python3 "$incoming/smoke_candidate.py" >/dev/null
flag_changed=1
python3 "$incoming/set_prod_write_flag.py" 1
sudo systemctl restart recipe-fastapi-production.service
for attempt in {1..20}; do
    if curl --fail --silent --max-time 5 -o /dev/null http://127.0.0.1:8012/health; then
        break
    fi
    sleep 1
done
RECIPE_SMOKE_BASE=http://127.0.0.1:8012 RECIPE_SMOKE_WRITES=1 \
    python3 "$incoming/smoke_candidate.py" >/dev/null
sudo install -m 644 "$incoming/myrecipesite_app.v2" /etc/nginx/sites-available/myrecipesite_app
sudo nginx -t
sudo systemctl reload nginx
public_ok=0
for attempt in {1..15}; do
    if RECIPE_SMOKE_BASE=http://192.168.1.13:5000 RECIPE_SMOKE_WRITES=1 \
            python3 "$incoming/smoke_candidate.py" > "$incoming/public-smoke.log" 2>&1; then
        public_ok=1
        break
    fi
    sleep 1
done
if (( ! public_ok )); then
    cat "$incoming/public-smoke.log" >&2
    exit 1
fi

set -a
source "$base/production.env"
set +a
cd "$release"
PYTHONPATH="$release" "$release/.venv/bin/python" "$incoming/smoke_writes.py" --execute
RECIPE_SMOKE_BASE=http://192.168.1.13:5000 RECIPE_SMOKE_WRITES=1 \
    python3 "$incoming/smoke_candidate.py" >/dev/null
systemctl is-active --quiet uwsgi.service
systemctl is-active --quiet recipe-fastapi-preview.service
printf '%s  %s\n' "$candidate_hash" /etc/nginx/sites-available/myrecipesite_app | sha256sum -c
flag_changed=0
echo PRODUCTION_WRITES_ENABLED_AND_TESTED
