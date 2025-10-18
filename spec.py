#!/usr/bin/env python3
# spec.py - minimal spec scaffold & design registrar (with planning/execution guides)

import argparse, os, sys

# ---------- File templates ----------

INDEX_YML = """# Task ledger for agent + human
# 'designs' lists the design docs agents should read.
# 'tasks' is a flat list; agents will add entries and update statuses.
designs: []
tasks: []
"""

SETTINGS_YML = """# Minimal execution settings for agents
settings:
  auto_execute_after_planning: false   # if true, start implementation immediately after planning
  next_task_loop: manual               # "manual" or "auto"
  require_owner_for_doing: false       # if true, must set 'owner' before switching a task to 'doing'
  branch_naming: "feat/{id}-{slug}"    # hint/pattern for branch names
  enforce_branching: true              # if true, agent must refuse to commit on protected branches
  protected_branches: ["main", "master", "develop"]
  commit_message_template: "{id}: {title}"
  pr_title_template: "{id}: {title}"
"""

TEMPLATE_TASK_MD = """---
id: TM-XXX
title: Short action name
status: todo           # todo | doing | done | blocked
labels: []             # e.g., db, backend, api, ui, sse, auditing, docs
deps: []               # other task IDs
owner: ""              # optional, set when taking the task
inputs:
  - <DESIGN_DOC_PATH>  # pick one or more paths from spec/index.yml:designs
outputs: []
timebox: "2h"
---

## Summary
One or two sentences of what must be built, referencing the design doc.

## Acceptance Criteria (measurable)
- [ ] Explicit, testable check #1
- [ ] Explicit, testable check #2
- [ ] Explicit, testable check #3

## Steps
- [ ] Read inputs
- [ ] Implement …
- [ ] Add/adjust tests
- [ ] Run verification
- [ ] Update spec/index.yml (status, deps if changed)

## Verification
Exact commands or API calls to prove success.

## Notes
Reuse existing services; do not invent endpoints unless the design says so.
"""

AGENT_HOWTO = """\
# How to Instruct the Agent (copy/paste friendly)

Treat this section as binding, highest-priority instructions. Do not deviate.

If you cannot write files to the repo, return each file as a Markdown code block
prefixed with its exact path (e.g., `spec/tasks/TM-001.md`) so the user can save it.

Before writing tasks, echo: `PLAN: creating N tasks from <design(s)>`. If designs list is empty, STOP.

0) If the design list below is empty, STOP and request: `spec add <path/to/design.md>`.

1) Plan tasks dynamically based on the design’s scope. Aim for ~2h per task by default (1–3h acceptable).
   If the feature is small, fewer tasks with ~1h each is fine; if large, create more tasks or phased batches.
   Before creating files, output: `PLAN: <N> tasks, ~<T>h each, reason: <short rationale>`.
   - Default target: ~2h per task (1–3h acceptable).
   - Default batch size: 6–15 tasks per planning pass; if more are needed, use phases.

2) For each task:
   - Use `spec/template.task.md` (keep the YAML header minimal).
   - Save as `spec/tasks/<ID>.md` where IDs are TM-### (TM-001, TM-002…).
   - Update `spec/index.yml` with: id, title, labels, status, deps, file (exact path).
   - Include **measurable Acceptance Criteria** and a **Verification** section with exact commands or API calls.

3) Status lifecycle: `todo | doing | done | blocked`. Set `owner` if used.
   - Mark `done` only after Verification passes.

4) Dependencies:
   - `deps` may reference only tasks present in `spec/index.yml`.
   - Avoid cycles. If a missing prerequisite is needed, set `status: blocked` and explain in the task body.

5) Boundaries:
   - Respect `spec/policies.md`.
   - Reuse existing services/patterns. Do **not** invent new endpoints unless the design explicitly says so.
   - Prefer small vertical slices (DB → Service → API) where applicable.
   - Do **not** edit helper files (`spec/template.task.md`, `spec/prompts.md`, `spec/policies.md`) unless asked.

6) After planning, check `spec/settings.yml`:
   - If `auto_execute_after_planning: true`, continue with `spec/EXECUTE.md`.
   - If false, STOP and wait for manual start.

Deterministic conventions:
- Task file path MUST equal `spec/tasks/<ID>.md`.
- IDs are uppercase TM-###.
- `deps` reference only known tasks; if blocked by missing tasks, set `status: blocked` and explain why in the task body.
"""

