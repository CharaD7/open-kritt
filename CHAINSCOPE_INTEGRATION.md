# ChainScope integration

This fork adds HuggingFace as a first-class model provider so ChainScope can
drive open-kritt with **Foundation-Sec**, the security-specialist model it uses
as its preferred review backend.

## What changed

| File | Change |
|---|---|
| `engine/open_kritt_engine/harnesses.py` | `HF_CODEX_BASE_URL`, `hf` in `MODEL_PROVIDERS`, `_append_hf_codex_config()` |
| `engine/open_kritt_engine/generation.py` | `hf` in `MODEL_PROVIDERS`, harness map, credential map |
| `engine/open_kritt_engine/account_activity.py` | `hf` credential env keys |
| `engine/open_kritt_engine/model_catalog.py` | `fetch_hf_models()`, dispatcher entry, `fetch_hf` param |
| `backend/src/lib/constants.js` | `hf` in `MODEL_PROVIDERS`, `MODEL_PROVIDER_HARNESSES` |
| `backend/src/lib/modelProviders.js` | `hf: ['HF_TOKEN', 'HUGGINGFACE_API_KEY']` |

`hf` mirrors `deepseek`: an OpenAI-compatible provider driven by the `codex`
harness, with a fixed base URL and the credential read from an env key.

## Configuration

```
HF_TOKEN=hf_...                 # required
```

The provider is registered automatically when `HF_TOKEN` (or
`HUGGINGFACE_API_KEY`) is set.

## Model id format

The HF router is OpenAI-compatible at `https://router.huggingface.co/v1`.
Model ids carry an optional `:provider` suffix, and **Foundation-Sec is only
reachable with it**:

```
fdtn-ai/Foundation-Sec-8B:featherless-ai
```

`fetch_hf_models()` preserves ids verbatim for exactly this reason, and injects
Foundation-Sec as the default when the router's `/v1/models` omits it — so the
ChainScope backend is always selectable.

## Startup note: 033 is not idempotent

`database/init/033_generations_deepseek_codex.sql` unconditionally runs
`ADD CONSTRAINT generations_check`, so it re-adds the **pre-hf** definition on
every startup. If any row already uses `model_provider='hf'`, 033 fails and 034
never runs — leaving the backend unable to boot.

The migration order is 033 → 034, so this is self-healing on a clean database:
clear any `hf` rows once, restart, and 034 installs the correct constraint.

`034` keeps every statement on one line because `backend/prisma/migrate.js`
splits the file naively on `;`; a multi-line `CHECK` would be cut mid-statement
and leave the constraint half-applied.

## Tests

```
cd engine && python3 -m pytest tests/test_model_catalog.py -q
# 21 passed
```

`test_fetch_hf_models_keeps_provider_suffix_and_marks_foundation_sec` and
`test_fetch_hf_models_injects_foundation_sec_when_router_omits_it` pin the
format.

No regressions: `test_engine.py` and `test_generation.py` produce an identical
failure set before and after (5 and 4 respectively, all pre-existing and
timing-related).

## ChainScope pairing

open-kritt is the **generator**: it runs agentic workflows over a repository and
produces candidate findings. ChainScope's `cs_verdict` layer is the **verifier**:
every candidate must be confirmed by an independent second method before it is
called CONFIRMED. Foundation-Sec serves as that second opinion via
`core/cs_sec_model.review_hosted()`.

Generation alone is not evidence. Keep the verdict gate between the two.

## Memory gate (why jobs never started)

The engine refuses to start a runner unless the host has
`ENGINE_MEMORY_RESERVE_GB + ENGINE_SCAN_RUNNER_MEMORY_RESERVATION_MB` free.
Defaults are `2` and `1536`, i.e. **3.5 GiB required**.

Three things make this hard to change:

1. **`.env` overrides `docker-compose.yml`.** `${VAR:-default}` uses the `.env`
   value when present, so editing compose alone does nothing.
2. **`docker compose restart` keeps the old container env.** Env changes need
   `--force-recreate`.
3. **The engine syncs container env back into `/data/engine-runtime.env` on
   startup**, so editing that file directly is overwritten on the next boot.

On a host with ~3.5 GiB free, set in `.env`:

```
ENGINE_MEMORY_RESERVE_GB=0.5
ENGINE_SCAN_RUNNER_MEMORY_MB=1024
ENGINE_SCAN_RUNNER_MEMORY_RESERVATION_MB=512
ENGINE_MIN_FREE_STORAGE_GB=5
ENGINE_IGNORE_LOW_STORAGE=true
```

Then `docker compose up -d --force-recreate engine`. The startup line should
read `0.500 GiB reserve, 0.500 GiB reservation per runner, 1.000 GiB hard cap`
and the `waiting for memory` warning must be gone.
