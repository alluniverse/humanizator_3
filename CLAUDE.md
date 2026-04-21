# Agent Instructions

This project uses **bd** (beads) for issue tracking. Run `bd prime` to get full workflow context.

## Non-Interactive Shell Commands

**ALWAYS use non-interactive flags** with file operations to avoid hanging on confirmation prompts.

Shell commands like `cp`, `mv`, and `rm` may be aliased to include `-i` (interactive) mode on some systems, causing the agent to hang indefinitely waiting for y/n input.

**Use these forms instead:**

```bash
cp -f source dest           # NOT: cp source dest
mv -f source dest           # NOT: mv source dest
rm -f file                  # NOT: rm file
rm -rf directory            # NOT: rm -r directory
cp -rf source dest          # NOT: cp -r source dest
```

**Other commands that may prompt:**

- `scp` - use `-o BatchMode=yes`
- `ssh` - use `-o BatchMode=yes`
- `apt-get` - use `-y` flag
- `brew` - use `HOMEBREW_NO_AUTO_UPDATE=1` env var

<!-- BEGIN BEADS INTEGRATION v:1 profile:minimal hash:ca08a54f -->

## Beads Issue Tracker

This project uses **bd (beads)** — a Dolt-powered, graph-based issue tracker that persists state across conversation compaction. It is the **single source of truth** for all work.

**IMPORTANT: Before working with beads, load the beads skill:**

```
/home/nevis/.agents/skills/beads/SKILL.md
```

Run `bd prime` for AI-optimized workflow context and up-to-date command reference.

### Quick Reference

```bash
bd prime                          # Full workflow context (canonical, always current)
bd ready                          # Find unblocked work
bd show <id>                      # Full issue context
bd show <id> --long               # Extended metadata
bd list --status in_progress      # See active work (post-compaction recovery)
bd create "title" -t <type> -p <priority> --tags <tag>  # Create issue
bd dep add <child> <parent>       # "child needs parent" (parent must close first)
bd update <id> --claim            # Atomically claim and start work
bd update <id> --notes "..."      # Add/update notes (overwrite, not append)
bd close <id> --reason "..."      # Complete work
bd dolt push                      # Push to Dolt remote
bd remember                       # Persistent knowledge store (use instead of MEMORY.md)
```

### Rules

- Use `bd` for ALL task tracking — do NOT use TodoWrite, TaskCreate, or standalone markdown TODO lists
- `bd prime` is the **canonical source of truth** for CLI syntax — use it when in doubt
- Use `bd remember` for persistent knowledge — do NOT use MEMORY.md files
- TodoWrite may only be used as a **tactical execution checklist within a single claimed bd task** (visible in-session progress). It is NOT a substitute for bd issue tracking.

---

### Mandatory Beads Workflow

**ALL meaningful work MUST go through the beads cycle. A task without a beads issue must NOT be executed.**

#### 1. Skill and Context First

At the start of every session:

```bash
# Load the beads skill for full guidance
# File: /home/nevis/.agents/skills/beads/SKILL.md

bd prime                     # Get AI-optimized workflow context
bd ready                     # See what's unblocked and ready
bd list --status in_progress # Check for work already claimed (post-compaction)
```

For each `in_progress` issue, run `bd show <id>` and read the notes to reconstruct context.

#### 2. Issue Hierarchy: Epic → Feature → Task

Every unit of work must live in the hierarchy:

| Type        | `-t` flag | Purpose                                   |
| ----------- | --------- | ----------------------------------------- |
| **Epic**    | `epic`    | High-level goal or product area           |
| **Feature** | `feature` | Functional capability within an Epic      |
| **Task**    | `task`    | Concrete actionable item within a Feature |

All items must:

- Be **linked** to their parent via `bd dep add <child> <parent>`
- Have **tags** (`--tags`) describing the domain/area
- Have a **priority** set (`-p 1` = highest)

#### Naming and Numbering Convention

Issue titles must include a **hierarchical prefix** based on position in the tree:

- Epic: `N. Title` — e.g. `1. Foundation`
- Feature: `N.M. Title` — e.g. `1.2. Monorepo Structure`
- Task: `N.M.K. Title` — e.g. `1.2.1. Initialize pnpm workspace`

