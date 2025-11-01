#!/usr/bin/env python3
# spec.py - minimal spec scaffold & design registrar (with planning/execution guides)

import argparse
import os
import re
import sys

# ---------- File templates ----------

INDEX_YML = """# Task ledger for agent + human
# 'designs' lists the design docs agents should read.
# 'tasks' is a flat list; agents will add entries and update statuses.
designs: []
tasks: []
"""

SETTINGS_YML = """# Minimal execution settings for agents
settings:
  auto_execute_after_planning: false                        # if true, start implementation immediately after planning
  next_task_loop: manual                                    # "manual" or "auto"
  require_owner_for_doing: false                            # if true, must set 'owner' before switching a task to 'doing'
  feature_branch_naming: "feat/{feature_slug}"              # parent branch per design/feature
  branch_naming: "feat/{feature_slug}/{id}-{slug}"          # hint/pattern for branch names
  feature_base_candidates: ["main", "master", "develop"]    # base for feature branch (first that exists)
  enforce_branching: true                                   # if true, agent must refuse to commit on protected branches
  protected_branches: ["main", "master", "develop"]
  commit_message_template: "{id}: {title}"
  pr_title_template: "{id}: {title}"
"""

TEMPLATE_TASK_MD = """---
id: T-XXX
title: Short action name
status: todo           # todo | doing | done | blocked
labels: []             # e.g., db, backend, api, ui, sse, auditing, docs
deps: []               # other task IDs
owner: ""              # optional, set when taking the task
inputs:
  - <DESIGN_DOC_PATH>  # pick one or more paths from spec/index.yml:designs
feature_branch: ""     # optional, e.g., feat/mobile-group-location-sharing
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
prefixed with its exact path (e.g., `spec/tasks/T-001.md`) so the user can save it.

Before writing tasks, echo: `PLAN: creating N tasks from <design(s)>`. If designs list is empty, STOP.

0) If the design list below is empty, STOP and request: `spec add <path/to/design.md>`.

1) Plan tasks dynamically based on the design’s scope. Aim for ~2h per task by default (1–3h acceptable).
   If the feature is small, fewer tasks with ~1h each is fine; if large, create more tasks or phased batches.
   Before creating files, output: `PLAN: <N> tasks, ~<T>h each, reason: <short rationale>`.
   - Default target: ~2h per task (1–3h acceptable).
   - Default batch size: 6–15 tasks per planning pass; if more are needed, use phases.

2) For each task:
   - Use `spec/template.task.md` (keep the YAML header minimal).
   - Save as `spec/tasks/<ID>.md` where IDs are T-### (T-001, T-002…).
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

6) **Feature Branch Workflow (MANDATORY)**:
   - Derive `{feature_slug}` from the chosen design doc filename (lowercased, non-alnum → `-`, strip extension).
     Example: `docs/design/Mobile Group Location Sharing.md` → `mobile-group-location-sharing`.
   - Compute the **feature parent branch** using settings: `feature_branch_naming` (default: `feat/{feature_slug}`).
   - Before implementing any task:
     1. Ensure a local default base (`main`, `master`, or `develop`) exists; choose the first that exists locally.
     2. Create/switch to the **feature branch** off that base.
   - For each task:
     - Compute `{slug}` from the task title (lowercase, hyphenated).
     - Create a **task branch** using `branch_naming` (default: `feat/{feature_slug}/{id}-{slug}`) **from the feature branch**.
   - **All PRs MUST target the feature branch**. Never target protected branches directly.
   - **Final merge from feature → master/main is the USER’s responsibility.** The agent must not propose or perform that merge.

7) After planning, check `spec/settings.yml`:
   - If `auto_execute_after_planning: true`, continue with `spec/EXECUTE.md`.
   - If false, STOP and wait for manual start.

Deterministic conventions:
- Task file path MUST equal `spec/tasks/<ID>.md`.
- IDs are uppercase T-###.
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
- Follow `spec/settings.yml` for branching (feature parent + per-task branches).
- All task branches MUST be created from the feature parent branch (not main/master/develop).
- Open PRs **only** against the feature parent branch. Never target protected branches directly.
- Final merge from feature → master/main/develop is **user-only** (agent must not attempt it).
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
- Use a feature parent branch per design (from base main/master/develop), then branch tasks from it.
- PR base must be the feature parent branch; never open PRs to protected branches.
- Final merge from feature → protected branches is **user-only**.
"""

