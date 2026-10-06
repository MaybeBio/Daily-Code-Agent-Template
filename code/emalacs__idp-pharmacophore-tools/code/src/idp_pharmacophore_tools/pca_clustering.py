import os
from collections import defaultdict
from typing import Dict, List, Optional, Set, Tuple

import numpy as np

from ._deps import (
    pd, md, MDTRAJ_AVAILABLE, tqdm,
    go, PLOTLY_AVAILABLE,
    _sklearn_PCA, _sklearn_StandardScaler, _sklearn_silhouette_score,
    _sklearn_silhouette_samples, _sklearn_AgglomerativeClustering,
    _DeeptimeKMeans, _plt,
    nx, NETWORKX_AVAILABLE,
    _hdbscan, HDBSCAN_AVAILABLE,
)

# ── PCA and trajectory clustering helpers ────────────────────────────────────

def res_space(nres: int, space: int) -> np.ndarray:
    """Residue pair index filter: excludes neighbours within ±space positions."""
    arr = np.arange(nres)
    return np.hstack([arr[np.abs(arr - i) > space] + i * nres for i in range(nres)])


def _pca_center(x: np.ndarray) -> np.ndarray:
    return x - x.mean(0)


def _pca_cov(x: np.ndarray, y: np.ndarray = None) -> np.ndarray:
    if y is None:
        y = x
    return _pca_center(x).T @ _pca_center(y) * (1 / (len(x) - 1))


def pca(x: np.ndarray, dim: int):
    """PCA via eigenvalue decomposition of the covariance matrix.

    Parameters
    ----------
    x   : np.ndarray, shape (n_samples, n_features)
    dim : int — number of principal components to retain

    Returns
    -------
    projection   : np.ndarray, shape (n_samples, dim)
    eigenvalues  : np.ndarray, shape (dim,)  — sorted descending
    eigenvectors : np.ndarray, shape (n_features, dim)
    """
    l, v = np.linalg.eigh(_pca_cov(x))
    idx  = l.argsort()[::-1]
    v, l = v[..., idx], l[idx]
    l, v = l[:dim], v[..., :dim]
    return x @ v, l, v


def fes2d(x, y, ax=None, xlabel=None, ylabel=None, cmap='jet', cbar=True,
          bins=50, weights=None, vmin=None, vmax=None,
          scatterx=None, scattery=None):
    """2D free energy surface as −log(P) from a 2D histogram.

    Returns (contour_set_or_None, fes_df).
    fes_df is a DataFrame indexed by y-bin centres with x-bin centres as columns.
    The contour plot is skipped when matplotlib is not available.
    """
    z, xe, ye = np.histogram2d(x, y, bins=bins, weights=weights)
    extent     = (xe.min(), xe.max(), ye.min(), ye.max())
    arr        = np.ma.masked_array(z, z == 0)
    F          = -np.log(arr)
    F         += -F.min()

    fes_df = pd.DataFrame(
        F.T,
        index=[float(v.real) for v in ye[:-1]],
        columns=[float(v.real) for v in xe[:-1]],
    )

    if _plt is None:
        return None, fes_df

    if ax is None:
        _, ax = _plt.subplots(1, 1, sharex=True, sharey=True)
    if scatterx is not None and scattery is not None:
        ax.scatter(scatterx, scattery, c='grey', s=60, edgecolors='black', alpha=0.5)
    a = ax.contourf(F.T, 30, cmap=cmap, extent=extent, zorder=-1, vmin=vmin, vmax=vmax)
    ax.set_xlabel(xlabel, fontsize=25)
    ax.set_ylabel(ylabel, fontsize=25)
    ax.tick_params(axis='x', labelsize=20)
    ax.tick_params(axis='y', labelsize=20)
    ax.set_aspect(abs((extent[1] - extent[0]) / (extent[3] - extent[2])) * 1.0)
    if cbar:
        cb = _plt.colorbar(a, ax=ax, fraction=0.046, pad=0.04, format='%.2f')
        cb.set_label('Free Energy / (kT)', size=25, labelpad=20)
        cb.ax.tick_params(labelsize=20)
    return a, fes_df


def kmeans(p: np.ndarray, k: int):
    """K-means clustering via deeptime.

    Returns (dtraj, frames_cl, cluster_centers).
    """
    if _DeeptimeKMeans is None:
        raise ImportError("deeptime required — install: pip install deeptime")
    cluster   = _DeeptimeKMeans(k, max_iter=1000).fit_fetch(p)
    dtraj     = cluster.transform(p)
    frames_cl = [np.where(dtraj == i)[0] for i in range(k)]
    return dtraj, frames_cl, cluster.cluster_centers


