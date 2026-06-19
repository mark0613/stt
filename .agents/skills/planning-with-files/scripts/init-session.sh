#!/usr/bin/env bash
# Initialize planning files for a new session.
#
# Usage:
#   ./init-session.sh                              # .planning/<date>-untitled-<short>/
#   ./init-session.sh [--template TYPE]            # same, with template choice
#   ./init-session.sh "Backend Refactor"           # .planning/<date>-backend-refactor/
#   ./init-session.sh --plan-dir "Quick Spike"     # explicit slug (--plan-dir kept for compatibility)
#
# Every plan is written under .planning/<date>-<slug>/. Without a project name
# the slug falls back to untitled-<short>.

set -e

TEMPLATE="default"
PROJECT_NAME=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --template|-t)
            TEMPLATE="$2"
            shift 2
            ;;
        --plan-dir)
            # Retained for backward compatibility; slug mode is now always on.
            shift
            ;;
        *)
            if [ -z "$PROJECT_NAME" ]; then
                PROJECT_NAME="$1"
            else
                PROJECT_NAME="$PROJECT_NAME $1"
            fi
            shift
            ;;
    esac
done

DATE=$(date +%Y-%m-%d)

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILL_ROOT="$(dirname "$SCRIPT_DIR")"
TEMPLATE_DIR="$SKILL_ROOT/templates"

if [ "$TEMPLATE" != "default" ] && [ "$TEMPLATE" != "analytics" ]; then
    echo "Unknown template: $TEMPLATE (available: default, analytics). Using default."
    TEMPLATE="default"
fi

slugify() {
    # Lowercase, non-alphanumerics → '-', collapse repeats, trim leading/trailing '-'
    printf '%s' "$1" \
        | tr '[:upper:]' '[:lower:]' \
        | sed -e 's/[^a-z0-9]/-/g' -e 's/-\{2,\}/-/g' -e 's/^-//' -e 's/-$//' \
        | cut -c1-40
}

short_uuid() {
    # Probe each candidate: command -v alone is not enough on Windows because
    # App Execution Aliases report presence but exit non-zero when run.
    _py="${PYTHON_BIN:-}"
    if [ -z "$_py" ]; then
        for _c in python3 python py; do
            if command -v "$_c" >/dev/null 2>&1 && "$_c" -c "import uuid" >/dev/null 2>&1; then
                _py="$_c"
                break
            fi
        done
    fi
    if [ -n "$_py" ]; then
        "$_py" -c "import uuid; print(uuid.uuid4().hex[:8])"
        return
    fi
    if command -v uuidgen >/dev/null 2>&1; then
        uuidgen | tr '[:upper:]' '[:lower:]' | tr -d '-' | cut -c1-8
        return
    fi
    # Last-ditch: seconds timestamp as 8 hex chars
    printf '%08x' "$(date +%s)" | cut -c1-8
}

write_default_task_plan() {
    cat > "$1" << 'EOF'
# Task Plan: [Brief Description]
<!--
  This file is the PLAN: goal, phases, and one line on what each phase is for. Keep it short.
  It describes the plan; it does not track execution — the running log goes in progress.md.
  KEEP OUT OF HERE:
    - Step-by-step execution, commit hashes, test logs -> progress.md
    - Decisions, discoveries, constraints, traps        -> findings.md (key points, not full copies)
  Rule: task_plan = the plan. progress = what I did. findings = the key points.
-->

## Goal
[One sentence describing the end state]

## Current Phase
Phase 1

## Phases
<!--
  Each phase = one summary line + a few plain bullets (use "-", NOT "- [ ]") describing the
  concrete things this phase will do. The bullets are the PLAN's breakdown, so a human reviewer
  can see what each phase entails. They are NOT a checklist to tick off — the running log of what
  you actually did goes in progress.md. Update only the **Status** line as a phase changes state.
-->

### Phase 1: Requirements & Discovery
Understand intent, constraints, and the shape of the work.
- Clarify the goal and acceptance criteria
- Identify constraints and unknowns
- **Status:** in_progress

### Phase 2: Planning & Structure
Decide the technical approach. (Record decisions and why in findings.md.)
- Choose the approach / structure
- Note the key decisions in findings.md
- **Status:** pending

### Phase 3: Implementation
Build the solution.
- [the concrete pieces to build]
- **Status:** pending

### Phase 4: Testing & Verification
Verify requirements are met. (Record test results in progress.md.)
- [what to verify]
- **Status:** pending

### Phase 5: Delivery
Final review and handoff.
- Review outputs and deliver
- **Status:** pending

## Open Questions
<!-- Questions that shape direction. Their answers (facts/decisions) go in findings.md once known. -->
1. [Question to answer]
EOF
}

