# Overview

<details>
<summary>Relevant source files</summary>

The following files were used as context for generating this wiki page:

- [.github/ISSUE_TEMPLATE.md](.github/ISSUE_TEMPLATE.md)
- [README.md](README.md)
- [main.py](main.py)

</details>



This document provides a high-level introduction to the DailyArXiv system, an automated research paper aggregation tool that fetches and organizes academic papers from arXiv based on predefined keywords. The system automatically generates two primary outputs: a comprehensive paper browser and daily notification summaries, all running on a scheduled automation pipeline.

For detailed information about the system's outputs and user interfaces, see [Output Formats & User Interfaces](#2). For technical implementation details, see [Core Implementation](#4). For automation and infrastructure, see [Automation & Infrastructure](#5).

## System Purpose and Architecture

The DailyArXiv system serves the research community by automatically collecting and organizing papers from three key domains: Time Series, Trajectory analysis, and Graph Neural Networks. The system operates entirely through GitHub's infrastructure, leveraging GitHub Actions for automation and GitHub Issues for notifications.

### High-Level System Architecture

```mermaid
graph TB
    subgraph "External Dependencies"
        arXiv["arXiv API<br/>export.arxiv.org/api/query"]
        GitHub["GitHub Platform<br/>Repository & Actions"]
    end
    
    subgraph "Core Processing"
        main_py["main.py<br/>Orchestration Script"]
        utils_py["utils.py<br/>API & Processing Utils"]
    end
    
    subgraph "Output Generation"
        README["README.md<br/>Comprehensive Paper Browser"]
        ISSUE_TEMPLATE[".github/ISSUE_TEMPLATE.md<br/>Daily Issue Summaries"]
    end
    
    subgraph "Automation Infrastructure"
        workflow[".github/workflows/<br/>Scheduled Execution"]
        cron["Beijing Time 00:30<br/>Daily Trigger"]
    end
    
    subgraph "Configuration"
        keywords["keywords = ['Time Series',<br/>'Trajectory',<br/>'Graph Neural Networks']"]
        limits["max_result = 100<br/>issues_result = 15"]
    end
    
    %% Processing Flow
    arXiv -->|"fetch papers"| utils_py
    utils_py -->|"processed data"| main_py
    main_py -->|"generate_table()"| README
    main_py -->|"generate_table()[:15]"| ISSUE_TEMPLATE
    
    %% Automation Flow  
    cron -->|"trigger"| workflow
    workflow -->|"execute"| main_py
    
    %% Configuration Flow
    keywords -->|"search terms"| main_py
    limits -->|"result limits"| main_py
    
    %% Backup System
    main_py -.->|"back_up_files()"| backup["File Backup System"]
    backup -.->|"restore_files()"| main_py
```

**Sources:** [main.py:1-73](), [README.md:1-11](), [.github/ISSUE_TEMPLATE.md:1-7]()

### Data Processing Pipeline

The system follows a clear data pipeline that transforms arXiv API responses into formatted markdown tables:

```mermaid
flowchart TD
    subgraph "Input Processing"
        keywords_input["keywords = ['Time Series',<br/>'Trajectory', 'Graph Neural Networks']"]
        config_input["max_result = 100<br/>issues_result = 15<br/>column_names = ['Title', 'Link',<br/>'Abstract', 'Date', 'Comment']"]
    end
    
    subgraph "Data Acquisition"
        api_call["get_daily_papers_by_keyword_with_retries()"]
        retry_logic["Retry mechanism<br/>with error handling"]
        xml_parse["feedparser XML processing"]
    end
    
    subgraph "Data Transformation"
        filter_tags["Filter by tags<br/>(cs.*, stat.*)"]
        format_papers["Format paper metadata<br/>(Title, Date, Abstract, etc.)"]
        generate_table_full["generate_table(papers)<br/>Full table with abstracts"]
        generate_table_brief["generate_table(papers[:15])<br/>Brief table without abstracts"]
    end
    
    subgraph "Output Files"
        readme_output["README.md<br/>~100 papers per keyword"]
        issue_output[".github/ISSUE_TEMPLATE.md<br/>~15 papers per keyword"]
    end
    
    subgraph "Safety Mechanisms"
        backup_system["back_up_files()<br/>restore_files()<br/>remove_backups()"]
        error_handling["sys.exit() on failure<br/>File restoration"]
    end
    
    %% Main flow
    keywords_input --> api_call
    config_input --> api_call
    api_call --> retry_logic
    retry_logic --> xml_parse
    xml_parse --> filter_tags
    filter_tags --> format_papers
    format_papers --> generate_table_full
    format_papers --> generate_table_brief
    generate_table_full --> readme_output
    generate_table_brief --> issue_output
    
    %% Safety flow
    backup_system -.->|"protect"| readme_output
    backup_system -.->|"protect"| issue_output
    error_handling -.->|"fallback"| backup_system
```

