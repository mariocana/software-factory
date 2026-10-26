---
base_branch: main
merge_mode: local            # local: merge into base_branch in the main checkout | pr: push and open a GitHub PR (needs gh)
auto_merge: true             # false: every task stops at needs_human
max_rounds: 2                # build+review rounds before the approver decides
max_auto_merge_lines: 400    # bigger diffs always go to a human
skills:                      # optional: impeccable, ponytail (install them in the project first)
ui_review: auto              # auto: only when spec says touches_ui | always | never
setup_command:               # e.g. npm ci  (run by the builder in a fresh worktree)
test_command:                # e.g. npm test
lint_command:                # e.g. npm run lint
run_command:                 # e.g. npm run dev -- --port 4173  (optional, for UX/UI reviewers)
---
# Software factory policy

Read by every factory agent. Commit this file: it is how the factory knows this project.

## Always escalate to a human
- Authentication, sessions, roles, permissions
- Payments, billing, subscriptions, paywalls
- Database migrations or schema changes
- Deleting or rewriting user data
- New runtime dependencies
- CI/CD, deployment, infrastructure, environment config
- Anything handling secrets or credentials

## Optional skills
- **impeccable** (pbakaus/impeccable): analyst writes PRODUCT.md, spec-writer adds a UX section, builder follows its craft rules and runs its detector, UI/UX reviewers run the detector and its audit/critique checks.
- **ponytail** (DietrichGebert/ponytail): builder writes the smallest complete change; reviewer-code adds ponytail-review's checks.

## Project notes
- <conventions the agents must follow that are not in CLAUDE.md>
