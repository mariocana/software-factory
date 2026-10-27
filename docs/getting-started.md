# Getting started

From an empty folder to a merged feature. Commands run inside Claude Code in your project, unless
they start with `claude plugin` or `git` (those go in a shell).

## 1. Install the plugin once

```bash
claude plugin marketplace add /Users/mario/Documents/Repo/software-factory
claude plugin install software-factory@software-factory
```

Restart Claude Code. To get a new version later: `claude plugin marketplace update software-factory`
then `claude plugin update software-factory@software-factory`, and restart.

## 2. Prepare the project

```bash
mkdir my-app && cd my-app && git init && git commit --allow-empty -m "init"
```

Optional, for a project with a UI: install Impeccable and Ponytail in the project (commands in the
README). Then, in Claude Code:

```
/factory init
```

It writes `.claude/factory.md`, the policy every agent reads. Check the base branch, merge mode
and commands; it lists what always goes to a human (auth, payments, migrations...).

## 3. Plan

```
/factory plan A booking site for a small yoga studio: class schedule, sign up for a class
with email, an admin page to add classes. Mobile first, Italian and English.
```

The analyst asks up to 8 questions, each with a recommended answer. Then it shows the scope, the
stack and a backlog like:

```
F01 Project skeleton                       ← always waits for you
F02 Class schedule page    (deps: F01)
F03 Sign up for a class    (deps: F02)
...
```

Approve, or answer "change" and say what. On approval it commits `docs/product.md` and the policy.

## 4. Build

One item at a time:

```
/factory next
```

Or the whole backlog, without being asked anything:

```
/factory run
```

F01 always stops for your approval and every item depends on it, so the first `run` stops there.
Look at the result, then:

```
/factory approve <F01 task id>
/factory run
```

Use auto mode or accept-edits mode so permission prompts do not stop the loop.

## 5. Follow along

```
/factory dashboard     → http://127.0.0.1:8765, refreshes every 3 seconds
/factory status        → tasks, and why any wait for you
```

Each task's files are in `.factory/tasks/<id>/`: `spec.md`, `build.md`, one review per reviewer
and round, `decision.md`.

## 6. When a task waits for you

The approver escalates when something needs a human: a sensitive area, high risk, a big diff,
a reviewer still asking for changes. Read `decision.md`, look at the branch
(`git diff main...factory/<id>`), then one of:

```
/factory approve <id>              merge it
/factory rework <id> <your notes>  one more build and review round
/factory reject <id>               drop it, keep the branch
```

A session that stopped halfway (closed, out of context) leaves its task in an active stage:
`/factory resume <id>` continues it.

## 7. Add features later

```
/factory plan update Add a waiting list when a class is full
```

The analyst adds new items and leaves done ones alone. For one small, independent change:
`/factory backlog <item>` to queue it, or `/factory <request>` to build it now.
