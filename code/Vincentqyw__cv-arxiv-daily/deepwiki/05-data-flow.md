# Data Flow

<details>
<summary>Relevant source files</summary>

The following files were used as context for generating this wiki page:

- [daily_arxiv.py](daily_arxiv.py)
- [docs/cv-arxiv-daily-web.json](docs/cv-arxiv-daily-web.json)
- [docs/cv-arxiv-daily-wechat.json](docs/cv-arxiv-daily-wechat.json)
- [docs/cv-arxiv-daily.json](docs/cv-arxiv-daily.json)

</details>



This document describes the flow of data within the CV-ArXiv-Daily system, from input sources through processing stages to final output formats. It explains how computer vision research papers are collected from arXiv, processed, enriched with code repository information, and published in various formats for different platforms.

## 1. Data Sources and Inputs

The CV-ArXiv-Daily system collects data from several external APIs and configuration files:

```mermaid
flowchart LR
    subgraph "Configuration"
        A["config.yaml"]
    end
    
    subgraph "External APIs"
        B["arXiv API"]
        C["Papers with Code API"]
        D["GitHub API"]
    end
    
    A -->|"Keywords & Settings"| E["daily_arxiv.py"]
    B -->|"Paper Metadata"| E
    C -->|"Official Repository Links"| E
    D -->|"Additional Repository Links"| E
    
    E -->|"Processes Data"| F["Output Formats"]
```

### 1.1 Configuration

The system behavior is defined by the `config.yaml` file, which specifies:
- Keywords for searching papers by research area
- Maximum results to fetch
- Output formats to generate

The configuration is loaded using the `load_config()` function, which parses the YAML file and prepares the keyword filters for arXiv queries.

Sources: [daily_arxiv.py:19-48]()

### 1.2 arXiv API

The primary source of paper information is the arXiv API, accessed through the `arxiv` Python package. The system queries arXiv using search terms defined in the configuration file to retrieve recent computer vision papers.

```mermaid
flowchart LR
    A["get_daily_papers()"] -->|"arxiv.Search(query, max_results)"| B["arXiv API"]
    B -->|"Returns paper metadata"| C["Paper Processing"]
    C -->|"Extracts"| D["Title, authors, abstract, ID, publish date, etc."]
```

Sources: [daily_arxiv.py:87-116]()

### 1.3 Code Repository APIs

For each paper fetched from arXiv, the system attempts to find associated code repositories:

```mermaid
flowchart TB
    A["Paper ID (e.g., 2110.01289)"] --> B["Papers with Code API"]
    B -->|"requests.get(base_url + paper_id)"| C{"Official repo found?"}
    C -->|"Yes"| D["Use official repository URL"]
    C -->|"No"| E["GitHub API (optional fallback)"]
    E -->|"get_code_link(paper_title)"| F{"GitHub repo found?"}
    F -->|"Yes"| G["Use GitHub repository URL"]
    F -->|"No"| H["Set repository link to null"]
```

The system first checks the Papers with Code API for an official repository. If none is found, it can optionally query the GitHub API using the paper title as a search term.

Sources: [daily_arxiv.py:65-85](), [daily_arxiv.py:126-144]()

## 2. Data Processing Pipeline

The data processing pipeline transforms raw paper information into structured data for publication:

```mermaid
flowchart TB
    A["demo() function"] -->|"Orchestrates process"| B["load_config()"]
    B -->|"Returns parsed config"| C["get_daily_papers()"]
    
    C -->|"For each keyword"| D["Query arXiv API"]
    D -->|"For each paper"| E["Extract metadata"]
    E --> F["Search for code repository"]
    F --> G["Format paper entry"]
    
    G -->|"JSON & markdown formats"| H["Data collection arrays"]
    H -->|"data_collector"| I["update_json_file()"]
    H -->|"data_collector_web"| J["update_json_file()"]
    
    I -->|"Updates"| K["cv-arxiv-daily.json"]
    I -->|"Updates"| L["cv-arxiv-daily-web.json"]
    J -->|"Updates"| M["cv-arxiv-daily-wechat.json"]
    
    K --> N["json_to_md()"]
    L --> N
    M --> N
    
    N -->|"Generates"| O["README.md"]
    N -->|"Generates"| P["docs/index.md"]
    N -->|"Generates"| Q["docs/wechat.md"]
```

