# PROMPTS — reusable prompts for every autobuild project

Two phases, both stored here so you paste (or reference) the same prompts every time.

- **Phase 1 — Spec Builder** is *interactive*. It interviews you and writes `SPEC.md` +
  `setup.sh`. Do this at your desk; it's short.
- **Phase 2 — Build** is *passive*. It reads those files and builds. Walk away.

## Quick use
1. Start a new session, select the repo, set mode to **Accept edits**.
2. Send: `Read PROMPTS.md and run Phase 1.` — answer its questions, then review the two
   files it commits.
3. Send: `Run Phase 2.` — walk away.

(Or copy the full prompt text below instead of referencing the file.)

---

## Phase 1 — Spec Builder (interactive; writes SPEC.md + setup.sh)

```text
You are setting up a new project. Do NOT write any application code in this phase. Your only
job now is to edit/produce two files — SPEC.md and setup.sh — that a later autonomous session will
build from.

Step 1 — Interview me. Ask ONE batched set of concise, high-signal questions (one round if
possible, two maximum), covering only what materially changes the build:
  - What the app does, and who uses it
  - Language/framework, storage, and deploy target
  - Must-haves for v1, and what is explicitly OUT of scope for v1
  - 2–4 concrete input → output examples
  - Any hard constraints (must / must-not), and any existing code or conventions to match
Infer sensible defaults for minor details and state them as assumptions rather than asking.
Do not drip questions one at a time.

Step 2 — After I answer, edit SPEC.md with these sections: Goal (1–2 sentences); Users;
Stack / constraints; In scope (v1); Explicitly OUT of scope; Behaviour by example (the concrete
input→output cases); Acceptance criteria (a checklist, including "app runs from a clean checkout
via setup.sh"); Known open decisions. Be specific and unambiguous — this file is the single
source of truth for the build, so any gap here becomes a wrong guess later.

Step 3 — Write setup.sh for the chosen stack: a bash script that bootstraps the environment
(venv, dependencies, etc.). It MUST finish in under ~5 minutes — run independent installs in
parallel with & and a final wait, background the largest downloads, avoid long retry sleeps, and
append "|| true" to non-critical commands so they don't block session start. Begin the script
with: set -euo pipefail  and  set -x.

Step 4 — Commit SPEC.md and setup.sh. Then STOP — do not begin implementing features. Summarise
what SPEC.md commits to, list every assumption you made, and tell me to review the two files and
then run Phase 2 to build.
```

---

## Phase 2 — Build (passive; reads the files and builds)

```text
Read SPEC.md and CLAUDE.md. SPEC.md is the source of truth. Build the project per the spec,
following the decision and interrupt rules in CLAUDE.md exactly, and use setup.sh for the
environment. Log progress to PROGRESS.md, and log assumptions and any blocking questions to
QUESTIONS.md. Never halt on the first blocker — keep working every unblocked path and batch
questions. Open a PR when a reviewable increment is ready.
```

---

## Notes
- **Permission modes:** Phase 1 uses **Accept edits** (it only writes two files while you watch).
  For Phase 2, keep **Accept edits** (or **Auto**) so the passive build doesn't stop for
  approvals. Use **Plan** only if you want to gate Phase 2 behind an approved plan.
- **Why the split:** the interactive part (deciding what to build) happens up front while you're
  present; the long autonomous part happens after, unattended. The review of the two generated
  files is your quality gate before you walk away.
- **Keep it in the template:** commit this file to `autobuild-template` alongside `CLAUDE.md`,
  `SPEC.md`, `QUESTIONS.md`, `PROGRESS.md`, and `setup.sh`. Every forked project inherits it.
```
