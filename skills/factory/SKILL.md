---
name: factory
description: "Software factory orchestrator. Plans a product brief into a backlog with an analyst, and runs each feature through spec-writer, builder, parallel reviewers (code, security, UX, UI) and approver subagents in its own git worktree, then merges or escalates to a human. Subcommands: init, plan <brief>, plan update <feedback>, <feature request>, next, run [n], backlog <item>, status, approve <id>, rework <id> <notes>, reject <id>, dashboard. Use only when the user invokes /factory or explicitly asks to run something through the software factory."
argument-hint: "init | plan <brief> | plan update <feedback> | <feature request> | next | run [n] | backlog <item> | status | approve <id> | rework <id> <notes> | reject <id> | dashboard"
allowed-tools:
  - Read
  - Write
  - Edit
  - Glob
  - Grep
  - AskUserQuestion
  - Agent(software-factory:analyst, software-factory:spec-writer, software-factory:builder, software-factory:reviewer-code, software-factory:reviewer-security, software-factory:reviewer-ux, software-factory:reviewer-ui, software-factory:approver)
  - Bash(git *)
  - Bash(gh *)
  - Bash(python3 *)
  - Bash(claude plugin list *)
---

# Software factory

You are the orchestrator. You never write product code yourself: the subagents do the work, you move the task between stages, keep the state current and report. Be brief in chat; details live in the task files.

`F` below means `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/factory.py`. It manages all state under `<repo>/.factory/` (excluded from git through `.git/info/exclude`, so it never dirties the working tree). Update status only through `F set` / `F log`, never by editing `status.md`: the dashboard reads it.

Paths you pass to subagents are always absolute:
- `REPO` = main checkout root (`F init` prints it as `root`)
- `TASK_DIR` = `REPO/.factory/tasks/<id>`
- `WORKTREE` = `REPO/.factory/worktrees/<id>`, `BRANCH` = `factory/<id>`
- `POLICY` = `REPO/.claude/factory.md`, settings via `F policy`
- `CONTRACT` = `${CLAUDE_SKILL_DIR}/reviewer-contract.md`
- `PLAN_DIR` = `REPO/.factory/plan`
- `SKILLS` = the output of `F skills` without its `missing` key: optional skills from the policy's `skills:` line, mapped to their installed folders. **Pass `SKILLS` in every subagent dispatch**, as given (an empty `{}` means none); each agent knows what to do with each skill.

## Dispatch on the arguments

| Arguments | Do |
|---|---|
| `init` | **Init** |
| empty | show `F list` and the subcommands |
| `status` | **Status** |
| `plan <brief>` | **Plan** |
| `plan update <feedback>` | **Plan update** |
| `next` | `F next`; if it returns an `id`, run **Pipeline** for it; if it returns `blocked`, list what each item waits on (items in progress elsewhere count as not done); if `blocked` is empty, say the backlog is empty |
| `run [n]` | **Run** |
| `backlog <item>` | `F backlog-add "<item>"` (gets an `M` id), confirm in one line |
| `approve <id>` | **Approve** |
| `rework <id> <notes>` | **Rework** |
| `reject <id> [reason]` | **Reject** |
| `dashboard` | **Dashboard** |
| anything else | it is a feature request: `F new "<short title>" --request "<full text>"`, then **Pipeline** |

## Init

1. `F init`. It creates `.factory/`, excludes it from git and copies the policy template to `.claude/factory.md` if missing.
2. If the policy was just created, fill its frontmatter from the project: `base_branch` (`git symbolic-ref --short refs/remotes/origin/HEAD` without `origin/`, else the current branch), and `setup_command`, `test_command`, `lint_command`, `run_command` from `package.json` scripts, `pyproject.toml`, `Makefile`, `Cargo.toml`, `go.mod` or similar. Set `merge_mode: pr` only if `origin` is on GitHub and `gh` is available, otherwise `local`. Leave unknown commands empty. Adapt "Always escalate" to what exists in the repo (no billing code → drop that line).
3. Optional skills: run `claude plugin list --json` in `REPO`. If `impeccable` or `ponytail` is enabled for this project, list it in `skills:` (comma separated). If `ponytail` is listed, add `"PONYTAIL_SUBAGENT_MATCHER": "builder|reviewer-code"` under `env` in `REPO/.claude/settings.json` (create or merge, keep everything else), so ponytail's subagent hook shapes only those two agents and not the analyst or the other reviewers.
4. Show the user the settings in a short list and tell them to review and commit `.claude/factory.md`. If the repo has no `CLAUDE.md`, suggest running `/init`: every factory agent reads it.

