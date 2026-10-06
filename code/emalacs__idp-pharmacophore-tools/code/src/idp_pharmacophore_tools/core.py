from .io import IOMixin
from .ligand_typing import LigandTypingMixin
from .contacts import ContactsMixin
from .structure_metrics import StructureMetricsMixin
from .pca_clustering import PCAClusteringMixin
from .voxel_maps import VoxelMapsMixin
from .pymol_export import PymolExportMixin
from .plotting import PlottingMixin


class PharmacophoreTrajectory(
    IOMixin, LigandTypingMixin, ContactsMixin, StructureMetricsMixin,
    PCAClusteringMixin, VoxelMapsMixin, PymolExportMixin, PlottingMixin,
):
    """Load and analyse MD trajectories for pharmacophore definition.

    Hybrid approach:
      - MDAnalysis + RDKit for ligand extraction and chemical feature typing
      - MDTraj for trajectory loading and all distance/contact computation

    Example
    -------
    >>> from idp_pharmacophore_tools import PharmacophoreTrajectory, draw_molecule_with_labels
    >>> sim = PharmacophoreTrajectory("system.gro", "traj.xtc")
    >>> sim.load(stride=1)                     # ligand auto-detected
    >>> sim.load(ligand_resname="LIG")         # explicit override
    >>> rings = sim.get_ligand_rings()
    >>> img, mol = draw_molecule_with_labels(sim.ligand_mol)
    """

    # ── Memory management ────────────────────────────────────────────────────

    def clear_results(self, keep_pca_clusters: bool = True) -> None:
        """Free RAM by resetting all computed results to None.

        The trajectory, topology definitions, and ligand chemical features are
        preserved so the object can be reused for further computations (e.g.
        on a new cluster subset) without reloading from disk.

        Parameters
        ----------
        keep_pca_clusters : bool
            When True (default), preserve the PCA cluster frame assignments
            (pca_frames_cl, pca_dtraj, pca_cluster_populations,
            pca_cluster_centers, pca_clusters_fig, pca_silhouette_score)
            so Section-6 cluster analysis can still run after clearing.
            Set to False to wipe PCA results as well.
        """
        # ── Aromatic contacts ─────────────────────────────────────────────
        self._stacked_full         = None
        self._pstacked_full        = None
        self._tstacked_full        = None
        self._stacked_by_ring      = None
        self._aromatic_rings       = None
        self._protein_rings_index  = None
        self.stacking_contacts_dict = None
        self.aromatic_contact_probability = None

        # ── General contact probability ───────────────────────────────────
        self.contact_probability  = None
        self.dual_contact_matrix  = None
        self.kd                   = None
        self.bound_fraction       = None
        self.kd_over_time         = None

        # ── Hydrophobic contacts ──────────────────────────────────────────
        self.hydrophobic_contact_probability      = None
        self.hydrophobic_contact_frames           = None
        self.hydrophobic_atom_contact_probability = None
        self.hydrophobic_ligand_atom_probability  = None
        self.hydrophobic_distances_df             = None

        # ── H-bond contacts ───────────────────────────────────────────────
        self.hbond_contact_probability     = None
        self.hbond_contact_frames_pd       = None
        self.hbond_contact_frames_ld       = None
        self.hbond_pairs_pd                = None
        self.hbond_pairs_ld                = None
        self.hbond_donors_acceptors        = None
        self.hbond_ligand_atom_probability = None
        self.hbond_distances_df            = None
        self.hbond_residue_distances_df    = None

        # ── DSSP ──────────────────────────────────────────────────────────
        self.dssp_df           = None
        self.dssp_over_time_df = None

        # ── Gyration radius & Sα ──────────────────────────────────────────
        self.rg_over_time           = None
        self.salpha_over_time       = None
        self.gyration_salpha_fes_df = None

        # ── Contact map ───────────────────────────────────────────────────
        self.contact_map_df     = None
        self.contact_map_raw_df = None

        # ── SASA ──────────────────────────────────────────────────────────
        self.sasa_atoms_df        = None
        self.sasa_residues_df     = None
        self.sasa_ligand_atoms_df = None

        # ── Residue dot positions ─────────────────────────────────────────
        self.residue_dot_positions = None

        # ── All-atom contacts + PCA feature matrix ────────────────────────
        self.all_atom_contact_probability     = None
        self.all_atom_contact_frames          = None
        self.all_atom_ligand_atom_probability = None
        self.all_atom_distances_df            = None

        # ── Voxel / pharmacophore ─────────────────────────────────────────
        self.negative_space_data          = None
        self.pharmacophore_maps_contested = None
        self.pharmacophore_maps_full      = None
        self.growth_space_features        = None

        # ── Graph clustering ──────────────────────────────────────────────
        self.graph_cluster_distance_matrix = None
        self.graph_cluster_graphs          = None
        self._graph_cluster_traj_attr      = None
        self._graph_cluster_full_n_frames  = None
        self.graph_cluster_labels          = None
        self.graph_cluster_df              = None
        self.graph_cluster_representatives = None
        self.graph_cluster_silhouette      = None
        self.graph_cluster_saved_paths     = None

        # ── PCA results ───────────────────────────────────────────────────
        if not keep_pca_clusters:
            self.pca_result              = None
            self.pca_fes_df              = None
            self.pca_fes_skl_df          = None
            self.pca_dtraj               = None
            self.pca_frames_cl           = None
            self.pca_cluster_centers     = None
            self.pca_clusters_fig        = None
            self.pca_cluster_populations = None
            self.pca_silhouette_score    = None
        else:
            # Only clear the large FES DataFrames and raw projection;
            # cluster assignments and visualisation figures are kept.
            self.pca_result     = None
            self.pca_fes_df     = None
            self.pca_fes_skl_df = None

        import gc
        gc.collect()
        print("Results cleared."
              + (" PCA cluster assignments retained." if keep_pca_clusters else ""))
