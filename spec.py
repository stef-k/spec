#!/usr/bin/env python3
# spec.py - minimal spec scaffold & design registrar (with built-in agent guide)

import argparse, os, sys

# ---------- File templates ----------

INDEX_YML = """# Task ledger for agent + human
# 'designs' lists the design docs agents should read.
# 'tasks' is a flat list; agents will add entries and update statuses.
designs: []
tasks: []
"""

TEMPLATE_TASK_MD = """---
id: TM-XXX
title: Short action name
status: todo           # todo | doing | done | blocked
labels: []             # e.g., db, backend, api, ui, sse, auditing, docs
deps: []               # other task IDs
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

1) Read the design doc(s) listed below.
2) Break the feature into 8–15 tasks (~2h each).
3) For each task:
   - Use `spec/template.task.md` (keep the YAML header minimal).
   - Save as `spec/tasks/<ID>.md` (IDs like TM-001, TM-002…).
   - Add/Update an entry in `spec/index.yml` with: id, title, labels, status, deps, file.
   - Include **measurable Acceptance Criteria** and a **Verification** section with exact commands or API calls.
4) Status lifecycle: `todo | doing | done | blocked`. Set `owner` if used.
5) Respect policies in `spec/policies.md`. Reuse existing services/patterns. Do NOT invent new endpoints unless the design says so.
6) Each task must be independently testable. Mark `done` only after verification passes.

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
- Create or update: `spec/index.yml` (flat list of tasks).
- Write task files to: `spec/tasks/` using `spec/template.task.md`.
- Keep tasks small, vertical slices (DB → Service → API) where applicable.
"""

POLICIES_MD = """# Minimal Policies (agents must obey)

- Security/Privacy: Only authorized users may access private location/manager data.
- Reuse: Use existing auth, SSE, logging/auditing, and controller patterns.
- No New Frameworks: Stick to the project stack; do not introduce new libs without explicit approval.
- API Scope: Keep endpoints private/internal exactly as in the design document(s).
- Tests/Verification: Every task must include runnable verification steps (commands, queries, or API calls).
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
    if safe_write("spec/index.yml", INDEX_YML, force): created.append("spec/index.yml")
    if safe_write("spec/template.task.md", TEMPLATE_TASK_MD, force): created.append("spec/template.task.md")
    if safe_write("spec/prompts.md", build_prompts_md([]), force): created.append("spec/prompts.md")
    if safe_write("spec/policies.md", POLICIES_MD, force): created.append("spec/policies.md")
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
    existing = read_text("spec/index.yml") if os.path.exists("spec/index.yml") else INDEX_YML
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
            while i < len(lines) and (lines[i].strip().startswith("- ") or lines[i].strip() == "" or lines[i].strip().startswith("#")):
                i += 1
            continue
        out.append(lines[i]); i += 1
    if not wrote:
        out.insert(1, "designs:")
        for d in designs:
            out.insert(2, f"- {d}")
    write_text("spec/index.yml", "\n".join(out) + ("\n" if not out[-1].endswith("\n") else ""))

def build_prompts_md(designs):
    bullets = "\n".join(f"- {d}" for d in designs) if designs else "- (none yet)"
    return PROMPTS_MD_TEMPLATE.format(design_bullets=bullets, agent_howto=AGENT_HOWTO)

def update_prompts_with_designs(designs):
    write_text("spec/prompts.md", build_prompts_md(designs))

# ---------- Commands ----------

def cmd_init(args):
    created = init_scaffold(force=args.force)
    if created:
        print("created:", ", ".join(created))
    else:
        print("nothing to do (already initialized). use --force to overwrite helper files.")

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
    """Print a concise user guide (human-facing instructions)."""
    guide = f"""\
Minimal Spec System — User Guide

1) Initialize once per repo:
   spec.py init

2) Register a design doc (append to prompts; add to index.yml):
   spec.py add docs/design/Trusted\\ Managers\\ Mechanism.md

3) Hand this prompt to your agent (copies the current planning prompt):
   spec.py prompt

4) The agent will:
   - Read the design doc(s) listed in spec/prompts.md
   - Create tasks in spec/tasks/ using spec/template.task.md
   - Update spec/index.yml with id/title/labels/status/deps/file
   - Keep task sizes ~2h with measurable Acceptance + Verification

5) You track progress by opening:
   - spec/index.yml  (statuses: todo|doing|done|blocked)
   - spec/tasks/TM-xxx.md (details of a slice)

Notes:
- `init` never touches spec/tasks/.
- `add` is idempotent; it just registers more design docs.
- Policies live in spec/policies.md (keep it one page).
"""
    sys.stdout.write(guide)

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

  # 5) If you really want to regenerate helper files (won't touch spec/tasks/)
  spec.py init --force
"""
    parser = argparse.ArgumentParser(
        description="Minimal spec system: scaffold once, register design docs, print agent prompt/guide.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=epilog
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_init = sub.add_parser("init", help="create the minimal spec scaffold (idempotent)")
    p_init.add_argument("--force", action="store_true",
                        help="overwrite helper files (index.yml, template.task.md, prompts.md, policies.md). never touches spec/tasks/")
    p_init.set_defaults(func=cmd_init)

    p_add = sub.add_parser("add", help="register a design doc (append to prompts; add to index.yml designs)")
    p_add.add_argument("design", help="path to the feature design markdown file (prose)")
    p_add.set_defaults(func=cmd_add)

    p_prompt = sub.add_parser("prompt", help="print the current agent planning prompt to stdout")
    p_prompt.set_defaults(func=cmd_prompt)

    p_guide = sub.add_parser("guide", help="print a short user guide (human-facing instructions)")
    p_guide.set_defaults(func=cmd_guide)

    args = parser.parse_args()
    args.func(args)

if __name__ == "__main__":
    main()