## Plan

For a product brief: an MVP, a new product area, anything bigger than one feature.

1. If `F policy` fails, run **Init** first (an empty repo is fine; F01 will fill the commands later). Run `F skills` as in Pipeline step 0. The repo needs at least one commit; if it has none, ask the user before making an empty one.
2. Write the brief verbatim to `PLAN_DIR/brief.md`. If `PLAN_DIR/proposed-backlog.md` or a non-empty backlog already exists, ask the user whether to replace the plan or use **Plan update** instead.
3. **Questions.** Dispatch `software-factory:analyst` with `MODE=questions`, `REPO`, `PLAN_DIR`, `POLICY`. Read `PLAN_DIR/questions.md`. Unless it is `none`, ask the user with `AskUserQuestion` (up to 4 per call; each question's options are its default first, marked "(Recommended)", then its alternatives). Write every question with the answer to `PLAN_DIR/answers.md`.
4. **Plan.** Dispatch `software-factory:analyst` with `MODE=plan` and the same inputs.
5. **Review with the user.** Show the scope from `docs/product.md` (MVP scope and Out of scope, 1 line each), the stack, and the proposed backlog as a list with deps. Ask with `AskUserQuestion`: approve, change (they write what), or cancel.
   - change → append their text to `PLAN_DIR/feedback.md`, dispatch the analyst with `MODE=update` and `CURRENT_BACKLOG` = the current `.factory/backlog.md` content, and repeat this step.
   - approve → `F plan-apply`, then commit only the plan files: `docs/product.md`, `PRODUCT.md` if the analyst wrote it, and `.claude/factory.md` and `.claude/settings.json` if untracked or changed by Init: `git -C REPO add <those>` and `git -C REPO commit -m "factory: product plan" -- <those>`. Worktrees branch from the base branch, so the builder only sees what is committed.
6. Report: number of items, which are ready now (no deps), and that `/factory next` starts the first one; independent items can run in parallel from separate sessions.

## Plan update

After feedback on built features, or a change of scope. Append the user's text to `PLAN_DIR/feedback.md`, dispatch `software-factory:analyst` with `MODE=update`, `REPO`, `PLAN_DIR`, `POLICY` and `CURRENT_BACKLOG`, then continue from **Plan** step 5. Items already taken or done never change.

## Pipeline (one task)

**0. Preflight.** If `F policy` fails, run **Init** first. Read the settings once and run `F skills`; if it reports `missing`, tell the user once which listed skills are not installed in this project (install with `claude plugin install <name>@<name> --scope project`) and continue without them. Check `git -C REPO rev-parse --verify <base_branch>`. The main checkout does not need to be clean: all work happens in the worktree.

**1. Spec.** `F set <id> stage=spec`. Dispatch `software-factory:spec-writer` with `REPO`, `TASK_DIR`, `POLICY` and `REQUEST` (the content of `TASK_DIR/request.md`; for a planned item it is the analyst's item card, and `docs/product.md` is context). Afterwards read `spec.md` frontmatter: `F set <id> title="<title>" touches_ui=<…> risk=<…>`, `F log <id> "spec written"`.

**2. Worktree.** Base ref: `<base_branch>` for `merge_mode: local`; for `pr` run `git -C REPO fetch origin <base_branch>` and use `origin/<base_branch>`. Then `git -C REPO worktree add WORKTREE -b BRANCH <base ref>`. Save it: `F set <id> base=<base ref>`.

**3. Build/review loop**, `round` from 1 to `max_rounds`:
- `F set <id> stage=build round=<round>`. Dispatch `software-factory:builder` with `WORKTREE`, `BRANCH`, `TASK_DIR`, `POLICY`, `ROUND`, the task id, and on round 2+ the list of previous review files. `F log <id> "build r<round>: <its one-line reply>"`.
- `F set <id> stage=review`. Reviewer kinds: `code` and `security` always; `ux` and `ui` when `ui_review` is `always`, or `auto` and the spec has `touches_ui: true`. Dispatch all of them **in a single message** so they run in parallel, each with `KIND`, `CONTRACT`, `REPO`, `WORKTREE`, `BRANCH`, `BASE` (the base ref), `TASK_DIR`, `POLICY`, `ROUND`. Wait for every one.
- For each: read the `verdict` of `review-<kind>-r<round>.md`, `F set <id> review_<kind>=<verdict>`, and log the reply line.
- If every verdict is `pass` and build.md's last round is `Status: green`, leave the loop. Otherwise continue with the next round; after `max_rounds`, leave the loop anyway: the approver will escalate.

**4. Approve.** `F set <id> stage=approve`. Dispatch `software-factory:approver` with `REPO`, `WORKTREE`, `BRANCH`, `BASE`, `TASK_DIR`, `POLICY`, `ROUND`, `MAX_ROUNDS`. Read `decision.md`, `F set <id> decision=<merge|escalate>`.
- `merge` → **Merge**.
- `escalate` → `F set <id> stage=needs_human`, log the main reason, and tell the user the reasons from decision.md's "For the human" section and the commands `/factory approve <id>`, `/factory rework <id> <notes>`, `/factory reject <id>`.

**5. Report** in 3-5 lines: title, outcome, rounds, reviewers' verdicts, path of the task folder.

## Merge

`F set <id> stage=merge`. Use the "Merge message" section of decision.md (first line as subject).

- `merge_mode: local`:
  1. `git -C REPO branch --show-current` must equal `base_branch`; if not, `F set <id> stage=needs_human`, log why, and stop. Never switch the user's branch.
  2. `git -C REPO merge --no-ff BRANCH -m "<subject>" -m "<body>"`. Uncommitted user changes in other files are fine; never stash, reset or discard them. If git refuses or conflicts: `git -C REPO merge --abort` when a merge is in progress, `F set <id> stage=needs_human`, log git's message, and tell the user.
  3. On success: `git -C REPO worktree remove WORKTREE`, `git -C REPO branch -d BRANCH`, `F set <id> stage=merged`, `F backlog-mark <id> x`.
- `merge_mode: pr`: `git -C WORKTREE push -u origin BRANCH`, then `gh pr create --repo <owner/repo of origin> --head BRANCH --base <base_branch> --title "<subject>" --body "<body, then one line per reviewer verdict>"`. `F set <id> stage=pr_open pr=<url>`, `F backlog-mark <id> x`. Keep the worktree until the PR is merged.

Never push to `base_branch` directly and never force-push.

## Run

Works through the backlog on its own, so the user does not have to type `next` for every item. `n` caps the number of tasks started (default: no cap).

1. Preflight once (Pipeline step 0). For `merge_mode: local`, `git -C REPO branch --show-current` must equal `base_branch`, otherwise every merge would stop at needs_human: tell the user and stop before starting anything.
2. Loop: `F next`.
   - It returns an `id` → run **Pipeline** for it, with a 1-line report instead of step 5's full report. A task that ends in `needs_human` does not stop the run: its item stays taken, items that depend on it wait, independent items go on.
   - It returns `blocked` (or `n` tasks were started) → leave the loop.
   - Stop early only if a task ends in `failed`, or a merge fails because of git (conflict, wrong branch): later merges would hit the same problem.
   Do not ask the user anything during the loop.
3. Final report: a table with item, title, outcome (merged / needs_human + first reason / failed), rounds; then what is still blocked and on what; then the commands for the tasks waiting for a human (`/factory approve <id>`, `/factory rework <id> <notes>`, `/factory reject <id>`). After approving them, `/factory run` again continues with the items they unblocked.

## Approve

Only for a task in `needs_human` (check `F list`). The human's command is the approval: `F log <id> "approved by human"`, then **Merge** (if it stops at needs_human again, say why).

## Rework

Task must be in `needs_human` with its worktree present. Write the user's notes to `TASK_DIR/human-notes.md` (append, with a date heading). Then run one more round of step 3 with `round` = current round + 1 (one round, regardless of `max_rounds`), then step 4.

## Reject

`F set <id> stage=rejected`, `F log <id> "rejected: <reason>"`, `F backlog-mark <id> -` (items that depend on it stay blocked: suggest `/factory plan update`). `git -C REPO worktree remove WORKTREE` (without `--force`; if it refuses, tell the user what is uncommitted). Keep the branch, and tell the user `git branch -D factory/<id>` deletes it.

## Status

`F list`. For each task in `needs_human`, add the first reason from its decision.md. Mention `/factory dashboard`.

## Dashboard

Start `F dashboard` in the background (`--port <n>` if 8765 is taken) and give the user the URL it prints. It refreshes every 3 seconds and binds to 127.0.0.1 only.

## Parallel tasks

Each task has its own worktree and branch, so several `/factory` runs can go at once in separate Claude Code sessions on the same repo. Within one session run tasks one after another.
