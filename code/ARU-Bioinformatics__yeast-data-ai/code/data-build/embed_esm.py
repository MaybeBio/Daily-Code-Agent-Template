"""Mean-pooled ESM-2 (35M) embeddings for every protein in work/proteins.fasta."""
import os
HERE = os.path.dirname(os.path.abspath(__file__))
import time, numpy as np, torch, esm
torch.set_num_threads(2)
W = os.path.join(HERE, 'work')
seqs = []
name = None
for line in open(f'{W}/proteins.fasta'):
    if line.startswith('>'):
        name = line[1:].strip()
    else:
        seqs.append((name, line.strip()))
model, alphabet = esm.pretrained.esm2_t12_35M_UR50D()
model.eval()
bc = alphabet.get_batch_converter()
L = model.num_layers
embs = np.zeros((len(seqs), model.embed_dim), dtype=np.float32)
t0 = time.time()
with torch.no_grad():
    for i, (n, s) in enumerate(seqs):
        s = s[:1022]
        _, _, toks = bc([(n, s)])
        rep = model(toks, repr_layers=[L])['representations'][L]
        embs[i] = rep[0, 1:len(s) + 1].mean(0).numpy()
        if i % 250 == 0:
            print(i, round(time.time() - t0), flush=True)
np.save(f'{W}/esm2_35M_mean.npy', embs)
open(f'{W}/esm2_order.txt', 'w').write('\n'.join(n for n, _ in seqs) + '\n')
print('done', embs.shape, round(time.time() - t0))
