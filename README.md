# Minimal Spec System

A tiny, human-friendly way to turn a prose design doc into small, testable tasks that AI agents can execute—without heavy process.

## What it does

* Scaffolds a minimal **`spec/`** folder (once).
* Registers one or more **design docs** for planning.
* Provides a **planning prompt** for agents to break the design into tasks.
* Keeps a **flat task ledger** you can skim in seconds.

## Who it’s for

* Builders who want agents to generate and execute tasks **from real specs**.
* People who prefer **simple Markdown + a YAML list** over complex tools.

---

got it. here’s a **drop-in replacement** for the **Install** section—copy/paste this into your README.

````md
## Install

You can keep `spec.py` outside your projects and run it from anywhere.

### macOS / Linux
**Option A — run with Python (no install):**
```bash
python3 /path/to/spec.py init
````

**Option B — make it a CLI on your PATH:**

```bash
# put it in a per-user bin and make it executable
mkdir -p ~/.local/bin
cp /path/to/spec.py ~/.local/bin/spec
chmod +x ~/.local/bin/spec

# ensure ~/.local/bin is on PATH (Bash/Zsh)
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc   # or ~/.zshrc
# reload your shell, then use:
spec init
```

> Tip: You can keep the filename as `spec.py`; renaming to `spec` just makes the command shorter. The script already has a shebang, so `chmod +x` lets you run it directly.

### Windows

**Option A — run with Python (no install):**

```powershell
# from any folder
py C:\path\to\spec.py init
# or
python C:\path\to\spec.py init
```

**Option B — add a simple CLI to your PATH:**

```powershell
# create a per-user bin and copy the script
New-Item -ItemType Directory -Force $HOME\bin | Out-Null
Copy-Item C:\path\to\spec.py $HOME\bin\spec.py

# add to PATH (per-user)
[Environment]::SetEnvironmentVariable(
  'Path', "$env:Path;$HOME\bin", 'User'
)
# restart the terminal to pick up the PATH change
```

Now you can run:

```powershell
py spec.py init
```

**Optional (nicer `spec` command on Windows):**
Create a wrapper file `%USERPROFILE%\bin\spec.bat` with:

```bat
@echo off
py "%~dp0spec.py" %*
```

Then you can call:

```powershell
spec init
```

> Requires **Python 3.x** (the `py` launcher comes with the official Windows Python installer).

---

## Quick Start

```bash
# 1) One-time scaffold
python3 spec.py init

# 2) Register a design doc (your prose feature spec)
python3 spec.py add "docs/design/Your Design Document.md"

# 3) Get the agent prompt (copy/paste into your AI agent)
python3 spec.py prompt

# (Optional) Show a short user guide
python3 spec.py guide
```

What gets created:

```
spec/
  index.yml            # task ledger (flat list)
  template.task.md     # tiny task template with YAML header
  prompts.md           # planning prompt that lists your design doc(s)
  policies.md          # one-page guardrails (edit if needed)
  tasks/               # agents will write TM-###.md here
docs/
  design/
    Your Design Document.md
```

---

## Commands

```bash
spec.py init            # create/update minimal scaffold (idempotent)
spec.py init --force    # overwrite helper files (never touches spec/tasks/)
spec.py add <design.md> # register a design doc (append to prompts, index)
spec.py prompt          # print the current agent planning prompt
spec.py guide           # print a short human guide
```

---

## Workflow

1. **Write** your feature as prose (Markdown) in `docs/design/...`.
2. **Add** the design doc: `spec.py add <path>`.
3. **Call** your agent with `spec.py prompt`.
4. The agent:

   * Creates tasks in `spec/tasks/` using `spec/template.task.md`.
   * Updates `spec/index.yml` with `id/title/labels/status/deps/file`.
5. **Track** progress by opening `spec/index.yml`.
   Drill into any task via `spec/tasks/TM-0xx.md`.

---

## Conventions (simple rules)

* **IDs**: `TM-001`, `TM-002`, …
* **Files**: each task lives at `spec/tasks/<ID>.md`.
* **Status**: `todo | doing | done | blocked`.
* **Deps**: only reference tasks that exist in `index.yml`.
* **Acceptance + Verification**: every task must include measurable checks and exact commands or calls to prove success.

---

## FAQ

**What’s the difference between `init` and `add`?**

* `init` sets up/refreshes the `spec/` scaffold.
* `add` registers a design doc (updates `index.yml: designs` and `prompts.md`).

**What does `--force` do?**

* Only for `init`. It **overwrites helper files** (`index.yml`, `template.task.md`, `prompts.md`, `policies.md`).
* It **never** touches `spec/tasks/`.

**Do I need epics?**

* No. Keep it flat. If you want grouping, use `labels` in tasks.

---

## Notes

* Edit **`policies.md`** to add project guardrails (security, reuse, licensing).
* Task files are **shared**: agents write them; you can tweak them.
* You can register **multiple design docs**; the prompt will list them all.

Happy shipping.
