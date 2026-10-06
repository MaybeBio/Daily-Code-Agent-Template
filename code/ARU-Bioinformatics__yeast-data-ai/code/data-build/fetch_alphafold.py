"""Fetch AlphaFold DB summary metrics (mean pLDDT, fraction very low) for every protein in the base table."""
import os
HERE = os.path.dirname(os.path.abspath(__file__))
import json, os, time, concurrent.futures as cf
import pandas as pd, requests

WORK = os.path.join(HERE, 'work')
out_path = f'{WORK}/alphafold.jsonl'
base = pd.read_csv(f'{WORK}/base.tsv', sep='\t')
done = set()
if os.path.exists(out_path):
    for line in open(out_path):
        done.add(json.loads(line)['uniprot'])
todo = [a for a in base.uniprot.dropna().unique() if a not in done]
print('to fetch:', len(todo), 'already:', len(done))
S = requests.Session()


def get(acc):
    for attempt in range(4):
        try:
            r = S.get(f'https://alphafold.ebi.ac.uk/api/prediction/{acc}', timeout=30)
            if r.status_code == 404:
                return {'uniprot': acc, 'found': False}
            if r.status_code == 200:
                d = r.json()
                e = next((x for x in d if x.get('uniprotAccession') == acc and x.get('sequenceStart', 1) == 1), d[0])
                return {'uniprot': acc, 'found': True, 'entry': e.get('entryId'), 'version': e.get('latestVersion'),
                        'plddt': e.get('globalMetricValue'), 'very_low': e.get('fractionPlddtVeryLow'),
                        'low': e.get('fractionPlddtLow'), 'confident': e.get('fractionPlddtConfident'),
                        'very_high': e.get('fractionPlddtVeryHigh'), 'start': e.get('uniprotStart'), 'end': e.get('uniprotEnd'),
                        'n_models': len(d)}
        except Exception as ex:  # network hiccup
            time.sleep(1 + attempt * 2)
    return {'uniprot': acc, 'found': None}


with open(out_path, 'a') as fh, cf.ThreadPoolExecutor(max_workers=8) as ex:
    for i, res in enumerate(ex.map(get, todo)):
        fh.write(json.dumps(res) + '\n')
        if i % 500 == 0:
            print(i, flush=True)
print('done')
