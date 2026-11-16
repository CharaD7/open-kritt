-- Allow HuggingFace (Foundation-Sec) draft generation through the Codex harness.
-- The HF router is OpenAI-compatible, so the codex harness drives it exactly as
-- it drives DeepSeek.
--
-- NOTE: every statement is kept on a single line. backend/prisma/migrate.js
-- splits the file naively on ';', so a multi-line CHECK would be cut mid-statement
-- and leave the constraint half-applied.

ALTER TABLE public.generations DROP CONSTRAINT IF EXISTS generations_model_provider_check;

ALTER TABLE public.generations ADD CONSTRAINT generations_model_provider_check CHECK (model_provider IN ('codex', 'claude', 'openrouter', 'xai', 'deepseek', 'hf'));

ALTER TABLE public.generations DROP CONSTRAINT IF EXISTS generations_check;

ALTER TABLE public.generations ADD CONSTRAINT generations_check CHECK (((model_provider = 'codex' AND harness = 'codex') OR (model_provider = 'claude' AND harness = 'claude-code') OR model_provider = 'openrouter' OR (model_provider = 'xai' AND harness = 'grok-build') OR (model_provider = 'deepseek' AND harness = 'codex') OR (model_provider = 'hf' AND harness = 'codex')));