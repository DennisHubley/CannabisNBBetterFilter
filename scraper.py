#!/usr/bin/env python3
"""
Cannabis NB catalog + per-store inventory scraper.

Builds data/catalog.json by walking the public cannabis-nb.com listing pages,
reading each product's size variants, and querying the same store-inventory
endpoint the site's own "Where to find" popup uses.

Stdlib only. Polite by default: a few workers, small delay, browser UA.

Usage:
  python3 scraper.py                      # refresh all categories (reuses cached variant codes)
  python3 scraper.py --category dried-flower
  python3 scraper.py --rebuild            # also re-fetch product pages (variant codes)
  python3 scraper.py --workers 4 --delay 0.15
"""

import argparse
import html
import json
import os
import random
import re
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE = "https://www.cannabis-nb.com"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0 Safari/537.36")

# Listing URLs exactly as the site's own navigation links them.
CATEGORIES = {
    "dried-flower":          "/01/all/menu/dried-flower/?q=%22menu+dried-flower%22",
    "beverages":             "/01/all/menu/beverages/?q=%22menu%2bbeverages%22",
    "concentrates":          "/01/all/menu/concentrates/?q=%22menu%2bconcentrates%22",
    "edibles":               "/01/all/menu/edibles/?q=%22menu%2bedibles%22",
    "oils--capsules":        "/01/all/menu/oils--capsules/?q=%22menu%2boils--capsules%22",
    "seeds":                 "/01/all/menu/seeds/?q=%22menu%2bseeds%22",
    "topicals":              "/01/all/menu/topicals/?q=%22menu%2btopicals%22",
    "vape-pens--cartridges": "/01/all/menu/vape-pens--cartridges/?q=%22menu%2bvape-pens--cartridges%22",
    "accessories":           "/01/all/accessories/",
}

CATEGORY_NAMES = {
    "dried-flower": "Dried Flower",
    "beverages": "Beverages",
    "concentrates": "Concentrates",
    "edibles": "Edibles",
    "oils--capsules": "Oils & Capsules",
    "seeds": "Seeds",
    "topicals": "Topicals",
    "vape-pens--cartridges": "Vapes",
    "accessories": "Accessories",
}

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
CATALOG_PATH = os.path.join(DATA_DIR, "catalog.json")
STATUS_PATH = os.path.join(DATA_DIR, "status.json")
LOCK_PATH = os.path.join(DATA_DIR, "scraper.lock")

TILE_RE = re.compile(r"onclick=\"window\.trackProductTileClick\('(.*?)'\)\"", re.S)
TOTAL_RE = re.compile(r"totalCount&quot;:(\d+)")
VARIANT_SELECT_RE = re.compile(
    r'<select[^>]*class="[^"]*VariationSwitch[^"]*"[^>]*>(.*?)</select>', re.S)
OPTION_RE = re.compile(r'<option[^>]*value="(\d+)"[^>]*>\s*([^<]*?)\s*</option>')
VARIATION_CODE_RE = re.compile(r'id="variationCode"[^>]*value="(\d+)"')
ONLINE_ROW_RE = re.compile(
    r'_innerStore">\s*Online\s*</div>\s*<div[^>]*>\s*(.*?)\s*</div>', re.S)
STORE_ROW_RE = re.compile(
    r'orgUnitNumber=(\d+)">([^<]+)</a>\s*</div>\s*<div[^>]*>\s*([^<]*?)\s*</div>', re.S)

_delay = 0.15
_status_lock = threading.Lock()
_status = {"phase": "idle", "done": 0, "total": 0, "detail": "", "error": None,
           "started": None, "finished": None}


def log(msg):
    print(msg, file=sys.stderr, flush=True)


def _write_status_locked():
    # unique tmp name per process; status writing must never kill a scrape
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        tmp = f"{STATUS_PATH}.{os.getpid()}.tmp"
        with open(tmp, "w") as f:
            json.dump(_status, f)
        os.replace(tmp, STATUS_PATH)
    except OSError as e:
        log(f"  ! status write failed: {e}")


def set_status(**kw):
    with _status_lock:
        _status.update(kw)
        _write_status_locked()


def bump_status(n=1):
    with _status_lock:
        _status["done"] += n
        _write_status_locked()


def fetch(url, ajax=False, tries=4):
    """GET a URL with retries and a polite delay."""
    headers = {"User-Agent": UA, "Accept-Language": "en-CA,en;q=0.9"}
    if ajax:
        headers["X-Requested-With"] = "XMLHttpRequest"
    last_err = None
    for attempt in range(tries):
        try:
            time.sleep(_delay + random.uniform(0, _delay))
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            last_err = e
            wait = 2 ** attempt
            log(f"  retry {attempt + 1}/{tries} in {wait}s for {url} ({e})")
            time.sleep(wait)
    raise RuntimeError(f"failed after {tries} tries: {url}: {last_err}")