Where:

- **N** = Epic number (ordered by creation date, starting from 1)
- **M** = Feature number within its Epic (ordered by numeric ID suffix, starting from 1)
- **K** = Task number within its Feature (ordered by numeric ID suffix, starting from 1)

When creating a new issue, determine its position in the hierarchy and prepend the correct prefix. When renaming or reordering, update all affected descendants to keep prefixes consistent.

**Dependency direction rule**: `bd dep add A B` means "A needs B" (B must close before A can start). Walk backward from the goal to set deps correctly.

#### 3. Receiving a Task

When the user gives a task:

1. Check if it already exists: `bd ready`, `bd list`, `bd show <id>`
2. Find the appropriate Epic/Feature — or create them if none exist:
   ```bash
   bd create "Epic name" -t epic -p 2 --tags domain
   bd create "Feature name" -t feature -p 2 --tags domain
   bd dep add <feature-id> <epic-id>
   ```
3. Create the Task under the Feature:
   ```bash
   bd create "Task name" -t task -p 1 --tags domain
   bd dep add <task-id> <feature-id>
   ```
4. Claim it atomically before starting:
   ```bash
   bd update <task-id> --claim
   ```

**Do NOT begin work until the Task exists in beads.**

#### 4. During Work — Use Beads as Memory

Before starting, read all related issues to learn from prior sessions:

```bash
bd show <id>          # Read notes, design, acceptance criteria
bd dep tree <id>      # Understand dependencies and related issues
```

Add notes as you make decisions (written for a future agent with zero context):

```bash
bd update <id> --notes "COMPLETED: X. IN PROGRESS: Y. NEXT: Z. KEY DECISION: ..."
```

Good notes include specific accomplishments, current state, next concrete step, and key decisions with rationale. See compaction survival format:

```
COMPLETED: <what was implemented>
IN PROGRESS: <what is partially done>
NEXT: <concrete next step>
BLOCKER: <if any>
KEY DECISION: <rationale for important choices>
```

#### 5. After Completing a Task

1. **Write experience note** — describe what was done, what worked, gotchas, so future agents can learn:
   ```bash
   bd update <task-id> --notes "COMPLETED: <summary>. EXPERIENCE: <lessons learned, approach that worked, pitfalls to avoid>"
   ```
2. **Close the task**:
   ```bash
   bd close <task-id> --reason "<brief summary of what was done>"
   ```
3. **Check what unblocked**: `bd ready` — report newly available work
4. **Run Session Completion** (see below)

#### 6. Side Quests and Discoveries

When you discover additional work during implementation:

```bash
bd create "Discovered issue" -t task -p 2 --tags domain
bd dep add <new-id> <current-id> --type discovered-from
```

Assess: is it a blocker (pause, switch) or deferrable (note and continue)?

#### 7. Never Skip Beads

- A task with no beads issue must NOT be executed
- If a task seems trivial, create a minimal issue and immediately claim it
- Ask: _"Could I resume this after 2 weeks without bd?"_ — if yes, bd is needed

---

## Session Completion

**When ending a work session**, you MUST complete ALL steps below. Work is NOT complete until `git push` succeeds.

**MANDATORY WORKFLOW:**

1. **File issues for remaining work** — create bd issues for anything that needs follow-up
2. **Update notes on in-progress issues** — write handoff notes so the next session can resume instantly
3. **Run quality gates** (if code changed) — tests, linters, builds
4. **Update issue status** — close finished work, update in-progress items
5. **PUSH TO REMOTE** — this is MANDATORY:
   ```bash
   git pull --rebase
   bd dolt push
   git push
   git status  # MUST show "up to date with origin"
   ```
6. **Verify** — all changes committed AND pushed
7. **Hand off** — summarize status for the next session

**CRITICAL RULES:**

- Work is NOT complete until `git push` succeeds
- NEVER stop before pushing — that leaves work stranded locally
- NEVER say "ready to push when you are" — YOU must push
- If push fails, resolve and retry until it succeeds
<!-- END BEADS INTEGRATION -->
