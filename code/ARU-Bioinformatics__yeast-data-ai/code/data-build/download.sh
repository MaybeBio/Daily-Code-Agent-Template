#!/usr/bin/env bash
# Download the source data into data-build/raw (about 600 MB, mostly BioGRID).
# The site was built with the releases current on 30 September 2026 – newer releases give
# slightly different numbers, so check the model answers if you rebuild.
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p raw work
cd raw

SGD=https://downloads.yeastgenome.org
curl -fsSLO $SGD/curation/chromosomal_feature/SGD_features.tab
curl -fsSLO $SGD/sequence/S288C_reference/orf_protein/orf_trans_all.fasta.gz
curl -fsSLO $SGD/sequence/S288C_reference/orf_dna/orf_coding_all.fasta.gz
curl -fsSLO $SGD/curation/literature/phenotype_data.tab
curl -fsSLO $SGD/curation/literature/go_slim_mapping.tab
curl -fsSLO $SGD/curation/literature/gene_association.sgd.gaf.gz

# Gene Ontology (release 2026-07-26 was used)
curl -fsSL -o go-basic.obo http://purl.obolibrary.org/obo/go/go-basic.obo

# PaxDb v6.1 integrated whole-organism protein abundance for S. cerevisiae (taxon 4932)
curl -fsSL -o paxdb_4932_integrated.txt https://pax-db.org/downloads/6.1/datasets/4932/4932-WHOLE_ORGANISM-integrated.txt

# BioGRID 5.0.261 (physical interactions are selected in build_base.py)
curl -fsSLO https://downloads.thebiogrid.org/Download/BioGRID/Release-Archive/BIOGRID-5.0.261/BIOGRID-ORGANISM-5.0.261.tab3.zip
unzip -o -j BIOGRID-ORGANISM-5.0.261.tab3.zip 'BIOGRID-ORGANISM-Saccharomyces_cerevisiae_S288c-5.0.261.tab3.txt'
rm BIOGRID-ORGANISM-5.0.261.tab3.zip

# UniProt human reference proteome (for the human-homologue search)
curl -fsSL -o human_UP000005640.fasta.gz https://ftp.uniprot.org/pub/databases/uniprot/current_release/knowledgebase/reference_proteomes/Eukaryota/UP000005640/UP000005640_9606.fasta.gz

# UniProt yeast entries (accessions, subcellular location, transmembrane helices; release 2026_03 was used)
cd ..
python3 fetch_uniprot.py