def plot_pca_clusters(projection: np.ndarray, dtraj: np.ndarray,
                      clustercenters: np.ndarray, title: str = '',
                      xlabel: str = 'PC1', ylabel: str = 'PC2'):
    """Plotly scatter of PCA projection coloured by cluster assignment.

    Returns go.Figure or None when Plotly is not available.
    """
    if not PLOTLY_AVAILABLE:
        return None
    n_cl   = int(dtraj.max()) + 1
    colors = [f'hsl({int(360 * i / n_cl)},70%,50%)' for i in range(n_cl)]
    fig    = go.Figure()
    for i in range(n_cl):
        mask = dtraj == i
        fig.add_trace(go.Scatter(
            x=projection[mask, 0], y=projection[mask, 1],
            mode='markers', name=f'Cluster {i + 1}',
            marker=dict(size=3, color=colors[i], opacity=0.6),
        ))
    for i, c in enumerate(clustercenters):
        fig.add_annotation(x=float(c[0]), y=float(c[1]), text=str(i + 1),
                           font=dict(size=14, color='white'), showarrow=False)
    fig.update_layout(title=title, xaxis_title=xlabel, yaxis_title=ylabel,
                      width=700, height=500)
    return fig


def plot_pca_pie(cluster_populations: 'pd.DataFrame'):
    """Plotly pie chart of PCA cluster population percentages.

    Returns go.Figure or None when Plotly is not available.
    """
    if not PLOTLY_AVAILABLE:
        return None
    fig = go.Figure(go.Pie(
        labels=[f'Cluster {int(c)}' for c in cluster_populations['Cluster']],
        values=cluster_populations['Percentage'],
        textinfo='label+percent',
    ))
    fig.update_layout(title='Cluster populations', width=500, height=400)
    return fig


def compute_pca(feature_matrix: np.ndarray, pca_dim: int = 2,
                analysis_dim: int = 2, n_clusters: int = 2,
                standard_scaler: bool = False):
    """PCA + K-means clustering pipeline.

    Mean-centering is performed internally by the covariance calculation.
    An optional StandardScaler step (zero mean, unit variance per feature)
    can be enabled with ``standard_scaler=True`` — this was the behaviour of
    the original REST-Analysis code and is needed to reproduce those results.
    Without it, features with higher post-kernel variance dominate the PCA.

    Parameters
    ----------
    feature_matrix : np.ndarray, shape (n_frames, n_features)
        Pre-processed feature matrix. For distance inputs with Gaussian kernel
        this is in [0,1]; otherwise raw distances in nm.
    pca_dim        : int — total principal components to compute
    analysis_dim   : int — PC dimensions used for K-means
    n_clusters     : int — number of K-means clusters
    standard_scaler : bool
        Apply sklearn StandardScaler (zero mean, unit std per feature) before
        PCA. Set to True to match the original REST-Analysis behaviour.
        Default False.

    Returns
    -------
    pca_result         : (projection, eigenvalues, eigenvectors)
    fes_df             : pd.DataFrame — 2D FES on PC1/PC2 (custom PCA)
    fes_skl_df         : pd.DataFrame — 2D FES from sklearn PCA (diagnostic)
    dtraj              : np.ndarray   — cluster assignment per frame
    frames_cl          : list[np.ndarray] — frame indices per cluster
    clustercenters     : np.ndarray   — cluster centroids in PC space
    clusters_fig       : go.Figure or None
    cluster_populations: pd.DataFrame
    silhouette         : float
    """
    if _sklearn_PCA is None:
        raise ImportError("scikit-learn required — install: pip install scikit-learn")
    if _DeeptimeKMeans is None:
        raise ImportError("deeptime required — install: pip install deeptime")

    print("Computing PCA …")

    # Optional StandardScaler — reproduces original REST-Analysis behaviour
    if standard_scaler:
        if _sklearn_StandardScaler is None:
            raise ImportError("scikit-learn required — install: pip install scikit-learn")
        print("  Applying StandardScaler (zero mean, unit std per feature) …")
        feature_matrix = _sklearn_StandardScaler().fit_transform(feature_matrix)

    # Sklearn PCA — diagnostic FES for comparison with the custom implementation
    pca_sk   = _sklearn_PCA(n_components=min(2, feature_matrix.shape[1]))
    proj_skl = pca_sk.fit_transform(feature_matrix)
    _, fes_skl_df = fes2d(proj_skl[:, 0], proj_skl[:, 1], cbar=False)

    # Custom PCA via eigendecomposition of the covariance matrix
    projection, l, v = pca(feature_matrix, dim=pca_dim)
    del feature_matrix
    print(f"  Eigenvalues: {l.shape}  Projection: {projection.shape}")

    _, fes_df = fes2d(projection[:, 0], projection[:, 1], cbar=False)

    # K-means on first analysis_dim PCs
    dtraj, frames_cl, clustercenters = kmeans(projection[:, :analysis_dim], n_clusters)
    silhouette = _sklearn_silhouette_score(projection, dtraj)

    clusters_fig = plot_pca_clusters(
        projection, dtraj, clustercenters,
        title=f'PCA clustering — silhouette: {silhouette:.3f}',
    )

    unique_vals, counts = np.unique(dtraj, return_counts=True)
    cluster_populations = pd.DataFrame({
        'Cluster':    unique_vals.astype(int).tolist(),
        'Count':      counts.astype(int).tolist(),
        'Percentage': [c / counts.sum() * 100 for c in counts],
    }).sort_values('Cluster').reset_index(drop=True)

    return (
        (projection, l, v),
        fes_df, fes_skl_df,
        dtraj, frames_cl, clustercenters,
        clusters_fig, cluster_populations, silhouette,
    )