def norm_size(s):
    """Normalize a size label: '28 G' -> '28g', '10pc' stays '10pc'."""
    s = (s or "").strip()
    m = re.fullmatch(r"([\d.]+)\s*([A-Za-z]+)", s)
    return (m.group(1) + m.group(2).lower()) if m else s


def parse_qty(text):
    """'Sold out' -> 0, '34' -> 34, other in-stock text -> -1 (available, qty unknown)."""
    t = html.unescape(text).strip()
    if not t or "sold" in t.lower():
        return 0
    digits = re.sub(r"[^\d]", "", t)
    if digits:
        return int(digits)
    return -1


def parse_tiles(page_html):
    """Extract product dicts from the GTM JSON embedded in each listing tile."""
    products = []
    for m in TILE_RE.finditer(page_html):
        raw = html.unescape(m.group(1))
        try:
            d = json.loads(raw)
        except json.JSONDecodeError as e:
            log(f"  ! could not parse a tile ({e}); skipping")
            continue
        url = d.get("Url") or ""
        if not url:
            continue
        pricing = d.get("Pricing") or {}
        per_unit = ((pricing.get("PricePerUnit") or {}).get("Amount"))
        if not per_unit:
            m2 = re.search(r"[\d.]+", pricing.get("PriceString") or "")
            per_unit = float(m2.group(0)) if m2 else None
        products.append({
            "name": d.get("DisplayName") or "",
            "url": url,
            "img": d.get("Image") or "",
            "type": d.get("AssociatedWith") or "",
            "thc": d.get("THC") or "",
            "cbd": d.get("CBD") or "",
            "unit": d.get("UnitOfMeasure") or "",
            "price": per_unit,
            "priceString": pricing.get("PriceString") or "",
            "promo": bool(pricing.get("IsOnPromotion")),
            "sizes": d.get("CnbDisplayAvailableSizes") or "",
            "occasions": d.get("CnbOccasions") or [],
            "rating": d.get("TotalRating"),
            "ratingCount": d.get("RatingCount"),
            "code": d.get("Code") or "",
        })
    return products


def crawl_category(slug, listing_url):
    """Walk every page of one category listing; return list of product dicts."""
    seen = {}
    sep = "&" if "?" in listing_url else "?"
    page = 1
    total = None
    while True:
        url = f"{BASE}{listing_url}{sep}FormModel.Page={page}"
        page_html = fetch(url)
        if total is None:
            m = TOTAL_RE.search(page_html)
            total = int(m.group(1)) if m else None
            log(f"[{slug}] {total if total is not None else '?'} products")
        tiles = parse_tiles(page_html)
        new = 0
        for p in tiles:
            if p["url"] not in seen:
                seen[p["url"]] = p
                new += 1
        log(f"[{slug}] page {page}: {len(tiles)} tiles, {new} new (have {len(seen)})")
        if not tiles or new == 0:
            break
        if total is not None and len(seen) >= total:
            break
        if page > 200:  # safety
            break
        page += 1
    for p in seen.values():
        p["category"] = slug
        path = urllib.parse.urlparse(p["url"]).path.strip("/").split("/")
        # /01/all/menu/<cat>/<subcat>/<slug>/ or /01/all/accessories/<subcat>/<slug>/
        try:
            i = path.index(slug)
            p["subcategory"] = path[i + 1] if len(path) - i > 2 else ""
        except ValueError:
            p["subcategory"] = ""
    return list(seen.values())


def fetch_variants(product):
    """Read a product page for its size-variant codes."""
    page_html = fetch(product["url"])
    variants = []
    for sel in VARIANT_SELECT_RE.finditer(page_html):
        for code, label in OPTION_RE.findall(sel.group(1)):
            label = html.unescape(label).strip()
            if code and all(v["code"] != code for v in variants):
                variants.append({"code": code, "size": label})
    if not variants:
        m = VARIATION_CODE_RE.search(page_html)
        if m:
            variants.append({"code": m.group(1), "size": ""})
    return variants


def fetch_inventory(product, variant, stores):
    """Query the store-inventory endpoint for one variant."""
    url = f"{product['url'].rstrip('/')}/FetchStoreInventory/?code={variant['code']}"
    body = fetch(url, ajax=True)
    m = ONLINE_ROW_RE.search(body)
    variant["online"] = parse_qty(m.group(1)) if m else 0
    qty_map = {}
    for org, name, qty_text in STORE_ROW_RE.findall(body):
        name = html.unescape(name).strip()
        stores[org] = name
        q = parse_qty(qty_text)
        if q:
            qty_map[org] = q
    variant["stores"] = qty_map


def load_existing():
    if os.path.exists(CATALOG_PATH):
        try:
            with open(CATALOG_PATH) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return None