PLAN_MD = """# PLAN  (Agent Task Planning)

Use **spec/prompts.md** as the authoritative, binding instructions. Do not deviate.

Policy Gate:
- Read `spec/policies.md` now and follow it for all decisions.

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

Policy Gate:
- Read `spec/policies.md` now and follow it for all code, tests, data handling, and commit/PR behavior.
- Feature parent branch hint: `settings.feature_branch_naming`
- Task branch hint: `settings.branch_naming`
- Candidate base for feature branch: `settings.feature_base_candidates`
- Protected branches: `settings.protected_branches` (NEVER commit here).
- Final feature → master/main merge is **user-only**.

0) Read `spec/settings.yml`.
   - If `settings.require_owner_for_doing: true`, set `owner` in the task file before switching to `doing`.
   - **Branching is mandatory if `settings.enforce_branching: true`.**
   - Feature parent branch pattern: `settings.feature_branch_naming` (e.g., feat/{feature_slug}).
   - Task branch pattern: `settings.branch_naming` (e.g., feat/{feature_slug}/{id}-{slug}).
   - Protected branches: `settings.protected_branches` (NEVER commit here).

1) Select a task:
   - Read `spec/index.yml` and pick the first `status: todo` whose `deps` are all `done`.

2) Take the task:
   - Open `spec/tasks/<ID>.md`.
   - If required by settings, set `owner: <name>`.
   - Change `status: doing`.

3) **Create/switch to the FEATURE parent branch (REQUIRED):**
   - Derive `{feature_slug}` from the first `inputs:` design file name (lowercase, non-alnum → '-', strip extension).
   - Compute `<feature_branch>` using `settings.feature_branch_naming`.
   - Determine `<base>` by choosing the first existing local branch from `settings.feature_base_candidates`.
   - If you cannot run shell, output the exact commands below; otherwise run:

```bash
# determine base locally (example sequence)
git show-ref --verify --quiet refs/heads/main   && base=main  || true
[ -z "$base" ] && git show-ref --verify --quiet refs/heads/master  && base=master || true
[ -z "$base" ] && git show-ref --verify --quiet refs/heads/develop && base=develop || true
[ -z "$base" ] && echo "No base branch found (main/master/develop). Create one first." && exit 1

git fetch origin
if git show-ref --verify --quiet "refs/heads/<feature_branch>"; then
  git switch "<feature_branch>"
  git merge --ff-only "$base" || true  # keep it fresh if desired
else
  git switch "$base"
  git pull --ff-only
  git switch -c "<feature_branch>"
fi
```

4) **Create/switch to the TASK working branch (from the feature branch):**
   - Compute `{slug}` from the task title (lowercase, hyphenated).
   - Branch name = `settings.branch_naming` with `{id}`, `{slug}`, `{feature_slug}` replaced.
   - If you cannot run shell commands, **return**:

```bash
git switch "<feature_branch>"
git switch -c "<task_branch>"   # or: git switch "<task_branch>" if it already exists
```

5) Implement per the task’s Summary + Acceptance Criteria.
   - Reuse existing services/patterns. Do not invent endpoints beyond the design.
   - Keep changes scoped to the task.

6) Tests & Verification:
   - Add/adjust tests as required.
   - Run the **Verification** steps from the task and ensure they pass.

7) Commit:
   - Commit message = `settings.commit_message_template` with `{id}` and `{title}` replaced.
   - If on a protected branch, STOP and output the correct branch/switch commands instead.

8) Open PR:
   - PR title = `settings.pr_title_template` with `{id}` and `{title}` replaced.
   - **PR base = <feature_branch>** (NEVER master/main/develop).
   - Include a link or reference to the task file and list Acceptance Criteria in the PR body.

9) Complete:
   - Check off Acceptance Criteria in the task file.
   - Flip `status: done` when verification passes.
   - Update `spec/index.yml` entry for `<ID>` with the final `status` (and `owner` if used).

10) Loop behavior (from settings):
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


def init_scaffold(force=False, force_index=False):
    """Create the minimal scaffold. Overwrite helper files only if force=True.
    Never overwrite spec/index.yml unless force_index=True."""
    ensure_spec_dirs()
    created = []
    # index.yml guarded separately
    if safe_write("spec/index.yml", INDEX_YML, force_index):
        created.append("spec/index.yml")
    # the rest respect --force
    if safe_write("spec/settings.yml", SETTINGS_YML, force):
        created.append("spec/settings.yml")
    if safe_write("spec/template.task.md", TEMPLATE_TASK_MD, force):
        created.append("spec/template.task.md")
    if safe_write("spec/prompts.md", build_prompts_md([]), force):
        created.append("spec/prompts.md")
    if safe_write("spec/policies.md", POLICIES_MD, force):
        created.append("spec/policies.md")
    if safe_write("spec/PLAN.md", PLAN_MD, force):
        created.append("spec/PLAN.md")
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
        # find insertion point after initial comments (if any)
        insert_at = 0
        while insert_at < len(out) and out[insert_at].strip().startswith("#"):
            insert_at += 1
        out[insert_at:insert_at] = ["designs:"] + [f"- {d}" for d in designs]
    write_text("spec/index.yml", "\n".join(out) + "\n")


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
        if ":" in s:
            key, val = s.split(":", 1)
            key = key.strip()
            val = val.strip()
            if key in (
                "auto_execute_after_planning",
                "require_owner_for_doing",
                "enforce_branching",
            ):
                out[key] = val.lower().startswith("true")
            elif key == "next_task_loop":
                out[key] = val
            elif key in (
                "branch_naming",
                "feature_branch_naming",  # NEW
                "commit_message_template",
                "pr_title_template",
            ):
                out[key] = val.strip('"')
            elif key in ("protected_branches", "feature_base_candidates"):  # NEW tuple
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
        # NEW: feature-parent branching defaults
        "feature_branch_naming": "feat/{feature_slug}",
        "branch_naming": "feat/{feature_slug}/{id}-{slug}",
        "feature_base_candidates": ["main", "master", "develop"],
        "enforce_branching": True,
        "protected_branches": ["main", "master", "develop"],
        "commit_message_template": "{id}: {title}",
        "pr_title_template": "{id}: {title}",
    }
    current.update(values or {})

    pb = ", ".join(f'"{b}"' for b in current["protected_branches"])
    fbc = ", ".join(f'"{b}"' for b in current["feature_base_candidates"])

    body = f"""# Minimal execution settings for agents
