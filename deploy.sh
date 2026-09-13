#!/bin/bash
# Scrape fresh stock data and publish the site to Netlify.
#
# One-time setup:
#   1. Create a free Netlify account at https://app.netlify.com
#   2. Make a personal access token: User settings -> Applications ->
#      Personal access tokens -> New access token
#   3. Save it (nothing else on the line) into a file called .netlify-token
#      in this folder:  pbpaste > .netlify-token   (after copying the token)
#
# Then every deploy is just:
#   ./deploy.sh                # scrape (~6 min) + publish
#   ./deploy.sh --skip-scrape  # publish current data without re-scraping

set -euo pipefail
cd "$(dirname "$0")"

API="https://api.netlify.com/api/v1"
TOKEN_FILE=".netlify-token"
SITE_FILE=".netlify-site"

if [ ! -f "$TOKEN_FILE" ]; then
  echo "Missing $TOKEN_FILE — see the setup comment at the top of deploy.sh" >&2
  exit 1
fi
TOKEN=$(tr -d '[:space:]' < "$TOKEN_FILE")

# 1. Fresh data
if [ "${1:-}" != "--skip-scrape" ]; then
  python3 scraper.py --category all
fi
if [ ! -f data/catalog.json ]; then
  echo "data/catalog.json not found — run a scrape first" >&2
  exit 1
fi

# 2. Assemble the static site
rm -rf dist
mkdir -p dist
cp -R web/. dist/
cp data/catalog.json dist/catalog.json
printf 'User-agent: *\nDisallow: /\n' > dist/robots.txt
printf '/*\n  X-Robots-Tag: noindex\n' > dist/_headers

# 3. Create the Netlify site on first run, remember it after that
if [ ! -f "$SITE_FILE" ]; then
  echo "Creating a new Netlify site..."
  resp=$(curl -sS -X POST "$API/sites" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" -d '{}')
  site_id=$(printf '%s' "$resp" | python3 -c "import json,sys;print(json.load(sys.stdin)['id'])")
  printf '%s' "$site_id" > "$SITE_FILE"
fi
SITE_ID=$(cat "$SITE_FILE")

# 4. Zip and deploy
(cd dist && zip -qr ../site.zip .)
echo "Uploading..."
deploy=$(curl -sS -X POST "$API/sites/$SITE_ID/deploys" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/zip" \
  --data-binary @site.zip)
rm -f site.zip
python3 - "$deploy" <<'EOF'
import json, sys
d = json.loads(sys.argv[1])
url = d.get("ssl_url") or d.get("url") or "?"
state = d.get("state", "?")
print(f"Deploy state: {state}")
print(f"Site is live at: {url}")
EOF
