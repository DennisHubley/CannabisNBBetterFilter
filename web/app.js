/* CNB Stock Finder frontend */
(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const state = {
    data: { stores: [], categories: [], products: [], generated: null },
    category: "all",
  };
  let statusTimer = null;

  // ---------- helpers ----------

  function thcUpper(s) {
    const m = String(s || "").match(/([\d.]+)\s*%?\s*$/);
    return m ? parseFloat(m[1]) : -1;
  }

  function variantQty(v, storeSel) {
    // returns quantity at the selected scope: number, -1 = in stock qty unknown, 0 = none
    if (storeSel === "all") {
      let total = 0, unknown = false;
      if (v.online === -1) unknown = true; else total += v.online || 0;
      for (const k in v.stores || {}) {
        const q = v.stores[k];
        if (q === -1) unknown = true; else total += q;
      }
      return total > 0 ? total : (unknown ? -1 : 0);
    }
    if (storeSel === "online") return v.online || 0;
    const q = (v.stores || {})[storeSel];
    return q === undefined ? 0 : q;
  }

  function productMatches(p, f) {
    if (f.category !== "all" && p.category !== f.category) return false;
    if (f.type && p.type !== f.type) return false;
    if (f.search && !p.name.toLowerCase().includes(f.search)) return false;
    const variants = (p.variants || []).filter(
      (v) => !f.size || v.size === f.size
    );
    if (!variants.length) return false;
    if (f.inStock) {
      return variants.some((v) => variantQty(v, f.store) !== 0);
    }
    return true;
  }

  function productStockTotal(p, f) {
    let t = 0;
    for (const v of p.variants || []) {
      if (f.size && v.size !== f.size) continue;
      const q = variantQty(v, f.store);
      if (q > 0) t += q;
      else if (q === -1) t += 1;
    }
    return t;
  }

  function fmtQty(q) {
    if (q === 0) return "sold out";
    if (q === -1) return "in stock";
    return q + " in stock";
  }

  function esc(s) {
    return String(s).replace(/[&<>"']/g, (c) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    }[c]));
  }

  // ---------- rendering ----------

  function currentFilters() {
    return {
      store: $("store").value || "all",
      inStock: $("inStock").checked,
      type: $("type").value,
      size: $("size").value,
      search: $("search").value.trim().toLowerCase(),
      sort: $("sort").value,
      category: state.category,
    };
  }

  function render() {
    const f = currentFilters();
    let items = state.data.products.filter((p) => productMatches(p, f));

    const sorters = {
      name: (a, b) => a.name.localeCompare(b.name),
      priceAsc: (a, b) => (a.price ?? 1e9) - (b.price ?? 1e9),
      priceDesc: (a, b) => (b.price ?? -1) - (a.price ?? -1),
      thc: (a, b) => thcUpper(b.thc) - thcUpper(a.thc),
      rating: (a, b) => (b.rating ?? -1) - (a.rating ?? -1),
      stock: (a, b) => productStockTotal(b, f) - productStockTotal(a, f),
    };
    items.sort(sorters[f.sort] || sorters.name);

    const storeName =
      f.store === "all" ? "any store or online" :
      f.store === "online" ? "online" :
      (state.data.stores.find((s) => s.id === f.store) || {}).name || "store";
    $("summary").textContent =
      `${items.length} of ${state.data.products.length} products` +
      (f.inStock ? ` in stock at ${storeName}` : "");

    const grid = $("grid");
    const frag = document.createDocumentFragment();
    for (const p of items) {
      frag.appendChild(card(p, f));
    }
    grid.replaceChildren(frag);

    const empty = $("empty");
    if (!state.data.products.length) {
      empty.textContent = state.staticMode
        ? "No catalog bundled with this deploy — run ./deploy.sh again."
        : "No data yet — hit “Refresh stock” to pull the catalog (first run takes a few minutes).";
      empty.classList.remove("hidden");
    } else if (!items.length) {
      empty.textContent = "Nothing matches those filters.";
      empty.classList.remove("hidden");
    } else {
      empty.classList.add("hidden");
    }
  }

  function card(p, f) {
    const el = document.createElement("div");
    el.className = "card";

    const variants = (p.variants || [])
      .filter((v) => !f.size || v.size === f.size)
      .map((v) => ({ v, q: variantQty(v, f.store) }));
    const shown = f.inStock ? variants.filter((x) => x.q !== 0) : variants;

    const rows = shown.map(({ v, q }) => `
      <div class="stock-row">
        <span>${esc(v.size || (p.sizes || "").replace(/^AVAILABLE IN /i, "") || "One size")}</span>
        <span class="stock-qty ${q === 0 ? "out" : ""}">${fmtQty(q)}</span>
      </div>`).join("");

    const rating = p.rating
      ? `<span class="rating">★ ${p.rating.toFixed(1)} (${p.ratingCount})</span>`
      : "";
    const pot = (p.thc || p.cbd)
      ? `<span class="pot">${p.thc ? "THC " + esc(p.thc) : ""}${p.thc && p.cbd ? " · " : ""}${p.cbd ? "CBD " + esc(p.cbd) : ""}</span>`
      : "";
    const price = p.priceString
      ? `<span class="price">${esc(p.priceString)}<span class="unit">${p.unit ? "/" + esc(p.unit) : ""}</span></span>`
      : "";

    el.innerHTML = `
      <div class="card-img">
        ${p.promo ? '<span class="promo">Promo</span>' : ""}
        ${p.img ? `<img loading="lazy" src="${esc(p.img)}/LargeThumbnail" alt="">` : ""}
      </div>
      <div class="card-body">
        <div class="card-name"><a href="${esc(p.url)}" target="_blank" rel="noopener">${esc(p.name)}</a></div>
        <div class="meta">
          ${p.type ? `<span class="badge">${esc(p.type)}</span>` : ""}
          ${pot}
        </div>
        <div class="meta">${price}${rating}</div>
        <div class="stock-list">${rows}</div>
      </div>`;
    return el;
  }

  function buildControls() {
    const d = state.data;

    const storeSel = $("store");
    const prev = storeSel.value;
    storeSel.innerHTML =
      '<option value="all">All stores + online</option>' +
      '<option value="online">Online (delivery)</option>' +
      d.stores.map((s) => `<option value="${esc(s.id)}">${esc(s.name)}</option>`).join("");
    if ([...storeSel.options].some((o) => o.value === prev)) storeSel.value = prev;

    const cats = d.categories.filter((c) =>
      d.products.some((p) => p.category === c.slug));
    const nav = $("categories");
    nav.innerHTML =
      `<button class="cat ${state.category === "all" ? "active" : ""}" data-cat="all">All</button>` +
      cats.map((c) =>
        `<button class="cat ${state.category === c.slug ? "active" : ""}" data-cat="${esc(c.slug)}">${esc(c.name)}</button>`
      ).join("");

    const scope = $("refreshScope");
    const prevScope = scope.value;
    scope.innerHTML = '<option value="all">All categories</option>' +
      Object.values(d.categories).map((c) =>
        `<option value="${esc(c.slug)}">${esc(c.name)} only</option>`).join("");
    if ([...scope.options].some((o) => o.value === prevScope)) scope.value = prevScope;

    rebuildDependentSelects();
  }

  function rebuildDependentSelects() {
    // size + type options follow the active category
    const pool = state.data.products.filter(
      (p) => state.category === "all" || p.category === state.category);

    const sizes = [...new Set(pool.flatMap((p) =>
      (p.variants || []).map((v) => v.size).filter(Boolean)))];
    sizes.sort((a, b) => (parseFloat(a) || 0) - (parseFloat(b) || 0) || a.localeCompare(b));
    const sizeSel = $("size");
    const prevSize = sizeSel.value;
    sizeSel.innerHTML = '<option value="">All</option>' +
      sizes.map((s) => `<option>${esc(s)}</option>`).join("");
    if (sizes.includes(prevSize)) sizeSel.value = prevSize;

    const types = [...new Set(pool.map((p) => p.type).filter(Boolean))].sort();
    const typeSel = $("type");
    const prevType = typeSel.value;
    typeSel.innerHTML = '<option value="">All</option>' +
      types.map((t) => `<option>${esc(t)}</option>`).join("");
    if (types.includes(prevType)) typeSel.value = prevType;
  }

  // ---------- data + refresh ----------

  function normSize(s) {
    s = (s || "").trim();
    const m = s.match(/^([\d.]+)\s*([A-Za-z]+)$/);
    return m ? m[1] + m[2].toLowerCase() : s; // "28 G" -> "28g"
  }

  function normalizeData(d) {
    // Most products come in exactly one size, so their page has no size
    // dropdown and the scraper stores an empty label — recover the size from
    // the tile's "AVAILABLE IN 28g" text so the size filter can see them.
    for (const p of d.products || []) {
      for (const v of p.variants || []) {
        v.size = normSize(v.size);
        if (!v.size && (p.variants.length === 1)) {
          const m = (p.sizes || "").match(/^AVAILABLE IN\s+(.+)$/i);
          if (m && !m[1].includes("-")) v.size = normSize(m[1]);
        }
      }
    }
  }

  async function loadData() {
    // Server mode (local python server) exposes /api/data; on static hosting
    // (e.g. Netlify) that 404s and we read the bundled snapshot instead.
    let res = null;
    try { res = await fetch("/api/data"); } catch { /* offline API */ }
    if (res && res.ok) {
      state.data = await res.json();
    } else {
      state.staticMode = true;
      $("refreshBtn").hidden = true;
      $("refreshScope").hidden = true;
      try {
        const r2 = await fetch("catalog.json");
        state.data = r2.ok ? await r2.json()
          : { generated: null, stores: [], categories: [], products: [] };
      } catch {
        state.data = { generated: null, stores: [], categories: [], products: [] };
      }
    }
    normalizeData(state.data);
    $("updated").textContent = state.data.generated
      ? "Updated " + state.data.generated.replace("T", " ")
      : "No data yet";
    buildControls();
    render();
  }

  async function pollStatus() {
    try {
      const res = await fetch("/api/status");
      const st = await res.json();
      const prog = $("progress");
      if (st.running) {
        prog.classList.remove("hidden");
        $("refreshBtn").disabled = true;
        const pct = st.total ? Math.round((st.done / st.total) * 100) : 0;
        const phase = { listing: "Reading listings", products: "Reading product pages",
                        inventory: "Checking store stock" }[st.phase] || st.phase;
        $("progressLabel").textContent =
          `${phase}… ${st.done || 0}/${st.total || "?"} ${st.detail || ""}`;
        $("progressBar").style.width = pct + "%";
        statusTimer = setTimeout(pollStatus, 1500);
      } else {
        $("refreshBtn").disabled = false;
        if (!prog.classList.contains("hidden")) {
          prog.classList.add("hidden");
          if (st.phase === "error") {
            alert("Refresh failed: " + (st.error || "unknown error"));
          }
          await loadData(); // pick up the fresh catalog
        }
      }
    } catch {
      statusTimer = setTimeout(pollStatus, 3000);
    }
  }

  async function refresh() {
    const scope = $("refreshScope").value || "all";
    const res = await fetch(`/api/refresh?category=${encodeURIComponent(scope)}`,
      { method: "POST" });
    if (res.ok) {
      $("progress").classList.remove("hidden");
      $("progressLabel").textContent = "Starting…";
      $("progressBar").style.width = "0%";
      clearTimeout(statusTimer);
      pollStatus();
    }
  }

  // ---------- events ----------

  $("categories").addEventListener("click", (e) => {
    const btn = e.target.closest(".cat");
    if (!btn) return;
    state.category = btn.dataset.cat;
    document.querySelectorAll(".cat").forEach((b) =>
      b.classList.toggle("active", b === btn));
    rebuildDependentSelects();
    render();
  });
  for (const id of ["store", "inStock", "type", "size", "sort"]) {
    $(id).addEventListener("change", render);
  }
  $("search").addEventListener("input", render);
  $("refreshBtn").addEventListener("click", refresh);

  loadData().then(() => { if (!state.staticMode) pollStatus(); });
})();