PROMPTS_MD_TEMPLATE = """# Planning Prompt (for Agent)

Read these design document(s):
{design_bullets}

{agent_howto}

## Output required
- Create or update `spec/index.yml` (flat list of tasks).
- Write task files to `spec/tasks/` using `spec/template.task.md`.
- Keep tasks small, vertical slices (DB → Service → API) where applicable.
"""

POLICIES_MD = """# Minimal Policies (agents must obey)

## Scope & Authority
- This file is **binding** for all work. Do not deviate.
- When in doubt, ask or propose a small change in a separate task.

## Security & Privacy
- Principle of least privilege. Touch only files/services required by the task.
- Never commit secrets or tokens. Use env vars or the repo’s secret manager.
- Do not log PII/credentials. Redact sensitive fields in logs/errors.
- Private data must remain private; follow the design’s access rules exactly.

## Dependencies & Tools
- **No new frameworks/libs** without explicit approval. Prefer stdlib/existing deps.
- Pin versions and update lockfiles. Avoid global/system installs.
- Do not modify CI/CD config unless the task explicitly says so.

## Code & Git Hygiene
- Follow `spec/settings.yml` for branching (branch pattern, protected branches).
- Small, atomic commits. Include task ID in commit messages/PR titles.
- Don’t push directly to protected branches.

## API, Schemas & Migrations
- Backward compatible by default. Additive changes first; breaking changes require explicit approval.
- Database/schema migrations must be reversible and **idempotent**.
- Separate data migrations from schema migrations where possible.

## Testing & Verification
- Every task must include runnable verification steps (commands or API calls).
- Add/update tests at the appropriate level (unit/integration/e2e) to cover acceptance criteria.
- Tests must pass locally (or in the provided runner) before marking `done`.

## Observability & Ops
- Log at appropriate levels; no secrets/PII in logs.
- Prefer metric/trace hooks only if the project already uses them.
- Use feature flags or configuration, **not** hard-coded constants, for toggles.

## Performance & Reliability
- Respect timeouts and retries; avoid infinite waits.
- Keep operations idempotent where applicable (especially APIs/tasks).
- Mind basic perf budgets (avoid O(n^2) on large inputs; stream for big files).

## UX / Accessibility / i18n (if user-facing)
- Don’t regress accessibility (labels, contrast, keyboard navigation).
- Keep copy externalized if the project already uses i18n.

## Licensing & Attribution
- Use compatible licenses only; preserve existing NOTICE/LICENSE files.
- Attribute third-party code as required by its license.

## External Calls & AI Use
- No new outbound network calls, third-party APIs, or AI services without approval.
- If an LLM is used inside the project, **never** send secrets/PII and follow its safety constraints.

## Documentation
- Update any touched README/config docs when behavior changes.
- Record notable decisions/limitations in the task’s Notes section.

## Project-Specific Additions
- (Add bullets here as the repo grows; keep this file under one page.)
"""

START_MD = """# START (Agent Kickoff)

Use **spec/prompts.md** as the authoritative, binding instructions. Do not deviate.

Steps:
1) Read the design list in `spec/prompts.md`.
2) Output first: `PLAN: <N> tasks, ~<T>h each, reason: <short rationale>`.
3) Generate tasks under `spec/tasks/` using `spec/template.task.md` and update `spec/index.yml`.
4) After planning, check `spec/settings.yml`:
   - If `auto_execute_after_planning: true`, continue with `spec/EXECUTE.md`.
   - Otherwise, STOP and wait for manual start.

If you cannot write files, return each file as a Markdown code block prefixed with its exact path.
"""

