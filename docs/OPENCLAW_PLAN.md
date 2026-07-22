# EPM OpenClaw — pivot plan

The pivot: from an IBM-Cloud-hosted, watsonx-backed EPM assistant to a
**self-owned, artifact-first, agentic EPM tool** that also **drives Oracle EPM's
web UI and Excel while you watch and it narrates** — Claude-for-Chrome, but
domain-specific, on models you control.

This doc is the anchor. It is grounded in four research passes (Together AI,
Fly.io, Chrome-extension architecture, Excel automation); the load-bearing
findings and their sources are inline.

---

## The stack

```
Users ──► Fly.io  (public site, OAuth in front)
           ├─ frontend (React/Vite)      — existing image
           ├─ backend  (FastAPI)         — existing image, streams via SSE
           │     └──► Together AI  (pay-per-token; serverless where possible)
           │           ├─ Qwen2.5-Coder-32B-Instruct  → rules / calc / Groovy / structured
           │           ├─ a vision model (Qwen2.5-VL / Qwen3-VL)  → screenshots
           │           ├─ an embedding model (BGE / M2-BERT)      → RAG (inference-only)
           │           └─ a cheap MoE generic model  → general chat
           │              (e.g. gpt-oss-120B ~$0.15/$0.60, or Qwen3-235B-A22B
           │               ~$0.20/$0.60 — NOT Llama-3.3-70B, which is old + pricey.
           │               Verify current price/quality at setup; catalog churns.)
           ├─ Postgres (Neon or Fly, per-user durable data)
           │
           ├─◄ Chrome extension (MV3)  → drives Oracle EPM web UI, narrates in a side panel
           └─◄ Excel layer             → offline macro/VBA reading (cross-platform)
                                          + optional live drive (Windows/VM only)
```

---

## Load-bearing findings (read before budgeting)

### 1. The fine-tuning cost cliff — the #1 decision
- Fine-tuning on Together is **cheap to run** (~$1–7 one-time for a few thousand
  examples — billed per training token).
- **Serving a fine-tuned model is the expensive part.** Default deployment is a
  **dedicated hourly endpoint** (~$6.49/hr H100 ≈ **$4,700/mo always-on**).
- It is only cheap (~$20–50/mo) **if the base qualifies for Together's
  Serverless Multi-LoRA** — a limited allowlist. **Action: confirm
  Qwen2.5-Coder-32B Multi-LoRA eligibility before committing to fine-tuning.**
- **Recommendation: don't fine-tune on day one.** Ship on **stock
  Qwen2.5-Coder-32B + RAG grounding** on your snapshot corpus (serverless, cheap,
  already how the app works). Fine-tune later only if quality demands it *and*
  serverless-LoRA is confirmed. Sources: Together fine-tuning / deploy /
  Serverless-Multi-LoRA docs.

### 2. Vision fine-tuning may not cover Qwen2.5-VL
Together's VLM fine-tuning docs name **Qwen3-VL-8B, Llama-4, Gemma-3** — not
Qwen2.5-VL-7B specifically. Stock VL models ground screens well un-tuned, so:
**run the vision model stock; only fine-tune the coder** (if at all). Verify the
live `fine-tuning-models` list before assuming otherwise.

### 3. Embeddings are inference-only
No fine-tuning of embedding models on Together. Use a served one (BGE / M2-BERT,
~$0.01/M tokens). Fine — RAG quality comes from chunking + grounding, not a
custom embedder, at this scale.

### 4. Excel: Windows only matters for *live* driving
- **Reading VBA macro source offline** (`.xlsm`) is fully cross-platform via
  **oletools/olevba** — full macro text + module names, no Excel, no Windows.
  This is the 90% case and ships first.
- **Live full-fidelity Excel automation** (run macros, read calculated cells)
  **requires real Windows** (pywin32/COM) or a Windows VM; macOS gets partial
  via xlwings+AppleScript; Linux has no real story. Office.js add-ins are
  cross-platform for read/write but **cannot touch existing VBA**.
- **Decision: offline macro reading (cross-platform) is core; live Excel drive
  is a later, optional, Windows-gated add-on.**

