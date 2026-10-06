# How the data were made

The practical only needs the files in `../data/`. This folder documents – and can
reproduce – how they were built. You do not need it to run or host the practical.

| Output | Contents |
|---|---|
| `data/yeast_genes.csv` | one row per gene (5,481 genes, 19 columns) |
| `data/yeast_esm2.csv` | ESM-2 protein-language-model embeddings, 32 principal components per protein |
| `data/assistant.json` | the assistant's prepared answers (generated with an AI model, then checked against the data and edited – edit it directly) |

## Steps

Requirements: Python 3.11+ with pandas, NumPy, scikit-learn and requests; DIAMOND 2.2.8
(`conda install -c bioconda diamond=2.2.8`); for the embeddings, PyTorch and `fair-esm`
(`pip install fair-esm`). The site was built with pandas 3.0, scikit-learn 1.8 and PyTorch 2.14 (CPU).

```bash
bash download.sh          # source data -> raw/ (≈600 MB, mostly BioGRID)
python3 build_base.py     # genes, essentiality, sequences, abundance, interactions -> work/
bash homology.sh          # DIAMOND: human homologues and yeast paralogues -> work/
python3 locations.py      # main compartment from GO annotations -> work/locations.tsv
python3 fetch_alphafold.py   # AlphaFold DB confidence for every protein (API; resumable)
python3 build_final.py    # -> ../data/yeast_genes.csv
python3 embed_esm.py      # ESM-2 35M embeddings (≈40 min on 2 CPU cores)
python3 esm_pca.py        # -> ../data/yeast_esm2.csv
```

With the same source releases (below), these steps reproduce the published files exactly (checked).
`download.sh` fetches PaxDb and BioGRID at fixed versions, but the *current* SGD, GO, UniProt and
AlphaFold DB releases, so a rebuild today may change some numbers slightly – if you rebuild, re-run the
notebook code and check the model answers in `index.html` and the prepared answers in
`data/assistant.json`.

## Sources and definitions

| Column | Source and definition |
|---|---|
| genes (rows) | SGD `SGD_features.tab`: Verified and Uncharacterized ORFs on the 16 nuclear chromosomes that have a deletion phenotype (null mutant, systematic deletion collection) in SGD `phenotype_data.tab` |
| `essential` | 1 if the null mutant is recorded as *inviable* in S288C, 0 if *viable*; genes with both records were removed (15) |
| `protein_length`, `gc_content`, `codon_bias` | SGD protein and coding sequences; codon adaptation index computed against the ribosomal-protein genes |
| `protein_abundance` | PaxDb v6.1, *S. cerevisiae* whole organism, integrated dataset (ppm) |
| `interaction_partners` | BioGRID 5.0.261: distinct partners in physical interactions |
| `transmembrane_helices` | UniProt (release 2026_03) transmembrane features |
| `human_homolog` | DIAMOND (`--more-sensitive`) hit in the UniProt human reference proteome UP000005640 with E ≤ 1e-10 |
| `paralog_identity` | highest % identity to another yeast ORF (DIAMOND, E ≤ 1e-10, alignment ≥ 50% of the query); 0 = none |
| `plddt`, `disorder`, `alphafold_id` | AlphaFold DB (model v6) summary: mean pLDDT; fraction of residues with pLDDT < 50 |
| `conditional_mutant_phenotypes` | SGD `phenotype_data.tab`: number of distinct phenotype/chemical/condition records for conditional, repressible or reduction-of-function alleles. **A deliberate data leak** used in the practical – such alleles are made because a gene is essential |
| `location` | SGD GO cellular-component annotations (GAF of 29 Sep 2026) grouped into 7 compartments with GO `go-basic.obo` (release 2026-07-26): the compartment with the most curated (low-throughput) annotations, organelles winning ties over the cytoplasm; high-throughput and electronic annotations only when there are no curated ones; for proteins with transmembrane helices, generic cytoplasm/cortex annotations are ignored when a membrane compartment is annotated; then UniProt's subcellular location; `Unknown` = none |
| `chromosome`, `description` | SGD |
| `yeast_esm2.csv` | ESM-2 `esm2_t12_35M_UR50D`: mean of the last-layer residue embeddings (480 numbers per protein, sequences cut at 1,022 residues), reduced to 32 principal components (82% of the variance) |

Please cite the original resources if you reuse the data (see the Reference chapter of the
practical). Licences: SGD, UniProt, Gene Ontology and AlphaFold DB data are CC BY 4.0;
BioGRID data are MIT-licensed; ESM-2 weights are MIT-licensed; for PaxDb see pax-db.org.
