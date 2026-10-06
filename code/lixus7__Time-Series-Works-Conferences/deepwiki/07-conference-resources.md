# Conference Resources

<details>
<summary>Relevant source files</summary>

The following files were used as context for generating this wiki page:

- [README.md](README.md)
- [docs/Conferences.md](docs/Conferences.md)

</details>



## Purpose and Scope

This page documents the conference resources available in the Time-Series-Works-Conferences repository. It covers how conference information is tracked, organized, and accessed to facilitate time series research. The conference resources provide a comprehensive reference for researchers to stay updated on relevant academic venues, submission deadlines, and accepted papers in the time series domain. For information about external resources like Google Drive and OneDrive paper collections, see [External Resources](#5).

Sources: [README.md:7-10]()

## Conference Tracking System

The repository maintains a structured system for tracking major AI/ML conferences relevant to time series research. This includes historical conference information as well as upcoming events. The tracking system serves several purposes:

1. Providing links to accepted papers from past conferences
2. Tracking submission deadlines for upcoming conferences
3. Maintaining a backlog of future conferences to monitor
4. Offering convenient access to conference websites and paper listings

### Conference Backlog System

The repository maintains a "Backlog" system at the top of the README file to track upcoming conferences that will be added to the resource list once their papers are published.

```
# Backlog (To do): KDD 2025, ...
```

This allows researchers to anticipate which conference proceedings will be added to the collection in the future.

Sources: [README.md:3]()

## Conference Information Structure

The conference information is primarily stored in the Conferences.md file, which provides a well-organized table of major AI/ML conferences relevant to time series research.

```mermaid
graph TD
    subgraph "Conference Resources Organization"
        ConferencesMD["Conferences.md"] --> TableOfConferences["Table of Conferences"]
        ConferencesMD --> UsefulWebsites["Useful Websites"]
        
        TableOfConferences --> |Contains| ConferenceEntries["Conference Entries"]
        
        ConferenceEntries --> |Has| ConfName["Conference Name"]
        ConferenceEntries --> |Has| SourceLink["Source Link to Papers"]
        ConferenceEntries --> |Has| Deadline["Submission Deadline"]
        ConferenceEntries --> |Has| Notification["Notification Date"]
        
        UsefulWebsites --> CCFDeadlines["CCF Conference Deadlines"]
        UsefulWebsites --> ConferenceEye["Conference Eye (会议之眼)"]
        UsefulWebsites --> Call4Papers["Call4Papers"]
        UsefulWebsites --> ConferenceList["Conference List"]
    end
    
    READMEFile["README.md"] --> |References| ConferencesMD
    READMEFile --> |Contains| ConferenceBacklog["Conference Backlog"]
    
    classDef default stroke:#333,stroke-width:1px;
```

Sources: [docs/Conferences.md:11-21](), [docs/Conferences.md:22-33]()

## Major Tracked Conferences

The repository systematically tracks the following major conferences that frequently publish time series research:

| Conference | Description | Relevance to Time Series |
|------------|-------------|--------------------------|
| AAAI | Association for the Advancement of Artificial Intelligence | Publishes broad AI research including time series forecasting |
| IJCAI | International Joint Conference on Artificial Intelligence | Features various time series applications |
| KDD | Knowledge Discovery and Data Mining | Strong focus on time series mining and forecasting |
| WWW | The Web Conference | Web-based time series applications |
| ICLR | International Conference on Learning Representations | Deep learning approaches for time series |
| ICML | International Conference on Machine Learning | Core machine learning techniques for time series |
| NeurIPS | Neural Information Processing Systems | Neural approaches to time series problems |
| CIKM | Conference on Information and Knowledge Management | Information extraction from time series |
| WSDM | Web Search and Data Mining | Web-related time series mining |

Each conference section provides links to accepted papers, submission deadlines, and notification dates when available.

Sources: [docs/Conferences.md:34-136]()

## Conference Resource Integration

The conference resources are integrated with the paper collection system to provide a comprehensive research reference. The following diagram illustrates how conference information is connected to the paper listings in the repository:

```mermaid
flowchart TD
    subgraph "Conference Information System"
        ConferencesMD["Conferences.md"] --> ConfTable["Conference Tables"]
        ConferencesMD --> ExternalLinks["External Conference Links"]
        ConfTable --> |Lists| PaperSources["Paper Source Links"]
        ConfTable --> |Provides| DeadlineInfo["Submission Deadlines"]
    end
    
    subgraph "Paper Organization System"
        README["README.md"] --> TaskCategories["Task Categories"]
        TaskCategories --> PaperEntries["Paper Entries"]
        PaperEntries --> |Contains| PaperInfo["Paper Information"]
        PaperInfo --> |Has| PubVenue["Publication Venue"]
        PaperInfo --> |Has| Model["Model Name"]
        PaperInfo --> |Has| Dataset["Dataset"]
        PaperInfo --> |Has| CodeRepo["Code Repository"]
    end
    
    ConferencesMD -.->|Referenced from| README
    PubVenue -.->|References| ConfTable
    PaperSources -.->|Used to update| PaperEntries
    
    subgraph "User Interaction"
        User["Researcher"] --> |Browses| README
        User --> |Consults| ConferencesMD
        User --> |Follows| ExternalLinks
        User --> |Tracks| DeadlineInfo
    end
    
    classDef default stroke:#333,stroke-width:1px;
```

Sources: [README.md:82-93](), [docs/Conferences.md:22-33]()

## External Conference Resources

The repository provides links to several external websites for tracking conference deadlines and calls for papers:

1. **CCF Conference Deadlines** - A resource from the China Computer Federation for tracking submission deadlines
2. **Conference Eye (会议之眼)** - A Chinese website for conference tracking
3. **Call4Papers** - A website aggregating calls for papers
4. **Conference List** - A listing of upcoming conferences

Additionally, the repository recommends using the following databases for querying conference information:
- **DBLP** - A comprehensive computer science bibliography database
- **Aminer** - A free online academic search and mining system (with Chinese interface option)

These external resources complement the internal conference tracking and provide additional ways to discover relevant conferences.

Sources: [docs/Conferences.md:11-21](), [docs/Conferences.md:6-8]()

## Conference Paper Access Flow

The following diagram illustrates how a researcher would typically access conference papers through this resource:

```mermaid
sequenceDiagram
    participant User as "Researcher"
    participant Repo as "GitHub Repository"
    participant ConfMD as "Conferences.md"
    participant ExtRes as "External Resources"
    participant Papers as "Paper Collection"
    
    User->>Repo: Access repository
    User->>ConfMD: View conference listings
    
    alt Find papers by conference
        User->>ConfMD: Select specific conference
        ConfMD->>ExtRes: Follow link to conference proceedings
        ExtRes-->>User: Browse conference papers
    else Find papers by research task
        User->>Repo: Navigate to time series task category
        Repo->>Papers: Filter papers by conference venue
        Papers-->>User: View relevant papers with code & datasets
    end
    
    User->>ExtRes: Track upcoming conference deadlines
    ExtRes-->>User: Plan submissions based on deadlines
```

Sources: [README.md:82-93](), [docs/Conferences.md:22-136]()

## Conference Papers in Research Collection

The conference information system directly supports the main paper collection, which organizes time series research by task and methodology. Each paper entry in the collection includes the publication venue, linking back to the relevant conference.

Example paper entry format:

| Task | Data | Model | Paper | Code | Publication |
|------|------|-------|-------|------|-------------|
| Multivariable | Dataset Name | Model Name | Paper Title | Repository Link | Conference Year |

This integration allows researchers to:
1. Find relevant papers from specific conferences
2. Track which conferences publish the most relevant time series research
3. Identify trends in time series research across different conferences over time

Sources: [README.md:98-199]()

## Relationship to Other Repository Components

The Conference Resources component is one part of the larger repository ecosystem, as shown in the following diagram:

```mermaid
graph TD
    subgraph "Repository Components"
        README["README.md: Main Index"]
        TaskCategorization["Time Series Tasks"]
        ConferenceInfo["Conference Resources"]
        PaperCollection["Research Papers"]
        ExternalResources["External Resources"]
        CodeImplementations["Code Implementations"]
        
        README --> TaskCategorization
        README --> ConferenceInfo
        README --> ExternalResources
        
        TaskCategorization --> PaperCollection
        ConferenceInfo --> PaperCollection
        PaperCollection --> CodeImplementations
        ExternalResources --> |"Full Text PDFs"| PaperCollection
    end
    
    subgraph "Documentation Website"
        WebsiteIndex["index.html"]
        Sidebar["_sidebar.md"]
        ConfPage["Conferences.md"]
        
        WebsiteIndex --> Sidebar
        Sidebar --> ConfPage
    end
    
    ConferenceInfo -.->|"Content reflected in"| ConfPage
    
    classDef default stroke:#333,stroke-width:1px;
```

The Conference Resources component provides the contextual information about where time series research is published, complementing the task-based organization of papers in the main collection.

Sources: [README.md:7-10](), [README.md:82-93]()

## Alternative AI/ML Conference Resources

In addition to the built-in conference tracking, the repository also links to an external GitHub repository specifically focused on conference papers:

```
[AI ML Summary Github](https://github.com/Lionelsy/Conference-Accepted-Paper-List)
```

This resource provides an alternative way to browse AI/ML conference papers and may include conferences not directly tracked in the Time-Series-Works-Conferences repository.

Sources: [README.md:10]()

## Maintaining and Updating Conference Information

The conference information is maintained through regular updates to both the README.md and Conferences.md files. As new conferences occur, their proceedings are added to the respective conference sections, and papers relevant to time series research are integrated into the task-based paper collection.

The backlog system at the top of the README.md file ensures that upcoming conferences are tracked and eventually incorporated into the resource collection.

Sources: [README.md:3](), [docs/Conferences.md:22-136]()

---