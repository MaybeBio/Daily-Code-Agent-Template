#!/usr/bin/env bash
# Human homologues and yeast paralogues with DIAMOND (version 2.2.8 was used).
# Run after build_base.py, which writes work/proteins.fasta and work/all_orfs.fasta.
set -euo pipefail
cd "$(dirname "$0")/work"
FMT="6 qseqid sseqid pident length qlen slen evalue bitscore"

diamond makedb --in ../raw/human_UP000005640.fasta.gz -d human --quiet
diamond blastp -q proteins.fasta -d human -o yeast_vs_human.tsv --outfmt $FMT \
  --max-target-seqs 5 --evalue 1e-5 --more-sensitive --threads 2 --quiet

diamond makedb --in all_orfs.fasta -d yeast_all --quiet
diamond blastp -q proteins.fasta -d yeast_all -o yeast_vs_yeast.tsv --outfmt $FMT \
  --max-target-seqs 25 --evalue 1e-5 --more-sensitive --threads 2 --quiet
# build_final.py then keeps hits with E <= 1e-10 (and, for paralogues, alignments covering >= 50% of the query)
