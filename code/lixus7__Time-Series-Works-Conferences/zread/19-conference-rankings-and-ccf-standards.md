

This page provides an overview of conference ranking systems used within this time series research repository, focusing on the China Computer Federation (CCF) classification system and a quality-based ranking developed for time series research evaluation. Understanding these standards is essential for navigating the curated paper collections and appreciating the repository's organization principles.

## CCF Classification System

The repository employs the **CCF ranking system** to annotate conference publications with standardized quality tiers. Papers are labeled with **A, B, or C** designations in the "Publication" column throughout the task-organized paper lists, providing immediate visibility into each venue's classification level within the CCF framework [Recent-Time-Series-Work-Group-by-Task.md](docs/Recent-Time-Series-Work-Group-by-Task.md#L4-L5). This annotation system enables researchers to quickly assess the perceived quality tier of publication venues without requiring external reference.

**Special Note on CCF Classifications**: The CCF system has limitations in capturing domain-specific excellence. A notable example is AISTAT (International Conference on Artificial Intelligence and Statistics), which holds a **CCF-C classification** but is recognized as **top-tier in computational mathematics**, particularly for probabilistic problems and statistical methodologies [Recent-Time-Series-Work-Group-by-Task.md](docs/Recent-Time-Series-Work-Group-by-Task.md#L7-L8). This discrepancy highlights why venue quality should be evaluated holistically rather than relying solely on CCF rankings.

## Quality-Based Conference Ranking for Time Series Research

Based on analysis of average paper quality and code availability across time series research publications, the repository establishes a hierarchical ranking of major conferences:

```
NeurIPS (NIPS) > ICML > ICLR > KDD > AAAI > IJCAI > WWW > CIKM > ICDM > WSDM
```

This ranking reflects the **empirical assessment** of research output quality specifically within the time series domain, incorporating factors such as paper rigor, code availability, and community impact [Recent-Time-Series-Work-Group-by-Task.md](docs/Recent-Time-Series-Work-Group-by-Task.md#L4-L6). The repository explicitly notes this is a subjective but data-informed evaluation ("Don't be rude, I'm talking about the average"), acknowledging that individual assessments may vary.

### Conference Tier Breakdown

| **Tier** | **Conferences** | **Primary Focus** | **CCF Status** |
|----------|-----------------|------------------|----------------|
| **Top Tier** | NeurIPS, ICML, ICLR | Machine learning theory, probabilistic methods | Variable (ICLR often unranked) |
| **High Tier** | KDD, AAAI, IJCAI | Data mining, general AI | A |
| **Mid Tier** | WWW, CIKM, ICDM | Web technologies, information management | A/B |
| **Applied Tier** | WSDM | Web search and data mining | B |

> [!TIP]
> When evaluating research venues for time series work, consider both CCF classification and domain-specific reputation. For example, ICLR lacks formal CCF ranking but consistently produces top-quality time series methodology papers, particularly in neural architectures and probabilistic forecasting.

## Special Classifications

The repository includes two additional classification markers beyond standard CCF ranks:

- **"None But Top"**: Indicates conferences without formal CCF classification that nevertheless produce top-tier research quality in their respective domains. This designation acknowledges excellence that transcends the CCF framework.
- **"None"**: Denotes venues without CCF classification where quality assessment is not explicitly ranked in the repository's evaluation system

These markers are particularly relevant for emerging conferences and specialized venues where CCF classification may not accurately reflect research impact or community standing.

## Conference Paper Collections

The repository organizes accepted papers from major conferences by year, providing comprehensive collections for time series research tracking. Available conference archives include:

- **AAAI** (2013-2022)
- **IJCAI** (2014-2022)
- **KDD** (2017-2022)
- **WWW** (2017-2022)
- **ICLR** (2020-2022)
- **ICML** (2019-2022)
- **NeurIPS** (historical archive)
- **CIKM** (historical archive via ACM DL)
- **WSDM** (historical archive via ACM DL) [Conferences.md](docs/Conferences.md#L22-L138)

Each conference entry includes links to official accepted paper lists and, where available, submission deadlines and notification dates for recent years. For detailed paper analysis organized by specific time series tasks, see the [Recent-Time-Series-Work-Group-by-Task.md](docs/Recent-Time-Series-Work-Group-by-Task.md#L1-L506) document.

## Recommended Research Resources

For comprehensive conference research and deadline tracking, the repository recommends the following external resources:

- **dblp** (https://dblp.uni-trier.de/): Primary bibliography database for computer science
- **Aminer** (https://www.aminer.cn/conf): Chinese-language conference search platform
- **CCF Conference Deadlines** (https://ccfddl.github.io/): CCF-focused deadline tracking
- **会议之眼** (https://www.conferenceeye.cn/#/layout/home): Chinese conference information resource
- **Call4Papers** (http://123.57.137.208/ccf/ccf-8.jsp): Conference call for papers aggregator [Conferences.md](docs/Conferences.md#L3-L16)

> [!TIP]
> The CCF Conference Deadlines aggregator (ccfddl.github.io) is particularly valuable for Chinese researchers, as it synchronizes with the CCF classification system and provides localized deadline information with timezone conversions.

## Application to Time Series Research

Understanding these ranking systems is crucial for effectively utilizing the repository's curated resources. When exploring papers by task categories such as [Multivariate Time Series Forecasting](4-multivariate-time-series-forecasting) or [Time Series Anomaly Detection](7-time-series-anomaly-detection), the CCF annotations and quality rankings provide immediate context about each publication's venue and perceived research quality.

The repository's quality-based ranking should guide literature review strategies:
- **Comprehensive surveys**: Start with NeurIPS, ICML, ICLR for methodological foundations
- **Applied approaches**: Focus on KDD, AAAI, IJCAI for practical implementations
- **Domain-specific**: Explore WWW, CIKM for web and information management contexts
- **Emerging trends**: Monitor non-CCF venues marked "None But Top" for cutting-edge methodologies

## Next Steps

For detailed exploration of conference-accepted papers in time series research, continue to:
- [Conference Deadlines and Submission Guide](20-conference-deadlines-and-submission-guide) for submission planning
- [Top Conference Paper Collections (NeurIPS, ICML, ICLR)](21-top-conference-paper-collections-neurips-icml-iclr) for venue-specific analysis
- [Domain-Specific Conference Collections (KDD, WWW, AAAI, IJCAI)](22-domain-specific-conference-collections-kdd-www-aaai-ijcai) for application-focused research
