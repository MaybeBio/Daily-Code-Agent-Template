# Main Processing Pipeline

<details>
<summary>Relevant source files</summary>

The following files were used as context for generating this wiki page:

- [main.py](main.py)

</details>



## Purpose and Scope

This document covers the main orchestration script that coordinates the daily paper aggregation process. The pipeline is implemented in `main.py` and serves as the central controller that fetches papers, processes them, and generates output files. For detailed information about the utility functions and API integration used by this pipeline, see [Utility Functions & API Integration](#4.2). For information about the output formats produced by this pipeline, see [Output Formats & User Interfaces](#2).

The main processing pipeline handles:
- Daily execution coordination and date validation
- Sequential processing of research keywords
- Dual output generation for different user interfaces
- Error handling and file backup/restore operations
- Rate limiting and API interaction management

## Pipeline Overview

The main processing pipeline follows a sequential workflow that processes each keyword independently and generates two distinct output formats.

```mermaid
flowchart TD
    START["main.py execution starts"]
    INIT["beijing_timezone = pytz.timezone('Asia/Shanghai')"]
    DATE_CHECK["current_date = datetime.now(beijing_timezone)"]
    READ_LAST["Read last update date from README.md"]
    
    CONFIG["keywords = ['Time Series', 'Trajectory', 'Graph Neural Networks']<br/>max_result = 100<br/>issues_result = 15"]
    
    BACKUP["back_up_files()"]
    OPEN_FILES["Open README.md and ISSUE_TEMPLATE.md for writing"]
    WRITE_HEADERS["Write file headers with current_date"]
    
    LOOP_START["for keyword in keywords:"]
    SET_LINK["Determine link type: 'AND' or 'OR'"]
    GET_PAPERS["get_daily_papers_by_keyword_with_retries()"]
    CHECK_PAPERS{"papers is None?"}
    
    GEN_TABLES["rm_table = generate_table(papers)<br/>is_table = generate_table(papers[:issues_result])"]
    WRITE_TABLES["Write tables to both files"]
    SLEEP["time.sleep(5)"]
    
    NEXT_KEYWORD["Next keyword"]
    CLOSE_FILES["Close both output files"]
    CLEANUP["remove_backups()"]
    END["Pipeline complete"]
    
    ERROR_HANDLE["restore_files()<br/>sys.exit('Failed to get papers!')"]
    
    START --> INIT
    INIT --> DATE_CHECK
    DATE_CHECK --> READ_LAST
    READ_LAST --> CONFIG
    CONFIG --> BACKUP
    BACKUP --> OPEN_FILES
    OPEN_FILES --> WRITE_HEADERS
    WRITE_HEADERS --> LOOP_START
    LOOP_START --> SET_LINK
    SET_LINK --> GET_PAPERS
    GET_PAPERS --> CHECK_PAPERS
    CHECK_PAPERS -->|Yes| ERROR_HANDLE
    CHECK_PAPERS -->|No| GEN_TABLES
    GEN_TABLES --> WRITE_TABLES
    WRITE_TABLES --> SLEEP
    SLEEP --> NEXT_KEYWORD
    NEXT_KEYWORD -->|More keywords| LOOP_START
    NEXT_KEYWORD -->|Complete| CLOSE_FILES
    CLOSE_FILES --> CLEANUP
    CLEANUP --> END
```

**Sources:** [main.py:1-73]()

## Initialization and Configuration

The pipeline begins with timezone configuration and parameter setup. The system operates on Beijing time to ensure consistent daily scheduling.

### Timezone and Date Handling

```mermaid
graph LR
    TIMEZONE["beijing_timezone"]
    CURRENT["current_date"]
    LAST["last_update_date"]
    README["README.md"]
    
    TIMEZONE -->|"pytz.timezone('Asia/Shanghai')"| CURRENT
    CURRENT -->|"datetime.now(beijing_timezone).strftime('%Y-%m-%d')"| COMPARISON["Date comparison logic"]
    README -->|"Read line with 'Last update:'"| LAST
    LAST --> COMPARISON
```

The date checking mechanism reads the last update date from the existing README.md file to prevent duplicate processing, though the check is currently commented out [main.py:22-23]().

### Keyword and Result Configuration

| Parameter | Value | Purpose |
|-----------|-------|---------|
| `keywords` | `["Time Series", "Trajectory", "Graph Neural Networks"]` | Research domains to search |
| `max_result` | `100` | Maximum papers per keyword for README.md |
| `issues_result` | `15` | Maximum papers per keyword for issue template |
| `column_names` | `["Title", "Link", "Abstract", "Date", "Comment"]` | Output table structure |

**Sources:** [main.py:10-34]()

## Main Processing Loop

The core processing logic iterates through each keyword and generates content for both output files simultaneously.

### Keyword Processing Flow

```mermaid
graph TD
    KEYWORD_START["keyword in keywords"]
    WRITE_HEADERS["f_rm.write('## {keyword}')<br/>f_is.write('## {keyword}')"]
    
    LINK_LOGIC{"len(keyword.split()) == 1?"}
    AND_LINK["link = 'AND'"]
    OR_LINK["link = 'OR'"]
    
    API_CALL["get_daily_papers_by_keyword_with_retries(keyword, column_names, max_result, link)"]
    
    NULL_CHECK{"papers is None?"}
    ERROR_PATH["Close files<br/>restore_files()<br/>sys.exit()"]
    
    TABLE_GEN["rm_table = generate_table(papers)<br/>is_table = generate_table(papers[:issues_result], ignore_keys=['Abstract'])"]
    
    WRITE_OUTPUT["f_rm.write(rm_table)<br/>f_is.write(is_table)"]
    RATE_LIMIT["time.sleep(5)"]
    
    KEYWORD_START --> WRITE_HEADERS
    WRITE_HEADERS --> LINK_LOGIC
    LINK_LOGIC -->|"Yes"| AND_LINK
    LINK_LOGIC -->|"No"| OR_LINK
    AND_LINK --> API_CALL
    OR_LINK --> API_CALL
    API_CALL --> NULL_CHECK
    NULL_CHECK -->|"Yes"| ERROR_PATH
    NULL_CHECK -->|"No"| TABLE_GEN
    TABLE_GEN --> WRITE_OUTPUT
    WRITE_OUTPUT --> RATE_LIMIT
```

### Link Type Determination Logic

The system uses different search strategies based on keyword complexity:
- **Single word keywords**: Uses `AND` logic to search for papers containing the keyword in both title and abstract
- **Multi-word keywords**: Uses `OR` logic for broader matching

This logic is implemented in [main.py:53-54]().

**Sources:** [main.py:50-69]()

## Output Generation Strategy

The pipeline employs a dual-output strategy, generating two different views of the same data for different use cases.

### File Writing Process

```mermaid
graph LR
    subgraph "File Operations"
        F_RM["f_rm = open('README.md', 'w')"]
        F_IS["f_is = open('.github/ISSUE_TEMPLATE.md', 'w')"]
    end
    
    subgraph "Header Generation"
        RM_HEADER["README.md header<br/>Project description<br/>Last update: {current_date}"]
        IS_HEADER["ISSUE_TEMPLATE.md header<br/>YAML frontmatter<br/>Title with date"]
    end
    
    subgraph "Content Processing"
        PAPERS["papers data"]
        FULL_TABLE["generate_table(papers)"]
        BRIEF_TABLE["generate_table(papers[:15], ignore_keys=['Abstract'])"]
    end
    
    F_RM --> RM_HEADER
    F_IS --> IS_HEADER
    PAPERS --> FULL_TABLE
    PAPERS --> BRIEF_TABLE
    FULL_TABLE --> F_RM
    BRIEF_TABLE --> F_IS
```

### Output Differentiation

| Output File | Content Strategy | Paper Limit | Abstract Inclusion |
|-------------|------------------|-------------|-------------------|
| `README.md` | Comprehensive browsing | 100 per keyword | Yes |
| `ISSUE_TEMPLATE.md` | Daily notifications | 15 per keyword | No |

The README.md receives the full table with abstracts for detailed browsing, while the issue template gets a condensed version without abstracts for notification purposes [main.py:62-63]().

**Sources:** [main.py:37-48](), [main.py:62-67]()

## Error Handling and Backup System

The pipeline implements a comprehensive backup and restore mechanism to ensure data integrity during processing.

### Backup and Restore Flow

```mermaid
graph TD
    START_BACKUP["back_up_files()"]
    PROCESSING["Main processing loop"]
    SUCCESS_CHECK{"Processing successful?"}
    
    NORMAL_END["f_rm.close()<br/>f_is.close()<br/>remove_backups()"]
    
    ERROR_DETECT["papers is None"]
    ERROR_CLEANUP["f_rm.close()<br/>f_is.close()<br/>restore_files()<br/>sys.exit()"]
    
    START_BACKUP --> PROCESSING
    PROCESSING --> SUCCESS_CHECK
    SUCCESS_CHECK -->|"Yes"| NORMAL_END
    SUCCESS_CHECK -->|"No"| ERROR_DETECT
    ERROR_DETECT --> ERROR_CLEANUP
```

### Error Detection Points

The pipeline checks for failures at the API level:
- **Null response detection**: If `get_daily_papers_by_keyword_with_retries()` returns `None`, the pipeline immediately triggers error recovery
- **File state preservation**: Original README.md and ISSUE_TEMPLATE.md are restored from backups
- **Clean exit**: The process terminates with an error message to prevent incomplete updates

### Rate Limiting Strategy

To prevent API blocking, the pipeline includes a 5-second delay between keyword processing cycles [main.py:68]().

**Sources:** [main.py:35](), [main.py:56-61](), [main.py:70-72]()

## Function Integration Points

The main pipeline coordinates with utility functions from `utils.py`:

| Function Call | Purpose | Parameters |
|---------------|---------|------------|
| `get_daily_papers_by_keyword_with_retries()` | Fetch papers with retry logic | keyword, column_names, max_result, link |
| `generate_table()` | Convert papers to markdown table | papers, ignore_keys (optional) |
| `back_up_files()` | Create backup copies | None |
| `restore_files()` | Restore from backups on error | None |
| `remove_backups()` | Clean up backup files | None |
| `get_daily_date()` | Format date for issue title | None |

**Sources:** [main.py:6-7](), [main.py:45](), [main.py:55](), [main.py:62-63]()

---