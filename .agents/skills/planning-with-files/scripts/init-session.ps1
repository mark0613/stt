# Initialize planning files for a new session (PowerShell mirror of init-session.sh).
#
# Usage:
#   .\init-session.ps1                                 # .planning\<date>-untitled-<short>\
#   .\init-session.ps1 -Template TYPE                  # same, with template choice
#   .\init-session.ps1 "Backend Refactor"              # .planning\<date>-backend-refactor\
#   .\init-session.ps1 -PlanDir "Quick Spike"          # explicit slug (-PlanDir kept for compatibility)
#
# Every plan is written under .planning\<date>-<slug>\. Without a project name
# the slug falls back to untitled-<short>.

param(
    [string]$ProjectName = "",
    [string]$Template = "default",
    [switch]$PlanDir  # Retained for backward compatibility; slug mode is now always on.
)

$DATE = Get-Date -Format "yyyy-MM-dd"

# Resolve template directory (skill root is one level up from scripts/)
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$SkillRoot = Split-Path -Parent $ScriptDir
$TemplateDir = Join-Path $SkillRoot "templates"

# Validate template
if ($Template -ne "default" -and $Template -ne "analytics") {
    Write-Host "Unknown template: $Template (available: default, analytics). Using default."
    $Template = "default"
}

function Get-Slug {
    param([string]$Text)
    $s = $Text.ToLower()
    $s = [regex]::Replace($s, '[^a-z0-9]', '-')
    $s = [regex]::Replace($s, '-{2,}', '-')
    $s = $s.Trim('-')
    if ($s.Length -gt 40) { $s = $s.Substring(0, 40) }
    return $s
}

function Get-ShortUuid {
    return ([guid]::NewGuid().ToString("N").Substring(0, 8))
}

function Write-DefaultTaskPlan {
    param([string]$Path)
    @"
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
"@ | Out-File -FilePath $Path -Encoding UTF8
}

function Write-DefaultFindings {
    param([string]$Path)
    @"
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
"@ | Out-File -FilePath $Path -Encoding UTF8
}

function Write-DefaultProgress {
    param([string]$Path)
    @"
# Progress Log

## Session: $DATE

### Current Status
- **Phase:** 1 - Requirements & Discovery
- **Started:** $DATE

### Actions Taken
-

### Test Results
| Test | Expected | Actual | Status |
|------|----------|--------|--------|

### Errors
| Error | Resolution |
|-------|------------|
"@ | Out-File -FilePath $Path -Encoding UTF8
}

function Write-AnalyticsProgress {
    param([string]$Path)
    @"
# Progress Log

## Session: $DATE

### Current Status
- **Phase:** 1 - Data Discovery
- **Started:** $DATE

### Actions Taken
-

### Query Log
| Query | Result Summary | Interpretation |
|-------|---------------|----------------|

### Errors
| Error | Resolution |
|-------|------------|
"@ | Out-File -FilePath $Path -Encoding UTF8
}

function New-PlanFiles {
    param([string]$TargetDir)
    $planPath = Join-Path $TargetDir "task_plan.md"
    $findingsPath = Join-Path $TargetDir "findings.md"
    $progressPath = Join-Path $TargetDir "progress.md"

    if (-not (Test-Path $planPath)) {
        $analyticsPlan = Join-Path $TemplateDir "analytics_task_plan.md"
        if ($Template -eq "analytics" -and (Test-Path $analyticsPlan)) {
            Copy-Item $analyticsPlan $planPath
        } else {
            Write-DefaultTaskPlan $planPath
        }
        Write-Host "Created $planPath"
    } else {
        Write-Host "$planPath already exists, skipping"
    }

    if (-not (Test-Path $findingsPath)) {
        $analyticsFindings = Join-Path $TemplateDir "analytics_findings.md"
        if ($Template -eq "analytics" -and (Test-Path $analyticsFindings)) {
            Copy-Item $analyticsFindings $findingsPath
        } else {
            Write-DefaultFindings $findingsPath
        }
        Write-Host "Created $findingsPath"
    } else {
        Write-Host "$findingsPath already exists, skipping"
    }

    if (-not (Test-Path $progressPath)) {
        if ($Template -eq "analytics") {
            Write-AnalyticsProgress $progressPath
        } else {
            Write-DefaultProgress $progressPath
        }
        Write-Host "Created $progressPath"
    } else {
        Write-Host "$progressPath already exists, skipping"
    }
}

$slug = Get-Slug $ProjectName
if (-not $slug) {
    $slug = "untitled-$(Get-ShortUuid)"
}
$baseId = "$DATE-$slug"
$planId = $baseId
$planRoot = Join-Path (Get-Location) ".planning"
$counter = 2
while (Test-Path (Join-Path $planRoot $planId) -PathType Container) {
    $planId = "$baseId-$counter"
    $counter++
}
$planFolder = Join-Path $planRoot $planId
New-Item -ItemType Directory -Path $planFolder -Force | Out-Null

$displayName = if ($ProjectName) { $ProjectName } else { "untitled" }
Write-Host "Initializing planning files for: $displayName (template: $Template)"
Write-Host "Plan slug: $planId"
New-PlanFiles $planFolder
Write-Host ""
Write-Host "Plan directory: $planFolder"