EXECUTE_MD = """# EXECUTE (Task Implementation Instructions for Agent)

Follow these steps exactly.

0) Read `spec/settings.yml`.
   - If `settings.require_owner_for_doing: true`, set `owner` in the task file before switching to `doing`.
   - **Branching is mandatory if `settings.enforce_branching: true`.**
   - Branch pattern hint: `settings.branch_naming` (e.g., feat/{id}-{slug}).
   - Protected branches: `settings.protected_branches` (NEVER commit here).

1) Select a task:
   - Read `spec/index.yml` and pick the first `status: todo` whose `deps` are all `done`.

2) Take the task:
   - Open `spec/tasks/<ID>.md`.
   - If required by settings, set `owner: <name>`.
   - Change `status: doing`.

3) **Create a working branch (REQUIRED when enforce_branching = true):**
   - Compute `<slug>` from the task title (lowercase, hyphenated, alnum+hyphen).
   - Branch name = `settings.branch_naming` with `{id}` and `{slug}` replaced.
   - Detect current branch. If it is in `protected_branches`, STOP and output the shell command to create/switch:
     - `git checkout -b <branch>` (if new) OR `git switch <branch>` (if exists).
   - If you cannot run shell commands, **return the exact commands** to run as a fenced code block.

4) Implement per the task’s Summary + Acceptance Criteria.
   - Reuse existing services/patterns. Do not invent endpoints beyond the design.
   - Keep changes scoped to the task.

5) Tests & Verification:
   - Add/adjust tests as required.
   - Run the **Verification** steps from the task and ensure they pass.

6) Commit:
   - Commit message = `settings.commit_message_template` with `{id}` and `{title}` replaced.
   - If on a protected branch, STOP and output the correct branch/switch commands instead.

7) Complete:
   - Check off Acceptance Criteria in the task file.
   - Flip `status: done` when verification passes.
   - Update `spec/index.yml` entry for `<ID>` with the final `status` (and `owner` if used).

8) Loop behavior (from settings):
   - If `settings.next_task_loop: auto`, repeat from step 1.
   - If `manual`, STOP and wait.

**If you cannot write files or run shell:**
Return each changed file and each required shell command as Markdown code blocks with exact repo paths/commands.
"""

# ---------- Helpers ----------


def relpath_from_repo(path):
    return os.path.normpath(path).replace("\\", "/")


def safe_write(path, content, force=False):
    if os.path.exists(path) and not force:
        return False
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)
    return True


