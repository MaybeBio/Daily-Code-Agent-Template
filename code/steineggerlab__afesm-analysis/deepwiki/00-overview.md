# Overview

<details>
<summary>Relevant source files</summary>

The following files were used as context for generating this wiki page:

- [concate_clustering/concatenation](concate_clustering/concatenation)
- [taxonomy/15_tax_LCA.ipynb](taxonomy/15_tax_LCA.ipynb)
- [taxonomy/taxonomy_lca](taxonomy/taxonomy_lca)

</details>



## Purpose and Scope

The **afesm-analysis** repository implements a comprehensive protein structure and sequence analysis pipeline that combines data from the AlphaFold Database (AFDB) and ESM Metagenomic Atlas. The system performs multi-stage clustering of protein sequences and structures, followed by sophisticated taxonomic classification and analysis.

This document provides a high-level overview of the entire system architecture and data flow. For detailed information about specific subsystems, see:
- Core data processing pipeline: [Core Data Processing Pipeline](#2)
- Taxonomic analysis components: [Taxonomy Analysis System](#3) 
- Visualization and reporting tools: [Visualization and Reporting](#4)
- Development setup: [Development Setup](#5)

## System Architecture

The afesm-analysis system consists of three primary layers that process protein data through concatenation, clustering, taxonomic classification, and visualization.

**Overall System Architecture**

```mermaid
graph TB
    subgraph "Data Sources"
        AFDB["AlphaFold Database<br/>/databases/foldseek/afdb"]
        ESM["ESM Metagenomic Atlas<br/>databases/esm/metagenomic_atlas/union/foldseekdb"]
    end
    
    subgraph "Core Processing (concate_clustering/concatenation)"
        concat["concate_afdb_esm_with_fragments()"]
        seqclust["seq_cluster_afesm()"]
        align["alignment_afesm_seq_cluster()"]
        createdb["createsubdb_seq_cluster()"]
        structclust["struct_cluster_afesm()"]
    end
    
    subgraph "Taxonomic Analysis"
        lca["taxonomy_lca<br/>MMseqs LCA computation"]
        mappers["Taxonomic Mappers<br/>superkingdom_mapper.ipynb<br/>phylum_mapper.ipynb<br/>genus_mapper.ipynb"]
        aggr["Data Aggregation<br/>taxonomy_universality_superkingdoms<br/>taxonomy_phylum_cnt"]
    end
    
    subgraph "Outputs & Visualization"
        combined_db["databases/afesm"]
        seq_clusters["clusters/afesm30"] 
        struct_clusters["clusters/afesm30_repseq_foldseek_clu"]
        viz["Jupyter Notebooks<br/>15_tax_LCA.ipynb<br/>15_tax_plain_bar.ipynb<br/>15_superkingdom_bar.ipynb"]
    end
    
    AFDB --> concat
    ESM --> concat
    concat --> combined_db
    concat --> seqclust
    seqclust --> seq_clusters
    seqclust --> align
    align --> createdb
    createdb --> structclust
    structclust --> struct_clusters
    
    struct_clusters --> lca
    struct_clusters --> mappers
    lca --> aggr
    mappers --> aggr
    aggr --> viz
```

Sources: [concate_clustering/concatenation:1-126](), [taxonomy/taxonomy_lca:1-18](), [taxonomy/15_tax_LCA.ipynb:1-331]()

## Core Components

### Data Processing Pipeline

The core data processing workflow is implemented in the `concate_clustering/concatenation` script, which orchestrates the entire protein analysis pipeline through five main functions:

| Function | Purpose | Output |
|----------|---------|---------|
| `concate_afdb_esm_with_fragments()` | Concatenates AFDB and ESM databases | `databases/afesm` |
| `seq_cluster_afesm()` | Clusters sequences at 30% identity | `clusters/afesm30` |
| `alignment_afesm_seq_cluster()` | Generates sequence alignments | `alignment/afesm30_aln*` |
| `createsubdb_seq_cluster()` | Creates representative sequence database | `databases/afesm30_repseq` |
| `struct_cluster_afesm()` | Clusters structures using Foldseek | `clusters/afesm30_repseq_foldseek_clu` |

### Taxonomic Classification System

The taxonomy analysis subsystem processes structure clusters through LCA (Lowest Common Ancestor) computation and hierarchical mapping:

- **LCA Analysis**: Implemented via `mmseqs lca` command in [taxonomy/taxonomy_lca:6]()
- **Taxonomic Mapping**: Collection of Jupyter notebooks for different taxonomic levels
- **Data Aggregation**: Scripts that count and aggregate taxonomic distributions

### Visualization and Reporting

The system generates visualizations through Jupyter notebooks that create SVG outputs:

- `15_tax_LCA.ipynb`: LCA prediction visualization with taxonomic level breakdowns
- `15_tax_plain_bar.ipynb`: Basic taxonomy distribution charts  
- `15_superkingdom_bar.ipynb`: Superkingdom-specific percentage plots

Sources: [concate_clustering/concatenation:4-125](), [taxonomy/taxonomy_lca:5-17](), [taxonomy/15_tax_LCA.ipynb:16-306]()

## Data Flow Architecture  

The system processes data through a linear pipeline with clear input/output dependencies between stages.

**End-to-End Data Flow**

```mermaid
flowchart TD
    subgraph "Input Databases"
        afdb_in["/databases/foldseek/afdb<br/>afdb"]
        esm_in["databases/esm/metagenomic_atlas/union/foldseekdb<br/>esmatlas_union"]
    end
    
    subgraph "Concatenation Stage"
        foldseek_concat["foldseek concatdbs"]
        output_afesm["databases/afesm"]
    end
    
    subgraph "Sequence Processing"
        mmseqs_cluster["mmseqs cluster<br/>--min-seq-id 0.3 --cov-mode 1 -c 0.9"]
        mmseqs_align["mmseqs align"]
        awk_filter["AWK pLDDT filtering<br/>qcov > 0.9 & highest pLDDT"]
        foldseek_createdb["foldseek createsubdb"]
    end
    
    subgraph "Structure Processing"
        foldseek_cluster["foldseek cluster<br/>-c 0.9 -e 0.01"]
        struct_out["clusters/afesm30_repseq_foldseek_clu"]
    end
    
    subgraph "Taxonomy Pipeline"
        mmseqs_lca["mmseqs lca<br/>--blacklist 12908,28384,2,2157"]
        tax_report["mmseqs taxonomyreport"]
        jupyter_viz["15_tax_LCA.ipynb<br/>taxpred.svg output"]
    end
    
    afdb_in --> foldseek_concat
    esm_in --> foldseek_concat
    foldseek_concat --> output_afesm
    output_afesm --> mmseqs_cluster
    mmseqs_cluster --> mmseqs_align
    mmseqs_align --> awk_filter
    awk_filter --> foldseek_createdb
    foldseek_createdb --> foldseek_cluster
    foldseek_cluster --> struct_out
    struct_out --> mmseqs_lca
    mmseqs_lca --> tax_report
    tax_report --> jupyter_viz
```

Sources: [concate_clustering/concatenation:16-121](), [taxonomy/taxonomy_lca:6-8](), [taxonomy/15_tax_LCA.ipynb:224-225]()

## Technology Stack

The system leverages several bioinformatics tools and programming environments:

- **Foldseek**: Structure similarity search and clustering
- **MMseqs2**: Sequence clustering and LCA computation  
- **AWK**: Text processing and data filtering
- **Python/Jupyter**: Analysis notebooks with pandas, matplotlib
- **Shell Scripts**: Pipeline orchestration and job scheduling via `srun`

The pipeline is designed to handle large-scale protein datasets, utilizing high-performance computing resources with SLURM job scheduling for computationally intensive steps like clustering operations.

Sources: [concate_clustering/concatenation:38-120](), [taxonomy/15_tax_LCA.ipynb:16-17](), [taxonomy/taxonomy_lca:6-7]()

---