settings:
  auto_execute_after_planning: {"true" if current["auto_execute_after_planning"] else "false"}
  next_task_loop: {current["next_task_loop"]}
  require_owner_for_doing: {"true" if current["require_owner_for_doing"] else "false"}

  # Branching workflow (feature-parent + per-task branches)
  feature_branch_naming: "{current["feature_branch_naming"]}"
  branch_naming: "{current["branch_naming"]}"
  feature_base_candidates: [{fbc}]

  enforce_branching: {"true" if current["enforce_branching"] else "false"}
  protected_branches: [{pb}]
  commit_message_template: "{current["commit_message_template"]}"
  pr_title_template: "{current["pr_title_template"]}"
"""
    write_text("spec/settings.yml", body)


def to_feature_slug(path_or_title: str) -> str:
    """
    Derive {feature_slug} from a design filename or plain title.
    Lowercase, replace non-alnum with '-', and trim dashes.
    """
    base = os.path.basename(path_or_title)
    name, _ = os.path.splitext(base)
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug


def compute_feature_branch(path_or_title: str, settings: dict | None = None) -> str:
    """
    Render the feature parent branch using spec/settings.yml pattern.
    """
    settings = settings or load_settings()
    pattern = settings.get("feature_branch_naming", "feat/{feature_slug}")
    return pattern.replace("{feature_slug}", to_feature_slug(path_or_title))


def task_branch_name(
    feature_design: str, task_id: str, task_title: str, settings: dict | None = None
) -> str:
    """
    Render a task branch from settings.branch_naming using {feature_slug}, {id}, {slug}.
    """
    settings = settings or load_settings()
    pattern = settings.get("branch_naming", "feat/{feature_slug}/{id}-{slug}")
    feature_slug = to_feature_slug(feature_design)
    slug = re.sub(r"[^a-z0-9]+", "-", task_title.lower()).strip("-")
    return (
        pattern.replace("{feature_slug}", feature_slug)
        .replace("{id}", task_id)
        .replace("{slug}", slug)
    )


def parse_task_file(path: str) -> dict:
    """
    Parse the YAML header from spec/tasks/*.md.
    Returns: {id,title,status,labels,deps,owner,file}
    """
    text = read_text(path)
    if not text.startswith("---"):
        raise ValueError(f"Missing YAML header in {path}")
    end = text.find("\n---", 3)
    header = text[4:end] if end != -1 else text[4:]
    out = {"labels": [], "deps": [], "owner": "", "file": path}
    for line in header.splitlines():
        s = line.strip()
        if not s or s.startswith("#") or ":" not in s:
            continue
        k, v = s.split(":", 1)
        k, v = k.strip(), v.strip()
        if k in ("id", "title", "status", "owner"):
            out[k] = v.strip('"')
        elif k in ("labels", "deps"):
            if v.startswith("[") and v.endswith("]"):
                inner = v[1:-1].strip()
                out[k] = [
                    p.strip().strip('"').strip("'")
                    for p in inner.split(",")
                    if p.strip()
                ]
            elif v:
                out[k] = [v.strip('"').strip("'")]
    out.setdefault("id", os.path.basename(path)[:-3])
    out.setdefault("title", "")
    out.setdefault("status", "todo")
    return out


def parse_index_tasks(index_path="spec/index.yml") -> list:
    if not os.path.exists(index_path):
        return []
    lines = read_text(index_path).splitlines()
    tasks, cur, in_tasks = [], {}, False
    for ln in lines:
        s = ln.strip()
        if s.startswith("tasks:"):
            in_tasks, cur = True, {}
            continue
        if not in_tasks:
            continue
        # parse flat list under tasks:
        if s.startswith("- "):
            if cur:
                tasks.append(cur)
                cur = {}
            if ":" in s[2:]:
                k, v = s[2:].split(":", 1)
                cur[k.strip()] = v.strip().strip('"')
            continue
        if s == "" or s.startswith("#"):
            continue
        if ":" in s:
            k, v = s.split(":", 1)
            k, v = k.strip(), v.strip()
            if k in ("id", "title", "status", "owner", "file"):
                cur[k] = v.strip('"')
            elif k in ("labels", "deps"):
                if v.startswith("[") and v.endswith("]"):
                    inner = v[1:-1].strip()
                    cur[k] = [
                        p.strip().strip('"').strip("'")
                        for p in inner.split(",")
                        if p.strip()
                    ]
                elif v:
                    cur[k] = [v.strip('"').strip("'")]
    if cur:
        tasks.append(cur)
    return tasks


def quick_diff_files_vs_index(files: list, index: list) -> list:
    """
    Return list of basic inconsistencies:
      - missing_in_index: file exists but no ledger entry
      - missing_file: ledger points to a file that doesn't exist
      - status_mismatch: header status != index status
    """
    out = []
    by_id_file = {t["id"]: t for t in files}
    by_id_index = {t["id"]: t for t in index}

    # file exists but not in index
    for tid, tf in by_id_file.items():
        if tid not in by_id_index:
            out.append({"type": "missing_in_index", "id": tid, "file": tf["file"]})

    # in index but file missing
    for tid, ti in by_id_index.items():
        f = ti.get("file") or f"spec/tasks/{tid}.md"
        if not os.path.exists(f):
            out.append({"type": "missing_file", "id": tid, "index_file": f})

    # status mismatch
    for tid, tf in by_id_file.items():
        ti = by_id_index.get(tid)
        if not ti:
            continue
        fs = (tf.get("status") or "").strip().lower()
        is_ = (ti.get("status") or "").strip().lower()
        if fs and is_ and fs != is_:
            out.append({
                "type": "status_mismatch",
                "id": tid,
                "file_status": fs,
                "index_status": is_,
                "file": tf["file"],
                "index_file": ti.get("file"),
            })
    return out


# ---------- Reindex (safe rebuild of index.yml) ----------


def parse_frontmatter_min(md_text):
    """
    Minimal front-matter parser (no external deps).
    Expects a YAML-ish header between --- lines; extracts common keys.
    """
    m = re.match(r"^---\n(.*?)\n---", md_text, re.DOTALL)
    if not m:
        return {}
    data = {}
    for line in m.group(1).splitlines():
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k in ("labels", "deps"):
            data[k] = re.findall(r"[A-Za-z0-9\-\_]+", v)
        else:
            data[k] = v
    return data


def cmd_reindex(_args):
    """Rebuild spec/index.yml from spec/tasks/*.md while preserving current designs."""
    designs = load_designs_from_index()
    tasks_dir = "spec/tasks"
    entries = []
    if os.path.isdir(tasks_dir):
        for name in sorted(os.listdir(tasks_dir)):
            if not name.endswith(".md"):
                continue
            path = os.path.join(tasks_dir, name)
            with open(path, "r", encoding="utf-8") as f:
                fm = parse_frontmatter_min(f.read())
            tid = fm.get("id") or os.path.splitext(name)[0]
            entry = {
                "id": tid,
                "title": fm.get("title", ""),
                "labels": fm.get("labels", []),
                "status": fm.get("status", "todo"),
                "deps": fm.get("deps", []),
                "file": f"spec/tasks/{name}",
            }
            if fm.get("owner"):
                entry["owner"] = fm["owner"]
            entries.append(entry)

    # write a simple YAML by hand (keeps this script dependency-free)
    lines = []
    lines.append("# Task ledger for agent + human")
    if designs:
        lines.append("designs:")
        for d in designs:
            lines.append(f"- {d}")
    else:
        lines.append("designs: []")
    if entries:
        lines.append("tasks:")
        for e in entries:
            lines.append(f"- id: {e['id']}")
            lines.append(f"  title: {e['title']}")
            lines.append(f"  labels: {e['labels']}")
            lines.append(f"  status: {e['status']}")
            lines.append(f"  deps: {e['deps']}")
            lines.append(f"  file: {e['file']}")
            if "owner" in e:
                lines.append(f"  owner: {e['owner']}")
    else:
        lines.append("tasks: []")

    write_text("spec/index.yml", "\n".join(lines) + "\n")
    print(f"rebuilt spec/index.yml from {len(entries)} task file(s).")


# ---------- Commands ----------


def cmd_init(args):
    created = init_scaffold(force=args.force, force_index=args.force_index)
    if created:
        print("created:", ", ".join(created))
    else:
        print(
            "nothing to do (already initialized). use --force for helpers; --force-index only if you really want to reset the ledger."
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
    guide = """\
Minimal Spec System — User Guide

1) Initialize once per repo:
   spec.py init

2) Register a design doc (append to prompts; add to index.yml):
   spec.py add docs/design/Trusted\\ Managers\\ Mechanism.md

3) Kick off an agent:
   - - Planning: open spec/PLAN.md (or print prompt with `spec.py prompt`)
   - Implementation: open spec/EXECUTE.md

4) Track progress:
   - spec/index.yml  (statuses: todo|doing|done|blocked)
   - spec/tasks/T-xxx.md (task detail)

Settings (spec/settings.yml):
- Auto/manual: auto_execute_after_planning, next_task_loop
- Multi-agent safety: require_owner_for_doing
- Branching:
  - feature_branch_naming (e.g., feat/{feature_slug})
  - branch_naming (e.g., feat/{feature_slug}/{id}-{slug})
  - feature_base_candidates (default: main, master, develop)
  - enforce_branching, protected_branches
- Templates: commit_message_template, pr_title_template

Task utilities:
- spec.py tasks               # list all tasks from files
- spec.py tasks --check       # report basic drift vs index (read-only)
- spec.py tasks --fix         # rebuild index.yml from files (same as reindex)

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
        raw = args.protected.replace(",", " ").split()
        vals["protected_branches"] = [p.strip() for p in raw if p.strip()]
    if args.commit_tmpl:
        vals["commit_message_template"] = args.commit_tmpl
    if args.pr_title_tmpl:
        vals["pr_title_template"] = args.pr_title_tmpl
    if args.feature_branch:
        vals["feature_branch_naming"] = args.feature_branch
    if args.feature_bases:
        raw = args.feature_bases.replace(",", " ").split()
        vals["feature_base_candidates"] = [p.strip() for p in raw if p.strip()]

    save_settings(vals)
    print("updated spec/settings.yml")


def cmd_feature(args):
    s = load_settings()
    slug = to_feature_slug(args.design)
    branch = compute_feature_branch(args.design, s)
    print(f"feature_slug: {slug}")
    print(f"feature_branch: {branch}")


def cmd_task_branch(args):
    s = load_settings()
    name = task_branch_name(args.design, args.task_id, args.task_title, s)
    print(name)


def cmd_tasks(args):
    # gather from files (source-of-truth for listing)
    file_tasks = []
    task_dir = os.path.join("spec", "tasks")
    if os.path.isdir(task_dir):
        for name in sorted(os.listdir(task_dir)):
            if name.endswith(".md"):
                try:
                    file_tasks.append(parse_task_file(os.path.join(task_dir, name)))
                except Exception as e:
                    print(f"warn: {name}: {e}", file=sys.stderr)

    # optional basic check vs index
    if args.check:
        idx_tasks = parse_index_tasks()
        issues = quick_diff_files_vs_index(file_tasks, idx_tasks)
        if not issues:
            print("OK: no inconsistencies found.")
        else:
            print("Inconsistencies:")
            for i in issues:
                if i["type"] == "missing_in_index":
                    print(f"- missing_in_index: {i['id']}  ({i['file']})")
                elif i["type"] == "missing_file":
                    print(
                        f"- missing_file: {i['id']}  (index points to {i['index_file']})"
                    )
                elif i["type"] == "status_mismatch":
                    print(
                        f"- status_mismatch: {i['id']}  file={i['file_status']}  index={i['index_status']}"
                    )
        if args.strict and issues:
            sys.exit(1)

    # filters (apply to what we show)
    tasks = file_tasks
    if args.status:
        want = {
            s.strip().lower() for s in re.split(r"[,\s]+", args.status) if s.strip()
        }
        tasks = [t for t in tasks if (t.get("status") or "").lower() in want]
    if args.owner:
        tasks = [
            t for t in tasks if (t.get("owner") or "").lower() == args.owner.lower()
        ]
    if args.grep:
        pat = args.grep.lower()
        tasks = [
            t
            for t in tasks
            if pat in (t.get("title") or "").lower() or pat in t["id"].lower()
        ]

    # outputs
    if args.count:
        print(len(tasks))
        return
    if args.ids_only:
        for t in tasks:
            print(t["id"])
        return
    if not tasks:
        print("No tasks found.")
        return

    col_id = max([2] + [len(t["id"]) for t in tasks])
    col_st = max([6] + [len(t.get("status") or "") for t in tasks])
    col_ow = max([5] + [len(t.get("owner") or "") for t in tasks])
    header = f"{'ID'.ljust(col_id)}  {'STATUS'.ljust(col_st)}  {'OWNER'.ljust(col_ow)}  TITLE"
    print(header)
    print("-" * len(header))
    for t in tasks:
        print(
            f"{t['id'].ljust(col_id)}  {(t.get('status') or '').ljust(col_st)}  {(t.get('owner') or '').ljust(col_ow)}  {t.get('title') or ''}"
        )

    # --fix delegates to your reindex logic
    if args.fix:
        cmd_reindex(args)


# ---------- CLI ----------


def main():
    epilog = """
Examples:
  # 1) Create minimal scaffold once (spec/ folder, helper files)
  spec.py init
  spec.py init --force              # refresh helpers (NOT the ledger)
  spec.py init --force-index        # DANGEROUS: resets spec/index.yml

  # 2) Register a design doc (idempotent)
  spec.py add docs/design/Trusted\\ Managers\\ Mechanism.md

  # 3) Print the current agent planning prompt (copy/paste into agent)
  spec.py prompt

  # 4) Show a concise user guide
  spec.py guide

  # 5) Configure execution & protection
  spec.py config --auto on --loop auto --require-owner on \\
                 --enforce on --protected "main, master, develop" \\
                 --feature-branch "feat/{feature_slug}" \\
                 --feature-bases "main, master, develop" \\
                 --branch "feat/{feature_slug}/{id}-{slug}" \\
                 --commit-tmpl "{id}: {title}" --pr-title-tmpl "{id}: {title}"

  # 6) Rebuild index.yml from existing task files (safe)
  spec.py reindex

    # 7) List tasks & check drift (safe)
  spec.py tasks                                 # list all from files
  spec.py tasks --status "todo,doing"           # filter by status
  spec.py tasks --owner stef --grep route       # filter by owner & substring
  spec.py tasks --check                         # compare files vs index (read-only)
  spec.py tasks --check --strict                # fail (exit 1) if drift found (CI-friendly)
  spec.py tasks --fix                           # sync index from files (same as: spec.py reindex)

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
        help="overwrite helper files (settings.yml, template.task.md, prompts.md, policies.md, PLAN.md, EXECUTE.md). never touches spec/tasks/",
    )
    p_init.add_argument(
        "--force-index",
        action="store_true",
        help="DANGEROUS: overwrite spec/index.yml (the task ledger). rarely needed.",
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
        "--branch",
        help="task branch naming pattern, e.g. 'feat/{feature_slug}/{id}-{slug}'",
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

    p_config.add_argument(
        "--feature-branch",
        dest="feature_branch",
        help="feature parent branch pattern, e.g. 'feat/{feature_slug}'",
    )
    p_config.add_argument(
        "--feature-bases",
        dest="feature_bases",
        help="comma or space separated candidate base branches for the feature branch (first existing wins), e.g. 'main, master, develop'",
    )

    p_config.set_defaults(func=cmd_config)

    p_reindex = sub.add_parser(
        "reindex", help="rebuild spec/index.yml from spec/tasks/*.md (safe)"
    )
    p_reindex.set_defaults(func=cmd_reindex)

    p_feature = sub.add_parser(
        "feature",
        help="derive feature slug/branch from a design filename or title",
    )
    p_feature.add_argument("design", help="design filename or plain title")
    p_feature.set_defaults(func=cmd_feature)

    p_taskbranch = sub.add_parser(
        "task-branch",
        help="render a task branch name for a given ID and title",
    )
    p_taskbranch.add_argument(
        "design", help="design filename or plain title (to derive {feature_slug})"
    )
    p_taskbranch.add_argument("task_id", help="task ID, e.g., T-012")
    p_taskbranch.add_argument("task_title", help="task title to slugify")
    p_taskbranch.set_defaults(func=cmd_task_branch)

    p_tasks = sub.add_parser(
        "tasks",
        help="list tasks from files; --check compares with index; --fix syncs ledger (reindex)",
    )
    p_tasks.add_argument(
        "--status", help="filter by status, e.g. 'todo' or 'todo,doing'"
    )
    p_tasks.add_argument("--owner", help="filter by owner (exact match)")
    p_tasks.add_argument(
        "--grep", help="substring match against id/title (case-insensitive)"
    )
    p_tasks.add_argument(
        "--check",
        action="store_true",
        help="compare files vs index and report basic inconsistencies",
    )
    p_tasks.add_argument(
        "--strict",
        action="store_true",
        help="exit 1 if --check finds inconsistencies (CI-friendly)",
    )
    p_tasks.add_argument(
        "--count", action="store_true", help="print only the number of matching tasks"
    )
    p_tasks.add_argument(
        "--ids-only", action="store_true", help="print only task IDs (one per line)"
    )
    p_tasks.add_argument(
        "--fix",
        action="store_true",
        help="rewrite spec/index.yml from files (same as reindex)",
    )
    p_tasks.set_defaults(func=cmd_tasks)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
