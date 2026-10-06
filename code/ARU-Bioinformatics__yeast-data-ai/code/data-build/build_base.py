"""Build the base yeast gene table from SGD, UniProt, PaxDb and BioGRID downloads.

Output: work/base.tsv (one row per nuclear, verified/uncharacterized ORF with a known
deletion phenotype in the S288C systematic deletion collection) and work/proteins.fasta.
"""
import os
HERE = os.path.dirname(os.path.abspath(__file__))
import gzip, re, math, collections, os
import pandas as pd

RAW = os.path.join(HERE, 'raw')
WORK = os.path.join(HERE, 'work')
os.makedirs(WORK, exist_ok=True)

# ---------------------------------------------------------------- SGD features
cols = ['sgdid', 'ftype', 'qualifier', 'orf', 'gene', 'alias', 'parent', 'sgdid2', 'chrom', 'start', 'stop',
        'strand', 'genpos', 'coordver', 'seqver', 'description']
feat = pd.read_csv(f'{RAW}/SGD_features.tab', sep='\t', header=None, names=cols, dtype=str, keep_default_na=False)
orfs = feat[(feat.ftype == 'ORF') & (feat.qualifier.isin(['Verified', 'Uncharacterized']))].copy()
orfs = orfs[~orfs.chrom.isin(['17', 'mitochondrion', ''])]  # nuclear genome only
orfs['chrom'] = orfs.chrom.astype(int)
print('ORFs (verified + uncharacterized, nuclear):', len(orfs), orfs.qualifier.value_counts().to_dict())
ALL_ORFS = sorted(orfs.orf)  # kept for the paralogue-search database (all_orfs.fasta)

# ---------------------------------------------------------------- sequences
def read_fasta(path):
    seqs = {}
    with gzip.open(path, 'rt') as fh:
        name = None
        buf = []
        for line in fh:
            if line.startswith('>'):
                if name:
                    seqs[name] = ''.join(buf)
                name = line[1:].split()[0]
                buf = []
            else:
                buf.append(line.strip())
        if name:
            seqs[name] = ''.join(buf)
    return seqs

prot = read_fasta(f'{RAW}/orf_trans_all.fasta.gz')
cds = read_fasta(f'{RAW}/orf_coding_all.fasta.gz')
orfs = orfs[orfs.orf.isin(prot) & orfs.orf.isin(cds)]
print('with sequences:', len(orfs))

# ---------------------------------------------------------------- essentiality (S288C systematic deletion)
pcols = ['feature', 'ftype', 'gene', 'sgdid', 'ref', 'exp', 'mutant', 'allele', 'strain', 'phenotype', 'chemical',
         'condition', 'details', 'reporter']
ph = pd.read_csv(f'{RAW}/phenotype_data.tab', sep='\t', header=None, names=pcols, dtype=str, keep_default_na=False)
sysnull = ph[(ph.mutant == 'null') & (ph.exp.str.contains('systematic mutation set')) & (ph.strain == 'S288C')]
inv = set(sysnull[sysnull.phenotype == 'inviable'].feature)
via = set(sysnull[sysnull.phenotype == 'viable'].feature)
conflict = inv & via
lab = {o: 1 for o in inv - conflict}
lab.update({o: 0 for o in via - conflict})
orfs['essential'] = orfs.orf.map(lab)
print('label known:', orfs.essential.notna().sum(), 'essential:', int(orfs.essential.sum()), 'conflicting removed:', len(conflict))
orfs = orfs[orfs.essential.notna()].copy()
orfs['essential'] = orfs.essential.astype(int)

# ---------------------------------------------------------------- sequence features
orfs['protein_length'] = orfs.orf.map(lambda o: len(prot[o].rstrip('*')))
orfs['gc_content'] = orfs.orf.map(lambda o: round(100 * sum(c in 'GC' for c in cds[o].upper()) / len(cds[o]), 1))

