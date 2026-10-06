# Daily Issue Templates

<details>
<summary>Relevant source files</summary>

The following files were used as context for generating this wiki page:

- [.github/ISSUE_TEMPLATE.md](.github/ISSUE_TEMPLATE.md)

</details>



This page documents the GitHub issue template system used for daily paper summary notifications in the DailyArXiv system. The issue template provides a condensed view of the latest research papers, optimized for notifications and quick browsing. For comprehensive paper browsing with full abstracts and extended listings, see [Paper Browser (README.md)](#2.1).

## Purpose and Structure

The daily issue template serves as a notification mechanism that automatically creates GitHub issues containing a curated summary of the latest research papers. Unlike the comprehensive README format, the issue template is designed for:

- **Limited paper count**: Approximately 15 papers per research category
- **Notification delivery**: Integration with GitHub's watch/subscription system
- **Quick scanning**: Condensed format without full abstracts
- **Email distribution**: Automatic email notifications to subscribers

## Template Format and Organization

The issue template follows a structured markdown format organized into three primary research categories:

```mermaid
graph TD
    subgraph "ISSUE_TEMPLATE.md Structure"
        HEADER["Issue Header"]
        HEADER --> META["Metadata: title, labels, date"]
        HEADER --> NOTICE["GitHub Repository Link Notice"]
        
        NOTICE --> TS_SECTION["Time Series Section"]
        NOTICE --> TRAJ_SECTION["Trajectory Section"] 
        NOTICE --> GNN_SECTION["Graph Neural Networks Section"]
        
        TS_SECTION --> TS_TABLE["| Title | Date | Comment |"]
        TRAJ_SECTION --> TRAJ_TABLE["| Title | Date | Comment |"]
        GNN_SECTION --> GNN_TABLE["| Title | Date | Comment |"]
        
        TS_TABLE --> TS_PAPERS["~15 Latest Papers"]
        TRAJ_TABLE --> TRAJ_PAPERS["~15 Latest Papers"]
        GNN_TABLE --> GNN_PAPERS["~15 Latest Papers"]
    end
    
    style HEADER fill:#f9f9f9
    style TS_SECTION fill:#e8f5e8
    style TRAJ_SECTION fill:#fff3e0
    style GNN_SECTION fill:#f3e5f5
```

Sources: [.github/ISSUE_TEMPLATE.md:1-64]()

### Header Structure

The template begins with YAML front matter containing metadata:

| Field | Purpose | Example |
|-------|---------|---------|
| `title` | Issue title with date | "Latest 15 Papers - May 30, 2025" |
| `labels` | Issue categorization | "documentation" |

The header also includes a redirect notice pointing users to the main repository for enhanced reading experience and complete paper listings.

Sources: [.github/ISSUE_TEMPLATE.md:1-6]()

### Research Category Tables

Each research category contains a markdown table with three columns:

```mermaid
graph LR
    subgraph "Table Structure"
        TITLE_COL["Title Column"]
        DATE_COL["Date Column"]
        COMMENT_COL["Comment Column"]
        
        TITLE_COL --> PAPER_LINK["arXiv Paper Link"]
        TITLE_COL --> PAPER_TITLE["Paper Title"]
        
        DATE_COL --> SUBMIT_DATE["Submission Date (YYYY-MM-DD)"]
        
        COMMENT_COL --> DETAILS_TAG["<details> Collapsible Sections"]
        COMMENT_COL --> VENUE_INFO["Conference/Journal Information"]
        COMMENT_COL --> META_INFO["Page Count, Figures, etc."]
    end
```

Sources: [.github/ISSUE_TEMPLATE.md:8-63]()

## Data Processing and Generation Pipeline

The issue template generation follows a streamlined process optimized for brevity and notification delivery:

```mermaid
flowchart TD
    subgraph "Input Processing"
        ARXIV_DATA["arXiv API Response"]
        FILTER_LOGIC["Tag Filtering (cs.*, stat.*)"]
        LIMIT_CONFIG["issues_result: 15"]
    end
    
    subgraph "Template Generation"
        BRIEF_FORMAT["Brief Table Generation"]
        NO_ABSTRACTS["Abstract Exclusion"]
        COLLAPSIBLE["Comment Collapsing"]
    end
    
    subgraph "Output System"
        TEMPLATE_FILE[".github/ISSUE_TEMPLATE.md"]
        GITHUB_ISSUE["GitHub Issue Creation"]
        EMAIL_NOTIFY["Email Notifications"]
    end
    
    ARXIV_DATA --> FILTER_LOGIC
    FILTER_LOGIC --> LIMIT_CONFIG
    LIMIT_CONFIG --> BRIEF_FORMAT
    BRIEF_FORMAT --> NO_ABSTRACTS
    NO_ABSTRACTS --> COLLAPSIBLE
    COLLAPSIBLE --> TEMPLATE_FILE
    TEMPLATE_FILE --> GITHUB_ISSUE
    GITHUB_ISSUE --> EMAIL_NOTIFY
```

Sources: [.github/ISSUE_TEMPLATE.md:1-64]()

### Key Differences from README Format

| Aspect | Issue Template | README Browser |
|--------|---------------|----------------|
| Paper Count | ~15 per category | ~40 per category |
| Abstracts | Excluded | Full abstracts included |
| Comments | Collapsible `<details>` tags | Full text display |
| Update Frequency | Daily via GitHub Issues | Daily via file commits |
| Notification Method | Email subscriptions | Repository watching |

## User Interaction and Notification Mechanisms

The issue template system integrates with GitHub's native notification infrastructure:

```mermaid
graph TB
    subgraph "User Subscription Flow"
        REPO_WATCH["Repository Watch Settings"]
        ISSUE_WATCH["Issues Notification Enabled"]
        EMAIL_PREF["Email Preferences"]
    end
    
    subgraph "Automated Generation"
        DAILY_CRON["Daily Cron Trigger (00:30 Beijing)"]
        TEMPLATE_UPDATE["ISSUE_TEMPLATE.md Update"]
        ISSUE_CREATE["GitHub Issue Creation"]
    end
    
    subgraph "Notification Delivery"
        GITHUB_NOTIFY["GitHub Notification System"]
        EMAIL_DELIVERY["Email Delivery Service"]
        USER_INBOX["User Email Inbox"]
    end
    
    REPO_WATCH --> ISSUE_WATCH
    ISSUE_WATCH --> EMAIL_PREF
    
    DAILY_CRON --> TEMPLATE_UPDATE
    TEMPLATE_UPDATE --> ISSUE_CREATE
    
    ISSUE_CREATE --> GITHUB_NOTIFY
    GITHUB_NOTIFY --> EMAIL_DELIVERY
    EMAIL_DELIVERY --> USER_INBOX
    
    EMAIL_PREF -.->|Configuration| EMAIL_DELIVERY
```

Sources: [.github/ISSUE_TEMPLATE.md:5-6]()

### Comment Formatting and Collapsible Content

The template uses HTML `<details>` tags to make lengthy comments collapsible, improving readability while preserving information:

```markdown
<details><summary>Accep...</summary><p>Accepted as a full paper at ICLR 2025 (top 5% of scores) in Singapore</p></details>
```

This approach allows users to:
- Quickly scan paper titles and dates
- Expand comments for additional context when needed
- Maintain clean visual formatting in email notifications

Sources: [.github/ISSUE_TEMPLATE.md:10-62]()

## Integration with GitHub Ecosystem

The issue template system leverages several GitHub features for seamless operation:

| GitHub Feature | Purpose | Implementation |
|---------------|---------|----------------|
| Issue Templates | Standardized formatting | `.github/ISSUE_TEMPLATE.md` |
| Issue Creation | Daily notifications | Automated via GitHub Actions |
| Watch System | User subscriptions | Native GitHub functionality |
| Email Integration | Notification delivery | GitHub's email service |
| Labels | Content categorization | `documentation` label |

The system creates a new issue daily, allowing users to receive consistent notifications while maintaining a searchable history of daily paper summaries.

Sources: [.github/ISSUE_TEMPLATE.md:1-4]()

---