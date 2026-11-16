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
