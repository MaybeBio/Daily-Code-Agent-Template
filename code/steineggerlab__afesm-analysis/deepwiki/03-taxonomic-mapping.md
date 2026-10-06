# Taxonomic Mapping

<details>
<summary>Relevant source files</summary>

The following files were used as context for generating this wiki page:

- [taxonomy/clade_mapper.ipynb](taxonomy/clade_mapper.ipynb)
- [taxonomy/descendant_mapper.ipynb](taxonomy/descendant_mapper.ipynb)
- [taxonomy/family_mapper.ipynb](taxonomy/family_mapper.ipynb)
- [taxonomy/genus_mapper.ipynb](taxonomy/genus_mapper.ipynb)
- [taxonomy/phylum_mapper.ipynb](taxonomy/phylum_mapper.ipynb)
- [taxonomy/superkingdom_mapper.ipynb](taxonomy/superkingdom_mapper.ipynb)

</details>



This document covers the taxonomic mapping subsystem that assigns hierarchical taxonomic classifications to protein structure data. The mapping system processes NCBI taxonomy dump files and creates lookup dictionaries for different taxonomic levels including superkingdom, phylum, family, genus, and clade classifications.

For information about LCA (Lowest Common Ancestor) analysis that uses these mappings, see [LCA Analysis](#3.2). For data aggregation workflows that consume these mappings, see [Data Aggregation and Processing](#3.3).

## System Overview

The taxonomic mapping system consists of individual Jupyter notebooks that each focus on a specific taxonomic hierarchy level. Each mapper reads NCBI taxonomy dump files and generates classification dictionaries that map taxonomic IDs to standardized taxonomic names.

```mermaid
graph TD
    subgraph "Input Data"
        A["merged.dmp<br/>NCBI taxonomy mergers"]
        B["afesm_names.dmp<br/>Taxonomic names"]
        C["afesm_nodes.dmp<br/>Taxonomic hierarchy"]
    end
    
    subgraph "Mapper Notebooks"
        D["superkingdom_mapper.ipynb"]
        E["phylum_mapper.ipynb"]
        F["family_mapper.ipynb"]
        G["genus_mapper.ipynb"]
        H["clade_mapper.ipynb"]
        I["descendant_mapper.ipynb"]
    end
    
    subgraph "Output Mappings"
        J["taxId → superkingdom"]
        K["taxId → phylum"]
        L["taxId → family"]
        M["taxId → genus"]
        N["taxId → clade"]
        O["parent → descendants"]
    end
    
    A --> D
    A --> E
    A --> F
    A --> G
    A --> H
    A --> I
    
    B --> D
    B --> E
    B --> F
    B --> G
    B --> H
    B --> I
    
    C --> D
    C --> E
    C --> F
    C --> G
    C --> H
    C --> I
    
    D --> J
    E --> K
    F --> L
    G --> M
    H --> N
    I --> O
```

Sources: [taxonomy/clade_mapper.ipynb:1-31](), [taxonomy/family_mapper.ipynb:1-31](), [taxonomy/genus_mapper.ipynb:1-31](), [taxonomy/phylum_mapper.ipynb:1-31](), [taxonomy/descendant_mapper.ipynb:1-10]()

## Data Processing Workflow

All mapper notebooks follow a consistent data processing pattern that parses NCBI taxonomy files and builds hierarchical lookup structures.

```mermaid
flowchart TD
    A["merged.dmp file"] --> B["Parse tab-delimited format"]
    B --> C["Extract current_id|previous_id pairs"]
    C --> D["Build cur_id2prev_id dictionary"]
    D --> E["Load taxonomic names"]
    E --> F["Traverse hierarchy"]
    F --> G["Generate level-specific mappings"]
    G --> H["Output taxonomy dictionaries"]
    
    subgraph "File Format"
        I["tokens = line.strip().split('\\t|\\t')<br/>cur_id = int(tokens[1].strip('\\t|'))<br/>prev_id = int(tokens[0])"]
    end
    
    B --> I
```

Sources: [taxonomy/clade_mapper.ipynb:9-31](), [taxonomy/family_mapper.ipynb:9-31](), [taxonomy/genus_mapper.ipynb:9-31](), [taxonomy/phylum_mapper.ipynb:9-31]()

## Individual Mapper Components

### Core Parsing Logic

Each mapper implements identical file parsing logic that processes the `merged.dmp` file format:

| Component | Implementation | Purpose |
|-----------|---------------|---------|
| File Reading | `merged_f = open("../../afesm5/taxonomy/taxdump/merged.dmp")` | Access NCBI taxonomy data |
| Line Parsing | `tokens = line.strip().split("\\t\|\\t")` | Extract tab-delimited fields |
| ID Extraction | `cur_id = int(tokens[1].strip('\\t\|'))` | Get current taxonomic ID |
| Mapping Build | `cur_id2prev_id[cur_id] = [prev_id]` | Build parent-child relationships |

Sources: [taxonomy/clade_mapper.ipynb:9-28](), [taxonomy/family_mapper.ipynb:9-28](), [taxonomy/genus_mapper.ipynb:9-28](), [taxonomy/phylum_mapper.ipynb:9-28]()

### Taxonomic Level Mappers

```mermaid
graph LR
    subgraph "Hierarchical Mappers"
        A["superkingdom_mapper"]
        B["phylum_mapper"] 
        C["family_mapper"]
        D["genus_mapper"]
        E["clade_mapper"]
    end
    
    subgraph "Relationship Mappers"
        F["descendant_mapper"]
    end
    
    subgraph "Output Format"
        G["Dict[int, str]<br/>{taxId: 'taxonomic_name'}"]
        H["Dict[int, List[int]]<br/>{parent_id: [child_ids]}"]
    end
    
    A --> G
    B --> G
    C --> G
    D --> G
    E --> G
    F --> H
```

Sources: [taxonomy/descendant_mapper.ipynb:7-10]()

### Descendant Mapping

The `descendant_mapper.ipynb` creates parent-to-children relationships, generating output like:

```python
{74109: [12, 338050],
 29: [30],
 184914: [36],
 42: [37]
 # ... additional parent -> descendant mappings
}
```

This enables hierarchical traversal from higher-level taxonomic groups down to their constituent taxa.

Sources: [taxonomy/descendant_mapper.ipynb:7-80]()

## Integration Architecture

The taxonomic mappers integrate with the broader AFESM analysis pipeline by providing standardized taxonomic classifications for downstream analysis components.

```mermaid
graph TD
    subgraph "Structure Clustering Pipeline"
        A["afesm30_repseq_foldseek_clu<br/>Structure clusters"]
    end
    
    subgraph "Taxonomic Mapping System"
        B["superkingdom_mapper"]
        C["phylum_mapper"]
        D["family_mapper"]
        E["genus_mapper"]
        F["clade_mapper"]
        G["descendant_mapper"]
    end
    
    subgraph "Downstream Analysis"
        H["taxonomy_lca<br/>LCA computation"]
        I["taxonomy_universality_superkingdoms<br/>Superkingdom analysis"]
        J["taxonomy_phylum_cnt<br/>Phylum counting"]
    end
    
    subgraph "Visualization"
        K["15_tax_LCA.ipynb"]
        L["15_superkingdom_bar.ipynb"]
        M["32_taxnodes_phylum.ipynb"]
    end
    
    A --> H
    B --> I
    C --> J
    D --> H
    E --> H
    F --> H
    G --> H
    
    H --> K
    I --> L
    J --> M
```

Sources: [taxonomy/clade_mapper.ipynb:1-31](), [taxonomy/family_mapper.ipynb:1-31](), [taxonomy/genus_mapper.ipynb:1-31](), [taxonomy/phylum_mapper.ipynb:1-31](), [taxonomy/descendant_mapper.ipynb:1-10]()

## File System Organization

The mapper notebooks access taxonomy data through a standardized file structure:

| File Path | Content | Usage |
|-----------|---------|-------|
| `../../afesm5/taxonomy/taxdump/merged.dmp` | NCBI taxonomy ID mergers | Primary input for all mappers |
| `../../afesm5/taxonomy/taxdump/afesm_names.dmp` | Taxonomic name definitions | Name resolution |
| `../../afesm5/taxonomy/taxdump/afesm_nodes.dmp` | Hierarchical relationships | Tree structure |

Each mapper notebook is located in the `taxonomy/` directory and follows the naming pattern `{level}_mapper.ipynb`.

Sources: [taxonomy/clade_mapper.ipynb:9](), [taxonomy/family_mapper.ipynb:9](), [taxonomy/genus_mapper.ipynb:9](), [taxonomy/phylum_mapper.ipynb:9]()

---