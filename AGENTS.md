# Agent Instructions

This project uses **bd** (beads) for issue tracking. Run `bd onboard` to get started.

## Quick Reference

```bash
bd ready              # Find available work
bd show <id>          # View issue details
bd update <id> --claim  # Claim work atomically
bd close <id>         # Complete work
bd dolt push          # Push beads data to remote
```

## Non-Interactive Shell Commands

**ALWAYS use non-interactive flags** with file operations to avoid hanging on confirmation prompts.

Shell commands like `cp`, `mv`, and `rm` may be aliased to include `-i` (interactive) mode on some systems, causing the agent to hang indefinitely waiting for y/n input.

**Use these forms instead:**
```bash
# Force overwrite without prompting
cp -f source dest           # NOT: cp source dest
mv -f source dest           # NOT: mv source dest
rm -f file                  # NOT: rm file

# For recursive operations
rm -rf directory            # NOT: rm -r directory
cp -rf source dest          # NOT: cp -r source dest
```

**Other commands that may prompt:**
- `scp` - use `-o BatchMode=yes` for non-interactive
- `ssh` - use `-o BatchMode=yes` to fail instead of prompting
- `apt-get` - use `-y` flag
- `brew` - use `HOMEBREW_NO_AUTO_UPDATE=1` env var

<!-- BEGIN BEADS INTEGRATION v:1 profile:minimal hash:ca08a54f -->
## Beads Issue Tracker

This project uses **bd (beads)** for issue tracking. Run `bd prime` to see full workflow context and commands.

### Quick Reference

```bash
bd ready              # Find available work
bd show <id>          # View issue details
bd update <id> --claim  # Claim work
bd close <id>         # Complete work
```

### Rules

- Use `bd` for ALL task tracking — do NOT use TodoWrite, TaskCreate, or markdown TODO lists
- Run `bd prime` for detailed command reference and session close protocol
- Use `bd remember` for persistent knowledge — do NOT use MEMORY.md files

## Issue Hierarchy (Epic → Feature → Task)

**ALWAYS maintain parent-child relationships** between issues:

```
Epic (type=epic)
└── Feature (type=feature, parent=epic_id)
    └── Tasks (type=task, parent=feature_id)
```

**Creating hierarchical work:**
```bash
# 1. Create Feature under Epic
bd create --title="Feature title" --type=feature --parent=mimesis_sam_2-54k

# 2. Create Tasks under Feature (parallel execution)
bd create --title="Task 1" --type=task --parent=mimesis_sam_2-1yd &
bd create --title="Task 2" --type=task --parent=mimesis_sam_2-1yd &
wait

# 3. Add dependencies between tasks if needed
bd dep add mimesis_sam_2-task2 mimesis_sam_2-task1  # task2 depends on task1

# 4. Verify hierarchy
bd show <epic_id>    # Shows all children
bd show <feature_id> # Shows parent and children
```

**Linking existing issues:**
```bash
# Link Feature to Epic
bd update mimesis_sam_2-feature --parent=mimesis_sam_2-epic

# Link Task to Feature  
bd update mimesis_sam_2-task --parent=mimesis_sam_2-feature
```

**NEVER leave orphaned Features or Tasks** — always link them to parent issues.

## Task Workflow Rules

### 1. Task Decomposition (on receive)

**Every task from user MUST be decomposed in beads BEFORE starting work:**

```
User Request
    ↓
Analyze complexity
    ↓
┌─────────────────┬─────────────────┬─────────────────┐
│   Simple Task   │  Complex Task   │   Epic Level    │
│   (1-2 hours)   │  (half-day+)    │  (multi-day)   │
├─────────────────┼─────────────────┼─────────────────┤
│ Create Task     │ Create Feature  │ Create Epic     │
│ under existing  │ with Tasks      │ with Features   │
│ Feature or root │ as children     │ and Tasks       │
└─────────────────┴─────────────────┴─────────────────┘
```

**Check existing beads first:**
```bash
bd ready                    # See available work
bd show <existing_id>       # Check if task fits existing Epic/Feature
```

**Create hierarchy as needed:**
```bash
# For Epic-level work
bd create --title="User request summary" --type=epic

# For Feature-level work  
bd create --title="Feature name" --type=feature --parent=<epic_id>

# For individual tasks
bd create --title="Specific task" --type=task --parent=<feature_id>
```

**ALWAYS claim the task before starting:**
```bash
bd update <task_id> --claim
```

### 2. Experience Saving (after user acceptance)

**ONLY save experience when ALL conditions met:**

1. ✅ User explicitly confirmed work is complete
2. ✅ User confirmed functionality works as expected
3. ✅ No critical bugs or issues remain
4. ✅ Code is committed and pushed

**How to save experience:**
```bash
bd remember "Key insight or reusable pattern learned"
```

**What to save:**
- Reusable code patterns
- Configuration tricks
- Debugging approaches that worked
- Integration lessons
- Performance optimizations

**What NOT to save:**
- Temporary fixes
- Half-baked solutions
- Unverified assumptions
- Work-in-progress notes

### 3. Commit Rules (beads workflow)

**After closing a task, commits MUST follow this pattern:**

```bash
# 1. Stage changes
git add <relevant_files>

# 2. Create descriptive commit
# Format: <type>(<scope>): <description>
#
# Types: feat, fix, docs, style, refactor, test, chore
git commit -m "feat(parser): add progress tracking for SAM.gov parser

- Add status, task_id, records_total, records_processed fields
- Create progress page with auto-refresh
- Add API endpoint for real-time status updates"

# 3. Close the bead task
bd close <task_id>

# 4. Push everything
git pull --rebase
bd dolt push
git push
```

**Commit message rules:**
- Use conventional commits format
- Reference bead ID in commit body if relevant
- List key changes as bullet points
- Keep subject line under 72 characters

## Session Completion

**When ending a work session**, you MUST complete ALL steps below. Work is NOT complete until `git push` succeeds.

**MANDATORY WORKFLOW:**

1. **File issues for remaining work** - Create issues for anything that needs follow-up
2. **Run quality gates** (if code changed) - Tests, linters, builds
3. **Update issue status** - Close finished work, update in-progress items
4. **PUSH TO REMOTE** - This is MANDATORY:
   ```bash
   git pull --rebase
   bd dolt push
   git push
   git status  # MUST show "up to date with origin"
   ```
5. **Clean up** - Clear stashes, prune remote branches
6. **Verify** - All changes committed AND pushed
7. **Hand off** - Provide context for next session

**CRITICAL RULES:**
- Work is NOT complete until `git push` succeeds
- NEVER stop before pushing - that leaves work stranded locally
- NEVER say "ready to push when you are" - YOU must push
- If push fails, resolve and retry until it succeeds
<!-- END BEADS INTEGRATION -->
