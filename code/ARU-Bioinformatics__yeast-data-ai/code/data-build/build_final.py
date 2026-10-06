"""Combine the base table with homology (DIAMOND) and AlphaFold features -> site data files."""
import os
HERE = os.path.dirname(os.path.abspath(__file__))
import json, os
import numpy as np, pandas as pd

W = os.path.join(HERE, 'work')
RAW = os.path.join(HERE, 'raw')
OUT = os.path.join(HERE, '..', 'data')
os.makedirs(OUT, exist_ok=True)
base = pd.read_csv(f'{W}/base.tsv', sep='\t')
# main compartment from curated GO annotations (build/locations.py) replaces the GO-slim/UniProt first pass
loc = pd.read_csv(f'{W}/locations.tsv', sep='\t', keep_default_na=False)
base['location'] = base.orf.map(dict(zip(loc.orf, loc.location))).fillna('Unknown')

cols = ['q', 's', 'pident', 'length', 'qlen', 'slen', 'evalue', 'bits']
hu = pd.read_csv(f'{W}/yeast_vs_human.tsv', sep='\t', header=None, names=cols)
hu = hu[hu.evalue <= 1e-10]
base['human_homolog'] = base.orf.isin(set(hu.q)).astype(int)

yy = pd.read_csv(f'{W}/yeast_vs_yeast.tsv', sep='\t', header=None, names=cols)
yy = yy[(yy.q != yy.s) & (yy.evalue <= 1e-10) & (yy.length >= 0.5 * yy.qlen)]
best = yy.groupby('q').pident.max()
base['paralog_identity'] = base.orf.map(best).fillna(0).round(1)

af = pd.DataFrame([json.loads(l) for l in open(f'{W}/alphafold.jsonl')])
af = af[af.found == True].set_index('uniprot')
base['plddt'] = base.uniprot.map(af.plddt).round(1)
base['disorder'] = base.uniprot.map(af.very_low).round(3)
base['alphafold_id'] = base.uniprot.map(af.entry)

# number of distinct phenotypes recorded in SGD for conditional or knock-down alleles
# (temperature-sensitive, repressible promoter, reduction of function). This column is a
# deliberate trap for the practical: such alleles are made *because* a gene is essential.
pcols = ['feature', 'ftype', 'gene', 'sgdid', 'ref', 'exp', 'mutant', 'allele', 'strain', 'phenotype', 'chemical',
         'condition', 'details', 'reporter']
ph = pd.read_csv(f'{RAW}/phenotype_data.tab', sep='\t', header=None, names=pcols, dtype=str, keep_default_na=False)
cond = ph[ph.mutant.isin(['conditional', 'repressible', 'reduction of function'])]
ncond = cond.groupby('feature').apply(lambda g: len(set(zip(g.phenotype, g.chemical, g.condition))))
base['conditional_mutant_phenotypes'] = base.orf.map(ncond).fillna(0).astype(int)

order = ['orf', 'gene', 'essential', 'protein_length', 'gc_content', 'codon_bias', 'protein_abundance', 'interaction_partners',
         'transmembrane_helices', 'human_homolog', 'paralog_identity', 'plddt', 'disorder', 'conditional_mutant_phenotypes', 'location', 'chromosome',
         'uniprot', 'alphafold_id', 'description']
df = base[order].copy()
df['protein_abundance'] = df.protein_abundance.round(3)
df.to_csv(f'{OUT}/yeast_genes.csv', index=False)
print(df.shape)
print(df.describe().T[['count', 'mean', '50%']].round(3))
print('missing:', df.isna().sum()[df.isna().sum() > 0].to_dict())
print('human homolog %:', round(100 * df.human_homolog.mean(), 1), '| with paralog (>0):', round(100 * (df.paralog_identity > 0).mean(), 1))
g = df.groupby('essential')
print(g[['protein_length', 'codon_bias', 'protein_abundance', 'interaction_partners', 'human_homolog', 'paralog_identity', 'plddt', 'disorder', 'transmembrane_helices']].median().T)
print(g[['human_homolog']].mean().T, (df.assign(par=df.paralog_identity > 0).groupby('par').essential.mean()))