write_default_findings() {
    cat > "$1" << 'EOF'
# Findings & Decisions

## Requirements
-

## Research Findings
-

## Technical Decisions
| Decision | Rationale |
|----------|-----------|

## Issues Encountered
| Issue | Resolution |
|-------|------------|

## Resources
-
EOF
}

write_default_progress() {
    local date_value="$1"
    local target="$2"
    cat > "$target" << EOF
# Progress Log

## Session: $date_value

### Current Status
- **Phase:** 1 - Requirements & Discovery
- **Started:** $date_value

### Actions Taken
-

### Test Results
| Test | Expected | Actual | Status |
|------|----------|--------|--------|

### Errors
| Error | Resolution |
|-------|------------|
EOF
}

write_analytics_progress() {
    local date_value="$1"
    local target="$2"
    cat > "$target" << EOF
# Progress Log

## Session: $date_value

### Current Status
- **Phase:** 1 - Data Discovery
- **Started:** $date_value

### Actions Taken
-

### Query Log
| Query | Result Summary | Interpretation |
|-------|---------------|----------------|

### Errors
| Error | Resolution |
|-------|------------|
EOF
}

create_files_in() {
    local target_dir="$1"
    local plan_path="$target_dir/task_plan.md"
    local findings_path="$target_dir/findings.md"
    local progress_path="$target_dir/progress.md"

    if [ ! -f "$plan_path" ]; then
        if [ "$TEMPLATE" = "analytics" ] && [ -f "$TEMPLATE_DIR/analytics_task_plan.md" ]; then
            cp "$TEMPLATE_DIR/analytics_task_plan.md" "$plan_path"
        else
            write_default_task_plan "$plan_path"
        fi
        echo "Created $plan_path"
    else
        echo "$plan_path already exists, skipping"
    fi

    if [ ! -f "$findings_path" ]; then
        if [ "$TEMPLATE" = "analytics" ] && [ -f "$TEMPLATE_DIR/analytics_findings.md" ]; then
            cp "$TEMPLATE_DIR/analytics_findings.md" "$findings_path"
        else
            write_default_findings "$findings_path"
        fi
        echo "Created $findings_path"
    else
        echo "$findings_path already exists, skipping"
    fi

    if [ ! -f "$progress_path" ]; then
        if [ "$TEMPLATE" = "analytics" ]; then
            write_analytics_progress "$DATE" "$progress_path"
        else
            write_default_progress "$DATE" "$progress_path"
        fi
        echo "Created $progress_path"
    else
        echo "$progress_path already exists, skipping"
    fi
}

SLUG="$(slugify "$PROJECT_NAME")"
if [ -z "$SLUG" ]; then
    SLUG="untitled-$(short_uuid)"
fi
BASE_ID="${DATE}-${SLUG}"
PLAN_SLUG="$BASE_ID"
PLAN_ROOT="${PWD}/.planning"
counter=2
while [ -d "${PLAN_ROOT}/${PLAN_SLUG}" ]; do
    PLAN_SLUG="${BASE_ID}-${counter}"
    counter=$((counter + 1))
done
PLAN_DIR="${PLAN_ROOT}/${PLAN_SLUG}"
mkdir -p "$PLAN_DIR"

echo "Initializing planning files for: ${PROJECT_NAME:-untitled} (template: $TEMPLATE)"
echo "Plan slug: $PLAN_SLUG"
create_files_in "$PLAN_DIR"
echo ""
echo "Plan directory: ${PLAN_DIR}"