The main data processing occurs in the `get_daily_papers()` function, which:
1. Creates an `arxiv.Search` instance with the configured query and parameters
2. Iterates through the results, extracting metadata for each paper
3. Searches for associated code repositories
4. Formats the paper information for both JSON storage and markdown display

Sources: [daily_arxiv.py:87-161]()

### 2.1 Paper Data Extraction

For each paper retrieved from arXiv, the system extracts the following metadata:
- Paper ID (e.g., "2110.07546")
- Title
- Authors (full list and first author)
- Publication and update dates
- Abstract
- arXiv URL
- Code repository URL (if available)

This metadata is structured into formatted strings for each output format.

Sources: [daily_arxiv.py:102-115]()

## 3. Data Storage and Persistence

The CV-ArXiv-Daily system uses JSON files as an intermediate data storage mechanism:

```mermaid
flowchart TB
    A["Data collector arrays"] -->|"update_json_file()"| B["Read existing JSON file"]
    B --> C["Merge new data with existing data"]
    C --> D["Write updated JSON to file"]
    
    subgraph "JSON Storage Files"
        E["cv-arxiv-daily.json<br>(for README)"]
        F["cv-arxiv-daily-web.json<br>(for Jekyll website)"]
        G["cv-arxiv-daily-wechat.json<br>(for WeChat)"]
    end
    
    D -->|"Stores formatted data in"| E
    D -->|"Stores formatted data in"| F
    D -->|"Stores formatted data in"| G
```

Each JSON file uses paper IDs (e.g., "2110.07546") as keys, with formatted strings as values. This allows for:
- Incremental updates without duplicating entries
- Platform-specific formatting
- Persistence between runs

Sources: [daily_arxiv.py:217-241]()

### 3.1 Data Update Mechanism

The system includes a mechanism to update repository links for existing papers:

```mermaid
flowchart TB
    A["update_paper_links()"] -->|"Reads"| B["Existing JSON file"]
    B --> C["Parse each paper entry"]
    C --> D{"Has valid code link?"}
    D -->|"No"| E["Query Papers with Code API"]
    D -->|"Yes"| F["Keep existing link"]
    E --> G{"New link found?"}
    G -->|"Yes"| H["Update paper entry"]
    G -->|"No"| I["Keep as null"]
    H --> J["Write updated JSON"]
    F --> J
    I --> J
```

This allows the system to retroactively add code repository links as they become available, without refetching the papers from arXiv.

Sources: [daily_arxiv.py:163-215]()

## 4. Output Generation

The CV-ArXiv-Daily system generates three different output formats from the stored JSON data:

```mermaid
flowchart TB
    A["json_to_md() function"] -->|"Reads"| B["JSON data files"]
    B --> C["Process JSON data"]
    C --> D["Format by platform"]
    
    D -->|"GitHub format"| E["README.md"]
    D -->|"Web format"| F["docs/index.md"]
    D -->|"Mobile/Social format"| G["docs/wechat.md"]
    
    H["pretty_math()"] -->|"Formats LaTeX"| D
```

The `json_to_md()` function converts JSON data to markdown, with specific formatting for each platform:

Sources: [daily_arxiv.py:243-368]()

### 4.1 Output Format Comparison

| Output Format | File | Purpose | Format Features |
|---------------|------|---------|----------------|
| GitHub README | README.md | Repository documentation | Full table with badges, TOC |
| Jekyll Website | docs/index.md | Web interface | Web-optimized table format |
| WeChat Content | docs/wechat.md | Mobile/social sharing | Simple list format |

Each format is optimized for its specific platform, ensuring the information is presented in the most suitable way for each context.

### 4.2 Custom Formatting

The system includes specialized formatting functions:
- `pretty_math()` - Properly formats LaTeX mathematics in paper titles
- `get_authors()` - Formats author lists with options for full list or first author only
- `sort_papers()` - Sorts papers by date for chronological display

These ensure consistent, readable output across all platforms.

Sources: [daily_arxiv.py:50-63](), [daily_arxiv.py:255-267]()

## 5. Complete Data Flow Diagram

The following diagram illustrates the complete data flow through the CV-ArXiv-Daily system:

