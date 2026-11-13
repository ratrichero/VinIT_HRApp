# Cloudflare evidence reranker

`@cf/baai/bge-reranker-base` is an optional cross-encoder for English CV/JD evidence retrieval, not an embedding model and not candidate ranking. After lexical/BGE retrieval, it reorders the **same** maximum five candidate chunks for each unresolved criterion before the LLM. It does not create evidence, findings, eligibility decisions or directly change mandatory/coverage policy. It can nevertheless change what the LLM focuses on and therefore affect downstream outcomes. Do not claim a quality or fairness improvement without an independently reviewed benchmark. LTR remains separate.

## Deployment and safety

- Migration `00020_reranker_controls.sql` is required **before deploying** this code; it starts with no selection (OFF). Do not apply it to any shared database without explicit operator approval and a backup/restore decision. The deploy script detects changed migrations but does not apply them. Drain/stop HRA processes and avoid mixed-version workers during rollout/rollback. Do not touch unrelated processes. The operator authorized migration without a separate backup for the test project `myrymlqdbyqmpynesiwk`; it was applied as Supabase version `20261112094826`. Postflight: no current reranker selection, BGE ON and LTR OFF unchanged, and no pending/processing operations. The operator reports deploying the reranker to the test VPS and a successful deployment smoke test; the deployed commit and worker behavior have not been independently verified. The operator subsequently reported a synthetic provider smoke PASS, described below.
- Admin UI: **BGE** tab → Cloudflare evidence reranker. Select an existing BGE draft with an encrypted Cloudflare API token and base URL `https://api.cloudflare.com/client/v4/accounts/<account-id>/ai/v1`. The token must have Workers AI permission. The reranker uses this account and credential but is independently enabled, even if embedding BGE is OFF; do not assume BGE approval implies reranker approval. Saving a draft alone does not enable anything.
- Approve the Cloudflare data destination explicitly in the reranker UI and confirm enable. API validates the fixed Cloudflare HTTPS account endpoint and requires `ALLOW_EXTERNAL_API=true` in the API process. Each worker also independently requires `ALLOW_EXTERNAL_API=true`, rechecks the current selection and endpoint policy before a request, and decrypts the key only when used. Network firewall and quota also apply. UI reflects database intent, not worker/provider health. API token is never returned or stored in operation snapshots. Enable/disable events are audited.
- CV text has best-effort redaction, including an additional redaction on every outgoing excerpt and query. **Redaction is not anonymization:** CV excerpts or JD criteria can still identify a person or contain confidential information. Approve privacy, legal basis, transfers, retention and provider terms before enabling. Do not send real data for tests without explicit authorization.
- On provider failure, policy/config errors, timeout, incomplete/duplicate/invalid results, keep original retrieval order and continue. Model scores are not probabilities and are never used as a hiring score. Only counts of attempted/succeeded/failed criterion reranks and public pinned selection are stored in assessment provenance, not texts, scores or token. Results are operation-scoped when reranking is selected, so provider failure cannot cause cross-operation cache reuse. A recovered operation retains its pin; if selection was disabled or changed, it falls back. An already in-flight request may finish after disable.
- Bounded input is at most 800 query characters and 1500 characters per excerpt, up to five excerpts and 15 seconds per criterion request; Cloudflare may impose further token truncation or errors. Character bounds are not token counts and long or technical excerpts may be truncated. Sequential requests add latency and cost; monitor before wider rollout.
- To disable: Admin UI **Tắt reranker / Disable reranker**. Newly attempted requests recheck selection; wait for in-flight requests to finish. BGE/LTR controls are independent. To roll back code, disable, drain all HRA workers, verify database and compatibility, then roll back as an operator-approved change. Do not remove schema while new processes are running.

## Validation

`backend/tests/test_reranker.py` uses an in-memory HTTP transport and synthetic strings only. Disposable PostgreSQL integration tests cover admin permissions, explicit approval, network gate, audit and disabling a pinned selection. These do not verify the real Cloudflare endpoint, real CV/JD quality, operational readiness, latency, cost, legal compliance, or fairness. A synthetic-only Cloudflare request was subsequently reported PASS by the operator. Before real use, evaluate on appropriately authorized HR/HM gold data with matching and fairness metrics; compare OFF vs ON and monitor fallback rate. Default remains OFF until explicitly enabled.

API schema: https://developers.cloudflare.com/workers-ai/models/bge-reranker-base/ and https://developers.cloudflare.com/workers-ai/models/bge-reranker-base/schema-output.json.

## Operator smoke test (synthetic only)

**Operator-reported result:** PASS on the test VPS with model `@cf/baai/bge-reranker-base`, 3 synthetic contexts, ordered IDs `synthetic-1`, `synthetic-3`, `synthetic-2`, elapsed 3159 ms, and `runtime_controls_changed: false`. The script validates that the provider returned a complete set of unique indices and finite scores before reporting PASS. This is one user-reported request, not a latency distribution, independent verification, worker end-to-end test or quality benchmark. No real CV/JD was used. Reranker and LTR remain subject to their separate runtime controls and authorization.

The operator has approved a single synthetic request. `backend/scripts/cloudflare_reranker_smoke.py --send` uses the first Cloudflare account/key in the active BGE route set and the backend process configuration. It does not change BGE, LTR or reranker controls, create an assessment or use CV/JD data. It requires `ALLOW_EXTERNAL_API=true` and a usable encrypted key. The production reranker validates a complete finite indexed response; the script prints only synthetic IDs, elapsed time and PASS/FAIL, never a token, account ID, response body or exception message. An API call can incur provider cost. A PASS validates this single isolated request, **not** worker behavior, model accuracy, fairness, privacy approval or production readiness.

If the deployed checkout does not contain the script, fetch it without changing the checked-out code or restarting any process:

```bash
(
  set -e
  tmp=$(mktemp /tmp/hra-reranker-smoke.XXXXXX)
  trap 'rm -f "$tmp"' EXIT
  git fetch origin arena/ea6e2570-vinit-hrapp
  git show FETCH_HEAD:backend/scripts/cloudflare_reranker_smoke.py > "$tmp"
  (cd backend && .venv/bin/python "$tmp" --send)
)
```

Only share the safe PASS/FAIL output; do not share `.env`, keys, account IDs or logs containing secrets. Run from the intended HRA repository; this reads `backend/.env` and does not touch Narrative. See [MATCHING_BENCHMARK_AND_PRIVACY.md](MATCHING_BENCHMARK_AND_PRIVACY.md) for the separate gold and governance work.
