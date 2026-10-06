# External Resources

<details>
<summary>Relevant source files</summary>

The following files were used as context for generating this wiki page:

- [README.md](README.md)
- [docs/README.md](docs/README.md)

</details>



This page documents the external resources linked from the Time-Series-Works-Conferences repository. These resources include cloud storage platforms hosting comprehensive paper collections, related GitHub repositories focusing on time series research, and other online resources that complement the repository's content. For conference-specific information, see [Conference Resources](#4).

## Paper Collections on Cloud Storage

The Time-Series-Works-Conferences repository links to external cloud storage platforms that host complete collections of time series research papers. These collections include papers that might not be directly listed in the GitHub repository and are organized by both task and methodology categories.

```mermaid
flowchart TD
    subgraph "External Storage Platforms"
        OneDrive["OneDrive Paper Collection"]
        GoogleDrive["Google Drive Paper Collection (VPN may be required)"]
    end
    
    subgraph "Organization Structure"
        Papers["Research Papers"] --> |"Organized by"| TaskCat["Task Categories"]
        Papers --> |"Organized by"| MethodCat["Methodology Categories"]
        
        TaskCat --> MTSF["Multivariable Time Series Forecasting"]
        TaskCat --> ProbF["Probabilistic Forecasting"]
        TaskCat --> TSI["Time Series Imputation"]
        TaskCat --> TSAD["Anomaly Detection"]
        TaskCat --> DP["Demand Prediction"]
        TaskCat --> OtherTasks["Other Specialized Tasks"]
        
        MethodCat --> TransBased["Transformer-based"]
        MethodCat --> GNNBased["Graph Neural Network-based"]
        MethodCat --> LLMBased["LLM-based"]
        MethodCat --> DiffusionBased["Diffusion Model-based"]
    end
    
    Papers --> |"Contains"| FullText["Full Text PDFs"]
    Papers --> |"Linked to"| CodeImpls["Code Implementations"]
```

**Diagram: Paper Collections Organization Structure**

The paper collections are accessible through:

