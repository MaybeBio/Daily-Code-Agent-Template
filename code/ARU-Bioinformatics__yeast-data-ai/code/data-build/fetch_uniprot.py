"""Download UniProt entries for S. cerevisiae S288C (taxon 559292) as TSV -> raw/uniprot_yeast.tsv.

Uses the paged search endpoint (the stream endpoint sometimes times out for this query).
"""
import os, re, requests

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'raw', 'uniprot_yeast.tsv')
URL = ('https://rest.uniprot.org/uniprotkb/search?query=organism_id:559292+AND+reviewed:true'
       '&fields=accession,gene_oln,gene_primary,protein_name,length,cc_subcellular_location,ft_transmem,xref_sgd'
       '&format=tsv&size=500')

S = requests.Session()
url, lines, header = URL, [], None
while url:
    r = S.get(url, timeout=120)
    r.raise_for_status()
    rows = r.text.rstrip('\n').split('\n')
    if header is None:
        header = rows[0]
        print('UniProt release', r.headers.get('X-UniProt-Release'), '| entries', r.headers.get('X-Total-Results'))
    lines.extend(rows[1:])
    m = re.search(r'<([^>]+)>;\s*rel="next"', r.headers.get('Link', ''))
    url = m.group(1) if m else None
with open(OUT, 'w', encoding='utf-8') as fh:
    fh.write(header + '\n' + '\n'.join(lines) + '\n')
print('wrote', OUT, len(lines), 'entries')