# ── Graph clustering helpers ──────────────────────────────────────────────────
# Residue contact-network sub-clustering: builds one residue-residue contact
# graph per frame, measures Jaccard distance between frames' edge sets, and
# clusters frames by that distance. Intended to run on a PCA cluster subset
# (see compute_pca_trajectory / compute_pca above) as a second-level
# "graph on PCA subsets" clustering step.

def _valid_graph_clusters(labels: np.ndarray, allow_noise: bool = True) -> Dict[int, List[int]]:
    """Return dict cluster_label -> indices. Drops noise (-1) when allow_noise=False."""
    cl2idx = defaultdict(list)
    for i, lab in enumerate(labels):
        if lab == -1 and not allow_noise:
            continue
        cl2idx[lab].append(i)
    return {c: idx for c, idx in cl2idx.items() if len(idx) > 0}


def silhouette_from_distance(D: np.ndarray, labels: np.ndarray) -> Tuple[Optional[float], Optional[np.ndarray]]:
    """Mean silhouette score from a precomputed distance matrix.

    Requires at least 2 clusters with no singletons (noise label -1 and
    singleton clusters are dropped first). Returns (mean_score, per_sample_scores)
    or (None, None) when fewer than 2 valid clusters remain.
    """
    if _sklearn_silhouette_score is None or _sklearn_silhouette_samples is None:
        raise ImportError("scikit-learn required — install: pip install scikit-learn")

    cl2idx = _valid_graph_clusters(labels, allow_noise=False)
    cl2idx = {c: idx for c, idx in cl2idx.items() if len(idx) >= 2}
    if len(cl2idx) < 2:
        return None, None
    keep = sorted([i for idx in cl2idx.values() for i in idx])
    D_sub = D[np.ix_(keep, keep)]
    y_sub = labels[keep]
    try:
        s   = _sklearn_silhouette_score(D_sub, y_sub, metric='precomputed')
        s_i = _sklearn_silhouette_samples(D_sub, y_sub, metric='precomputed')
        return float(s), s_i
    except Exception:
        return None, None


def _build_nx_graphs(top, frame_edge_sets: List[Set[Tuple[int, int]]]) -> list:
    """One networkx.Graph per frame: nodes = all residues, edges = contacts in that frame."""
    if not NETWORKX_AVAILABLE:
        raise ImportError("networkx required — install: pip install networkx")
    node_ids = [r.index for r in top.residues]
    graphs = []
    for edges in frame_edge_sets:
        G = nx.Graph()
        G.add_nodes_from(node_ids)
        G.add_edges_from(edges)
        graphs.append(G)
    return graphs