**Sources:** [main.py:25-73](), [utils.py]() (referenced in imports)

## Key System Components

### Primary Keywords and Search Strategy

The system focuses on three research domains defined in [main.py:25]():

| Keyword | Search Logic | Purpose |
|---------|-------------|---------|
| `Time Series` | `OR` logic | Multi-word terms use OR between words |
| `Trajectory` | `AND` logic | Single words search title AND abstract |
| `Graph Neural Networks` | `OR` logic | Multi-word terms use OR between words |

The search logic is determined by [main.py:53-54]() where single words use `AND` logic while multi-word phrases use `OR` logic.

### Output Limits and Constraints

The system operates with two distinct output limits configured in [main.py:27-28]():

- **`max_result = 100`**: Maximum papers fetched from arXiv API per keyword for README.md
- **`issues_result = 15`**: Maximum papers included in GitHub issue templates

### File Management and Safety

The system implements a robust backup mechanism through three key functions:

```mermaid
graph LR
    subgraph "File Operations"
        backup["back_up_files()"]
        restore["restore_files()"] 
        cleanup["remove_backups()"]
    end
    
    subgraph "Protected Files"
        readme_file["README.md"]
        issue_file[".github/ISSUE_TEMPLATE.md"]
    end
    
    subgraph "Error Handling"
        success_path["Successful execution"]
        failure_path["API failure or error"]
    end
    
    backup -->|"create backups"| readme_file
    backup -->|"create backups"| issue_file
    
    success_path --> cleanup
    failure_path --> restore
    
    restore -->|"restore from backup"| readme_file
    restore -->|"restore from backup"| issue_file
```

**Sources:** [main.py:35](), [main.py:60](), [main.py:72]()

## Temporal Execution Pattern

The system operates on a strict daily schedule configured in the GitHub Actions workflow:

### Daily Execution Cycle

```mermaid
timeline
    title Daily Paper Aggregation Timeline (Beijing Time)
    
    section Pre-Execution
        00:00-00:29 : Quiet Period
                    : No system activity
    
    section Execution Window
        00:30 : Cron Trigger
              : GitHub Actions activation
              : Environment setup
        
        00:31-00:35 : Paper Collection
                    : get_daily_papers_by_keyword_with_retries()
                    : Process each keyword sequentially
                    : 5-second delays between keywords
        
        00:36-00:40 : Table Generation  
                    : generate_table() for README
                    : generate_table()[:15] for issues
                    : File writing operations
    
    section Post-Processing
        00:41+ : Cleanup & Notification
               : remove_backups()
               : Git commit and push
               : GitHub issue creation
```

The 5-second delay between keyword processing is implemented in [main.py:68]() to avoid being blocked by the arXiv API.

**Sources:** [main.py:68](), [main.py:15]() (Beijing timezone), GitHub Actions workflow (referenced in automation)

## Date Handling and Updates

The system uses Beijing timezone for all date operations and includes update tracking:

- **Current date calculation**: [main.py:15]() using `pytz.timezone('Asia/Shanghai')`
- **Last update tracking**: [main.py:17-21]() reads from existing README.md
- **Date formatting**: [main.py:40]() and [main.py:45]() for output files

The system writes the current date to both output files to track when the data was last refreshed, providing transparency to users about data freshness.

**Sources:** [main.py:10](), [main.py:15](), [main.py:40](), [main.py:45]()

---