def read_text(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def write_text(path, txt):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(txt)


def ensure_spec_dirs():
    os.makedirs("spec/tasks", exist_ok=True)


def init_scaffold(force=False):
    """Create the minimal scaffold. Overwrite helper files only if force=True."""
    ensure_spec_dirs()
    created = []
    if safe_write("spec/index.yml", INDEX_YML, force):
        created.append("spec/index.yml")
    if safe_write("spec/settings.yml", SETTINGS_YML, force):
        created.append("spec/settings.yml")
    if safe_write("spec/template.task.md", TEMPLATE_TASK_MD, force):
        created.append("spec/template.task.md")
    if safe_write("spec/prompts.md", build_prompts_md([]), force):
        created.append("spec/prompts.md")
    if safe_write("spec/policies.md", POLICIES_MD, force):
        created.append("spec/policies.md")
    if safe_write("spec/START.md", START_MD, force):
        created.append("spec/START.md")
    if safe_write("spec/EXECUTE.md", EXECUTE_MD, force):
        created.append("spec/EXECUTE.md")
    return created


def load_designs_from_index():
    if not os.path.exists("spec/index.yml"):
        return []
    lines = read_text("spec/index.yml").splitlines()
    designs, in_designs = [], False
    for line in lines:
        s = line.strip()
        if s.startswith("designs:"):
            in_designs = True
            continue
        if in_designs:
            if s.startswith("- "):
                designs.append(s[2:].strip())
            elif s == "" or s.startswith("#"):
                continue
            else:
                break
    return designs


def save_designs_to_index(designs):
    existing = (
        read_text("spec/index.yml") if os.path.exists("spec/index.yml") else INDEX_YML
    )
    lines = existing.splitlines()
    out, i, wrote = [], 0, False
    while i < len(lines):
        s = lines[i].strip()
        if s.startswith("designs:"):
            out.append("designs:")
            for d in designs:
                out.append(f"- {d}")
            wrote = True
            i += 1
            while i < len(lines) and (
                lines[i].strip().startswith("- ")
                or lines[i].strip() == ""
                or lines[i].strip().startswith("#")
            ):
                i += 1
            continue
        out.append(lines[i])
        i += 1
    if not wrote:
        out.insert(1, "designs:")
        for d in designs:
            out.insert(2, f"- {d}")
    write_text(
        "spec/index.yml", "\n".join(out) + ("\n" if not out[-1].endswith("\n") else "")
    )


def build_prompts_md(designs):
    bullets = "\n".join(f"- {d}" for d in designs) if designs else "- (none yet)"
    return PROMPTS_MD_TEMPLATE.format(design_bullets=bullets, agent_howto=AGENT_HOWTO)


def update_prompts_with_designs(designs):
    write_text("spec/prompts.md", build_prompts_md(designs))


def load_settings():
    if not os.path.exists("spec/settings.yml"):
        return {}
    lines = read_text("spec/settings.yml").splitlines()
    out, in_block = {}, False
    for line in lines:
        s = line.strip()
        if s.startswith("settings:"):
            in_block = True
            continue
        if not in_block or s == "" or s.startswith("#"):
            continue
        # simple key: value parser
        if ":" in s:
            key, val = s.split(":", 1)
            key = key.strip()
            val = val.strip()
            if (
                key == "auto_execute_after_planning"
                or key == "require_owner_for_doing"
                or key == "enforce_branching"
            ):
                out[key] = val.lower().startswith("true")
            elif key == "next_task_loop":
                out[key] = val
            elif (
                key == "branch_naming"
                or key == "commit_message_template"
                or key == "pr_title_template"
            ):
                out[key] = val.strip('"')
            elif key == "protected_branches":
                # parse ["a","b"] or [a, b] or comma string
                val = val.strip()
                if val.startswith("[") and val.endswith("]"):
                    inner = val[1:-1].strip()
                    parts = [
                        p.strip().strip('"').strip("'")
                        for p in inner.split(",")
                        if p.strip()
                    ]
                    out[key] = [p for p in parts if p]
                else:
                    parts = [p.strip() for p in val.split(",")]
                    out[key] = [p for p in parts if p]
    return out


def save_settings(values):
    current = {
        "auto_execute_after_planning": False,
        "next_task_loop": "manual",
        "require_owner_for_doing": False,
        "branch_naming": "feat/{id}-{slug}",
        "enforce_branching": True,
        "protected_branches": ["main", "master", "develop"],
        "commit_message_template": "{id}: {title}",
        "pr_title_template": "{id}: {title}",
    }
    current.update(values or {})
    pb = ", ".join(f'"{b}"' for b in current["protected_branches"])
    body = f"""# Minimal execution settings for agents
settings:
  auto_execute_after_planning: {"true" if current["auto_execute_after_planning"] else "false"}
  next_task_loop: {current["next_task_loop"]}
  require_owner_for_doing: {"true" if current["require_owner_for_doing"] else "false"}
  branch_naming: "{current["branch_naming"]}"
  enforce_branching: {"true" if current["enforce_branching"] else "false"}
  protected_branches: [{pb}]
  commit_message_template: "{current["commit_message_template"]}"
  pr_title_template: "{current["pr_title_template"]}"
"""
    write_text("spec/settings.yml", body)


# ---------- Commands ----------


def cmd_init(args):
    created = init_scaffold(force=args.force)
    if created:
        print("created:", ", ".join(created))
    else:
        print(
            "nothing to do (already initialized). use --force to overwrite helper files."
        )


def cmd_add(args):
    if not os.path.isfile(args.design):
        print(f"error: design file not found: {args.design}", file=sys.stderr)
        sys.exit(2)
    ensure_spec_dirs()
    if not os.path.exists("spec/index.yml"):
        init_scaffold(force=False)

    design_rel = relpath_from_repo(args.design)
    designs = load_designs_from_index()
    if design_rel not in designs:
        designs.append(design_rel)
        save_designs_to_index(designs)
        update_prompts_with_designs(designs)
        print(f"registered design: {design_rel}")
    else:
        update_prompts_with_designs(designs)
        print(f"design already registered: {design_rel}")


def cmd_prompt(_args):
    """Print the current agent planning prompt to stdout."""
    designs = load_designs_from_index()
    sys.stdout.write(build_prompts_md(designs))


def cmd_guide(_args):
    guide = f"""\
Minimal Spec System — User Guide

1) Initialize once per repo:
   spec.py init

2) Register a design doc (append to prompts; add to index.yml):
   spec.py add docs/design/Trusted\\ Managers\\ Mechanism.md

3) Kick off an agent:
   - Planning: open spec/START.md (or print prompt with `spec.py prompt`)
   - Implementation: open spec/EXECUTE.md

4) Track progress:
   - spec/index.yml  (statuses: todo|doing|done|blocked)
   - spec/tasks/TM-xxx.md (task detail)

Settings (spec/settings.yml):
- Auto/manual: auto_execute_after_planning, next_task_loop
- Multi-agent safety: require_owner_for_doing
- Branch protection: enforce_branching, protected_branches, branch_naming
- Templates: commit_message_template, pr_title_template
"""
    sys.stdout.write(guide)


def cmd_config(args):
    """Toggle settings without editing YAML."""
    ensure_spec_dirs()
    if not os.path.exists("spec/settings.yml"):
        init_scaffold(force=False)
    vals = load_settings()
    if args.auto is not None:
        vals["auto_execute_after_planning"] = args.auto == "on"
    if args.loop is not None:
        vals["next_task_loop"] = args.loop
    if args.require_owner is not None:
        vals["require_owner_for_doing"] = args.require_owner == "on"
    if args.branch:
        vals["branch_naming"] = args.branch
    if args.enforce is not None:
        vals["enforce_branching"] = args.enforce == "on"
    if args.protected:
        # comma or space separated list
        raw = args.protected.replace(",", " ").split()
        vals["protected_branches"] = [p.strip() for p in raw if p.strip()]
    if args.commit_tmpl:
        vals["commit_message_template"] = args.commit_tmpl
    if args.pr_title_tmpl:
        vals["pr_title_template"] = args.pr_title_tmpl
    save_settings(vals)
    print("updated spec/settings.yml")


# ---------- CLI ----------


def main():
    epilog = """
Examples:
  # 1) Create minimal scaffold once (spec/ folder, helper files)
  spec.py init

  # 2) Register a design doc (idempotent)
  spec.py add docs/design/Trusted\\ Managers\\ Mechanism.md

  # 3) Print the current agent planning prompt (copy/paste into agent)
  spec.py prompt

  # 4) Show a concise user guide
  spec.py guide

  # 5) Configure execution & protection
  spec.py config --auto on --loop auto --require-owner on \\
                 --enforce on --protected "main, master, develop" \\
                 --branch "feat/{id}-{slug}" \\
                 --commit-tmpl "{id}: {title}" --pr-title-tmpl "{id}: {title}"
"""
    parser = argparse.ArgumentParser(
        description="Minimal spec system: scaffold once, register design docs, and guide agents for planning/execution.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=epilog,
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_init = sub.add_parser(
        "init", help="create the minimal spec scaffold (idempotent)"
    )
    p_init.add_argument(
        "--force",
        action="store_true",
        help="overwrite helper files (index.yml, settings.yml, template.task.md, prompts.md, policies.md, START.md, EXECUTE.md). never touches spec/tasks/",
    )
    p_init.set_defaults(func=cmd_init)

    p_add = sub.add_parser(
        "add",
        help="register a design doc (append to prompts; add to index.yml designs)",
    )
    p_add.add_argument(
        "design", help="path to the feature design markdown file (prose)"
    )
    p_add.set_defaults(func=cmd_add)

    p_prompt = sub.add_parser(
        "prompt", help="print the current agent planning prompt to stdout"
    )
    p_prompt.set_defaults(func=cmd_prompt)

    p_guide = sub.add_parser(
        "guide", help="print a short user guide (human-facing instructions)"
    )
    p_guide.set_defaults(func=cmd_guide)

    p_config = sub.add_parser(
        "config", help="toggle execution/protection settings (writes spec/settings.yml)"
    )
    p_config.add_argument(
        "--auto", choices=["on", "off"], help="auto start execution after planning"
    )
    p_config.add_argument(
        "--loop",
        choices=["auto", "manual"],
        help="auto pick next task after finishing one",
    )
    p_config.add_argument(
        "--require-owner",
        choices=["on", "off"],
        help="require owner before switching a task to 'doing'",
    )
    p_config.add_argument(
        "--branch", help="branch naming pattern, e.g. 'feat/{id}-{slug}'"
    )
    p_config.add_argument(
        "--enforce",
        choices=["on", "off"],
        help="enforce branching; refuse commits on protected branches",
    )
    p_config.add_argument(
        "--protected",
        help="comma or space separated protected branches, e.g. 'main, master, develop'",
    )
    p_config.add_argument(
        "--commit-tmpl",
        dest="commit_tmpl",
        help="commit message template, e.g. '{id}: {title}'",
    )
    p_config.add_argument(
        "--pr-title-tmpl",
        dest="pr_title_tmpl",
        help="PR title template, e.g. '{id}: {title}'",
    )
    p_config.set_defaults(func=cmd_config)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