def main():
    global _delay
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--category", default="all",
                    help="one category slug, or 'all' (default)")
    ap.add_argument("--rebuild", action="store_true",
                    help="re-fetch product pages even when variant codes are cached")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--delay", type=float, default=0.15,
                    help="base per-request delay in seconds")
    args = ap.parse_args()
    _delay = max(0.0, args.delay)

    if args.category != "all" and args.category not in CATEGORIES:
        ap.error(f"unknown category '{args.category}'. "
                 f"Choose from: {', '.join(CATEGORIES)} or 'all'")

    # refuse to run two scrapes at once (they'd hammer the site and race on files)
    os.makedirs(DATA_DIR, exist_ok=True)
    if os.path.exists(LOCK_PATH):
        try:
            pid = int(open(LOCK_PATH).read().strip() or 0)
            os.kill(pid, 0)  # raises if that pid is gone
            log(f"another scrape (pid {pid}) is already running; exiting")
            sys.exit(1)
        except (ValueError, ProcessLookupError, PermissionError):
            pass  # stale lock
    with open(LOCK_PATH, "w") as f:
        f.write(str(os.getpid()))

    slugs = list(CATEGORIES) if args.category == "all" else [args.category]
    started = time.strftime("%Y-%m-%dT%H:%M:%S")
    set_status(phase="listing", done=0, total=len(slugs), detail="", error=None,
               started=started, finished=None)

    existing = load_existing()
    cached_variants = {}
    kept_products = []
    if existing:
        for p in existing.get("products", []):
            if p.get("variants"):
                cached_variants[p["url"]] = [
                    {"code": v["code"], "size": v.get("size", "")}
                    for v in p["variants"]]
            if p.get("category") not in slugs:
                kept_products.append(p)  # categories not being refreshed survive

    stores = {s["id"]: s["name"] for s in (existing or {}).get("stores", [])}

    try:
        # Phase 1: listings
        products = []
        for i, slug in enumerate(slugs):
            set_status(phase="listing", detail=CATEGORY_NAMES.get(slug, slug),
                       done=i, total=len(slugs))
            products.extend(crawl_category(slug, CATEGORIES[slug]))
        log(f"catalog: {len(products)} products across {len(slugs)} categories")

        # Phase 2: product pages (variant codes), only where not cached
        need_pages = [p for p in products
                      if args.rebuild or p["url"] not in cached_variants]
        set_status(phase="products", done=0, total=len(need_pages), detail="")
        log(f"fetching {len(need_pages)} product pages "
            f"({len(products) - len(need_pages)} cached)")
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            futs = {ex.submit(fetch_variants, p): p for p in need_pages}
            for fut in as_completed(futs):
                p = futs[fut]
                try:
                    cached_variants[p["url"]] = fut.result()
                except Exception as e:
                    log(f"  ! variants failed for {p['url']}: {e}")
                    cached_variants.setdefault(p["url"], [])
                bump_status()

        for p in products:
            p["variants"] = [dict(v) for v in cached_variants.get(p["url"], [])]
            # Single-size products have no size dropdown on their page, so the
            # variant label comes back empty — recover it from the tile's
            # "AVAILABLE IN 28g" text so size filtering works.
            for v in p["variants"]:
                v["size"] = norm_size(v["size"])
            if len(p["variants"]) == 1 and not p["variants"][0]["size"]:
                m = re.match(r"AVAILABLE IN\s+(.+)$", p.get("sizes") or "", re.I)
                if m and "-" not in m.group(1):
                    p["variants"][0]["size"] = norm_size(m.group(1))

        # Phase 3: inventory per variant
        jobs = [(p, v) for p in products for v in p["variants"]]
        set_status(phase="inventory", done=0, total=len(jobs), detail="")
        log(f"fetching inventory for {len(jobs)} variants")
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            futs = {ex.submit(fetch_inventory, p, v, stores): (p, v)
                    for p, v in jobs}
            for fut in as_completed(futs):
                p, v = futs[fut]
                try:
                    fut.result()
                except Exception as e:
                    log(f"  ! inventory failed for {p['name']} {v.get('size')}: {e}")
                    v.setdefault("online", 0)
                    v.setdefault("stores", {})
                bump_status()

        all_products = kept_products + products
        catalog = {
            "generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "stores": sorted(
                ({"id": k, "name": v} for k, v in stores.items()),
                key=lambda s: s["name"]),
            "categories": [{"slug": s, "name": CATEGORY_NAMES.get(s, s)}
                           for s in CATEGORIES],
            "products": all_products,
        }
        os.makedirs(DATA_DIR, exist_ok=True)
        tmp = CATALOG_PATH + ".tmp"
        with open(tmp, "w") as f:
            json.dump(catalog, f, separators=(",", ":"))
        os.replace(tmp, CATALOG_PATH)
        set_status(phase="done", detail="", finished=time.strftime("%Y-%m-%dT%H:%M:%S"))
        log(f"wrote {CATALOG_PATH} ({len(all_products)} products, "
            f"{len(stores)} stores)")
    except Exception as e:
        set_status(phase="error", error=str(e),
                   finished=time.strftime("%Y-%m-%dT%H:%M:%S"))
        raise
    finally:
        try:
            os.remove(LOCK_PATH)
        except OSError:
            pass


if __name__ == "__main__":
    main()
