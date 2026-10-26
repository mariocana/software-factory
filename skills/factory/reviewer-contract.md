# Reviewer contract

Shared by every `reviewer-*` agent of the software factory.

## Inputs (given by the orchestrator)

- `KIND`: your review kind (`code`, `security`, `ux`, `ui`)
- `REPO`: main checkout, `WORKTREE`: the task's worktree, `BRANCH`, `BASE` (the ref the branch started from)
- `TASK_DIR`: task folder, `POLICY`: project factory policy, `ROUND`: current round number

## Read

1. `TASK_DIR/spec.md`: what was asked, acceptance criteria, out of scope.
2. `TASK_DIR/build.md`: the latest round section, what the builder claims.
3. On round 2+: your own `TASK_DIR/review-<KIND>-r<ROUND-1>.md`. Check each earlier blocking finding is fixed, or that the builder's rejection in build.md is right.
4. The diff: `git -C <WORKTREE> diff <BASE>...HEAD` (and `--stat` first). Read the surrounding code of changed files too, not only the hunks.

## Allowed

Read, Grep, Glob, `git -C <WORKTREE> log/diff/show/blame`, and running the project's own test, lint or build commands in `WORKTREE`. **Not allowed:** editing or creating any file other than your review file, committing, installing new packages, network calls other than to a local dev server, touching `REPO`.

## Output

Write exactly one file, `TASK_DIR/review-<KIND>-r<ROUND>.md`:

```markdown
---
verdict: pass | changes
blocking: <number of blocking findings>
minor: <number of minor findings>
---
## Summary
<one or two lines>

## Findings
- [blocking] `path/file.ext:42` — what is wrong and what happens because of it — suggested fix
- [minor] `path/file.ext:10` — … — …

## Checked
- <what you checked and found fine, one line each>
```

`verdict` is `changes` if and only if `blocking` > 0. Every finding names a file and line in the diff or in code the diff affects. No finding without evidence: if you are unsure, read more code or drop it. Do not repeat what another reviewer kind covers (code: correctness and tests; security: vulnerabilities; ux: flow and accessibility; ui: visual design).

Reply to the orchestrator with one line: `<KIND>: <verdict>, <blocking> blocking, <minor> minor`.
