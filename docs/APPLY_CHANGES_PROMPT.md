# Prompt for your local Codex

The revised ZIP already contains the fixes. Use this prompt if you want Codex to integrate its `review_changes.patch` into your existing working folder and teach you the result. Put the patch beside your project first and give Codex its actual path.

```text
I am a second-year student working on DocVerify. Read the workspace AGENTS.md
instructions and inspect my current files before changing anything. I have
attached review_changes.patch from an independent review of docverify-review(2).zip.

Integrate this reviewed patch into my existing project. Preserve my local edits,
.env, accounts, uploaded PDFs, database and Git history. Do not rebuild the project
from scratch, reset the database, delete volumes, force a patch through conflicts,
or invent commits/authorship. If my code already contains a change, keep it.

First run git status --short and git apply --check using the actual patch path.
If the check succeeds, apply it. If my working copy differs, compare the relevant
functions and integrate the intended fixes carefully while preserving my changes.
Read docs/INDEPENDENT_REVIEW.md and docs/READ_THIS_FIRST.md after integration.

Verify migration 0003 against an isolated database. Never run destructive pytest
against the application database. Tell me when my running deployment needs the
normal additive migration; do not claim tests migrated it. Do not overwrite .env.

Use the existing virtual environment where possible. From the project root run:
  .venv/bin/python -m pytest -q
  .venv/bin/python -m ruff check backend scripts
  .venv/bin/python -m ruff format --check backend scripts
  npm --prefix frontend run typecheck
  npm --prefix frontend run build
Use the equivalent environment paths on Windows. Report actual passes, failures
and unavailable checks. Fix integration regressions without weakening assertions.

Keep the intended scope: selectable-text purchase orders, quotations and invoices.
Do not describe it as proving genuineness, implementing OCR, or validating an issuer.
Do not add a provider key, paid service or new infrastructure to make a demo pass.

Then explain upload -> storage -> worker -> extraction -> deterministic checks ->
results in beginner language, with a dry run of the 8000-versus-10200 sample. For
each changed function, explain its inputs, return value, important branches, failure
path and test. Teach the Python/framework syntax as it appears. List intentional
behavior changes separately from refactoring, and finish with questions that check
whether I understand the code. Be candid about AI assistance and project limits.
```

For a fresh demonstration, use the revised folder directly and follow the README startup commands. The patch is for integrating into an older working copy; do not reapply it to the already revised folder.
