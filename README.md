# CNB Stock Finder

A personal, local website that fixes the one thing cannabis-nb.com won't do:
**pick a store, see only what's actually in stock there.**

It scrapes the public Cannabis NB catalog and the same per-store inventory
endpoint their "Where to find" popup uses, saves a snapshot to
`data/catalog.json`, and serves a filterable product browser at
`http://127.0.0.1:8765/`.

## Run it

```bash
./run.sh
```

That starts the local server and opens your browser. On first run there's no
data yet — click **Refresh stock** in the header (leave it on "All categories")
and wait a few minutes while it pulls everything. After that, refreshes are
faster because product pages are cached; only stock quantities are re-checked.

You can also scrape from the command line:

```bash
python3 scraper.py                        # everything
python3 scraper.py --category dried-flower
python3 scraper.py --rebuild              # re-learn product sizes too
```

## What you get

- **Store picker** — any of the 30+ CNB stores, online delivery, or all combined
- **In stock only** (on by default) — sold-out products simply disappear
- Exact quantities per size at the chosen store (e.g. "3.5g — 34 in stock")
- Category tabs, type (Indica/Sativa/Hybrid), size, THC/price/rating sorting, search
- Every card links to the real product page for ordering

## Putting it on Netlify

The site also runs as a pure static page: the frontend detects there's no local
API and reads a bundled `catalog.json` snapshot instead (the Refresh button is
hidden — you refresh by redeploying).

One-time setup:

1. Create a free account at https://app.netlify.com
2. Make a token: **User settings → Applications → Personal access tokens →
   New access token**
3. Paste the token into a file named `.netlify-token` in this folder
   (it's gitignored; never commit it)

Then every deploy is one command:

```bash
./deploy.sh
```

That scrapes fresh data (~6 min) and publishes. Use `./deploy.sh --skip-scrape`
to push the current snapshot without re-scraping. The first run creates a site
with a random `*.netlify.app` name — rename it in the Netlify dashboard if you
like. The deploy includes `robots.txt` + `X-Robots-Tag: noindex` so search
engines stay away, but anyone with the URL can view it — keep the link to
yourself (or add Netlify's password protection).

## Notes

- Requires only Python 3 (macOS's is fine). No dependencies to install.
- Data is a snapshot from the last refresh, not live — refresh before a trip.
- Be nice: the scraper runs a few polite requests at a time with delays.
  It's for personal use.
- Stock numbers come from Cannabis NB's own store-inventory endpoint, the same
  one behind "Where to find" on their product pages.
