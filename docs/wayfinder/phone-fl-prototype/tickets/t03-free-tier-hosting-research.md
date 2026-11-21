---
title: What free tiers can host the aggregation service and the weights storage?
labels: [wayfinder:research]
status: closed
assignee: research agent (claimed 2026-11-19, closed 2026-11-19)
parent: MAP
blocked_by: []
---

## Question

From each provider's official pricing and limits pages, list free options for (a) a small always-reachable HTTP service that receives model updates and (b) durable storage for aggregated weights (Render free, Hugging Face Spaces and Hub, Fly.io, Cloudflare Workers and R2, GitHub releases, others). Record sleep and cold-start behaviour, storage persistence, request size limits, CPU and memory limits, and terms that forbid the use. Output: `docs/research/free-tier-aggregation-hosting.md`.

## Resolution (2026-11-19)

Findings are in `docs/research/free-tier-aggregation-hosting.md` (pages read 2026-11-19 through a summarising fetch tool, so nothing is verbatim; unconfirmed items are marked UNVERIFIED there). This is a fact-finding result, not a decision; the choice is made in the update, aggregation and storage ticket.

- Render free (already used): spins down after 15 minutes idle, about a minute to wake, ephemeral filesystem, free Postgres expires after 30 days. Fine as the HTTP service, not as weights storage.
- Cloudflare Workers Free plus R2 is the best documented fit for a service and weights storage (100,000 requests a day, 10 ms CPU, 10 GB-month R2). UNVERIFIED: whether R2 needs a payment method, and its prohibited-use terms.
- Hugging Face: a Hub repo can store weights, but the docs and the pricing page conflict on whether a free Docker Space can be created. A static Space cannot receive POSTs.
- Fly.io has no free tier for new accounts; Koyeb needs a card hold. Both fail "free user".
- GitHub Releases works as a read-only artifact store; writing needs a token.
- Open: the size of one phone update is unknown until the phone model exists, so no request-size margin is computed.