```mermaid
flowchart TD
    A["config.yaml"] -->|"load_config()"| B["Configuration Data"]
    
    subgraph "Input Sources"
        C["arXiv API"]
        D["Papers with Code API"]
        E["GitHub API"]
    end
    
    B -->|"Keywords & Filters"| F["get_daily_papers()"]
    C -->|"Paper Metadata"| F
    F -->|"Paper IDs"| G["Code Repository Search"]
    D -->|"Official Repos"| G
    E -->|"Additional Repos"| G
    
    F --> H["Formatted Paper Data"]
    G --> H
    
    H -->|"data_collector arrays"| I["update_json_file()"]
    I -->|"Updates"| J["JSON Storage Files"]
    
    subgraph "JSON Files"
        J1["cv-arxiv-daily.json"]
        J2["cv-arxiv-daily-web.json"]
        J3["cv-arxiv-daily-wechat.json"]
    end
    J --> J1
    J --> J2
    J --> J3
    
    K["update_paper_links()"] --> J
    
    J1 -->|"json_to_md()"| L["README.md"]
    J2 -->|"json_to_md()"| M["docs/index.md"]
    J3 -->|"json_to_md()"| N["docs/wechat.md"]
    
    subgraph "Final Outputs"
        L
        M
        N
    end
```

This diagram shows how data flows from input sources through processing functions to storage and finally to the various output formats.

Sources: [daily_arxiv.py:370-443]()

## 6. Implementation Detail: Paper Collection

The `get_daily_papers()` function is the core of the data collection process:

```mermaid
sequenceDiagram
    participant main as "demo() function"
    participant gdp as "get_daily_papers()"
    participant arxiv as "arxiv.Search"
    participant pwc as "Papers with Code API"
    participant gh as "GitHub API"
    
    main->>gdp: Call with topic, query, max_results
    gdp->>arxiv: Create search with query parameters
    arxiv-->>gdp: Return search results iterator
    
    loop For each result
        gdp->>gdp: Extract paper metadata
        gdp->>pwc: Query for official code
        pwc-->>gdp: Return official repository (if any)
        
        alt No official repository and fallback enabled
            gdp->>gh: Search for repository
            gh-->>gdp: Return best match repository (if any)
        end
        
        gdp->>gdp: Format paper data for storage
    end
    
    gdp-->>main: Return structured paper data
```

The function processes each paper and produces two formats for each:
1. Table row format for GitHub and web display: `|date|title|authors|paper_link|code_link|`
2. List format for WeChat: `- date, title, authors, paper_link, code_link`

These different formats are collected in separate data structures (`content` and `content_to_web`) to be stored in different JSON files.

Sources: [daily_arxiv.py:87-161]()

## 7. JSON Data Structure

The JSON files serve as an intermediate representation between the raw data from arXiv and the formatted markdown outputs:

```json
{
  "SLAM": {
    "2110.07546": "|**2021-10-14**|**Active SLAM over Continuous Trajectory and Control: A Covariance-Feedback Approach**|Shumon Koga et.al.|[2110.07546](http://arxiv.org/abs/2110.07546)|null|\n",
    "2110.06541": "|**2021-10-13**|**Collaborative Radio SLAM for Multiple Robots based on WiFi Fingerprint Similarity**|Ran Liu et.al.|[2110.06541](http://arxiv.org/abs/2110.06541)|null|\n"
  },
  "Visual Localization": {
    "2201.03212": "|**2022-01-10**|**Why-So-Deep: Towards Boosting Previously Trained Models for Visual Place Recognition**|M. Usman Maqbool Bhutta et.al.|[2201.03212](http://arxiv.org/abs/2201.03212)|**[link](https://github.com/UsmanMaqbool/why-so-deep)**|\n"
  }
}
```

Each JSON file contains a dictionary where:
- Top-level keys are research topics ("SLAM", "Visual Localization", etc.)
- Second-level keys are arXiv paper IDs
- Values are formatted strings ready for insertion into markdown files

This structure allows for:
1. Easy updating of existing entries
2. Organization by research topic
3. Quick conversion to markdown

Sources: [docs/cv-arxiv-daily.json](), [docs/cv-arxiv-daily-web.json](), [docs/cv-arxiv-daily-wechat.json]()

## 8. Conclusion

The data flow in the CV-ArXiv-Daily system can be summarized as:

1. **Input Collection**: Fetch papers from arXiv based on configured keywords
2. **Data Enrichment**: Search for associated code repositories
3. **Structured Storage**: Store formatted data in JSON files
4. **Markdown Generation**: Convert JSON data to markdown for different platforms

This pipeline efficiently transforms raw research paper data into well-structured, platform-specific formats, making the latest computer vision research accessible across different platforms.

---