# codon adaptation index (Sharp & Li 1987) with the cytoplasmic ribosomal protein genes as the reference set
CODE = {}
bases = 'TCAG'
aas = 'FFLLSSSSYY**CC*WLLLLPPPPHHQQRRRRIIIMTTTTNNKKSSRRVVVVAAAADDEEGGGG'
i = 0
for a in bases:
    for b in bases:
        for c in bases:
            CODE[a + b + c] = aas[i]
            i += 1
syn = collections.defaultdict(list)
for cod, aa in CODE.items():
    syn[aa].append(cod)

def codons(seq):
    seq = seq.upper()
    return [seq[i:i + 3] for i in range(0, len(seq) - 2, 3)]

ref = orfs[orfs.gene.str.match(r'^RP[LS]\d+[AB]?$')]
print('CAI reference genes (cytoplasmic ribosomal proteins):', len(ref))
counts = collections.Counter()
for o in ref.orf:
    counts.update(c for c in codons(cds[o]) if c in CODE)
w = {}
for aa, cods in syn.items():
    if aa in '*MW':
        continue
    mx = max(counts[c] for c in cods)
    for c in cods:
        w[c] = max(counts[c], 0.5) / mx  # 0.5 pseudo-count for codons never used in the reference set

def cai(seq):
    ls = [math.log(w[c]) for c in codons(seq) if c in w]
    return math.exp(sum(ls) / len(ls)) if ls else float('nan')

orfs['codon_bias'] = orfs.orf.map(lambda o: round(cai(cds[o]), 3))

# ---------------------------------------------------------------- PaxDb protein abundance (ppm)
pax = pd.read_csv(f'{RAW}/paxdb_4932_integrated.txt', sep='\t', comment='#', header=None, names=['name', 'sid', 'abundance'])
pax['orf'] = pax.sid.str.replace('4932.', '', regex=False)
abund = dict(zip(pax.orf, pax.abundance))
orfs['protein_abundance'] = orfs.orf.map(abund)
print('with abundance:', orfs.protein_abundance.notna().sum())

# ---------------------------------------------------------------- BioGRID physical interaction partners
bg = pd.read_csv(f'{RAW}/BIOGRID-ORGANISM-Saccharomyces_cerevisiae_S288c-5.0.261.tab3.txt', sep='\t', dtype=str,
                 usecols=['Systematic Name Interactor A', 'Systematic Name Interactor B', 'Experimental System Type',
                          'Organism ID Interactor A', 'Organism ID Interactor B', 'Throughput'])
bg = bg[(bg['Experimental System Type'] == 'physical') & (bg['Organism ID Interactor A'] == '559292') & (bg['Organism ID Interactor B'] == '559292')]
bg = bg[bg['Systematic Name Interactor A'] != bg['Systematic Name Interactor B']]
partners = collections.defaultdict(set)
for a, b in zip(bg['Systematic Name Interactor A'], bg['Systematic Name Interactor B']):
    partners[a].add(b)
    partners[b].add(a)
orfs['interaction_partners'] = orfs.orf.map(lambda o: len(partners.get(o, ())))
print('physical interactions:', len(bg), 'median partners:', orfs.interaction_partners.median())

# ---------------------------------------------------------------- UniProt: accession, location, transmembrane helices
up = pd.read_csv(f'{RAW}/uniprot_yeast.tsv', sep='\t', dtype=str, keep_default_na=False)
acc = {}
loc_txt = {}
tm = {}
for _, r in up.iterrows():
    for o in re.split(r'[;\s]+', r['Gene Names (ordered locus)']):
        o = o.strip()
        if re.match(r'^Y[A-P][LR]\d{3}[WC](-[A-Z])?$', o):
            acc.setdefault(o, r['Entry'])
            loc_txt.setdefault(o, r['Subcellular location [CC]'])
            tm.setdefault(o, len(re.findall(r'TRANSMEM ', r['Transmembrane'])))
orfs['uniprot'] = orfs.orf.map(acc)
orfs['transmembrane_helices'] = orfs.orf.map(tm)
print('with UniProt accession:', orfs.uniprot.notna().sum())

