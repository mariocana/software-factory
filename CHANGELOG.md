# Changelog

## 0.4.1 — 2026-10-27
- `/factory resume <id>`: continue a task whose session stopped mid-pipeline (closed, interrupted,
  out of context), from the stage it reached. `next` and `run` skip such tasks because their item
  is still marked taken.
- `/factory run` lists tasks left in an active stage, with the `resume` command for each.

## 0.4.0 — 2026-10-27
- `/factory run [n]`: builds the backlog on its own, taking the next ready item until nothing is
  ready or `n` tasks have started. A task escalated to a human does not stop the run; independent
  items go on. Stops early on a failed task or a git merge problem. Ends with a summary table.

## 0.3.0 — 2026-10-26
- Optional skills, listed in the policy's `skills:` line:
  [Impeccable](https://github.com/pbakaus/impeccable) (design context, craft rules, detector and
  audit/critique in UI/UX review) and [Ponytail](https://github.com/DietrichGebert/ponytail)
  (smallest complete change in the builder, ponytail-review checks in code review).
- `factory.py skills` resolves listed skills to their installed folders; every agent gets `SKILLS`.
- `/factory init` detects installed skills and scopes Ponytail's subagent hook to the builder and
  code reviewer with `PONYTAIL_SUBAGENT_MATCHER`.

## 0.2.0 — 2026-10-26
- Analyst stage: `/factory plan <brief>` asks the open questions, writes `docs/product.md` and a
  backlog of small vertical slices with dependencies (`F01`…); you approve it.
- `/factory plan update <feedback>` re-plans open items; taken and done items never change.
- `/factory next` takes the first open item whose dependencies are done.
- Items added by hand with `/factory backlog` get `M` ids, so a plan never overwrites them.

## 0.1.0 — 2026-10-26
- First version: spec writer, builder, parallel reviewers (code, security, UX, UI) and approver
  as subagents, orchestrated by the `/factory` skill.
- One git worktree and branch per task; local merge without stash or branch switch, or a GitHub PR.
- Per-project policy in `.claude/factory.md`; state in Markdown under `.factory/`, excluded from git.
- Local dashboard (`/factory dashboard`).
