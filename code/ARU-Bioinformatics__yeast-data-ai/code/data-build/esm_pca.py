"""PCA-reduce the ESM-2 embeddings to 32 components for the site."""
import os
HERE = os.path.dirname(os.path.abspath(__file__))
import numpy as np, pandas as pd
from sklearn.decomposition import PCA
W = os.path.join(HERE, 'work')
OUT = os.path.join(HERE, '..', 'data')
E = np.load(f'{W}/esm2_35M_mean.npy')
orfs = [l.strip() for l in open(f'{W}/esm2_order.txt') if l.strip()]
pca = PCA(n_components=32, random_state=0).fit(E)
Z = pca.transform(E)
print('explained variance (32 PCs): %.3f' % pca.explained_variance_ratio_.sum(), 'first 2:', pca.explained_variance_ratio_[:2].round(3))
out = pd.DataFrame(Z.round(4), columns=[f'esm_{i + 1}' for i in range(32)])
out.insert(0, 'orf', orfs)
out.to_csv(os.path.join(OUT, 'yeast_esm2.csv'), index=False)
np.save(f'{W}/esm2_pca32.npy', Z)
print(out.shape)
