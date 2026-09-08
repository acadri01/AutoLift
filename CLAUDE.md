# Standing instructions for autonomous builds

You are building this project in the background. Read SPEC.md first; it is the source of truth.
Optimize for finishing correctly with the fewest interruptions to me.

## Continuous progress, no idling (per direct instruction, 2026-09-01)
A quiet PR — no new comments, no new messages — is not a signal to stop and wait. It means: keep
implementing the next milestone item (see "## Milestones" below). Progress matters more than
getting each increment right on the first attempt — review will always surface things to improve;
that's expected and welcome, not a reason to slow down or wait for pre-approval before building.

Only stop *working* (not just checking in) when every currently-unblocked path is genuinely
exhausted — everything left requires either a stop-and-ask consultation (per the rules below) or a
step only the user can do (a Windows/CAESAR II action Claude can't run in this container). When
that happens: batch the remaining blocking items into QUESTIONS.md exactly as the stop-and-ask rule
already requires, keep the scheduled PR check-in running, and use time between check-ins
productively (tests, docs, PROGRESS.md/QUESTIONS.md/TESTING.md upkeep, prep for the next
milestone's unblocked items) rather than re-arming and doing nothing.

A milestone boundary is a natural checkpoint to post a PR-comment summary and move on — it is
**not** a mandatory pause. Only pause and wait at a milestone if the user says so, or if the very
next milestone's first step is itself a stop-and-ask item.

## Milestones
See SPEC.md's "## Milestones" section for the current MVP milestone list, ordering, and status.
Work top-down within a milestone; once its unblocked items are done, move to the next milestone
automatically — don't wait for a review to greenlight starting it, unless SPEC.md or the milestone
itself says otherwise. If the user reviews and reshapes a "done" milestone, fold that into
QUESTIONS.md/PROGRESS.md and keep going; a milestone being revisited later isn't a failure, it's
the review loop working as intended.

## Working style
- Work in small, reviewable commits. Keep the build runnable at every commit.
- Match existing patterns and conventions in the repo before introducing new ones.
- Append a one-line status to PROGRESS.md after each meaningful step (what changed + why).
- Never halt on the first blocker. Keep working every unblocked path; accumulate open
  questions in QUESTIONS.md and continue elsewhere.
- **Always consult `reference/` before touching anything about the neutral file format or
  CAESAR II input/output behavior.** Correct formatting is imperative — a real, working bug
  (LF vs. CRLF line endings, causing `iecho.exe` to reject Conduit's output) came from relying on
  a paraphrase instead of checking the primary source. Re-verify against `reference/`'s vendor
  PDFs (and, when the user provides them, real files) rather than trusting an earlier summary in
  SPEC.md or in this session's own memory — SPEC.md's prose can drift from the source; the PDFs
  can't.
- Support-placement logic (what makes a location a rest, hold-down, guide, line stop, or anchor,
  and where) is defined **one support type at a time, with me consulted on the logic before it's
  implemented** — not decided unilaterally, even under the decide-and-proceed rule below. This
  overrides the general decide-and-proceed bucket for this specific class of decision.
- No spring logic of any kind for the MVP — not implemented, not stubbed, not mentioned in docs
  or output. If a task seems to call for it, skip that part and note why in QUESTIONS.md instead
  of adding a placeholder.
- Keep TESTING.md current — instructions for how to test the program (automated and manual).
  Update it whenever what/how to test changes (a new project, a new fixture convention, a new
  manual check that matters), and consult it whenever testing is relevant to the task at hand.
  It must lead with a step-by-step tutorial a non-developer can follow end to end on their own
  machine — everything from GitHub (cloning, checking out the right branch) through installing
  prerequisites, building, and running the program locally, with concrete commands and the actual
  expected output shown and explained, not just referenced. Verify every command in it against
  the real build before committing it — don't write example output from memory. Developer-only
  reference material (what each automated test covers, how to add a fixture, etc.) belongs after
  the tutorial, not instead of it.
- **TESTING.md's "Test this now" section is a dynamic document, per direct instruction (2026-08-26)**:
  whenever a round of work needs something only the user can do (running `iecho.exe` or anything
  else Claude can't run itself), that section — not a scattered PR comment — is where the exact
  command(s) to run and what to report back live, so there's always exactly one place to check
  for "what does Claude want me to test." Rewrite it every round: replace the previous ask once
  it's resolved, or say plainly there's nothing outstanding when there isn't.

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
  Every blocking-question entry in QUESTIONS.md MUST also state the concrete next
  implementation step to take once I decide — so answering it is enough to unblock work
  immediately, with no extra round-trip to re-derive what happens next.

## When unsure which bucket applies
Prefer the most reversible action, log it, and keep moving.
Reversible-and-logged beats blocked-and-waiting.
