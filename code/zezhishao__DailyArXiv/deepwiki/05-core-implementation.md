# Core Implementation

<details>
<summary>Relevant source files</summary>

The following files were used as context for generating this wiki page:

- [main.py](main.py)
- [utils.py](utils.py)

</details>



This document provides detailed technical documentation of the processing logic, API interactions, and data transformation pipeline that powers the DailyArXiv system. It covers the core implementation components that fetch, process, and format research papers from arXiv.

For specific details about the main orchestration workflow, see [Main Processing Pipeline](#4.1). For comprehensive coverage of utility functions and API integration patterns, see [Utility Functions & API Integration](#4.2). For higher-level system design, see [System Architecture](#3).

## Processing Architecture

The core implementation consists of two primary modules that work together to transform arXiv API responses into formatted markdown outputs. The system employs a pipeline architecture where data flows through distinct processing stages.

### Core Data Processing Pipeline

```mermaid
flowchart TD
    subgraph "Configuration Layer"
        keywords["keywords = ['Time Series', 'Trajectory', 'Graph Neural Networks']"]
        max_result["max_result = 100"]
        issues_result["issues_result = 15"]
        column_names["column_names = ['Title', 'Link', 'Abstract', 'Date', 'Comment']"]
    end
    
    subgraph "API Layer"
        request_paper_with_arXiv_api["request_paper_with_arXiv_api()"]
        arxiv_response["arXiv XML Response"]
        feedparser_parse["feedparser.parse()"]
    end
    
    subgraph "Data Processing Layer"
        filter_tags["filter_tags()"]
        get_daily_papers_by_keyword["get_daily_papers_by_keyword()"]
        get_daily_papers_by_keyword_with_retries["get_daily_papers_by_keyword_with_retries()"]
    end
    
    subgraph "Output Generation Layer"
        generate_table_full["generate_table() - Full"]
        generate_table_brief["generate_table() - Brief"]
        readme_output["README.md"]
        issue_output["ISSUE_TEMPLATE.md"]
    end
    
    subgraph "File Management Layer"
        back_up_files["back_up_files()"]
        restore_files["restore_files()"]
        remove_backups["remove_backups()"]
    end
    
    keywords --> get_daily_papers_by_keyword_with_retries
    max_result --> request_paper_with_arXiv_api
    column_names --> get_daily_papers_by_keyword
    
    get_daily_papers_by_keyword_with_retries --> get_daily_papers_by_keyword
    get_daily_papers_by_keyword --> request_paper_with_arXiv_api
    request_paper_with_arXiv_api --> arxiv_response
    arxiv_response --> feedparser_parse
    feedparser_parse --> filter_tags
    filter_tags --> generate_table_full
    filter_tags --> generate_table_brief
    
    back_up_files --> readme_output
    back_up_files --> issue_output
    generate_table_full --> readme_output
    generate_table_brief --> issue_output
    
    readme_output --> remove_backups
    issue_output --> remove_backups
    
    restore_files -.->|"On Error"| readme_output
    restore_files -.->|"On Error"| issue_output
```

**Sources:** [main.py:25-28](), [main.py:33](), [main.py:55](), [main.py:62-63](), [utils.py:16](), [utils.py:49](), [utils.py:60](), [utils.py:70](), [utils.py:80]()

### Paper Data Structure Transformation

The system transforms raw arXiv API responses through multiple data structure conversions to produce the final markdown output.

```mermaid
flowchart LR
    subgraph "Raw arXiv Response"
        xml_entry["XML Entry"]
        title_raw["entry.title"]
        summary_raw["entry.summary"]
        authors_raw["entry.authors[]"]
        link_raw["entry.link"]
        tags_raw["entry.tags[]"]
        comment_raw["entry.arxiv_comment"]
        updated_raw["entry.updated"]
    end
    
    subgraph "EasyDict Paper Object"
        paper_title["paper.Title"]
        paper_abstract["paper.Abstract"]
        paper_authors["paper.Authors[]"]
        paper_link["paper.Link"]
        paper_tags["paper.Tags[]"]
        paper_comment["paper.Comment"]
        paper_date["paper.Date"]
    end
    
    subgraph "Filtered Paper Object"
        filtered_columns["Selected Columns Only"]
        cs_stat_tags["cs.* and stat.* Tags Only"]
    end
    
    subgraph "Formatted Table Object"
        formatted_title["**[Title](Link)**"]
        formatted_date["YYYY-MM-DD"]
        formatted_abstract["<details><summary>Show</summary><p>Abstract</p></details>"]
        formatted_authors["First Author et al."]
        formatted_comment["Truncated or Collapsed"]
    end
    
    xml_entry --> paper_title
    title_raw --> paper_title
    summary_raw --> paper_abstract
    authors_raw --> paper_authors
    link_raw --> paper_link
    tags_raw --> paper_tags
    comment_raw --> paper_comment
    updated_raw --> paper_date
    
    paper_title --> filtered_columns
    paper_abstract --> filtered_columns
    paper_tags --> cs_stat_tags
    
    filtered_columns --> formatted_title
    filtered_columns --> formatted_date
    filtered_columns --> formatted_abstract
    filtered_columns --> formatted_authors
    filtered_columns --> formatted_comment
```

**Sources:** [utils.py:27-46](), [utils.py:49-58](), [utils.py:77](), [utils.py:80-126]()

## API Integration Layer

### arXiv API Query Construction

The system constructs specialized queries for the arXiv API that search both titles and abstracts for specified keywords. The query logic uses different linking strategies based on keyword complexity.

| Parameter | Value | Purpose |
|-----------|-------|---------|
| `search_query` | `ti:"keyword"+OR/AND+abs:"keyword"` | Searches both title and abstract fields |
| `max_results` | 100 (configurable) | Limits results per query |
| `sortBy` | `lastUpdatedDate` | Ensures recent papers appear first |
| `link` | `OR` (multi-word) / `AND` (single-word) | Controls keyword matching strategy |

The URL construction in `request_paper_with_arXiv_api()` creates properly encoded queries:

**Sources:** [utils.py:16-23](), [main.py:53-54]()

### Response Processing and Error Handling

The system implements a robust retry mechanism to handle arXiv API inconsistencies. The `get_daily_papers_by_keyword_with_retries()` function provides automatic retry logic with exponential backoff.

```mermaid
flowchart TD
    start["get_daily_papers_by_keyword_with_retries()"]
    attempt["Attempt API Call"]
    check_results["len(papers) > 0?"]
    success["Return papers"]
    wait["time.sleep(60 * 30)"]
    retry_check["retries < 6?"]
    fail_return["return None"]
    
    start --> attempt
    attempt --> check_results
    check_results -->|"Yes"| success
    check_results -->|"No"| wait
    wait --> retry_check
    retry_check -->|"Yes"| attempt
    retry_check -->|"No"| fail_return
```

**Sources:** [utils.py:60-68](), [main.py:56-61]()

## Data Filtering and Processing

### Tag-Based Filtering

The `filter_tags()` function implements subject area filtering to focus on computer science and statistics papers. It examines the tag prefix before the first dot to determine subject classification.

```python
# Filtering logic from utils.py:49-58
target_fields = ["cs", "stat"]  # Computer Science and Statistics
for tag in paper.Tags:
    if tag.split(".")[0] in target_fields:
        # Paper belongs to target subject area
        results.append(paper)
        break
```

**Sources:** [utils.py:49-58]()

### Column Selection and Data Cleaning

The system processes raw paper data through several cleaning operations:

| Function | Operation | Purpose |
|----------|-----------|---------|
| `remove_duplicated_spaces()` | Normalize whitespace | Clean up formatting inconsistencies |
| Column selection | Extract specified fields only | Reduce data to required columns |
| Date formatting | Convert ISO format to YYYY-MM-DD | Standardize date display |

**Sources:** [utils.py:13-14](), [utils.py:77](), [utils.py:89]()

## Output Generation Engine

### Markdown Table Generation

The `generate_table()` function converts processed paper data into markdown tables with specialized formatting for different content types. It handles dual output modes: full tables for README.md and brief tables for issue templates.

```mermaid
flowchart TD
    subgraph "Input Processing"
        papers_input["List[Dict[str, str]] papers"]
        ignore_keys["ignore_keys parameter"]
    end
    
    subgraph "Formatting Rules"
        title_format["Title: **[Title](Link)**"]
        date_format["Date: YYYY-MM-DD"]
        abstract_format["Abstract: <details> collapsible"]
        authors_format["Authors: First Author et al."]
        comment_format["Comment: Truncated if long"]
    end
    
    subgraph "Table Structure"
        header_gen["Generate Header Row"]
        separator_gen["Generate Separator Row"]
        body_gen["Generate Data Rows"]
    end
    
    subgraph "Output"
        markdown_table["Markdown Table String"]
    end
    
    papers_input --> title_format
    papers_input --> date_format
    papers_input --> abstract_format
    papers_input --> authors_format
    papers_input --> comment_format
    
    ignore_keys --> abstract_format
    
    title_format --> header_gen
    date_format --> header_gen
    abstract_format --> header_gen
    authors_format --> header_gen
    comment_format --> header_gen
    
    header_gen --> separator_gen
    separator_gen --> body_gen
    body_gen --> markdown_table
```

**Sources:** [utils.py:80-126](), [main.py:62-63]()

### File Management and Safety Mechanisms

The system implements a comprehensive backup and restore mechanism to ensure data integrity during file operations.

| Function | Purpose | Files Affected |
|----------|---------|----------------|
| `back_up_files()` | Create safety copies | README.md → README.md.bk<br/>ISSUE_TEMPLATE.md → ISSUE_TEMPLATE.md.bk |
| `restore_files()` | Rollback on error | Restore from .bk files |
| `remove_backups()` | Cleanup after success | Delete .bk files |

**Sources:** [utils.py:128-141](), [main.py:35](), [main.py:60](), [main.py:72]()

## Configuration and Parameters

The core implementation uses several key configuration parameters that control system behavior:

| Parameter | Location | Value | Impact |
|-----------|----------|-------|---------|
| `keywords` | [main.py:25]() | `["Time Series", "Trajectory", "Graph Neural Networks"]` | Determines search scope |
| `max_result` | [main.py:27]() | `100` | API query limit per keyword |
| `issues_result` | [main.py:28]() | `15` | Papers included in issue templates |
| `column_names` | [main.py:33]() | `["Title", "Link", "Abstract", "Date", "Comment"]` | Output table structure |
| `beijing_timezone` | [main.py:10]() | `Asia/Shanghai` | Timezone for date operations |

**Sources:** [main.py:25-33](), [main.py:10]()

---