LOC_ORDER = [
    ('Mitochondrion', r'Mitochondri'),
    ('Nucleus', r'Nucleus|Nucleolus|Chromosome|nucleus'),
    ('Endoplasmic reticulum', r'Endoplasmic reticulum|Microsome'),
    ('Golgi / vesicles', r'Golgi|Endosome|vesicle|Vesicle|Vacuole|vacuole|Lysosome|Autophag'),
    ('Plasma membrane / cell wall', r'Cell membrane|Bud|bud|Cell projection|Secreted|cell wall|Cell wall|Cell cortex|Cell septum'),
    ('Peroxisome', r'Peroxisome'),
    ('Cytoplasm', r'Cytoplasm|cytoskeleton|Cytosol|P-body|Stress granule'),
]

def location(txt):
    if not txt:
        return 'Unknown'
    t = txt.replace('SUBCELLULAR LOCATION:', '')
    t = re.sub(r'\{[^}]*\}', '', t)
    t = re.sub(r'Note=.*', '', t)
    # the first location mentioned is usually the main one; report the category of the first match
    best = None
    for name, pat in LOC_ORDER:
        m = re.search(pat, t)
        if m and (best is None or m.start() < best[1]):
            best = (name, m.start())
    return best[0] if best else 'Unknown'

# main compartment: SGD GO-slim cellular-component terms (better coverage), UniProt as a fallback
gs = pd.read_csv(f'{RAW}/go_slim_mapping.tab', sep='\t', header=None, dtype=str, keep_default_na=False,
                 names=['orf', 'gene', 'sgdid', 'aspect', 'term', 'goid', 'ftype'])
gs = gs[gs.aspect == 'C']
terms = gs.groupby('orf').term.apply(set).to_dict()
GO_ORDER = [
    ('Mitochondrion', {'mitochondrion'}),
    ('Nucleus', {'nucleus', 'nucleolus', 'chromatin', 'nuclear envelope', 'preribosome', 'spliceosomal complex', 'kinetochore'}),
    ('Endoplasmic reticulum', {'endoplasmic reticulum'}),
    ('Golgi, vesicles & vacuole', {'Golgi apparatus', 'endosome', 'cytoplasmic vesicle', 'vacuole'}),
    ('Plasma membrane & cell wall', {'plasma membrane', 'cell wall', 'site of polarized growth', 'external encapsulating structure', 'incipient cellular bud site'}),
    ('Peroxisome', {'peroxisome'}),
    ('Cytoplasm', {'cytoplasm', 'cytosol', 'large ribosomal subunit', 'small ribosomal subunit', 'cytoplasmic stress granule'}),
]
UP_MAP = {'Golgi / vesicles': 'Golgi, vesicles & vacuole', 'Plasma membrane / cell wall': 'Plasma membrane & cell wall'}

def go_location(o):
    t = terms.get(o, set())
    for name, s in GO_ORDER:
        if t & s:
            return name
    u = location(loc_txt.get(o, ''))
    return UP_MAP.get(u, u)

orfs['location'] = orfs.orf.map(go_location)
print(orfs.location.value_counts().to_dict())

orfs = orfs.rename(columns={'chrom': 'chromosome'})
keep = ['orf', 'gene', 'qualifier', 'chromosome', 'uniprot', 'essential', 'protein_length', 'gc_content', 'codon_bias',
        'protein_abundance', 'interaction_partners', 'transmembrane_helices', 'location', 'description']
orfs['gene'] = [g if g else o for g, o in zip(orfs.gene, orfs.orf)]
base = orfs[keep].sort_values('orf').reset_index(drop=True)
base.to_csv(f'{WORK}/base.tsv', sep='\t', index=False)
with open(f'{WORK}/proteins.fasta', 'w') as fh:
    for o in base.orf:
        fh.write(f'>{o}\n{prot[o].rstrip("*")}\n')
print('base table:', base.shape, 'essential fraction:', round(base.essential.mean(), 3))
# every verified/uncharacterised nuclear ORF: the database for the paralogue search
with open(f'{WORK}/all_orfs.fasta', 'w') as fh:
    for o in ALL_ORFS:
        if o in prot:
            fh.write(f'>{o}\n{prot[o].rstrip("*")}\n')
