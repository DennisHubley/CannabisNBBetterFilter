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

## Running it on Netlify (via GitHub)

With the site connected to this GitHub repo, every push triggers a Netlify
build that **runs the scraper on Netlify's servers** ([netlify-build.sh](netlify-build.sh))
and publishes the freshly scraped snapshot from `dist/`. Nothing data-related
gets committed to git.

**Refreshing from the deployed site**: the Refresh button calls a serverless
function ([netlify/functions/refresh.mjs](netlify/functions/refresh.mjs)) that
triggers a rebuild; the page then updates itself when the new data is live
(~8 minutes). One-time setup in the Netlify dashboard:

1. **Site configuration → Build & deploy → Build hooks → Add build hook**
   (any name, main branch). Copy the URL it gives you.
2. **Site configuration → Environment variables → Add a variable**:
   key `BUILD_HOOK_URL`, value = that URL.
3. Redeploy once (push anything, or **Deploys → Trigger deploy**) so the
   function picks up the variable.

Notes:
- Each refresh uses ~8 of your Netlify build minutes (free tier: 300/month,
  so roughly one refresh a day is comfortably free).
- A failed build (e.g. their site is down) keeps the previous version live.
- The deploy ships `robots.txt` + `noindex` so search engines stay away, but
  anyone with the URL can view it and press Refresh — keep the link to
  yourself, or add Netlify's password protection.

### Alternative: deploy from your Mac without GitHub

`./deploy.sh` scrapes locally and uploads a zip via Netlify's API (needs a
personal access token in `.netlify-token` — see the comments in the script).
Use one flow or the other, not both, so you don't end up with two sites.

## Notes

- Requires only Python 3 (macOS's is fine). No dependencies to install.
- Data is a snapshot from the last refresh, not live — refresh before a trip.
- Be nice: the scraper runs a few polite requests at a time with delays.
  It's for personal use.
- Stock numbers come from Cannabis NB's own store-inventory endpoint, the same
  one behind "Where to find" on their product pages.
