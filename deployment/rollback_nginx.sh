#!/usr/bin/env bash
set -Eeuo pipefail

site=/etc/nginx/sites-available/myrecipesite_app
legacy=/home/pi/myrecipes-v2/incoming/myrecipesite_app.legacy
expected=0088b9521c02513e6a71e490f9ed0260584b3aa683bc7304da4a524d8236d805
printf '%s  %s\n' "$expected" "$legacy" | sha256sum -c
sudo install -m 644 "$legacy" "$site"
sudo nginx -t
sudo systemctl reload nginx
for attempt in {1..15}; do
    if curl --fail --silent --max-time 5 -o /dev/null http://192.168.1.13:5000/; then
        break
    fi
    sleep 1
done
curl --fail --silent --show-error --max-time 20 -o /dev/null http://192.168.1.13:5000/
systemctl is-active uwsgi.service
echo LEGACY_ROUTING_RESTORED
