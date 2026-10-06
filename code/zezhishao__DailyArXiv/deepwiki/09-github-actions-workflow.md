# GitHub Actions Workflow

<details>
<summary>Relevant source files</summary>

The following files were used as context for generating this wiki page:

- [.github/workflows/update.yaml](.github/workflows/update.yaml)

</details>



This document provides detailed documentation of the automated GitHub Actions workflow that orchestrates the daily paper aggregation process. The workflow is responsible for scheduling, executing, and deploying the paper collection pipeline, handling all automation aspects of the DailyArXiv system.

For information about the core processing logic executed by this workflow, see [Main Processing Pipeline](#4.1). For details about system dependencies managed by this workflow, see [Dependencies & Configuration](#5.2).

## Workflow Overview

The GitHub Actions workflow is defined in [.github/workflows/update.yaml:1-48]() and serves as the primary automation engine for the DailyArXiv system. It operates on a scheduled basis to fetch, process, and publish research papers automatically without manual intervention.

### Workflow Configuration

| Property | Value | Purpose |
|----------|-------|---------|
| **Name** | `Update` | Workflow identifier in GitHub Actions |
| **Runner** | `ubuntu-latest` | Execution environment |
| **Python Version** | `3.9` | Runtime version for processing scripts |
| **Schedule** | `30 16 * * 0-4` | Monday-Friday at 00:30 Beijing time |
| **Permissions** | `contents: write`, `issues: write` | Repository modification rights |

**Workflow Execution Timeline**

```mermaid
timeline
    title GitHub Actions Workflow Execution
    
    section Trigger Phase
        00:30 Beijing : Cron Schedule Activates
                     : "30 16 * * 0-4" UTC trigger
                     : Workflow "Update" starts
        
    section Environment Setup
        Step 1 : Checkout Repository
              : "actions/checkout@v3"
              : Clone master branch
        
        Step 2 : Python Environment
              : "actions/setup-python@v4" 
              : Install Python 3.9
        
        Step 3 : Dependencies
              : "pip install -r requirements.txt"
              : Load required packages
        
    section Core Processing
        Step 4 : Execute Pipeline
              : "python main.py"
              : Run paper collection
              : Generate output files
        
    section Deployment
        Step 5 : Commit Changes
              : "github-actions-x/commit@v2.9"
              : Push README.md updates
              : Push ISSUE_TEMPLATE.md updates
        
        Step 6 : User Notification
              : "JasonEtco/create-an-issue@v2"
              : Create GitHub issue
              : Trigger email notifications
```

Sources: [.github/workflows/update.yaml:1-48]()

## Trigger Mechanisms

The workflow supports two trigger mechanisms for different operational scenarios:

### Scheduled Execution

The primary trigger uses a cron schedule defined at [.github/workflows/update.yaml:7-8]():

```
schedule:
  - cron: '30 16 * * 0-4' # 00:30 Beijing time every Monday to Friday
```

This schedule translates to:
- **UTC Time**: 16:30 (4:30 PM)
- **Beijing Time**: 00:30 (12:30 AM next day)
- **Frequency**: Monday through Friday only
- **Weekend Behavior**: No automatic execution on weekends

### Manual Testing Trigger

A secondary trigger mechanism exists for testing purposes at [.github/workflows/update.yaml:4-6]():

```
label:
  types:
    - created # for test
```

This allows manual workflow execution when labels are created on issues or pull requests.

**Trigger Integration Diagram**

```mermaid
flowchart TD
    subgraph "External Triggers"
        CRON["Cron Schedule<br/>30 16 * * 0-4"]
        LABEL["Label Creation<br/>Manual Testing"]
    end
    
    subgraph "GitHub Actions Engine"
        WORKFLOW["update.yaml<br/>Workflow Definition"]
        RUNNER["ubuntu-latest<br/>Execution Environment"]
    end
    
    subgraph "Processing Pipeline"
        CHECKOUT["actions/checkout@v3<br/>Repository Access"]
        PYTHON["actions/setup-python@v4<br/>Python 3.9 Runtime"]
        DEPS["pip install<br/>requirements.txt"]
        MAIN["python main.py<br/>Core Processing"]
    end
    
    subgraph "Output Actions"
        COMMIT["github-actions-x/commit@v2.9<br/>File Updates"]
        ISSUE["JasonEtco/create-an-issue@v2<br/>Notifications"]
    end
    
    CRON --> WORKFLOW
    LABEL --> WORKFLOW
    WORKFLOW --> RUNNER
    RUNNER --> CHECKOUT
    CHECKOUT --> PYTHON
    PYTHON --> DEPS
    DEPS --> MAIN
    MAIN --> COMMIT
    MAIN --> ISSUE
    
    COMMIT --> FILES["README.md<br/>.github/ISSUE_TEMPLATE.md"]
    ISSUE --> NOTIFY["GitHub Issue<br/>Email Notifications"]
```

Sources: [.github/workflows/update.yaml:3-8]()

## Job Configuration and Permissions

### Security Permissions

The workflow requires specific permissions defined at [.github/workflows/update.yaml:10-12]():

| Permission | Scope | Purpose |
|------------|-------|---------|
| `contents: write` | Repository files | Modify README.md and ISSUE_TEMPLATE.md |
| `issues: write` | GitHub issues | Create notification issues |

### Job Definition

The single job `update_daily_papers` is configured at [.github/workflows/update.yaml:15-16]() with:
- **Runner**: `ubuntu-latest` for reliable Linux environment
- **Isolation**: Each execution runs in a fresh container
- **Concurrency**: Single job execution prevents conflicts

Sources: [.github/workflows/update.yaml:10-16]()

## Step-by-Step Execution Flow

### Step 1: Repository Checkout

[.github/workflows/update.yaml:18-19]() configures repository access:

```yaml
- name: Checkout repository
  uses: actions/checkout@v3
```

This step:
- Clones the repository to the runner filesystem
- Provides access to source code and configuration files
- Uses the stable `v3` version of the checkout action

### Step 2: Python Environment Setup

[.github/workflows/update.yaml:21-24]() establishes the runtime environment:

```yaml
- name: Set up Python
  uses: actions/setup-python@v4
  with:
    python-version: '3.9'
```

Key aspects:
- **Version Pinning**: Python 3.9 for consistent behavior
- **Package Manager**: pip is available for dependency installation
- **Virtual Environment**: Isolated from system packages

### Step 3: Dependency Installation

[.github/workflows/update.yaml:26-27]() installs required packages:

```yaml
- name: Install dependencies
  run: pip install -r requirements.txt
```

This step loads all Python packages needed for the processing pipeline as defined in the requirements.txt file.

### Step 4: Core Processing Execution

[.github/workflows/update.yaml:29-31]() runs the main processing logic:

```yaml
- name: Update papers
  run: |
    python main.py
```

This executes the core paper collection and processing pipeline documented in [Main Processing Pipeline](#4.1).

### Step 5: File Commitment and Deployment

[.github/workflows/update.yaml:33-42]() handles output file management:

```yaml
- name: Commit and push changes
  uses: github-actions-x/commit@v2.9
  with:
    github-token: ${{ secrets.GITHUB_TOKEN }}
    push-branch: 'master'
    commit-message: '✏️ Update papers automatically.'
    force-add: 'true'
    files: README.md .github/ISSUE_TEMPLATE.md
    name: Zezhishao
    email: 864453277@qq.com
```

Configuration details:
- **Target Branch**: `master` for production deployment
- **Files**: Only README.md and ISSUE_TEMPLATE.md are committed
- **Force Add**: Ensures files are included even if gitignored
- **Author Identity**: Consistent commit attribution

### Step 6: User Notification

[.github/workflows/update.yaml:44-47]() creates user notifications:

```yaml
- name: Create an issue to notify
  uses: JasonEtco/create-an-issue@v2
  env:
    GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

This step creates a GitHub issue that triggers email notifications to repository watchers.

**Step Execution Flow Diagram**

```mermaid
flowchart TD
    subgraph "GitHub Actions Runner ubuntu-latest"
        START["Workflow Start<br/>update_daily_papers job"]
        
        STEP1["actions/checkout@v3<br/>Clone Repository"]
        STEP2["actions/setup-python@v4<br/>Install Python 3.9"]
        STEP3["pip install -r requirements.txt<br/>Load Dependencies"]
        STEP4["python main.py<br/>Execute Processing"]
        STEP5["github-actions-x/commit@v2.9<br/>Commit Files"]
        STEP6["JasonEtco/create-an-issue@v2<br/>Create Notification"]
        
        END["Workflow Complete"]
    end
    
    subgraph "File System"
        REPO["Repository Files<br/>Source Code"]
        REQ["requirements.txt<br/>Dependencies"]
        MAIN["main.py<br/>Processing Script"]
        OUTPUT["README.md<br/>ISSUE_TEMPLATE.md"]
    end
    
    subgraph "GitHub Platform"
        MASTER["master branch<br/>Production"]
        ISSUES["GitHub Issues<br/>Notifications"]
        EMAIL["Email System<br/>User Notifications"]
    end
    
    START --> STEP1
    STEP1 --> REPO
    STEP1 --> STEP2
    STEP2 --> STEP3
    STEP3 --> REQ
    STEP3 --> STEP4
    STEP4 --> MAIN
    STEP4 --> OUTPUT
    STEP4 --> STEP5
    STEP5 --> MASTER
    STEP5 --> STEP6
    STEP6 --> ISSUES
    STEP6 --> END
    
    ISSUES --> EMAIL
```

Sources: [.github/workflows/update.yaml:17-48]()

## Integration with System Components

The GitHub Actions workflow serves as the orchestration layer that connects all system components:

### Input Dependencies

- **Source Code**: Main processing scripts accessed via checkout
- **Configuration**: requirements.txt and embedded parameters
- **Scheduling**: Cron-based timing for regular execution

### Output Targets

- **Repository Files**: README.md and ISSUE_TEMPLATE.md updates
- **Version Control**: Automatic git commits to master branch
- **User Interface**: GitHub issue creation for notifications

### External Service Integration

**System Integration Map**

```mermaid
graph TB
    subgraph "GitHub Actions Workflow"
        WORKFLOW["update.yaml<br/>Workflow Definition"]
        JOB["update_daily_papers<br/>Job Execution"]
    end
    
    subgraph "Processing Components"
        MAIN_PY["main.py<br/>Orchestration Script"]
        UTILS_PY["utils.py<br/>API Functions"]
        DEPS["requirements.txt<br/>Package Dependencies"]
    end
    
    subgraph "Output Files"
        README["README.md<br/>Paper Browser"]
        TEMPLATE[".github/ISSUE_TEMPLATE.md<br/>Daily Summary"]
    end
    
    subgraph "GitHub Platform"
        ACTIONS["GitHub Actions<br/>Execution Engine"]
        REPO["Repository<br/>File Storage"]
        ISSUES_SYS["Issues System<br/>Notifications"]
    end
    
    subgraph "External APIs"
        ARXIV["arXiv API<br/>Paper Source"]
        EMAIL_SVC["Email Service<br/>User Notifications"]
    end
    
    WORKFLOW --> ACTIONS
    ACTIONS --> JOB
    JOB --> MAIN_PY
    MAIN_PY --> UTILS_PY
    UTILS_PY --> ARXIV
    
    JOB --> DEPS
    MAIN_PY --> README
    MAIN_PY --> TEMPLATE
    
    JOB --> REPO
    JOB --> ISSUES_SYS
    ISSUES_SYS --> EMAIL_SVC
    
    README --> REPO
    TEMPLATE --> REPO
```

Sources: [.github/workflows/update.yaml:1-48]()

## Error Handling and Monitoring

### Failure Modes

The workflow includes several points where failures can occur:

1. **Network Issues**: arXiv API unavailability during paper fetching
2. **Processing Errors**: Python script exceptions in main.py execution
3. **Git Conflicts**: Concurrent modifications to target files
4. **Permission Issues**: GitHub token or repository access problems

### Built-in Resilience

- **Atomic Operations**: Each step completes fully or fails completely
- **Clean Environment**: Fresh runner for each execution eliminates state issues
- **Force Add**: Ensures file updates succeed even with git conflicts
- **Token Authentication**: Automatic GitHub token management

### Monitoring Capabilities

GitHub Actions provides built-in monitoring through:
- **Execution Logs**: Detailed step-by-step output capture
- **Failure Notifications**: Email alerts for workflow failures
- **History Tracking**: Complete execution history and timing data
- **Manual Retry**: Ability to re-run failed workflows

Sources: [.github/workflows/update.yaml:33-42]()

---