### 5. Fly.io shape
- **Two apps** (frontend + backend), each its own `fly.toml`; private
  `*.internal` 6PN networking between them.
- **Auth: oauth2-proxy in front with Google/GitHub OAuth + an email allowlist**
  is the simplest *real* auth for 3–5 known users (no password storage). Clerk
  free tier is the comparable hosted alternative.
- **SSE**: works, but set `min_machines_running=1` on the backend so a chat
  stream never hits a cold start mid-response.
- **Cost**: ~$10–20/mo with scale-to-zero + Neon/self-managed Postgres.

### 6. Chrome extension architecture
- MV3: **service worker** (orchestration + CDP debugger) + **content scripts**
  (DOM / accessibility-tree read + click/type) + **side panel** (persistent
  narration UI).
- **Accessibility-tree snapshot as primary grounding** (assign ref IDs, target
  `ref=42` not pixels); screenshot (vision model) as fallback for canvas/ARIA-poor
  views. This is what Claude's own extension does.
- References to study: **browser-use**, **Nanobrowser** (an actual MV3
  multi-agent extension), the reverse-engineered Claude-for-Chrome gist.
- Effort for an EPM-targeted narrated prototype: **~6–10 weeks** (Oracle's
  ADF/JET UI + dynamic grids/iframes is the hard part).

---

## Phased build order

**Phase 0 — leave IBM.** Tear down Postgres + App ID + Code Engine so billing
stops. (Commands to be run by the operator.)

**Phase 1 — local/Together core.** App on Fly (or local first), provider =
Together, models = stock Qwen2.5-Coder-32B (chat/code/structured) + generic 70B
+ served embeddings. Confirm chat + RAG grounding work. *(Vision plumbing already
shipped — the provider speaks multi-part image content + a `vision` role model.)*

**Phase 2 — artifact-first.** Make snapshot + Excel/CSV ingestion the primary
flow; live Oracle connector becomes optional/toggle. Add **olevba** macro reading
so the tool documents Excel exports offline.

**Phase 3 — Fly + OAuth + Postgres.** Deploy two apps, oauth2-proxy front door,
Neon Postgres, per-user isolation (the `EPMW_MULTI_USER` + `X-Forwarded-Email`
wiring already exists). Public site, real login.

**Phase 4 — the narrated browser agent (the headline feature).** MV3 extension:
side panel + accessibility-tree grounding + screenshot fallback (routed to the
vision model) + an agent loop over WebSocket to the backend, narrating each step.
Target Oracle EPM Planning UI first.

**Phase 5 — fine-tune (only if warranted).** Confirm serverless-LoRA eligibility;
export the corpus (exporter already exists); LoRA the coder on your snapshot
rule bodies; A/B vs stock. Optionally add specialized experts + a router.

**Phase 6 — live Excel (optional, Windows).** xlwings/COM on a Windows box for
interactive build/demo, if the offline-documentation flow proves it's needed.

---

## Cost summary (light usage, 3–5 users)

| Item | Monthly |
|---|---|
| Fly.io (2 apps, scale-to-zero-ish + backend warm for SSE) | ~$10–20 |
| Postgres (Neon small / Fly self-managed) | ~$0–19 |
| Together — stock serverless (coder + chat + embeddings + vision) | ~$40–100 |
| Together — **fine-tuned coder, IF dedicated endpoint required** | **~$2k–5k ⚠️** |
| **Total (no dedicated endpoint)** | **~$50–140/mo** |

The dedicated-endpoint line is the whole ballgame — avoid it by staying stock or
confirming serverless-LoRA first.

---

## Open decisions for the operator
1. **Fine-tune now or stay stock?** (Recommend stock + RAG first.)
2. **Confirm Together Serverless Multi-LoRA eligibility for Qwen2.5-Coder-32B.**
3. **Will there be a Windows machine** for live Excel, or is offline macro
   reading enough? (Recommend offline-only to start.)
4. **Public + OAuth** confirmed (vs. the old private/VPN model) — yes, per pivot.
