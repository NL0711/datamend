# Free-tier hosting for the aggregation service and the weights storage: facts from primary sources

Compiled 2026-11-19 for the phone on-device training prototype (wayfinder ticket t03, `docs/wayfinder/phone-fl-prototype/`). Single-device prototype, so traffic is tiny (one phone, periodic updates). That is an assumption, not a measurement.

## BANNER: what was read and what was not

All pages below were read on 2026-11-19 through a summarising fetch tool (WebFetch), not verbatim. Free-tier limits change often; re-check before relying on a number. Anything not stated by the page is marked UNVERIFIED.

READ (official pages):
- Render free instances: https://render.com/docs/free
- Hugging Face Spaces overview, GPU/hardware and sleep, Hub storage limits, pricing, terms: https://huggingface.co/docs/hub/spaces-overview , https://huggingface.co/docs/hub/spaces-gpus , https://huggingface.co/docs/hub/storage-limits , https://huggingface.co/pricing , https://huggingface.co/terms-of-service
- Cloudflare Workers limits and pricing, R2 pricing and limits: https://developers.cloudflare.com/workers/platform/limits/ , https://developers.cloudflare.com/workers/platform/pricing/ , https://developers.cloudflare.com/r2/pricing/ , https://developers.cloudflare.com/r2/platform/limits/
- Fly.io pricing FAQ: https://docs.fly.io/about/pricing
- Koyeb pricing FAQ: https://www.koyeb.com/docs/faqs/pricing
- Google Cloud free-tier features: https://docs.cloud.google.com/free/docs/free-cloud-features
- GitHub releases docs and Terms of Service: https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases , https://docs.github.com/en/site-policy/github-terms/github-terms-of-service
- Supabase billing page: https://supabase.com/docs/guides/platform/billing-on-supabase