- **OneDrive**: [https://1drv.ms/u/s!Au2cJRs-_u93lDbLrSDkDy8htv2V?e=ftuaXd](https://1drv.ms/u/s!Au2cJRs-_u93lDbLrSDkDy8htv2V?e=ftuaXd)
- **Google Drive**: [https://drive.google.com/drive/folders/17bILWdDxUrufRp3yilYfoU5VKywwS1g6?usp=sharing](https://drive.google.com/drive/folders/17bILWdDxUrufRp3yilYfoU5VKywwS1g6?usp=sharing)

These collections feature:

- Papers organized by research task (forecasting, imputation, anomaly detection, etc.)
- Papers organized by methodology approach (transformer-based, GNN-based, etc.)
- Full-text PDFs available for download
- Comprehensive coverage of papers mentioned in the GitHub repository and additional related work

Sources: [README.md:42-47]()

## Related GitHub Repositories

The repository links to several other high-quality GitHub repositories that also focus on time series research. These repositories offer complementary perspectives, organizations, and collections of time series papers and resources.

```mermaid
graph LR
    subgraph "Time Series Research Ecosystem"
        MainRepo["Time-Series-Works-Conferences"]
        
        subgraph "Related GitHub Repositories"
            XiyuanRepo["xiyuanzh/time-series-papers"]
            QingsongRepo["qingsongedu/awesome-AI-for-time-series-papers"]
            TrajectoryRepo["xuehaouwa/Awesome-Trajectory-Prediction"]
            StarList["Time-series Repo-Star List"]
        end
        
        MainRepo --> |"References"| XiyuanRepo
        MainRepo --> |"References"| QingsongRepo
        MainRepo --> |"References"| TrajectoryRepo
        MainRepo --> |"References"| StarList
        
        XiyuanRepo --> |"Focus on"| GeneralTS["General Time Series Papers"]
        QingsongRepo --> |"Focus on"| AITS["AI for Time Series"]
        TrajectoryRepo --> |"Focus on"| TrajPrediction["Trajectory Prediction"]
        StarList --> |"Curated by"| RepoOwner["Repository Owner"]
    end
```

**Diagram: Related GitHub Repositories Ecosystem**

The related repositories include:

| Repository | Description | Link |
|------------|-------------|------|
| xiyuanzh/time-series-papers | Collection of time series research papers | [GitHub Link](https://github.com/xiyuanzh/time-series-papers) |
| qingsongedu/awesome-AI-for-time-series-papers | Comprehensive list of AI applications for time series | [GitHub Link](https://github.com/qingsongedu/awesome-AI-for-time-series-papers) |
| xuehaouwa/Awesome-Trajectory-Prediction | Focused on trajectory prediction papers | [GitHub Link](https://github.com/xuehaouwa/Awesome-Trajectory-Prediction) |
| Time-series Repo-Star List | Repository owner's curated list of time series repositories | [GitHub Link](https://github.com/stars/lixus7/lists/time-series-list) |

Each of these repositories offers a different organization or focus on time series research, providing complementary resources to the main repository.

Sources: [README.md:12-20]()

## AI/ML Conference Resources

The repository links to external resources for tracking AI/ML conferences relevant to time series research.

```mermaid
flowchart LR
    subgraph "Conference Resources"
        AIMSummary["AI ML Summary GitHub Repository"]
        ConferencePage["Conferences.md Page"]
    end
    
    subgraph "Information Provided"
        Deadlines["Conference Submission Deadlines"]
        AcceptedPapers["Accepted Papers Lists"]
        VenuesByYear["Conference Venues by Year"]
    end
    
    AIMSummary --> Deadlines
    AIMSummary --> AcceptedPapers
    ConferencePage --> VenuesByYear
    ConferencePage --> Deadlines
```

**Diagram: Conference Resource Structure**

The main external resource for conference information is:

- **AI ML Summary GitHub**: A repository that tracks conference information including accepted papers. Available at [GitHub Link](https://github.com/Lionelsy/Conference-Accepted-Paper-List)

This complements the repository's internal Conferences page, which provides more structured information about conferences relevant to time series research.

Sources: [README.md:10]()

## Resource Access Integration

The following diagram illustrates how users typically interact with the repository and its external resources:

```mermaid
sequenceDiagram
    participant User as "Researcher/User"
    participant Repo as "Time-Series-Works-Conferences"
    participant Storage as "Cloud Storage (OneDrive/Google Drive)"
    participant Other as "Related GitHub Repositories"
    participant Conf as "Conference Resources"
    
    User->>Repo: Access repository
    User->>Repo: Navigate README.md
    
    alt Looking for paper collections
        Repo->>Storage: Link to OneDrive/Google Drive
        User->>Storage: Access complete paper collections
        Storage->>User: Provide organized papers by task/methodology
    end
    
    alt Looking for additional time series resources
        Repo->>Other: Link to related repositories
        User->>Other: Access complementary time series resources
    end
    
    alt Looking for conference information
        Repo->>Conf: Link to conference resources
        User->>Conf: Access conference dates, deadlines, accepted papers
    end
```

**Diagram: User Interaction Flow with External Resources**

This integration enables users to:

1. Browse the repository for a curated index of time series papers
2. Access full-text PDFs through cloud storage links
3. Explore complementary resources through related repositories
4. Stay updated on relevant conferences through linked conference resources

Sources: [README.md:5-47]()

## External Resource Data Organization

The time series papers in the external resources are organized in a consistent structure that mirrors the repository's organization. The main categorization is by task, with each paper entry containing detailed information.

```mermaid
classDiagram
    class PaperCollection {
        +OrganizeByTask()
        +OrganizeByMethodology()
    }
    
    class PaperEntry {
        +Task: String
        +Data: String
        +Model: String
        +Paper: Link
        +Code: Link
        +Publication: String
    }
    
    class TaskCategories {
        +MultivariableForecasting
        +ProbabilisticForecasting
        +TimeSeriesImputation
        +AnomalyDetection
        +DemandPrediction
        +TimeSeriesGeneration
        +OtherTasks
    }
    
    PaperCollection "1" -- "many" PaperEntry: contains
    PaperCollection -- TaskCategories: organizes by
```

**Diagram: Paper Entry Structure in External Resources**

The typical paper entry structure includes:

1. Task type (e.g., Multivariable Forecasting, Imputation)
2. Dataset information
3. Model name and approach
4. Link to the original paper
5. Link to code implementation (if available)
6. Publication venue and date

This consistent organization makes it easy to find relevant papers across both the repository and external resources.

Sources: [README.md:97-198]()

## Using the External Resources

To effectively use the external resources linked from this repository:

1. **For comprehensive paper access:**
   - Visit the OneDrive or Google Drive links to access full-text PDFs
   - Papers are organized by task and methodology categories

2. **For exploring complementary time series resources:**
   - Visit the related GitHub repositories for different organizational approaches
   - The repository owner's starred list provides additional curated resources

3. **For conference information:**
   - Check the AI ML Summary GitHub for up-to-date information about conferences
   - Visit the repository's Conferences page for structured conference information

4. **For finding specific papers:**
   - Use the repository's task-based tables to find paper details
   - Follow the cloud storage links to access full papers

These external resources complement the repository's main content, providing comprehensive access to time series research papers and related information.

Sources: [README.md:42-47](), [README.md:12-20](), [README.md:10]()

---