def jaccard_distance_matrix(edge_sets: List[Set[Tuple[int, int]]]) -> np.ndarray:
    """Full pairwise Jaccard distance matrix between per-frame contact edge sets.

    distance = 1 - |A ∩ B| / |A ∪ B|

    Exact, O(n_frames²) pure-Python loop over set intersection/union — no
    vectorized or approximate (MinHash) fallback. Fine for a few thousand
    frames; can take a long time (potentially hours) at tens of thousands of
    frames. See DEVELOPMENT.md "Known limitation" for context.
    """
    print("Computing Jaccard distance matrix (exact)...")
    n = len(edge_sets)
    D = np.zeros((n, n), dtype=float)
    for i in tqdm(range(n)):
        Ai = edge_sets[i]
        for j in range(i + 1, n):
            Aj = edge_sets[j]
            if not Ai and not Aj:
                dist = 0.0
            else:
                inter = len(Ai & Aj)
                union = len(Ai | Aj)
                dist = 1.0 - (inter / union if union > 0 else 0.0)
            D[i, j] = D[j, i] = dist
    return D


def _cluster_by_distance(D: np.ndarray, clustering_method: str, n_clusters: Optional[int],
                         linkage: str, distance_threshold: Optional[float],
                         hdbscan_min_cluster_size: int = 10) -> np.ndarray:
    """Cluster frames from a precomputed distance matrix (agglomerative or hdbscan)."""
    if clustering_method == "hdbscan":
        if not HDBSCAN_AVAILABLE:
            raise ImportError("hdbscan required for clustering_method='hdbscan' — "
                              "install: pip install hdbscan")
        clusterer = _hdbscan.HDBSCAN(metric='precomputed', min_cluster_size=hdbscan_min_cluster_size)
        return clusterer.fit_predict(D)

    if _sklearn_AgglomerativeClustering is None:
        raise ImportError("scikit-learn required — install: pip install scikit-learn")
    model = _sklearn_AgglomerativeClustering(
        n_clusters=n_clusters,
        metric='precomputed',
        linkage=linkage,
        distance_threshold=None if n_clusters is not None else distance_threshold,
    )
    return model.fit_predict(D)


def _representative_frames(graphs: list, labels: np.ndarray,
                           criterion: str = "max_degree") -> Dict[int, int]:
    """Pick one representative frame per cluster.

    criterion='max_degree' picks the frame with the highest mean node degree
    (densest contact network); any other value falls back to the frame with
    the most edges. Noise label (-1, HDBSCAN only) is skipped.
    """
    reps: Dict[int, int] = {}
    for cl in sorted(set(labels)):
        if cl == -1:
            continue
        idx = np.where(labels == cl)[0]
        if criterion == "max_degree":
            best_i, best_score = None, -1
            for i in idx:
                degs = [d for _, d in graphs[i].degree()]
                score = float(np.mean(degs)) if degs else 0.0
                if score > best_score:
                    best_i, best_score = i, score
            reps[cl] = int(best_i)
        else:
            best_i = max(idx, key=lambda i: graphs[i].number_of_edges())
            reps[cl] = int(best_i)
    return reps


def _save_gexf(graphs: list, out_dir: str) -> None:
    """Write one .gexf file per frame graph (viewable in Gephi/Cytoscape)."""
    if not NETWORKX_AVAILABLE:
        raise ImportError("networkx required — install: pip install networkx")
    os.makedirs(out_dir, exist_ok=True)
    for i, G in enumerate(graphs):
        nx.write_gexf(G, os.path.join(out_dir, f"frame_{i:06d}.gexf"))


