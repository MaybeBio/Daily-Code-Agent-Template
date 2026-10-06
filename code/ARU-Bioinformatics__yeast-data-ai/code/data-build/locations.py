"""Main cellular compartment of each yeast protein from SGD's Gene Ontology annotations.

Rules
  * cellular-component annotations from the SGD GAF, excluding NOT qualifiers;
  * each GO term is mapped to one category through its is_a/part_of ancestors
    (an organelle wins over the generic 'cytoplasm' it is part of);
  * tier 1 = manually curated, low-throughput evidence; tier 2 = high-throughput and
    electronic annotations, used only when a gene has no tier-1 category;
  * the main compartment is the category with the most annotations (distinct term +
    reference); ties are broken in the order of CATS; for integral membrane proteins
    (UniProt transmembrane helices) generic 'Cytoplasm' annotations (cortex, bud,
    cytoskeleton-associated) do not count when a membrane compartment is annotated;
  * UniProt's subcellular location is the last resort, then 'Unknown'.
Writes work/locations.tsv (orf, location, tier).
"""
import os
HERE = os.path.dirname(os.path.abspath(__file__))
import gzip, re, collections, pandas as pd

RAW = os.path.join(HERE, 'raw')
WORK = os.path.join(HERE, 'work')

# ------------------------------------------------------------------ ontology
parents = collections.defaultdict(set)
names = {}
cur = None
obsolete = set()
for line in open(f'{RAW}/go-basic.obo', encoding='utf-8'):
    line = line.rstrip('\n')
    if line == '[Term]':
        cur = None
        continue
    if line.startswith('[') and line != '[Term]':
        cur = 'SKIP'
        continue
    if cur == 'SKIP':
        continue
    if line.startswith('id: GO:'):
        cur = line[4:]
    elif cur and line.startswith('name: '):
        names[cur] = line[6:]
    elif cur and line.startswith('is_a: '):
        parents[cur].add(line[6:16])
    elif cur and line.startswith('relationship: part_of '):
        parents[cur].add(line[22:32])
    elif cur and line.startswith('is_obsolete: true'):
        obsolete.add(cur)

anc_cache = {}
def ancestors(t):
    if t in anc_cache:
        return anc_cache[t]
    seen = {t}
    stack = [t]
    while stack:
        x = stack.pop()
        for p in parents.get(x, ()):
            if p not in seen:
                seen.add(p)
                stack.append(p)
    anc_cache[t] = seen
    return seen

CATS = [
    ('Nucleus', {'GO:0005634', 'GO:0005694', 'GO:0005635'}),                   # nucleus, chromosome, nuclear envelope
    ('Mitochondrion', {'GO:0005739'}),
    ('Endoplasmic reticulum', {'GO:0005783'}),
    ('Golgi, vesicles & vacuole', {'GO:0005794', 'GO:0005768', 'GO:0031410', 'GO:0005773', 'GO:0000323'}),
    ('Plasma membrane & cell wall', {'GO:0005886', 'GO:0005618', 'GO:0030312', 'GO:0005576'}),
    ('Peroxisome', {'GO:0005777'}),
    ('Cytoplasm', {'GO:0005737', 'GO:0005829', 'GO:0005856', 'GO:0005840', 'GO:0005938',
                   'GO:0030427', 'GO:0005933', 'GO:0010494', 'GO:0000932'}),  # + cortex, polarised growth, bud, stress granule, P-body
]
for _, s in CATS:
    for t in s:
        assert t in names, t

def category(term):
    a = ancestors(term)
    for name, s in CATS:
        if a & s:
            return name
    return None

HTP = {'HDA', 'HTP', 'HMP', 'HGI', 'HEP', 'IEA'}

