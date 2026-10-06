import argparse
import itertools
import math
import os
import tempfile
from collections import defaultdict
from itertools import product
from typing import Dict, List, Optional, Set, Tuple

import numpy as np

try:
    import pandas as pd
    PANDAS_AVAILABLE = True
except ImportError:
    PANDAS_AVAILABLE = False
    print("Warning: pandas not available — install: pip install pandas")

pyblock = None
try:
    import pyblock
    PYBLOCK_AVAILABLE = True
except ImportError:
    PYBLOCK_AVAILABLE = False
    print("Warning: pyblock not available — block errors default to 0; "
          "install: pip install pyblock")

try:
    from tqdm import tqdm
    TQDM_AVAILABLE = True
except ImportError:
    TQDM_AVAILABLE = False
    tqdm = lambda x, **kw: x   # no-op passthrough when tqdm not installed

try:
    import mdtraj as md
    MDTRAJ_AVAILABLE = True
except ImportError:
    MDTRAJ_AVAILABLE = False
    print("Warning: MDTraj not available")

# MDTraj H-bond geometry helpers — private API used by baker_hubbard2.
# Standard _get_bond_triplets does NOT accept lig_donors; ligand donors are
# appended manually inside baker_hubbard2 after calling the standard function.
_get_bond_triplets        = None
_compute_bounded_geometry = None
try:
    from mdtraj.geometry.hbond import _get_bond_triplets, _compute_bounded_geometry
except ImportError:
    if MDTRAJ_AVAILABLE:
        print("Warning: mdtraj.geometry.hbond internals not importable — "
              "compute_hbond_contacts() will not work")

try:
    import MDAnalysis as mda
    MDA_AVAILABLE = True
except ImportError:
    MDA_AVAILABLE = False
    print("Warning: MDAnalysis not available")

try:
    from rdkit import Chem
    from rdkit.Chem import AllChem
    from rdkit.Chem.Draw import rdMolDraw2D
    import io
    from PIL import Image
    RDKIT_AVAILABLE = True
except ImportError:
    RDKIT_AVAILABLE = False
    print("Warning: RDKit/PIL not available")

# rdDetermineBonds was added in RDKit 2022.09 — keep separate so an older RDKit
# doesn't break RDKIT_AVAILABLE for the rest of the module.
rdDetermineBonds = None
try:
    from rdkit.Chem import rdDetermineBonds
    RDKIT_DETERMINE_BONDS_AVAILABLE = True
except ImportError:
    RDKIT_DETERMINE_BONDS_AVAILABLE = False
    if RDKIT_AVAILABLE:
        print("Warning: rdDetermineBonds not available (requires RDKit >= 2022.09) — "
              "aromaticity will not be detected correctly for .gro inputs")

go = None
try:
    import plotly.graph_objects as go
    PLOTLY_AVAILABLE = True
except ImportError:
    PLOTLY_AVAILABLE = False

try:
    import torch
    USE_GPU    = torch.cuda.is_available()
    GPU_DEVICE = torch.device('cuda:1') if USE_GPU else None
    # GPU_DEVICE = torch.device('cuda') if USE_GPU else None
    TORCH_AVAILABLE = True
    if USE_GPU:
        print(f"[GPU] Acceleration enabled: {torch.cuda.get_device_name(0)}")
except ImportError:
    torch      = None
    USE_GPU    = False
    GPU_DEVICE = None
    TORCH_AVAILABLE = False
    print("Warning: PyTorch not available — GPU acceleration disabled for voxel analysis; "
          "install: pip install torch")

try:
    import mrcfile
    MRCFILE_AVAILABLE = True
except ImportError:
    mrcfile = None
    MRCFILE_AVAILABLE = False
    print("Warning: mrcfile not available — MRC volume export disabled; "
          "install: pip install mrcfile")

try:
    from sklearn.metrics import pairwise_distances as _sklearn_pairwise_distances
    from sklearn.metrics import silhouette_score as _sklearn_silhouette_score
    from sklearn.metrics import silhouette_samples as _sklearn_silhouette_samples
    from sklearn.decomposition import PCA as _sklearn_PCA
    from sklearn.preprocessing import StandardScaler as _sklearn_StandardScaler
    from sklearn.cluster import AgglomerativeClustering as _sklearn_AgglomerativeClustering
    SKLEARN_AVAILABLE = True
except ImportError:
    _sklearn_pairwise_distances       = None
    _sklearn_silhouette_score         = None
    _sklearn_silhouette_samples       = None
    _sklearn_PCA                      = None
    _sklearn_StandardScaler           = None
    _sklearn_AgglomerativeClustering  = None
    SKLEARN_AVAILABLE = False
    print("Warning: scikit-learn not available — ligand centroid PDB, PCA, and graph "
          "clustering disabled; install: pip install scikit-learn")

try:
    import networkx as nx
    NETWORKX_AVAILABLE = True
except ImportError:
    nx = None
    NETWORKX_AVAILABLE = False
    print("Warning: networkx not available — graph clustering disabled; "
          "install: pip install networkx")

try:
    import hdbscan as _hdbscan
    HDBSCAN_AVAILABLE = True
except ImportError:
    _hdbscan = None
    HDBSCAN_AVAILABLE = False
    # Only warn when actually requested — hdbscan is an optional clustering backend
    # for compute_graph_clustering()/cluster_graph_clustering() (default backend is
    # 'agglomerative', which only needs scikit-learn).

try:
    from scipy import ndimage as _scipy_ndimage
    SCIPY_AVAILABLE = True
except ImportError:
    _scipy_ndimage = None
    SCIPY_AVAILABLE = False
    print("Warning: scipy not available — Gaussian smoothing of MRC maps disabled; "
          "install: pip install scipy")

try:
    from deeptime.clustering import KMeans as _DeeptimeKMeans
    DEEPTIME_AVAILABLE = True
except ImportError:
    _DeeptimeKMeans = None
    DEEPTIME_AVAILABLE = False
    print("Warning: deeptime not available — PCA K-means clustering disabled; "
          "install: pip install deeptime")

try:
    import matplotlib.pyplot as _plt
    from matplotlib.figure import Figure as _MplFigure
    from matplotlib.backends.backend_agg import FigureCanvasAgg as _MplFigureCanvasAgg
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    _plt = None
    _MplFigure = None
    _MplFigureCanvasAgg = None
    MATPLOTLIB_AVAILABLE = False
    print("Warning: matplotlib not available — FES plots disabled; "
          "install: pip install matplotlib")
