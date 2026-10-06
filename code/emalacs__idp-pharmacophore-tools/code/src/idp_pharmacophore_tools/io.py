from itertools import product
from typing import Dict, List, Optional

import numpy as np

from ._deps import md
from .ligand_typing import analyze_topology, extract_ligand_mol


class IOMixin:

    def __init__(self, topology: str, trajectory: str) -> None:
        self._topology_path   = topology
        self._trajectory_path = trajectory

        # Populated by load()
        self.traj          = None   # full MDTraj trajectory
        self.protein_traj  = None   # protein-only slice
        self.protein_top   = None
        self.prot_lig_traj = None   # protein + ligand slice
        self.prot_lig_top  = None
        self.ligand_traj   = None   # ligand-only slice
        self.ligand_top    = None
        self.ligand_resname = None
        self.ligand_mol    = None   # RDKit Mol
        self.offset        = 0

        # Populated by _build_topology_definitions()
        self.residue_names            = None
        self.residue_names_dict       = None
        self.chain_counter            = 0
        self.simulation_times         = None
        self.protein_residue_numbers  = None
        self.ligand_residue_numbers   = None
        self.hydrophobic_residue_atoms_dict = None

        # Selection indices in prot_lig context (used for hbond computation)
        self._ligand_sel_idx  = None
        self._protein_sel_idx = None

        # Populated by get_ligand_rings(); used by get_atom_property()
        # NOTE: these are atom names from the RDKit PDB — validate against
        #       MDTraj atom names during benchmarking.
        self._ligand_aromatic_atom_names: set = set()
        # When not None, get_ligand_rings() returns this instead of running RDKit.
        # Each entry needs at minimum: {'atom_names': [...], 'aromatic': bool}
        self._manual_rings: Optional[List[Dict]] = None

        # Populated by compute_aromatic_contacts(); used by compute_contact_probability()
        self._stacked_full        = None   # (n_frames, n_protein_residues) geometric (p+t)
        self._pstacked_full       = None
        self._tstacked_full       = None
        self._stacked_by_ring     = None   # list[(n_frames, n_protein_residues)] per ligand ring
        self._aromatic_rings      = None   # ring dicts from get_ligand_rings()
        self._protein_rings_index = None   # residue indices of aromatic protein residues
        self.stacking_contacts_dict = None  # {'sum': array, '0': array, ...} for pharmacophore

        # Populated by compute_aromatic_contacts()
        self.aromatic_contact_probability = None  # pd.DataFrame indexed by residue name

        # Populated by compute_contact_probability()
        self.contact_probability  = None   # pd.DataFrame indexed by residue name
        self.dual_contact_matrix  = None   # (n_residues, n_residues) co-occurrence DataFrame
        self.kd                   = None   # (KD_mM, KD_error_mM)
        self.bound_fraction       = None   # (boundfrac, boundfrac_be)
        self.kd_over_time         = None   # pd.DataFrame cumulative bound-fraction time series

        # Populated by compute_hydrophobic_contacts()
        self.hydrophobic_contact_probability      = None  # pd.DataFrame indexed by residue name
        self.hydrophobic_contact_frames           = None  # (n_frames, n_pairs) binary array
        self.hydrophobic_atom_contact_probability = None  # ligand atom × protein atom DataFrame
        self.hydrophobic_ligand_atom_probability  = None  # per-ligand-atom probability DataFrame
        self.hydrophobic_distances_df             = None  # per-frame per-residue mean distance (if save_pca=True)

        # Populated by compute_hbond_contacts()
        self.hbond_contact_probability     = None  # pd.DataFrame indexed by residue name
        self.hbond_contact_frames_pd       = None  # (n_frames, n_residues) protein-donor binary
        self.hbond_contact_frames_ld       = None  # (n_frames, n_residues) ligand-donor binary
        self.hbond_pairs_pd                = None  # {res_idx: {prot_donor: {lig_acc: count}}}
        self.hbond_pairs_ld                = None  # {res_idx: {lig_donor: {prot_acc: count}}}
        self.hbond_donors_acceptors        = None  # topology-level donor/acceptor inventory
        self.hbond_ligand_atom_probability = None  # per-ligand-atom LD/PD probability DataFrame
        self.hbond_distances_df            = None  # per-frame raw distances (if save_pca=True)
        self.hbond_residue_distances_df    = None  # residue-pair distances (if save_pca=True)

        # Populated by compute_dssp()
        self.dssp_df           = None  # pd.DataFrame indexed by residue name
        self.dssp_over_time_df = None  # pd.DataFrame indexed by simulation time (if get_over_time=True)

        # Populated by compute_gyration_salpha()
        self.rg_over_time            = None  # np.ndarray, shape (n_frames,), Rg in nm
        self.salpha_over_time        = None  # np.ndarray, shape (n_frames,), per-frame total Sα
        self.gyration_salpha_fes_df  = None  # pd.DataFrame, 2D FES (Sα rows × Rg cols, kcal/mol)

        # Populated by compute_contact_map()
        self.contact_map_df     = None  # (n_res × n_res) contact probability DataFrame
        self.contact_map_raw_df = None  # (n_frames × n_pairs) raw distance DataFrame

        # Populated by compute_sasa()
        self.sasa_atoms_df         = None  # (n_frames × n_protein_atoms)    SASA in nm²
        self.sasa_residues_df      = None  # (n_frames × n_protein_residues) SASA in nm²
        self.sasa_ligand_atoms_df  = None  # (n_frames × n_ligand_atoms)     SASA in nm²
                                           # computed on prot_lig_traj (protein context)

        # Populated by compute_residue_dot_positions()
        self.residue_dot_positions = None  # dict: 'aromatic'/'hydrophobic'/'hba'/'hbd'
                                           # → np.ndarray (N, 3) absolute Å coordinates
                                           # (same system as MRC voxels — no centroid shift)

        # Populated by compute_all_atom_contacts()
        self.all_atom_contact_probability     = None  # pd.DataFrame indexed by residue name
        self.all_atom_contact_frames          = None  # (n_frames, n_lig_heavy * n_prot_heavy) binary
        self.all_atom_ligand_atom_probability = None  # per-ligand-atom contact probability DataFrame
        self.all_atom_distances_df            = None  # (n_frames, n_prot_heavy) mean distances (if save_pca=True)

        # Populated by compute_pca_trajectory()
        self.pca_result              = None   # (projection, eigenvalues, eigenvectors)
        self.pca_fes_df              = None   # 2D FES DataFrame (custom PCA)
        self.pca_fes_skl_df          = None   # 2D FES DataFrame (sklearn PCA, diagnostic)
        self.pca_dtraj               = None   # cluster assignment per frame, shape (n_frames,)
        self.pca_frames_cl           = None   # list of frame index arrays per cluster
        self.pca_cluster_centers     = None   # cluster centroids in PC space
        self.pca_clusters_fig        = None   # Plotly figure of PCA scatter
        self.pca_cluster_populations = None   # cluster size DataFrame
        self.pca_silhouette_score    = None   # float

        # Populated by compute_graph_clustering()
        self.graph_cluster_distance_matrix = None  # (n_frames, n_frames) Jaccard distance matrix
        self.graph_cluster_graphs          = None  # list[nx.Graph], one per frame
        self._graph_cluster_traj_attr      = None  # 'protein_traj' or 'prot_lig_traj' —
                                                    # which trajectory D/graphs are aligned to
        self._graph_cluster_full_n_frames  = None  # frame count of the original, un-sliced simulation —
                                                    # used by save_graph_cluster_trajectories()'s population filter

        # Populated by cluster_graph_clustering()
        self.graph_cluster_labels          = None  # (n_frames,) cluster label per frame (-1 = noise, hdbscan only)
        self.graph_cluster_df              = None  # pd.DataFrame: frame, time_ps, cluster, n_edges, mean_degree, Rg_nm
        self.graph_cluster_representatives = None  # dict: cluster_label -> representative frame index (local)
        self.graph_cluster_silhouette      = None  # float or None (None if <2 valid non-singleton clusters)

        # Populated by save_graph_cluster_trajectories()
        self.graph_cluster_saved_paths     = None  # dict: cluster_label -> {trajectory_path, structure_path,
                                                    #                          representative_frame, subset_frames}

        # Populated by compute_negative_space()
        self.negative_space_data          = None   # dict: masks, free_fraction, protein_occupancy, grid_info, volumes

        # Populated by define_pharmacophore()
        self.pharmacophore_maps_contested = None   # residue-type feature maps on contested space (occ ≥ 30%)
        self.pharmacophore_maps_full      = None   # residue-type feature maps on full shell (no threshold)
        self.growth_space_features        = None   # chemical features + linear scores for growth space

    # ── 1. Load ──────────────────────────────────────────────────────────────

    def load(self, ligand_resname: str = None, stride: int = 1, offset: int = 0) -> None:
        """Load topology + trajectory, extract ligand, build topology definitions.

        Parameters
        ----------
        ligand_resname : str, optional
            Ligand residue name. Auto-detected from topology when not provided.
        stride : int
            Load every N-th frame.
        offset : int
            Added to residue sequence numbers to match experimental convention.
            Defaults to 0; wire up CLI/notebook I/O when finalizing the algorithm.
        """
        # Step 1: MDAnalysis topology scan — auto-detect ligand
        topo_info = analyze_topology(self._topology_path)
        if 'error' in topo_info:
            print(f"Warning: topology scan failed — {topo_info['error']}")
            topo_info = {'has_ligand': False}

        if ligand_resname is not None:
            self.ligand_resname = ligand_resname
        elif topo_info.get('has_ligand'):
            self.ligand_resname = topo_info['ligand_resname']
            print(f"Auto-detected ligand: {self.ligand_resname}")
        else:
            self.ligand_resname = None

        # Step 2: load full trajectory (MDTraj)
        self.traj = md.load(self._trajectory_path, top=self._topology_path, stride=stride)
        print(f"\t{self._topology_path}")
        print(f"\t{self._trajectory_path}")
        print(f"\t{self.traj}")

        # Step 3: protein-only slice
        # Explicit exclusion prevents MDTraj from including the ligand in the protein slice
        protein_sel_str = (
            f'protein and not resname {self.ligand_resname}'
            if self.ligand_resname else 'protein'
        )
        protein_sel = self.traj.topology.select(protein_sel_str)
        self.protein_traj = self.traj.atom_slice(protein_sel)
        self.protein_top  = self.protein_traj.topology

        # Step 4: protein+ligand and ligand-only slices
        if self.ligand_resname:
            prot_lig_sel = self.traj.topology.select(
                f'protein or resname {self.ligand_resname}'
            )
            self.prot_lig_traj = self.traj.atom_slice(prot_lig_sel)
            self.prot_lig_top  = self.prot_lig_traj.topology

            lig_sel = self.traj.topology.select(f'resname {self.ligand_resname}')
            self.ligand_traj = self.traj.atom_slice(lig_sel)
            self.ligand_top  = self.ligand_traj.topology

            self._ligand_sel_idx  = self.prot_lig_top.select(f'resname {self.ligand_resname}')
            self._protein_sel_idx = self.prot_lig_top.select('protein')

        # Step 5: extract ligand as RDKit mol (MDAnalysis)
        if self.ligand_resname:
            self.ligand_mol = extract_ligand_mol(self._topology_path, self.ligand_resname)

        # Step 6: build residue/atom definitions
        self.offset = offset
        self._build_topology_definitions()

        print(f"\nLoaded: {self.traj.n_frames} frames")
        print(f"Protein residues: {self.protein_top.n_residues}")
        if self.ligand_resname:
            print(f"Ligand '{self.ligand_resname}': {self.ligand_top.n_atoms} atoms")

    def _build_topology_definitions(self) -> None:
        """Build residue numbering, atom selection arrays, and index dictionaries."""
        residue_names, chain_ids, residue_names_dict = [], [], {}
        chain_counter = residue_counter = 0

        for residue in self.protein_top.residues:
            name = f"{residue.name}_{residue.resSeq + self.offset}"
            if name in residue_names and residue_counter == len(residue_names):
                chain_counter += 1
                residue_counter = 0
            residue_names.append(name)
            chain_ids.append(chain_counter)
            residue_names_dict[residue.index] = name
            residue_counter += 1

        if chain_counter > 0:
            residue_names = [f"{n}_{c}" for n, c in zip(residue_names, chain_ids)]

        self.residue_names       = residue_names
        self.residue_names_dict  = residue_names_dict
        self.chain_counter       = chain_counter
        self.simulation_times    = self.protein_traj.time.tolist()
        self.protein_residue_numbers = [r.index for r in self.protein_top.residues]

        # Protein atom selections
        self.all_protein_atoms        = self.protein_top.select('all')
        self.all_protein_atoms_noh    = self.protein_top.select('all and not element H')
        self.hydrophobic_atoms_protein = self.protein_top.select('element C')

        # Hydrophobic residue → atom counter mapping
        # atom_counter is 0-based within the C-only selection (not global atom index)
        hydrophobic_residue_atoms = {}
        for atom_counter, atom_idx in enumerate(self.hydrophobic_atoms_protein):
            atom = self.protein_top.atom(atom_idx)
            key  = f"{atom.residue.name}_{atom.residue.resSeq + self.offset}"
            hydrophobic_residue_atoms.setdefault(key, []).append(atom_counter)
        self.hydrophobic_residue_atoms_dict = hydrophobic_residue_atoms

        if not self.ligand_resname:
            return

        # Ligand-specific definitions (all indices in prot_lig context)
        self.ligand_residue_numbers = [
            r.index for r in self.prot_lig_top.residues
            if r.name == self.ligand_resname
        ]
        self.all_ligand_atoms     = self.prot_lig_top.select(f'resname {self.ligand_resname}')
        self.all_ligand_atoms_noh = self.prot_lig_top.select(
            f'resname {self.ligand_resname} and not element H'
        )
        self.hydrophobic_atoms_ligand = self.prot_lig_top.select(
            f'resname {self.ligand_resname} and (element C or element S)'
        )

        # Combined protein+ligand residue name dict
        max_prot_key = max(residue_names_dict.keys()) if residue_names_dict else -1
        lig_residue_names_dict = {
            max_prot_key + 1 + i: f"{r.name}_{r.resSeq + self.offset}"
            for i, r in enumerate(self.ligand_top.residues)
        }
        self.all_residue_names_dict = residue_names_dict | lig_residue_names_dict

        # Atom name dict (prot_lig context — for contact matrix labeling)
        self.prot_lig_atom_names_dict = {
            atom.index: f'{atom.name}_{atom.residue.name}_{atom.residue.resSeq + self.offset}'
            for atom in self.prot_lig_top.atoms
        }

        # Ordered ligand atom labels for dataframe indexing
        self.ligand_atom_labels = [
            f'{self.prot_lig_top.atom(n).name}_{self.prot_lig_top.atom(n).residue.name}'
            f'_{self.prot_lig_top.atom(n).residue.resSeq + self.offset}'
            for n in self.prot_lig_top.select(f'resname {self.ligand_resname}')
        ]

        # Hydrophobic contact pairs (ligand C/S × protein C)
        self.protein_ligand_hphob_pairs = np.array(
            list(product(self.hydrophobic_atoms_ligand, self.hydrophobic_atoms_protein))
        )

    # ── 1b. Trajectory alignment ──────────────────────────────────────────────

    def ligand_align(self, selection: str = None) -> None:
        """Superpose the trajectory on a subset of ligand atoms, in-place.

        Centers and aligns every frame of ``prot_lig_traj`` onto the first
        frame using the atoms identified by *selection*.  The operation is
        in-place (MDTraj ``superpose`` returns ``self``), so no extra RAM is
        consumed and no file is written to disk.

        Call this immediately after ``load()`` and before any contact or
        voxel computation.

        Parameters
        ----------
        selection : str, optional
            MDTraj selection string identifying the reference atoms, e.g.
            ``"resname LIG and (name C1 or name C2 or name C3)"``.
            Use ``draw_molecule_with_labels()`` to identify atom names.
            When omitted, the default is to align on the entire ligand,
            built from ``self.ligand_resname`` (set by ``load()``).
        """
        if self.prot_lig_traj is None:
            raise RuntimeError("Call load() before ligand_align()")

        if selection is None:
            selection = f"resname {self.ligand_resname}"

        atom_indices = self.prot_lig_top.select(selection)
        if len(atom_indices) == 0:
            raise ValueError(f"Selection '{selection}' matched no atoms in prot_lig_top")

        print(f"Aligning on {len(atom_indices)} atom(s): {selection}")
        self.prot_lig_traj.superpose(
            reference=self.prot_lig_traj,
            frame=0,
            atom_indices=atom_indices,
        )

        # Sync ligand_traj to the aligned coordinates so ligand_centroid.pdb
        # (written by save_mrc_files from ligand_traj) matches the MRC grid.
        if self.ligand_traj is not None:
            self.ligand_traj.xyz[:] = self.prot_lig_traj.xyz[:, self._ligand_sel_idx, :]

        print("Alignment done — prot_lig_traj and ligand_traj updated in-place.")