# ------------------------------------------------------------------ annotations
counts = {1: collections.defaultdict(collections.Counter), 2: collections.defaultdict(collections.Counter)}
seen = set()
with gzip.open(f'{RAW}/gene_association.sgd.gaf.gz', 'rt', encoding='utf-8') as fh:
    for line in fh:
        if line.startswith('!'):
            continue
        f = line.rstrip('\n').split('\t')
        if len(f) < 15 or f[8] != 'C' or 'NOT' in f[3]:
            continue
        syn = f[10].split('|')
        orf = next((s for s in syn if re.match(r'^Y[A-P][LR]\d{3}[WC](-[A-Z])?$', s)), None)
        if orf is None:
            continue
        term, ev, ref = f[4], f[6], f[5]
        key = (orf, term, ref)
        if key in seen:
            continue
        seen.add(key)
        cat = category(term)
        if cat:
            counts[2 if ev in HTP else 1][orf][cat] += 1

ORDER = [c for c, _ in CATS]
def pick(c):
    return max(c.items(), key=lambda kv: (kv[1], -ORDER.index(kv[0])))[0]

base = pd.read_csv(f'{WORK}/base.tsv', sep='\t', dtype=str, keep_default_na=False)
up = dict(zip(base.orf, base.location))   # previous assignment (GO-slim, UniProt fallback) – only for comparison

# UniProt fallback
upt = pd.read_csv(f'{RAW}/uniprot_yeast.tsv', sep='\t', dtype=str, keep_default_na=False)
loc_txt = {}
for _, r in upt.iterrows():
    for o in re.split(r'[;\s]+', r['Gene Names (ordered locus)']):
        if re.match(r'^Y[A-P][LR]\d{3}[WC](-[A-Z])?$', o.strip()):
            loc_txt.setdefault(o.strip(), r['Subcellular location [CC]'])
UP_ORDER = [
    ('Mitochondrion', r'Mitochondri'),
    ('Nucleus', r'Nucleus|Nucleolus|Chromosome|nucleus'),
    ('Endoplasmic reticulum', r'Endoplasmic reticulum|Microsome'),
    ('Golgi, vesicles & vacuole', r'Golgi|Endosome|vesicle|Vesicle|Vacuole|vacuole|Lysosome|Autophag'),
    ('Plasma membrane & cell wall', r'Cell membrane|Secreted|cell wall|Cell wall'),
    ('Peroxisome', r'Peroxisome'),
    ('Cytoplasm', r'Cytoplasm|cytoskeleton|Cytosol|P-body|Stress granule|Bud|bud|Cell cortex|Cell projection|Cell septum'),
]
def uniprot_loc(txt):
    if not txt:
        return None
    t = txt.replace('SUBCELLULAR LOCATION:', '')
    t = re.sub(r'\{[^}]*\}', '', t)
    t = re.sub(r'Note=.*', '', t)
    best = None
    for name, pat in UP_ORDER:
        m = re.search(pat, t)
        if m and (best is None or m.start() < best[1]):
            best = (name, m.start())
    return best[0] if best else None

tmh = dict(zip(base.orf, pd.to_numeric(base.transmembrane_helices, errors='coerce').fillna(0)))
def pick_tm(o, c):
    if tmh.get(o, 0) >= 1 and len(c) > 1 and 'Cytoplasm' in c:
        c = {k: v for k, v in c.items() if k != 'Cytoplasm'}
    return pick(c)

rows = []
for o in base.orf:
    if counts[1].get(o):
        rows.append((o, pick_tm(o, counts[1][o]), 'curated'))
    elif counts[2].get(o):
        rows.append((o, pick_tm(o, counts[2][o]), 'high-throughput'))
    else:
        u = uniprot_loc(loc_txt.get(o, ''))
        rows.append((o, u or 'Unknown', 'uniprot' if u else 'none'))
loc = pd.DataFrame(rows, columns=['orf', 'location', 'tier'])
loc.to_csv(f'{WORK}/locations.tsv', sep='\t', index=False)
print(loc.tier.value_counts().to_dict())
print(loc.location.value_counts().to_dict())
changed = sum(up[o] != l for o, l in zip(loc.orf, loc.location))
print('changed vs previous:', changed)
