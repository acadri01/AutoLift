# Standing instructions for autonomous builds

You are building this project in the background. Read SPEC.md first; it is the source of truth.
Optimize for finishing correctly with the fewest interruptions to me.

## Working style
- Work in small, reviewable commits. Keep the build runnable at every commit.
- Match existing patterns and conventions in the repo before introducing new ones.
- Append a one-line status to PROGRESS.md after each meaningful step (what changed + why).
- Never halt on the first blocker. Keep working every unblocked path; accumulate open
  questions in QUESTIONS.md and continue elsewhere.

## Decide-and-proceed (do NOT interrupt me) when the choice is:
- Reversible and low-stakes, OR internal-only (naming, file layout, helper structure)
- Already implied by SPEC.md or by existing code patterns
- A routine engineering call (which std-lib helper, test structure, formatting)
→ Pick the most reversible option, implement it, and log it in QUESTIONS.md under
  "Assumptions made" — do not wait for me.

## Stop and ask me ONLY when the choice is:
- Irreversible or destructive (data migration, deleting data, force-push, dropping a feature)
- A change to the public API, data schema, or external contract
- Security-, auth-, payment-, or secret-handling-related
- Something that incurs real cost or hits an external/paid service
- Something requiring human/social contact
- A genuine requirement ambiguity where the branches lead to materially different products
- A direct contradiction inside SPEC.md
→ Batch ALL currently-known blocking questions into QUESTIONS.md, make as much unblocked
  progress as possible first, then pause. Do not drip-feed one question at a time.

## When unsure which bucket applies
Prefer the most reversible action, log it, and keep moving.
Reversible-and-logged beats blocked-and-waiting.
