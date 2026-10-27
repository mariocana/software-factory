# software-factory

A small agent software factory for Claude Code, installable in any repository as a plugin.
You describe a feature; subagents write the spec, build it in a git worktree, review it in parallel
and decide whether it merges on its own or waits for you.

```
brief ─► analyst (opus) ─► docs/product.md + backlog F01..Fn with deps ─► you approve

request ─► spec-writer ─► builder ─► reviewers (parallel) ─► approver ─► merge | needs_human
  (opus)      (opus)        ▲   code · security · ux · ui        (opus)
                            └──── changes, max N rounds ◄──┘
```

The orchestrator is your Claude Code session running the `/factory` skill. State is Markdown
under `.factory/` in your repo, kept out of git through `.git/info/exclude`, so it never makes the
working tree dirty. A local dashboard shows every task.

New here? Read [docs/getting-started.md](docs/getting-started.md), a walk-through from an empty
folder to a merged feature. Changes between versions are in [CHANGELOG.md](CHANGELOG.md).

## Install

```bash
claude plugin marketplace add /Users/mario/Documents/Repo/software-factory
claude plugin install software-factory@software-factory
```

(or push this repo to GitHub and use `owner/software-factory` as the marketplace). Restart
Claude Code so the agents load.

## Use, inside any project

| Command | What it does |
|---|---|
| `/factory init` | creates `.factory/`, writes `.claude/factory.md` (policy) filled from the project; review and commit it |
| `/factory plan <brief>` | analyst asks the open questions, writes `docs/product.md` and a backlog of small vertical slices with dependencies; you approve it |
| `/factory plan update <feedback>` | re-plan open items; taken and done items never change |
| `/factory add a copy button to code blocks` | runs a feature through the whole pipeline |
| `/factory backlog <item>` / `/factory next` | queue an item by hand (`M` id); take the first open item whose deps are done |
| `/factory run [n]` | builds the backlog on its own: takes the next ready item until nothing is ready (or `n` tasks), skipping past escalated tasks to independent items, then reports what merged and what waits for you |
| `/factory resume <id>` | continue a task whose session stopped halfway, from the stage it reached |
| `/factory status` | list tasks and why any wait for you |
| `/factory approve <id>` | merge a task the approver escalated |
| `/factory rework <id> <notes>` | one more build/review round with your notes |
| `/factory reject <id>` | stop a task, remove its worktree, keep its branch |
| `/factory dashboard` | live board at http://127.0.0.1:8765 |

Inside a project the skill may show as `/software-factory:factory`.
Several tasks can run at once from separate Claude Code sessions: each has its own worktree
(`.factory/worktrees/<id>`) and branch (`factory/<id>`).

For a simple project: `/factory plan <brief>`, approve the backlog, then `/factory run`. F01 (the
skeleton) always waits for your approval, and every item depends on it, so the first `run` stops
there: `/factory approve <F01 task>`, then `/factory run` again. Run Claude Code in auto mode or
accept-edits mode so permission prompts do not stop the loop.

## Per-project policy: `.claude/factory.md`

Frontmatter settings: `base_branch`, `merge_mode` (`local` merge into the base branch, or `pr`
via `gh`), `auto_merge`, `max_rounds`, `max_auto_merge_lines`, `ui_review` (`auto|always|never`),
and the `setup/test/lint/run` commands. The body lists what always goes to a human (auth, billing,
migrations, new dependencies...) and project notes. Every agent reads it, together with the
project's `CLAUDE.md`.

## Optional skills

List them in the policy (`skills: impeccable, ponytail`) after installing them in the project:

```bash
claude plugin marketplace add pbakaus/impeccable --scope project
claude plugin install impeccable@impeccable --scope project
claude plugin marketplace add DietrichGebert/ponytail --scope project
claude plugin install ponytail@ponytail --scope project
```

| Skill | Used by | How |
|---|---|---|
| [Impeccable](https://github.com/pbakaus/impeccable) | analyst, spec-writer, builder, reviewer-ui, reviewer-ux | PRODUCT.md and DESIGN.md as design context, craft and harden rules while building, its deterministic detector (`detect --json`) and audit/critique checks in review |
| [Ponytail](https://github.com/DietrichGebert/ponytail) | builder, reviewer-code | smallest complete change while building; ponytail-review's checks in code review |

`scripts/factory.py skills` resolves each listed skill to its installed folder (`claude plugin list
--json`) and the orchestrator passes those paths to every agent. `/factory init` also scopes
ponytail's subagent hook to the builder and code reviewer with `PONYTAIL_SUBAGENT_MATCHER`.
Both plugins add their own hooks to every session in the project: Impeccable checks UI edits,
Ponytail sets its mode and shows its band.

## Files

```
.claude-plugin/plugin.json, marketplace.json
agents/       analyst, spec-writer, builder, reviewer-{code,security,ux,ui}, approver
skills/factory/SKILL.md              orchestrator
skills/factory/reviewer-contract.md  shared reviewer inputs and output format
skills/factory/templates/factory.md  policy template
scripts/factory.py                   state (tasks, backlog) and dashboard, stdlib only
docs/getting-started.md              walk-through
CHANGELOG.md
```

## Design choices

- **Analyst and spec-writer are separate.** The analyst decides what to build and in which order
  (product level, `docs/product.md`); the spec-writer turns one item into files and tests. F01 is
  the project skeleton and always goes to a human.
- **The orchestrator decides the flow, agents do one job each.** Subagents cannot start other
  subagents, so the loop lives in the skill.
- **State changes go through `scripts/factory.py`**, not free-form edits, so the dashboard always
  parses it.
- **Reviewers are read-only** and must cite `file:line`; only `blocking` findings trigger a rework.
  UX/UI reviewers run only when the spec says the change touches the UI.
- **The approver is told to merge** green, reviewed, in-policy changes. Escalation needs a listed
  reason, so the human queue stays short.
- **Merge never touches your uncommitted work**: no stash, no reset, no branch switch. If git
  cannot merge cleanly the task waits for you.
- **Cost:** every task runs 4-7 subagents. Opus is used for spec, builder, security and approver;
  Sonnet for code/UX/UI review. Change `model:` in `agents/*.md` to trade cost for quality.
