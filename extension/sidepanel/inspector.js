// Workbook Inspector — the "open the extension on an Excel sheet and see all the
// macros and moving parts" surface. Ships the chosen file to the backend's
// stateless `/api/spreadsheet/inspect` endpoint (which parses, never executes)
// and renders the full picture: macros + triggers, sheets, named ranges,
// tables, pivots, charts and data connections.

const $ = (id) => document.getElementById(id);

// Tiny DOM helper. `text` is always set via textContent so untrusted workbook
// content (macro source, connection strings) can never inject markup.
function el(tag, opts = {}, kids = []) {
  const n = document.createElement(tag);
  if (opts.class) n.className = opts.class;
  if (opts.text != null) n.textContent = String(opts.text);
  if (opts.attrs) for (const [k, v] of Object.entries(opts.attrs)) n.setAttribute(k, v);
  for (const k of [].concat(kids)) if (k) n.appendChild(k);
  return n;
}

export function initInspector({ getConfig }) {
  const dropZone = $("dropZone");
  const fileInput = $("wbFile");
  const statusEl = $("inspectStatus");
  const results = $("inspectResults");

  const setStatus = (msg, isErr = false) => {
    statusEl.textContent = msg || "";
    statusEl.classList.toggle("hidden", !msg);
    statusEl.classList.toggle("err", !!isErr);
  };

  async function inspect(file) {
    if (!file) return;
    results.innerHTML = "";
    setStatus(`Inspecting ${file.name}…`);
    const cfg = getConfig() || {};
    const base = (cfg.backendUrl || "").replace(/\/+$/, "");
    if (!base) { setStatus("Set a Backend URL in ⚙ Settings first.", true); return; }
    const form = new FormData();
    form.append("file", file, file.name);

    // Match the agent's auth: token → token-gated /api/ext route (Bearer, no
    // cookie); no token → integrated route with the website session cookie.
    const token = (cfg.apiToken || "").trim();
    const path = token ? "/api/ext/spreadsheet/inspect" : "/api/spreadsheet/inspect";
    const opts = { method: "POST", body: form };
    if (token) opts.headers = { authorization: `Bearer ${token}` };
    else opts.credentials = "include";

    let res;
    try {
      res = await fetch(`${base}${path}`, opts);
    } catch (err) {
      setStatus(`Can't reach the backend at ${base}: ${err.message}`, true);
      return;
    }
    if (!res.ok) {
      let detail = `${res.status}`;
      try { const b = await res.json(); detail = b.detail || detail; } catch { /* keep */ }
      if (res.status === 401 || res.status === 403) {
        detail = token
          ? "API token was rejected — generate a fresh one on the Browser Agent page."
          : "not signed in — open EPM Wizard and sign in, or add an API token in ⚙ Settings.";
      }
      setStatus(`Inspect failed: ${detail}`, true);
      return;
    }
    const data = await res.json();
    setStatus("");
    render(data);
  }

  function render(w) {
    results.innerHTML = "";
    results.appendChild(summaryCard(w));

    if ((w.triggers || []).length) {
      results.appendChild(section("Auto-run triggers — what makes it move", triggersBody(w.triggers), "trigger"));
    }
    if ((w.vbaModules || []).length) {
      results.appendChild(section(`Macros (${(w.procedures || []).length} procs · ${w.vbaModules.length} modules)`,
        macrosBody(w.vbaModules, w.procedures || [])));
    } else if (w.macroEnabled) {
      results.appendChild(section("Macros", el("div", { class: "imuted body", text: "Macro-enabled file, but no VBA code was found." })));
    }
    if ((w.sheets || []).length) results.appendChild(section(`Sheets (${w.sheets.length})`, sheetsBody(w.sheets)));
    if ((w.namedRanges || []).length) results.appendChild(section(`Named ranges (${w.namedRanges.length})`, namedBody(w.namedRanges)));
    if ((w.tables || []).length) results.appendChild(section(`Tables (${w.tables.length})`, tablesBody(w.tables)));
    if ((w.pivotTables || []).length) results.appendChild(section(`Pivot tables (${w.pivotTables.length})`, pivotsBody(w.pivotTables)));
    if ((w.charts || []).length) results.appendChild(section(`Charts (${w.charts.length})`, chartsBody(w.charts)));
    if ((w.connections || []).length) results.appendChild(section(`Data connections (${w.connections.length})`, connsBody(w.connections)));
    if ((w.issues || []).length) results.appendChild(section("Notes", listBody(w.issues, "imuted")));
  }

  // ── section builders ──────────────────────────────────────────────────────
  function summaryCard(w) {
    const card = el("div", { class: "wb-summary" }, [
      el("div", { class: "fname", text: w.filename || "workbook" }),
      el("div", { class: "sline", text: w.summary || "" }),
    ]);
    const badges = el("div", { class: "wb-badges" });
    badges.appendChild(el("span", { class: "pill", text: (w.fileFormat || "").toUpperCase() || "?" }));
    badges.appendChild(el("span", {
      class: "pill " + (w.hasMacros ? "macro" : "ok"),
      text: w.hasMacros ? "macros" : (w.macroEnabled ? "macro-enabled, empty" : "no macros"),
    }));
    if ((w.triggers || []).length) badges.appendChild(el("span", { class: "pill macro", text: `${w.triggers.length} auto-run` }));
    card.appendChild(badges);
    return card;
  }

  function section(title, bodyNode, extraClass = "") {
    const wrap = el("div", { class: "isec" + (extraClass ? " " + extraClass : "") });
    wrap.appendChild(el("h3", { text: title }));
    if (bodyNode.classList && bodyNode.classList.contains("body")) wrap.appendChild(bodyNode);
    else wrap.appendChild(el("div", { class: "body" }, bodyNode));
    return wrap;
  }

  function triggersBody(triggers) {
    const box = el("div", { class: "kv" });
    for (const t of triggers) {
      const row = el("div", {}, [
        el("b", { text: t.name }),
        document.createTextNode(`  ${t.module ? "· " + t.module + " " : ""}`),
        el("span", { class: "badge-auto", text: t.scope === "auto" ? "AUTO" : "EVENT" }),
      ]);
      box.appendChild(row);
    }
    return box;
  }

  function macrosBody(modules, procedures) {
    const frag = document.createElement("div");
    const procCount = {};
    for (const p of procedures) procCount[p.module] = (procCount[p.module] || 0) + 1;
    for (const m of modules) {
      const det = el("details", { class: "mod" });
      const sum = el("summary", {}, [
        el("span", { text: m.name }),
        el("span", { class: "meta", text: `${m.lineCount || 0} lines · ${procCount[m.name] || 0} procs` }),
      ]);
      det.appendChild(sum);
      det.appendChild(el("pre", { text: m.code || "" }));
      frag.appendChild(det);
    }
    frag.classList.add("body");
    frag.style.padding = "0";
    return frag;
  }

  function table(headers, rows) {
    const t = el("table", { class: "itable" });
    const thead = el("tr");
    for (const h of headers) thead.appendChild(el("th", { text: h }));
    t.appendChild(thead);
    for (const r of rows) {
      const tr = el("tr");
      for (const c of r) tr.appendChild(el("td", { class: c.mono ? "mono" : "", text: c.text != null ? c.text : c }));
      t.appendChild(tr);
    }
    return t;
  }

  function sheetsBody(sheets) {
    return table(["Sheet", "Visible", "Dimensions", "Formulas", "Tables", "Charts"],
      sheets.map((s) => [
        s.name,
        s.visibility === "visible" ? "yes" : (s.visibility || "yes"),
        { text: s.dimensions || "", mono: true },
        String(s.formulaCount || 0), String(s.tableCount || 0), String(s.chartCount || 0),
      ]));
  }
  function namedBody(names) {
    return table(["Name", "Scope", "Refers to"],
      names.map((n) => [n.name, n.scope || "workbook", { text: n.refersTo || "", mono: true }]));
  }
  function tablesBody(tables) {
    return table(["Table", "Sheet", "Range", "Columns"],
      tables.map((t) => [t.name, t.sheet || "", { text: t.ref || "", mono: true }, (t.columns || []).join(", ")]));
  }
  function pivotsBody(pivots) {
    return table(["Pivot", "Location", "Source"],
      pivots.map((p) => [p.name, { text: p.location || "", mono: true }, { text: p.source || "", mono: true }]));
  }
  function chartsBody(charts) {
    return table(["Type", "Sheet", "Title"], charts.map((c) => [c.chartType || "Chart", c.sheet || "", c.title || ""]));
  }
  function connsBody(conns) {
    return table(["Name", "Type", "Source", "Command"],
      conns.map((c) => [c.name || "", c.type || "", { text: c.source || "", mono: true }, { text: c.command || "", mono: true }]));
  }
  function listBody(items, cls) {
    const box = el("div", {});
    for (const it of items) box.appendChild(el("div", { class: cls, text: "• " + it }));
    return box;
  }

  // ── input wiring ──────────────────────────────────────────────────────────
  fileInput.addEventListener("change", () => { if (fileInput.files[0]) inspect(fileInput.files[0]); });
  ["dragenter", "dragover"].forEach((e) =>
    dropZone.addEventListener(e, (ev) => { ev.preventDefault(); dropZone.classList.add("drag"); }));
  ["dragleave", "drop"].forEach((e) =>
    dropZone.addEventListener(e, (ev) => { ev.preventDefault(); dropZone.classList.remove("drag"); }));
  dropZone.addEventListener("drop", (ev) => {
    const f = ev.dataTransfer?.files?.[0];
    if (f) inspect(f);
  });
}