NOT READ (page text did not come through): the Render Terms (https://render.com/terms) and Acceptable Use page (https://render.com/acceptable-use) returned only navigation, so Render's prohibited-use terms are UNVERIFIED. The Cloudflare service-specific terms page returned only the CDN section, so Workers/R2 prohibited-use terms are UNVERIFIED (see section 3). Supabase's per-plan free limits were only partly itemised by the fetch (numbers below marked accordingly). Google Cloud Run's own pricing page came back truncated, so the figures come from the free-features page.

Repo fact (not a web source): `render.yaml` already deploys `datamend-backend` on Render `plan: free`, with comments "512 MB RAM; measured ~305 MiB idle locally" and "No persistent disk on free: SQLite resets on every restart/redeploy/spin-down".

## 1. Summary table (free, no payment assumed unless noted)

| Option | Role | Sleep / cold start | Persistence | Key limits | Verdict for this prototype |
|---|---|---|---|---|---|
| Render free web service | HTTP service | Spins down after 15 min without inbound traffic; spin-up "about one minute" | Ephemeral filesystem; lost on redeploy, restart, spin-down | 750 free instance hours per workspace per month; single instance | Works for the service; cannot hold weights locally |
| Hugging Face Spaces (Gradio/Docker) | HTTP service | Free hardware sleeps after about 48 h idle; visitor restarts it | Disk is not persistent | 2 vCPU, 16 GB, 50 GB disk | NOT usable free: creating Gradio or Docker Spaces needs a paid plan |
| Hugging Face static Space | Static hosting only | n/a | Git repo | Free for everyone | Cannot receive POSTs (no server code); not an aggregation endpoint |
| Hugging Face Hub repo | Weights storage | n/a | Durable (git/LFS) | Public: "best-effort"; private: 100 GB free | Viable for weights, but a Hub write needs a token and git commit semantics |
| Cloudflare Workers (Free) | HTTP service | No sleep stated; startup must finish in 1 s | Stateless; pair with KV, D1, R2, DO | 100,000 requests/day; 10 ms CPU; 128 MB | Strong fit for a tiny update receiver |
| Cloudflare R2 | Weights storage | n/a | Durable object storage | 10 GB-month, 1M Class A, 10M Class B per month, egress free | Strong fit; payment-method requirement UNVERIFIED |
| Cloudflare D1 / KV / Durable Objects | Small state | n/a | Durable | D1 5 GB; KV 1 GB; DO SQLite 5 GB | Optional, for a run record |
| Fly.io | HTTP service | n/a | n/a | No free tier for new organisations; $1 trial credit for 7 days | Not free |
| Koyeb | HTTP service | Cold-start behaviour not stated | Not stated | One free web service, 512 MB, 0.1 vCPU, 2 GB SSD; card required | Possible; needs a card, scale-to-zero UNVERIFIED |
| GitHub Releases | Weights storage | n/a | Durable | 2 GiB per file, no stated total or bandwidth limit, 1,000 assets per release | Viable as read-only artifact store; writing needs a token |
| Google Cloud Run + Cloud Storage | Service + storage | Not read | Not read | 2M requests, 180,000 vCPU-s, 360,000 GiB-s per month; 5 GB-months storage | Needs a billing account (see section 2) |
| Supabase free | Database | Inactive projects pause after one week | Postgres | 500 MB DB, 1 GB storage, 5 GB egress per month, 2 projects | Not needed; pause behaviour is a trap |

## 2. Per-provider facts

### Render free web service (the repo already uses this tier)
Source: https://render.com/docs/free, read 2026-11-19.
- Spin-down: "Render spins down a Free web service that goes 15 minutes without receiving any inbound traffic." Inbound HTTP requests and WebSocket messages on existing connections count as traffic.
- Cold start: spin-up takes "about one minute".
- Hours: 750 free instance hours per workspace per calendar month; spun-down services do not consume hours; at zero the services are suspended until next month; unused hours do not roll over.
- Filesystem: ephemeral; lost on redeploy, restart or spin-down; persistent disks are not supported.
- Other limits: single instance, no scaling, no one-off jobs, no shell access, no private-network traffic, outbound ports 25, 465 and 587 blocked; Render may restart a free service at any time; a free service may be suspended for an "uncommonly high volume" of service-initiated traffic (no threshold given).
- RAM, CPU, request size limit: NOT stated on this page. UNVERIFIED from Render docs; the 512 MB figure is only the repo's own comment in `render.yaml`.
- Free Postgres: one per workspace, 1 GB, expires 30 days after creation with a 14-day grace period then deletion, no backups. Free Key Value: does not persist to disk; all data lost on restart. So neither is a durable store for weights.
- Consequence for the app: the first request after 15 idle minutes waits about a minute, so the app must show "service waking"; any file or SQLite state the service holds can vanish at any restart, so aggregated weights must live in external storage, and "no open run today" is the normal state after a reset.
- Prohibited-use terms: UNVERIFIED (Terms and Acceptable Use text not retrieved).

### Hugging Face
Sources: https://huggingface.co/docs/hub/spaces-overview , https://huggingface.co/docs/hub/spaces-gpus , read 2026-11-19.
- Docs warning: "Static Spaces are free for everyone. Gradio and Docker Spaces run on compute and require a paid plan to create: PRO for personal accounts, Team or Enterprise for organizations." Free personal accounts can host up to 2 Gradio Spaces on ZeroGPU only. The Hardware page repeats this for CPU Basic. PRO is $9 per month per https://huggingface.co/pricing.
- CONFLICT: the pricing page lists "CPU Basic is free" for Spaces without the paid-plan caveat. The two docs pages are explicit about the creation restriction, so treat a free always-on HTTP Space as NOT available. Verify by trying to create one with a free account before relying on either reading.
- If it were available: CPU Basic is 2 vCPU, 16 GB, 50 GB non-persistent disk; free hardware sleeps after inactivity ("currently, 48 hours") and restarts when someone visits; only ports 80, 443 and 8080 are open for outbound requests.
- Hub storage (https://huggingface.co/docs/hub/storage-limits): free user public storage is "Best-effort"; private storage 100 GB free; no per-repo size limit but uploads count against the account quota; 500 GB hard limit per file; the page asks that public uploads be useful to the community. A tiny weights file for a prototype is within scope of private storage.
- Terms (https://huggingface.co/terms-of-service): HF may "modify, suspend, or discontinue" the services and may suspend or terminate access "anytime with or without cause"; content may be removed at HF's discretion. No specific compute or storage prohibition was found in the main terms; the Supplemental Terms were not read (UNVERIFIED).

### Cloudflare Workers, R2, D1, KV, Durable Objects
Sources: https://developers.cloudflare.com/workers/platform/limits/ , https://developers.cloudflare.com/workers/platform/pricing/ , https://developers.cloudflare.com/r2/pricing/ , https://developers.cloudflare.com/r2/platform/limits/ , read 2026-11-19.
- Workers Free: 100,000 requests per day (resets 00:00 UTC; over the limit returns Error 1027); 10 ms CPU per HTTP request (time waiting on fetch, KV or DB calls does not count); 128 MB memory per isolate; 50 subrequests per invocation.
- Request body: set by the domain's Cloudflare plan, 100 MB on Free and Pro; larger returns 413. The Workers limits page lists this under the request-body table; whether that table binds a `workers.dev` hostname on a Free account is not stated (UNVERIFIED).
- Cold start: no sleep or spin-down is described. Global-scope code must start within 1 second.
- R2 free tier (Standard storage): 10 GB-month storage, 1 million Class A operations and 10 million Class B operations per month, egress free. Object limit about 5 TiB; single-part upload about 5 GiB (the page is internally inconsistent on the exact figure); writes to the same object key limited to 1 per second (HTTP 429 above that); `r2.dev` public endpoints are for testing, not production.
- R2 payment method: the pricing page does not say whether a card is required. UNVERIFIED.
- Free storage products: Workers KV 1 GB, 1,000 writes per day; D1 5 GB, 100,000 rows written per day; Durable Objects (SQLite only on Free) 5 GB, 100,000 requests per day. The pricing page notes a January 2026 target date for Durable Objects SQLite storage billing and does not say how that affects Free (UNVERIFIED).
- Terms: the service-specific terms page retrieved only the CDN section (non-Enterprise customers must use paid Developer Platform services to serve video and large files via the CDN). Nothing found that forbids this use; Workers and R2 terms themselves were not retrieved, UNVERIFIED.

### Fly.io
Source: https://docs.fly.io/about/pricing, read 2026-11-19.
- "New organizations don't have a free tier or a monthly free usage allowance." New accounts get $1 of trial credit that lasts 7 days or until used; no card needed to start, a card is needed to continue. Bills under $5 per month are waived for a personal organization. Not a free option.

### Koyeb
Source: https://www.koyeb.com/docs/faqs/pricing, read 2026-11-19.
- One free web service per organization (Frankfurt or Washington, D.C.): 512 MB RAM, 0.1 vCPU, 2 GB SSD. One free Postgres: 5 hours active time, 1 GB. 100 GB outbound per month free.
- Card required to prevent abuse: a $29 pre-authorization hold, which may take 7 to 21 days to disappear. This conflicts with "free users only, no accounts and payment"; treat as a barrier.
- Cold start and scale-to-zero: the page links to a roadmap and does not confirm it. UNVERIFIED.

### GitHub Releases
Sources: https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases , https://docs.github.com/en/site-policy/github-terms/github-terms-of-service , read 2026-11-19.
- Each release file must be under 2 GiB; no limit on total release size or bandwidth; up to 1,000 assets per release.
- Terms: "Abuse or excessively frequent requests" via the API may lead to suspension; GitHub alone determines abuse; tokens may not be shared to exceed rate limits; one free machine account is allowed. No bandwidth or storage rule was in the ToS text; the Acceptable Use Policies were not read (UNVERIFIED).
- Fit: a read-only, versioned artifact store for the current weights. Writing a release from a service needs a token with repo write access, which must live in `.env`/service secrets only.

### Google Cloud (Cloud Run, Cloud Storage)
Source: https://docs.cloud.google.com/free/docs/free-cloud-features, read 2026-11-19.
- Cloud Run: 2 million requests, 360,000 GB-seconds and 180,000 vCPU-seconds per month, 1 GB outbound from North America. Cloud Storage: 5 GB-months regional (US regions `us-east1`, `us-west1`, `us-central1` only), 5,000 Class A and 50,000 Class B operations per month, 100 GB egress per month.
- A billing account requirement and cold-start behaviour were not confirmed from the pages read (UNVERIFIED); do not assume it is card-free.

### Supabase (for completeness)
Source: https://supabase.com/docs/guides/platform/billing-on-supabase, read 2026-11-19. Free plan includes two projects; per the fetch summary 500 MB database per project, 1 GB storage, 5 GB egress; inactive projects pause after one week. Exact free-plan figures were summarised, not quoted (UNVERIFIED). Not needed here.

## 3. Findings for the t03 question

1. The repo's current Render free service already satisfies (a) in principle, with a roughly one-minute wake and a 15-minute idle sleep, but it has no durable disk, so it cannot also be (b).
2. Hugging Face Docker/Gradio Spaces are not free to create (docs say a paid plan is required), so they are not a free alternative for (a).
3. A Cloudflare Worker (100,000 requests per day, 10 ms CPU, no sleep described) plus R2 (10 GB-month) or D1/KV covers both (a) and (b) with documented free allowances; the open issues are the unconfirmed R2 payment-method rule and the 10 ms CPU cap (fine for storing a small JSON or binary update, not for averaging large tensors in the Worker).
4. GitHub Releases or a private Hugging Face Hub repo are free durable stores for published weights, but both need a write token held by the service.
5. Fly.io has no free tier; Koyeb requires a card.

## 4. Open uncertainties (all UNVERIFIED)

- Render free-tier RAM and CPU, request-body limit, and Render Terms/Acceptable Use prohibited-use text.
- Whether Cloudflare R2 needs a payment method on a Free account; Workers and R2 prohibited-use terms; Durable Objects Free-plan effect of the 2026 billing change.
- Whether `workers.dev` requests are subject to the 100 MB request-body figure.
- Hugging Face: conflict between the pricing page (CPU Basic free) and the docs (compute Spaces need a paid plan); Supplemental Terms.
- Koyeb scale-to-zero and cold start; Google Cloud Run billing-account requirement and cold start.
- Size of one phone model update: unknown until the phone model (ticket t05/t06) exists, so no request-size margin can be computed yet.