class PCAClusteringMixin:

    # ── 4b. PCA trajectory analysis ───────────────────────────────────────────

    def compute_pca_trajectory(self, pca_dim: int = 2, analysis_dim: int = 2,
                               n_clusters: int = 2, gaussian_kernel: bool = True,
                               gaussian_sigma: float = 0.3,
                               standard_scaler: bool = False):
        """Run PCA + K-means clustering on the all-atom contact distance matrix.

        Requires compute_all_atom_contacts(save_pca=True) to have been called first.

        A Gaussian kernel exp(−d²/2σ²) is applied to raw distances before PCA
        (recommended). An optional StandardScaler step can be enabled with
        ``standard_scaler=True`` to reproduce results from the original
        REST-Analysis codebase, where StandardScaler was applied inside
        compute_pca after the Gaussian kernel.

        Parameters
        ----------
        pca_dim : int
            Total number of principal components to compute. Default 2.
        analysis_dim : int
            Number of PC dimensions passed to K-means. Default 2.
        n_clusters : int
            Number of K-means clusters. Default 2.
        gaussian_kernel : bool
            Apply Gaussian kernel exp(−d²/2σ²) to distances before PCA.
            Default True.
        gaussian_sigma : float
            Kernel width in nm. Default 0.3 nm (3 Å).
        standard_scaler : bool
            Apply StandardScaler (zero mean, unit std per feature) after the
            Gaussian kernel and before PCA. Set to True to match the original
            REST-Analysis behaviour. Default False.

        Returns
        -------
        (projection, eigenvalues, eigenvectors)
            Also stored on self.pca_result and related attributes.
        """
        if self.all_atom_distances_df is None:
            raise RuntimeError(
                "Call compute_all_atom_contacts(save_pca=True) before compute_pca_trajectory()"
            )

        pca_matrix = self.all_atom_distances_df.to_numpy()
        print(f"PCA input: {pca_matrix.shape[0]} frames × {pca_matrix.shape[1]} features")

        if gaussian_kernel:
            print(f"Applying Gaussian kernel (σ = {gaussian_sigma} nm) …")
            pca_matrix = np.exp(-(pca_matrix ** 2) / (2 * gaussian_sigma ** 2))

        (projection, l, v), fes_df, fes_skl_df, dtraj, frames_cl, clustercenters, \
            clusters_fig, cluster_populations, silhouette = \
            compute_pca(pca_matrix, pca_dim=pca_dim, analysis_dim=analysis_dim,
                        n_clusters=n_clusters, standard_scaler=standard_scaler)

        self.pca_result              = (projection, l, v)
        self.pca_fes_df              = fes_df
        self.pca_fes_skl_df          = fes_skl_df
        self.pca_dtraj               = dtraj
        self.pca_frames_cl           = frames_cl
        self.pca_cluster_centers     = clustercenters
        self.pca_clusters_fig        = clusters_fig
        self.pca_cluster_populations = cluster_populations
        self.pca_silhouette_score    = silhouette

        print(f"  Silhouette score : {silhouette:.3f}")
        print(f"  Cluster sizes    : {[len(f) for f in frames_cl]}")

        return projection, l, v

    # ── 4f. Graph-based sub-clustering ────────────────────────────────────────
    # Second-level clustering on top of a PCA cluster subset: builds a
    # residue-contact-network graph per frame and clusters frames by Jaccard
    # distance between those networks. Run this on a PCA-sliced `sim_cl`
    # (see analysis.ipynb Section 6) to split a PCA cluster further, mirroring
    # the original REST-Analysis "PCA_C{i}_Graph{j}" sub-clustering scheme.

    def compute_graph_clustering(self, cutoff: float = 0.6, scheme: str = 'closest',
                                 use_ligand: bool = False,
                                 full_trajectory_frames: Optional[int] = None):
        """Build per-frame residue contact graphs and the Jaccard distance matrix.

        Step 1 of the graph-clustering pipeline (expensive — O(n_frames²)
        Jaccard computation). Run cluster_graph_clustering() afterwards to
        assign labels; re-running that second step with different clustering
        parameters does not require rebuilding the graphs/distance matrix.

        Parameters
        ----------
        cutoff : float
            Residue-residue closest-atom distance cutoff in nm defining a
            contact edge. Default 0.6 nm.
        scheme : str
            MDTraj contact scheme passed to md.compute_contacts. Default 'closest'.
        use_ligand : bool
            If True, build the contact network on self.prot_lig_traj (protein +
            ligand residues). If False (default), use self.protein_traj (protein only).
        full_trajectory_frames : int or None
            Frame count of the original, un-sliced simulation this trajectory was
            taken from (e.g. sim.protein_traj.n_frames, when this is called on a
            PCA-cluster subset sim_cl). Used by save_graph_cluster_trajectories()'s
            min_population_fraction filter. Defaults to this trajectory's own
            n_frames when None — i.e. assumes self is already the full simulation.

        Returns
        -------
        (D, graphs)
            D      : (n_frames, n_frames) Jaccard distance matrix
            graphs : list[nx.Graph], one per frame
            Also stored on self.graph_cluster_distance_matrix / self.graph_cluster_graphs.
        """
        if not MDTRAJ_AVAILABLE:
            raise ImportError("MDTraj required — install via conda-forge: mdtraj")
        if not NETWORKX_AVAILABLE:
            raise ImportError("networkx required — install: pip install networkx")

        traj_attr = 'prot_lig_traj' if use_ligand else 'protein_traj'
        traj = getattr(self, traj_attr)
        if traj is None:
            raise RuntimeError("Call load() before compute_graph_clustering()")

        print(f"Building residue contact graphs ({'protein+ligand' if use_ligand else 'protein'}, "
              f"cutoff={cutoff} nm, scheme='{scheme}') …")

        n_res = traj.n_residues
        res_pairs = np.stack(np.triu_indices(n_res, 1), 1)

        print("Computing residue–residue closest-atom distances...")
        dists, used_pairs = md.compute_contacts(traj, contacts=res_pairs, scheme=scheme)
        used_pairs = [(int(i), int(j)) for i, j in used_pairs]

        print("Thresholding to contacts and building edge sets...")
        frame_edge_sets: List[Set[Tuple[int, int]]] = []
        for f in tqdm(range(traj.n_frames)):
            mask = dists[f] < cutoff
            edges = {used_pairs[k] for k, m in enumerate(mask) if m}
            frame_edge_sets.append(edges)

        graphs = _build_nx_graphs(traj.topology, frame_edge_sets)
        D = jaccard_distance_matrix(frame_edge_sets)

        self.graph_cluster_distance_matrix = D
        self.graph_cluster_graphs          = graphs
        self._graph_cluster_traj_attr      = traj_attr
        self._graph_cluster_full_n_frames  = (
            full_trajectory_frames if full_trajectory_frames is not None else traj.n_frames
        )

        return D, graphs

    def cluster_graph_clustering(self, clustering_method: str = 'agglomerative',
                                 n_clusters: Optional[int] = None, linkage: str = 'average',
                                 distance_threshold: float = 0.4, representative_by: str = 'max_degree',
                                 hdbscan_min_cluster_size: int = 10,
                                 save_gexf: bool = False, gexf_dir: str = 'graphs_gexf'):
        """Cluster frames from the distance matrix built by compute_graph_clustering().

        Step 2 of the graph-clustering pipeline (cheap — safe to re-run with
        different clustering parameters without recomputing D/graphs).

        Parameters
        ----------
        clustering_method : str
            'agglomerative' (default, scikit-learn) or 'hdbscan' (optional dependency).
        n_clusters : int or None
            Number of clusters for agglomerative clustering. Mutually exclusive
            with distance_threshold — set exactly one, leave the other as its default.
        linkage : str
            Agglomerative linkage criterion. Default 'average'.
        distance_threshold : float
            Agglomerative distance threshold, used only when n_clusters is None.
        representative_by : str
            'max_degree' (default) picks the highest mean-node-degree frame per
            cluster; any other value picks the frame with the most edges.
        hdbscan_min_cluster_size : int
            Only used when clustering_method='hdbscan'. Default 10.
        save_gexf : bool
            If True, write one .gexf file per frame graph to gexf_dir (viewable
            in Gephi/Cytoscape). Default False.

        Returns
        -------
        (graph_df, representatives, silhouette)
            graph_df        : pd.DataFrame — frame, time_ps, cluster, n_edges, mean_degree, Rg_nm
            representatives : dict — cluster_label -> representative frame index (local)
            silhouette      : float or None (None if <2 valid non-singleton clusters)
            Also stored on self.graph_cluster_labels / self.graph_cluster_df /
            self.graph_cluster_representatives / self.graph_cluster_silhouette.
        """
        if self.graph_cluster_distance_matrix is None or self.graph_cluster_graphs is None:
            raise RuntimeError(
                "Call compute_graph_clustering() before cluster_graph_clustering()"
            )

        D      = self.graph_cluster_distance_matrix
        graphs = self.graph_cluster_graphs
        traj   = getattr(self, self._graph_cluster_traj_attr)

        print(f"Clustering {len(graphs)} frames ({clustering_method}) …")
        labels = _cluster_by_distance(D, clustering_method, n_clusters, linkage,
                                      distance_threshold, hdbscan_min_cluster_size)
        silhouette, _ = silhouette_from_distance(D, labels)

        graph_df = pd.DataFrame({
            "frame":       np.arange(traj.n_frames),
            "time_ps":     traj.time,
            "cluster":     labels,
            "n_edges":     [g.number_of_edges() for g in graphs],
            "mean_degree": [np.mean([d for _, d in g.degree()]) if g.number_of_nodes() > 0 else 0.0
                            for g in graphs],
            "Rg_nm":       md.compute_rg(traj).flatten(),
        })

        representatives = _representative_frames(graphs, labels, criterion=representative_by)

        if save_gexf:
            _save_gexf(graphs, gexf_dir)
            print(f"Saved per-frame graphs to {gexf_dir}/*.gexf")

        self.graph_cluster_labels          = labels
        self.graph_cluster_df              = graph_df
        self.graph_cluster_representatives = representatives
        self.graph_cluster_silhouette      = silhouette

        print(f"  Silhouette score : {silhouette}")
        print(f"  Cluster sizes    :\n{graph_df['cluster'].value_counts().to_string()}")

        return graph_df, representatives, silhouette

    def save_graph_cluster_trajectories(self, output_dir: str,
                                        min_population_fraction: float = 0.01,
                                        clusters_to_save: Optional[int] = None):
        """Write per-cluster sub-trajectories from cluster_graph_clustering() results.

        For each cluster passing the min_population_fraction floor (all of
        them by default, optionally capped further to the top clusters_to_save
        by population), writes into {output_dir}/graph_clusters/:
          cluster_{rank}_trajectory.xtc  — full multi-frame subset
          cluster_{rank}_trajectory.gro  — single representative frame

        Parameters
        ----------
        min_population_fraction : float
            Drop clusters smaller than this fraction of the *original* full
            simulation (self._graph_cluster_full_n_frames, set by
            compute_graph_clustering()'s full_trajectory_frames argument —
            not just this trajectory's own frame count). Default 0.01 (1%).
        clusters_to_save : int or None
            If given, further cap to the top clusters_to_save by population
            among those passing the fraction floor. Default None (keep all
            that pass the floor).

        Clusters are ranked by population size, largest first (rank 0 =
        largest), matching the on-disk naming already used elsewhere in this
        project's output/ folders. The noise label (-1, HDBSCAN only) is
        never saved.

        Frame indices (subset_frames, representative_frame) are in the *local*
        index space of whichever trajectory compute_graph_clustering() used
        (self.protein_traj or self.prot_lig_traj) — already relative to a PCA
        cluster subset if this is called on a sim_cl slice, not a global index
        into some larger "complete" trajectory.

        Returns
        -------
        dict : cluster_label -> {trajectory_path, structure_path, representative_frame, subset_frames}
            Also stored on self.graph_cluster_saved_paths.
        """
        if self.graph_cluster_df is None or self.graph_cluster_representatives is None:
            raise RuntimeError(
                "Call cluster_graph_clustering() before save_graph_cluster_trajectories()"
            )

        traj = getattr(self, self._graph_cluster_traj_attr)
        out_dir = os.path.join(output_dir, 'graph_clusters')
        os.makedirs(out_dir, exist_ok=True)

        cluster_counts = self.graph_cluster_df['cluster'].value_counts().sort_values(ascending=False)
        cluster_counts = cluster_counts[cluster_counts.index != -1]

        min_frames = min_population_fraction * self._graph_cluster_full_n_frames
        clusters = cluster_counts[cluster_counts >= min_frames].index.tolist()
        dropped = cluster_counts[cluster_counts < min_frames]
        if len(dropped):
            print(f"  Dropping {len(dropped)} cluster(s) below {min_population_fraction*100:.1f}% "
                  f"of {self._graph_cluster_full_n_frames} frames ({min_frames:.0f} frames): "
                  f"{dropped.to_dict()}")

        if clusters_to_save is not None:
            clusters = clusters[:clusters_to_save]

        saved_paths = {}
        for rank, cluster in enumerate(clusters):
            subset_frames = self.graph_cluster_df.loc[
                self.graph_cluster_df['cluster'] == cluster, 'frame'
            ].tolist()
            representative_frame = self.graph_cluster_representatives[cluster]

            trajectory_path = os.path.join(out_dir, f'cluster_{rank}_trajectory.xtc')
            structure_path  = os.path.join(out_dir, f'cluster_{rank}_trajectory.gro')

            traj[subset_frames].save_xtc(trajectory_path)
            traj[representative_frame].save_gro(structure_path)

            print(f"  Cluster {cluster} → rank {rank}: {len(subset_frames)} frames, "
                  f"representative frame {representative_frame}")

            saved_paths[cluster] = {
                'trajectory_path':      trajectory_path,
                'structure_path':       structure_path,
                'representative_frame': representative_frame,
                'subset_frames':        subset_frames,
            }

        self.graph_cluster_saved_paths = saved_paths
        return saved_paths
