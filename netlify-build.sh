#!/bin/bash
# Netlify build: scrape fresh stock data, then assemble the static site.
set -euo pipefail
python3 --version

python3 scraper.py --category all

rm -rf dist
mkdir -p dist
cp -R web/. dist/
cp data/catalog.json dist/catalog.json
printf 'User-agent: *\nDisallow: /\n' > dist/robots.txt
printf '/*\n  X-Robots-Tag: noindex\n' > dist/_headers
echo "Build assembled: $(du -sh dist | cut -f1)"
