import itertools
from itertools import product

import numpy as np

from ._deps import (
    md, MDTRAJ_AVAILABLE, pd, PANDAS_AVAILABLE, tqdm,
    _get_bond_triplets, _compute_bounded_geometry,
)
from ._constants import DEFAULT_CONTACT_CUTOFF, DEFAULT_HYDROPHOBIC_CUTOFF
from ._stats import get_blockerrors_pyblock_nanskip, get_blockerror_pyblock_nanskip


# ── Aromatic geometry helpers ─────────────────────────────────────────────────

def find_plane_normal_new(positions):
    """Fit a best-fit plane to each set of ring atoms and return normal vectors.

    Parameters
    ----------
    positions : np.ndarray, shape (n_frames, n_ring_atoms, 3)

    Returns
    -------
    np.ndarray, shape (n_frames, 3)
    """
    num_atoms = positions.shape[0]
    A = positions[:, :, 0:2].reshape(-1, 2)
    B = positions[:, :, 2].reshape(-1)
    A = np.concatenate((A, np.ones((A.shape[0], 1))), axis=1)
    A = A.reshape(num_atoms, positions.shape[1], -1)
    results = np.empty((num_atoms, 3))
    for i in range(num_atoms):
        A_slice = A[i, :, :]
        B_slice = B[i * A.shape[1]:(i + 1) * A.shape[1]]
        out = np.linalg.lstsq(A_slice, B_slice, rcond=-1)
        na_c, nb_c, d_c = out[0]
        if d_c != 0.0:
            cu = 1.0 / d_c
            bu = -nb_c * cu
            au = -na_c * cu
        else:
            cu, bu, au = 1.0, -nb_c, -na_c
        normal = np.asarray([au, bu, cu])
        normal /= np.linalg.norm(normal)
        results[i, :] = normal
    return results


def find_plane_normal2_assign_atomid_new(positions, id1, id2, id3):
    """Compute ring normal via cross product of three atoms (sign reference)."""
    v1 = positions[:, id1] - positions[:, id2]
    v1 /= np.linalg.norm(v1, axis=1)[:, np.newaxis]
    v2 = positions[:, id3] - positions[:, id1]
    v2 /= np.linalg.norm(v2, axis=1)[:, np.newaxis]
    return np.cross(v1, v2)


def get_ring_center_normal_trj_assign_atomid_new(position_array, id1, id2, id3):
    """Compute ring center and sign-consistent normal vector for every frame.

    Parameters
    ----------
    position_array : np.ndarray, shape (n_frames, n_ring_atoms, 3)
    id1, id2, id3 : int
        Atom positions within the ring used as the sign-reference normal.

    Returns
    -------
    np.ndarray, shape (n_frames, 2, 3)
        [:, 0, :] = ring center, [:, 1, :] = normal vector.
    """
    centers_overtraj = np.mean(position_array, axis=1)  # (n_frames, 3)
    normal  = find_plane_normal_new(position_array)
    normal2 = find_plane_normal2_assign_atomid_new(position_array, id1, id2, id3)
    normal_updated = np.empty(normal.shape)
    for frame in range(len(position_array)):
        if np.dot(normal[frame], normal2[frame]) < 0:
            normal_updated[frame] = -normal[frame]
        else:
            normal_updated[frame] = normal[frame]
    return np.stack((centers_overtraj, normal_updated), axis=1)


def normvector_connect_new(point1, point2, axis=1):
    """Return normalized vector from point2 to point1."""
    vec  = point1 - point2
    norm = np.sqrt(np.sum(vec ** 2, axis=axis, keepdims=True))
    return vec / norm


def angle_new(v1, v2, axis=1):
    """Angle (radians) between v1 and v2 with numerical stability clipping."""
    dot   = np.sum(v1 * v2, axis=axis)
    norm1 = np.sqrt(np.sum(v1 ** 2, axis=axis))
    norm2 = np.sqrt(np.sum(v2 ** 2, axis=axis))
    cos_a = np.clip(dot / (norm1 * norm2), -1.0, 1.0)
    return np.arccos(cos_a)


def Kd_calc(bound: float, conc: float) -> float:
    """Dissociation constant from bound fraction and ligand concentration (M)."""
    return (1 - bound) * conc / bound


def get_Kd(prot_lig_traj, simulation_times, contact_overTime: np.ndarray):
    """Compute Kd (mM) and bound-fraction time series from a binary contact vector.

    Parameters
    ----------
    prot_lig_traj : mdtraj.Trajectory
        Protein+ligand trajectory; used for box size (unitcell_lengths).
    simulation_times : list
        Frame times in ps (from self.simulation_times).
    contact_overTime : np.ndarray, shape (n_frames,)
        Per-frame total contact count; binarised internally.

    Returns
    -------
    kd : tuple (float, float)
        (KD in mM, KD_error in mM).
    bound_fraction_df : pd.DataFrame
        Cumulative bound-fraction time series indexed by frame time.
    bound_fraction : tuple (float, float)
        (boundfrac, boundfrac_be) over the full trajectory.
    """
    box_L = prot_lig_traj.unitcell_lengths[0][0]          # nm
    box_V_L = ((box_L * 1e-9) ** 3) * 1000                # litres
    concentration = 1.0 / (box_V_L * 6.023e23)            # mol/L

    contact_binary = (contact_overTime > 0).astype(int)
    boundfrac, boundfrac_be = get_blockerror_pyblock_nanskip(contact_binary)

    kd_val   = Kd_calc(boundfrac,              concentration) * 1000   # mM
    kd_upper = Kd_calc(boundfrac + boundfrac_be, concentration) * 1000
    kd_error = kd_val - kd_upper

    time_axis = np.linspace(0, simulation_times[-1], len(contact_binary))
    stride = 1
    bf_by_frame, err_up, err_low, t2 = [], [], [], []
    for i in tqdm(range(stride, len(contact_binary), stride)):
        bf, be = get_blockerror_pyblock_nanskip(contact_binary[:i])
        bf_by_frame.append(bf)
        err_up.append(bf - be)
        err_low.append(bf + be)
        t2.append(time_axis[i])

    bound_fraction_df = pd.DataFrame({
        'bound_fraction':       bf_by_frame,
        'bound_fraction_error_up':  err_up,
        'bound_fraction_error_low': err_low,
    }, index=t2)

    return (kd_val, kd_error), bound_fraction_df, (boundfrac, boundfrac_be)


# ── H-bond helpers ───────────────────────────────────────────────────────────

def _get_bond_triplets_print(topology, lig_donors, exclude_water=True,
                              sidechain_only=False, offset=0):
    """Return a dict of donor/acceptor information for the topology.

    Used by print_donors_acceptors() to build a human-readable inventory of
    N–H, O–H and S–H donors plus O/N/S acceptors.
    """
    hbond_donors_acceptors_dict = {}

    def can_participate(atom):
        if exclude_water and atom.residue.is_water:
            return False
        if sidechain_only and not atom.is_sidechain:
            return False
        return True

    def get_donors(e0, e1):
        elems = set((e0, e1))
        atoms = [(one, two) for one, two in topology.bonds
                 if set((one.element.symbol, two.element.symbol)) == elems]
        atoms = [pair for pair in atoms
                 if can_participate(pair[0]) and can_participate(pair[1])]
        indices = []
        for a0, a1 in atoms:
            pair = (a0.index, a1.index)
            if a0.element.symbol == e1:
                pair = pair[::-1]
            indices.append(pair)
        return indices

    nbonds = 0
    for _ in topology.bonds:
        nbonds += 1
        break
    if nbonds == 0:
        raise ValueError('No bonds found in topology. Try '
                         'traj._topology.create_standard_bonds().')

    def _fmt(idx):
        a = topology.atom(idx)
        return f'{a.residue.name} {a.residue.resSeq + offset} {a.name}'

    hbond_donors_acceptors_dict['NH_donors'] = [
        f'{_fmt(i[0])} -> {topology.atom(i[1]).name}' for i in get_donors('N', 'H')
    ]
    hbond_donors_acceptors_dict['OH_donors'] = [
        f'{_fmt(i[0])} -> {topology.atom(i[1]).name}' for i in get_donors('O', 'H')
    ]
    hbond_donors_acceptors_dict['SH_donors'] = [
        f'{_fmt(i[0])} -> {topology.atom(i[1]).name}' for i in get_donors('S', 'H')
    ]

    acceptor_elements = frozenset(('O', 'N', 'S'))
    hbond_donors_acceptors_dict['acceptors'] = [
        f'{topology.atom(a.index).residue.name} '
        f'{topology.atom(a.index).residue.resSeq + offset} {a.name}'
        for a in topology.atoms
        if a.element.symbol in acceptor_elements and can_participate(a)
    ]
    return hbond_donors_acceptors_dict


def baker_hubbard2(traj, freq=0.1, exclude_water=True, periodic=True,
                   sidechain_only=False, distance_cutoff=0.35, angle_cutoff=150,
                   lig_donor_index=[]):
    """Per-frame H-bond detection using Baker–Hubbard geometry criteria.

    Extended version of MDTraj's baker_hubbard that accepts additional ligand
    donor pairs via lig_donor_index.

    Parameters
    ----------
    traj : mdtraj.Trajectory
        Single-frame trajectory.
    freq : float
        Minimum fraction of frames a triplet must appear in.
    distance_cutoff : float
        Donor–acceptor distance cutoff in nm.
    angle_cutoff : float
        Donor–H–acceptor angle cutoff in degrees.
    lig_donor_index : list of [int, int]
        Additional donor–hydrogen index pairs from the ligand
        (MDTraj atom indices in the prot_lig topology context).

    Returns
    -------
    bond_triplets : np.ndarray, shape (n_hbonds, 3)
        [donor, hydrogen, acceptor] indices for detected H-bonds.
    raw : tuple (bond_triplets_raw, distances_raw)
        Full potential-triplet array and raw distances (for save_pca path).
    """
    angle_cutoff_rad = np.radians(angle_cutoff)

    if traj.topology is None:
        raise ValueError('baker_hubbard2 requires topology information')

    # Standard MDTraj triplets (protein only — no lig_donors parameter)
    bond_triplets = _get_bond_triplets(
        traj.topology,
        exclude_water=exclude_water,
        sidechain_only=sidechain_only,
    )

    # Append ligand donor triplets: pair each lig (heavy, H) with every O/N/S acceptor
    if lig_donor_index:
        acceptor_elements = frozenset(('O', 'N', 'S'))
        acceptors = [a.index for a in traj.topology.atoms
                     if a.element.symbol in acceptor_elements]
        lig_triplets = np.array(
            [(heavy, h, acc)
             for heavy, h in lig_donor_index
             for acc in acceptors
             if heavy != acc],
            dtype=int,
        )
        if lig_triplets.size:
            bond_triplets = np.vstack([bond_triplets, lig_triplets])

    bond_triplets_raw = bond_triplets.copy()

    result = _compute_bounded_geometry(
        traj, bond_triplets, distance_cutoff, [1, 2], [0, 1, 2],
        freq=freq, periodic=periodic,
    )
    if len(result) == 4:
        mask, distances, angles, distances_raw = result
    else:
        mask, distances, angles = result
        distances_raw = distances  # older MDTraj — no raw distances returned
    presence    = np.logical_and(distances < distance_cutoff, angles > angle_cutoff_rad)
    mask[mask]  = np.mean(presence, axis=0) > freq

    return bond_triplets.compress(mask, axis=0), (bond_triplets_raw, distances_raw)


def print_donors_acceptors(traj, exclude_water=True, sidechain_only=False,
                           angle_cutoff=150, lig_donor_index=[], offset=0):
    """Return a topology-level inventory of H-bond donors and acceptors.

    Parameters
    ----------
    traj : mdtraj.Trajectory
        Single-frame trajectory (only topology is used).
    lig_donor_index : list of (str, str)
        Ligand donor atom name pairs (passed through for reference; topology
        donor scan uses topology bonds only).
    offset : int
        Residue number offset applied to labels.

    Returns
    -------
    dict with keys 'NH_donors', 'OH_donors', 'SH_donors', 'acceptors'.
    """
    return _get_bond_triplets_print(
        traj.topology,
        lig_donors=lig_donor_index,
        exclude_water=exclude_water,
        sidechain_only=sidechain_only,
        offset=offset,
    )


def add_hbond_pair(donor, acceptor, hbond_pairs, donor_res):
    """Accumulate an H-bond observation into the pairs dictionary.

    hbond_pairs[donor_res][donor][acceptor] counts the number of frames in
    which this donor–acceptor interaction was observed.
    """
    if donor_res not in hbond_pairs:
        hbond_pairs[donor_res] = {}
    if donor not in hbond_pairs[donor_res]:
        hbond_pairs[donor_res][donor] = {}
    if acceptor not in hbond_pairs[donor_res][donor]:
        hbond_pairs[donor_res][donor][acceptor] = 0
    hbond_pairs[donor_res][donor][acceptor] += 1


class ContactsMixin:

    # ── 4. Contact probability ────────────────────────────────────────────────

    def compute_aromatic_contacts(self):
        """Compute aromatic contact probabilities between ligand and protein residues.

        Geometric criteria (cutoffs fixed per literature definition):
          p-stack : r ≤ 6.5 Å, θ ≤ 45°, φ ≤ 60°
          t-stack : r ≤ 7.5 Å, θ ≥ 75°, φ ≤ 60°
        Distances in nm (MDTraj convention); angles in degrees.

        Returns
        -------
        pd.DataFrame
            Indexed by residue name. Columns: aromatic_stacking,
            aromatic_stacking_error, aromatic_pstacking, aromatic_pstacking_error,
            aromatic_tstacking, aromatic_tstacking_error, plus per-ligand-ring
            columns '0', '0_error', '1', '1_error', ...
            Also stored on self.contact_probability.
        """
        # ── ligand aromatic rings → MDTraj atom indices ───────────────────────
        rings = self.get_ligand_rings()
        aromatic_rings = [r for r in rings if r['aromatic']]
        if not aromatic_rings:
            raise ValueError("No aromatic rings detected in ligand — "
                             "check that get_ligand_rings() returns aromatic=True rings")

        ligand_rings_conv = []
        for ring in aromatic_rings:
            indices = [int(self.convert_ligand_atom_name(name)[0])
                       for name in ring['atom_names']]
            ligand_rings_conv.append(indices)

        protein_rings, protein_rings_index, _ = self.get_protein_rings()

        n_lig    = len(aromatic_rings)
        n_frames = self.prot_lig_traj.n_frames

        # Cutoffs in nm
        p_stack_cutoff = 0.65   # 6.5 Å
        t_stack_cutoff = 0.75   # 7.5 Å

        # Ring-center distances are computed from raw xyz (no MDTraj PBC path).
        # This is correct only when the complex is already made whole (no atoms
        # split across periodic boundaries).  A PBC-corrected trajectory satisfies
        # this; verify your input if results look anomalous.

        # ── ring centres + normals: (n_frames, 2, 3) per ring ─────────────────
        lig_params = [
            get_ring_center_normal_trj_assign_atomid_new(
                self.prot_lig_traj.xyz[:, np.array(idx), :], 0, 1, 2)
            for idx in ligand_rings_conv
        ]
        prot_params = [
            get_ring_center_normal_trj_assign_atomid_new(
                self.prot_lig_traj.xyz[:, ring, :], 0, 1, 2)
            for ring in protein_rings
        ]

        # ── pairwise geometry: (n_frames, n_lig × n_prot) ────────────────────
        n_pairs   = n_lig * len(protein_rings)
        distances = np.zeros((n_frames, n_pairs))
        thetas    = np.zeros((n_frames, n_pairs))
        phis      = np.zeros((n_frames, n_pairs))

        for i, (lp, pp) in enumerate(itertools.product(lig_params, prot_params)):
            lig_c, prot_c = lp[:, 0, :], pp[:, 0, :]
            lig_n, prot_n = lp[:, 1, :], pp[:, 1, :]
            distances[:, i] = np.linalg.norm(lig_c - prot_c, axis=1)
            connect      = normvector_connect_new(prot_c, lig_c)
            theta        = np.rad2deg(angle_new(prot_n, lig_n))
            phi          = np.rad2deg(angle_new(prot_n, connect))
            thetas[:, i] = np.abs(theta) - 2 * (np.abs(theta) > 90.0) * (np.abs(theta) - 90.0)
            phis[:, i]   = np.abs(phi)   - 2 * (np.abs(phi)   > 90.0) * (np.abs(phi)   - 90.0)

        pstacked = np.zeros((n_frames, n_pairs), dtype=int)
        tstacked = np.zeros((n_frames, n_pairs), dtype=int)
        stacked  = np.zeros((n_frames, n_pairs), dtype=int)

        for j in range(n_pairs):
            r_p  = np.where(distances[:, j] <= p_stack_cutoff)[0]
            r_t  = np.where(distances[:, j] <= t_stack_cutoff)[0]
            e    = np.where(thetas[:, j] <= 45)[0]
            f    = np.where(phis[:, j]   <= 60)[0]
            g    = np.where(thetas[:, j] >= 75)[0]
            p_fr = np.intersect1d(np.intersect1d(e, f), r_p)
            t_fr = np.intersect1d(np.intersect1d(g, f), r_t)
            pstacked[p_fr, j] = 1
            tstacked[t_fr, j] = 1
            stacked[p_fr, j]  = 1
            stacked[t_fr, j]  = 1

        # ── split by ligand ring: each sub-array (n_frames, n_prot_rings) ─────
        stk_by_ring  = np.split(stacked,  n_lig, axis=1)
        pstk_by_ring = np.split(pstacked, n_lig, axis=1)
        tstk_by_ring = np.split(tstacked, n_lig, axis=1)

        # Fix overcounting: a residue contacted by multiple ligand rings counts once
        fix_stk  = (np.sum(np.stack(stk_by_ring,  axis=0), axis=0) != 0).astype(int)
        fix_pstk = (np.sum(np.stack(pstk_by_ring, axis=0), axis=0) != 0).astype(int)
        fix_tstk = (np.sum(np.stack(tstk_by_ring, axis=0), axis=0) != 0).astype(int)

        # ── map to full protein residue array (n_frames, n_protein_residues) ──
        n_res = self.protein_traj.n_residues
        stk_full  = np.zeros((n_frames, n_res), dtype=int)
        pstk_full = np.zeros((n_frames, n_res), dtype=int)
        tstk_full = np.zeros((n_frames, n_res), dtype=int)
        stk_by_ring_full = [np.zeros((n_frames, n_res), dtype=int) for _ in range(n_lig)]

        for ri, res_idx in enumerate(protein_rings_index):
            stk_full[:, res_idx]  = fix_stk[:, ri]
            pstk_full[:, res_idx] = fix_pstk[:, ri]
            tstk_full[:, res_idx] = fix_tstk[:, ri]
            for l in range(n_lig):
                stk_by_ring_full[l][:, res_idx] = stk_by_ring[l][:, ri]

        # stacking_contacts_dict used by compute_contact_probability() and define_pharmacophore()
        self.stacking_contacts_dict = {
            'sum': stk_full,
            **{str(l): stk_by_ring_full[l] for l in range(n_lig)},
        }

        self._stacked_full        = stk_full
        self._pstacked_full       = pstk_full
        self._tstacked_full       = tstk_full
        self._stacked_by_ring     = stk_by_ring_full
        self._aromatic_rings      = aromatic_rings
        self._protein_rings_index = protein_rings_index

        # ── aggregate to per-residue probabilities ────────────────────────────
        if not PANDAS_AVAILABLE:
            raise ImportError("pandas required — install: pip install pandas")

        stk_ave,  stk_be  = get_blockerrors_pyblock_nanskip(stk_full,  1.0)
        pstk_ave, pstk_be = get_blockerrors_pyblock_nanskip(pstk_full, 1.0)
        tstk_ave, tstk_be = get_blockerrors_pyblock_nanskip(tstk_full, 1.0)

        df = pd.DataFrame({
            'aromatic_stacking':        stk_ave,
            'aromatic_stacking_error':  stk_be,
            'aromatic_pstacking':       pstk_ave,
            'aromatic_pstacking_error': pstk_be,
            'aromatic_tstacking':       tstk_ave,
            'aromatic_tstacking_error': tstk_be,
        }, index=self.residue_names)

        for l in range(n_lig):
            ring_ave, ring_be = get_blockerrors_pyblock_nanskip(stk_by_ring_full[l], 1.0)
            df[str(l)]       = ring_ave
            df[f'{l}_error'] = ring_be

        self.aromatic_contact_probability = df
        return df

    def compute_contact_probability(self, cutoff: float = DEFAULT_CONTACT_CUTOFF,
                                    scheme: str = 'closest-heavy'):
        """Compute general distance-based protein–ligand contact probability.

        Uses MDTraj compute_contacts on all protein–ligand residue pairs.
        Contacts defined by distance < cutoff (nm).

        Parameters
        ----------
        cutoff : float
            Distance cutoff in nm. Default 0.6 nm (6 Å).
        scheme : str
            MDTraj contact scheme. Default 'closest-heavy'.

        Returns
        -------
        pd.DataFrame
            Indexed by residue name. Columns: contact_probability,
            contact_probability_error, Kd, Kd_error.
            Stored on self.contact_probability.

        Also stores
        -----------
        self.dual_contact_matrix : residue co-occurrence DataFrame
        self.kd                  : (KD_mM, KD_error_mM)
        self.bound_fraction      : (boundfrac, boundfrac_be)
        self.kd_over_time        : cumulative bound-fraction time series DataFrame
        """
        if not MDTRAJ_AVAILABLE:
            raise ImportError("MDTraj required — install via conda-forge: mdtraj")
        if not PANDAS_AVAILABLE:
            raise ImportError("pandas required — install: pip install pandas")

        combined_pairs = self.get_protein_ligand_pairs()
        distances = np.asarray(
            md.compute_contacts(self.prot_lig_traj, combined_pairs, scheme=scheme)[0]
        ).astype(float)

        contact_matrix = (distances < cutoff).astype(int)
        del distances

        contact_probability_ave, contact_probability_be = \
            get_blockerrors_pyblock_nanskip(contact_matrix, 1.0)

        dual_contact = (contact_matrix.T @ contact_matrix) / len(contact_matrix)
        self.dual_contact_matrix = pd.DataFrame(
            dual_contact,
            index=self.residue_names,
            columns=self.residue_names,
        )

        contact_overTime = np.sum(contact_matrix, axis=1)
        kd, kd_over_time_df, bound_fraction = get_Kd(
            prot_lig_traj=self.prot_lig_traj,
            simulation_times=self.simulation_times,
            contact_overTime=contact_overTime,
        )

        self.kd             = kd
        self.kd_over_time   = kd_over_time_df
        self.bound_fraction = bound_fraction

        df = pd.DataFrame({
            'contact_probability':       contact_probability_ave,
            'contact_probability_error': contact_probability_be,
            'Kd':                        kd[0],
            'Kd_error':                  kd[1],
        }, index=self.residue_names)

        self.contact_probability = df
        return df

    def compute_all_atom_contacts(self, cutoff: float = DEFAULT_CONTACT_CUTOFF,
                                   save_pca: bool = False):
        """Compute all-heavy-atom protein–ligand contact probabilities.

        Computes pairwise distances between every ligand heavy atom and every
        protein heavy atom (no element filter — all non-H atoms included).
        Contacts defined by distance < cutoff (nm).

        Parameters
        ----------
        cutoff : float
            Distance cutoff in nm. Default 0.6 nm (6 Å).
        save_pca : bool
            When True, store a per-frame distance matrix averaged over ligand
            atoms as self.all_atom_distances_df — shape (n_frames, n_prot_heavy),
            columns are protein atom name labels, index is simulation time.
            Used as input to the PCA trajectory-subset algorithm.

        Returns
        -------
        pd.DataFrame
            Indexed by residue name. Columns: all_atom_contacts,
            all_atom_contacts_error.
            Also stored on self.all_atom_contact_probability.

        Also stores
        -----------
        self.all_atom_contact_frames          : (n_frames, n_lig_heavy * n_prot_heavy) binary
        self.all_atom_ligand_atom_probability : per-ligand-atom probability DataFrame
        self.all_atom_distances_df            : (n_frames, n_prot_heavy) mean distances (save_pca only)
        """
        if not MDTRAJ_AVAILABLE:
            raise ImportError("MDTraj required — install via conda-forge: mdtraj")
        if not PANDAS_AVAILABLE:
            raise ImportError("pandas required — install: pip install pandas")

        prot_heavy_idx = self.prot_lig_top.select('protein and not element H')
        lig_heavy_idx  = self.all_ligand_atoms_noh

        n_lig_heavy  = len(lig_heavy_idx)
        n_prot_heavy = len(prot_heavy_idx)
        n_frames     = self.prot_lig_traj.n_frames

        print(f"All-atom contacts: {n_lig_heavy} ligand heavy × {n_prot_heavy} protein heavy "
              f"= {n_lig_heavy * n_prot_heavy:,} pairs")

        all_pairs = np.array(list(product(lig_heavy_idx, prot_heavy_idx)))
        all_contacts = np.asarray(
            md.compute_distances(self.prot_lig_traj, all_pairs)
        ).astype(np.float32)   # (n_frames, n_lig_heavy * n_prot_heavy)

        # PCA distance matrix: mean over ligand atoms → (n_frames, n_prot_heavy)
        # Created before binarizing so the raw float array is still available.
        all_atom_distances_df = None
        if save_pca:
            atom_names_dict = self.get_atom_name_dict()
            col_names = [atom_names_dict[a] for a in prot_heavy_idx]
            all_atom_distances_df = pd.DataFrame(
                all_contacts.reshape(n_frames, n_lig_heavy, n_prot_heavy).mean(axis=1),
                index=self.simulation_times,
                columns=col_names,
            )

        # Binary contacts and reshape
        all_contact_frames = np.where(all_contacts < cutoff, 1, 0)
        reshaped = all_contact_frames.reshape(n_frames, n_lig_heavy, n_prot_heavy)
        del all_contacts

        # Per-ligand-atom probability of any contact with any protein atom
        init_df = pd.DataFrame(
            index=[self.prot_lig_atom_names_dict.get(e, e) for e in self.all_ligand_atoms]
        )
        init_df['temp'] = 0
        init_df = init_df[~init_df.index.str.startswith('H')]
        lig_atom_prob_df = pd.DataFrame(
            index=[self.prot_lig_atom_names_dict.get(e, e) for e in lig_heavy_idx]
        )
        lig_atom_prob_df['Probability'] = (reshaped == 1).any(axis=-1).mean(axis=0)
        lig_atom_prob_df = pd.concat([init_df, lig_atom_prob_df], axis=1)
        lig_atom_prob_df.fillna(0, inplace=True)
        lig_atom_prob_df.drop('temp', axis=1, inplace=True)

        # OR-reduce to residue level: any ligand atom contacts this protein atom?
        any_lig_contact = reshaped.any(axis=1)   # (n_frames, n_prot_heavy)

        atom_to_res = np.array([
            self.prot_lig_top.atom(a).residue.index for a in prot_heavy_idx
        ])

        n_res = self.protein_traj.n_residues
        res_contacts = np.zeros((n_frames, n_res), dtype=np.int8)
        for j, res_idx in enumerate(atom_to_res):
            res_contacts[:, res_idx] |= any_lig_contact[:, j]

        ave, be = get_blockerrors_pyblock_nanskip(res_contacts.astype(float), 1.0)
        df = pd.DataFrame({'all_atom_contacts': ave}, index=self.residue_names)
        df['all_atom_contacts_error'] = be

        self.all_atom_contact_probability     = df
        self.all_atom_contact_frames          = all_contact_frames
        self.all_atom_ligand_atom_probability = lig_atom_prob_df
        self.all_atom_distances_df            = all_atom_distances_df

        return df

    def compute_hydrophobic_contacts(self, cutoff: float = DEFAULT_HYDROPHOBIC_CUTOFF,
                                     save_pca: bool = False):
        """Compute hydrophobic contact probabilities between ligand and protein residues.

        Atom-level distances between ligand C/S atoms and protein C atoms.
        Contacts defined by distance < cutoff (nm).

        Parameters
        ----------
        cutoff : float
            Distance cutoff in nm. Default 0.40 nm (4.0 Å).
        save_pca : bool
            When True, also compute per-frame per-residue mean distance DataFrame,
            stored on self.hydrophobic_distances_df (used for downstream PCA).

        Returns
        -------
        pd.DataFrame
            Indexed by residue name. Columns: hydrophobic_contacts,
            hydrophobic_contacts_error.
            Also stored on self.hydrophobic_contact_probability.
        """
        if not MDTRAJ_AVAILABLE:
            raise ImportError("MDTraj required — install via conda-forge: mdtraj")
        if not PANDAS_AVAILABLE:
            raise ImportError("pandas required — install: pip install pandas")

        n_lig_hphob  = len(self.hydrophobic_atoms_ligand)
        n_prot_hphob = len(self.hydrophobic_atoms_protein)
        n_frames     = self.prot_lig_traj.n_frames

        hphob_contacts = np.asarray(
            md.compute_distances(self.prot_lig_traj, self.protein_ligand_hphob_pairs)
        ).astype(float)

        # Per-frame per-residue mean distance (optional — used for downstream PCA)
        hphob_distances_df = pd.DataFrame(
            index=self.simulation_times,
            columns=self.hydrophobic_residue_atoms_dict.keys(),
        )
        if save_pca:
            reshaped_dist = hphob_contacts.reshape(n_frames, n_lig_hphob, n_prot_hphob)
            mean_dist = np.mean(reshaped_dist, axis=1)  # (n_frames, n_prot_hphob)
            for res, atom_idxs in self.hydrophobic_residue_atoms_dict.items():
                hphob_distances_df[res] = np.mean(mean_dist[:, atom_idxs], axis=1)

        hphob_contact_frames = np.where(hphob_contacts < cutoff, 1, 0)
        reshaped_contact = hphob_contact_frames.reshape(n_frames, n_lig_hphob, n_prot_hphob)

        # Atom-level mean contact probability: (n_lig_hphob, n_prot_hphob)
        mean_atom_contacts = reshaped_contact.mean(0)
        atom_contact_df = pd.DataFrame(
            mean_atom_contacts,
            index=[self.prot_lig_atom_names_dict.get(e, e) for e in self.hydrophobic_atoms_ligand],
            columns=[self.prot_lig_atom_names_dict.get(e, e) for e in self.hydrophobic_atoms_protein],
        )

        # Per-ligand-atom probability of any hydrophobic contact with any protein atom
        init_df = pd.DataFrame(
            index=[self.prot_lig_atom_names_dict.get(e, e) for e in self.all_ligand_atoms]
        )
        init_df['temp'] = 0
        init_df = init_df[~init_df.index.str.startswith('H')]
        ligand_atom_prob_df = pd.DataFrame(
            index=[self.prot_lig_atom_names_dict.get(e, e) for e in self.hydrophobic_atoms_ligand]
        )
        ligand_atom_prob_df['Probability'] = (reshaped_contact == 1).any(-1).mean(0)
        ligand_atom_prob_df = pd.concat([init_df, ligand_atom_prob_df], axis=1)
        ligand_atom_prob_df.fillna(0, inplace=True)
        ligand_atom_prob_df.drop('temp', inplace=True, axis=1)

        # Map atom contacts to residues: (n_frames, n_protein_residues)
        # Reduce ligand dimension: is protein C atom j contacted by ANY lig C/S atom?
        any_lig_contact = reshaped_contact.any(axis=1)  # (n_frames, n_prot_hphob)

        # Residue index for each protein C atom — one lookup per atom, not per frame
        atom_to_res = np.array([
            self.prot_lig_top.atom(atom_idx).residue.index
            for atom_idx in self.hydrophobic_atoms_protein
        ])

        # OR-reduce into residue slots (n_frames, n_protein_residues)
        n_res = self.protein_traj.n_residues
        Hphob_res_contacts = np.zeros((n_frames, n_res), dtype=np.int8)
        for j, res_idx in enumerate(atom_to_res):
            Hphob_res_contacts[:, res_idx] |= any_lig_contact[:, j]

        hphob_ave, hphob_be = get_blockerrors_pyblock_nanskip(Hphob_res_contacts, 1.0)
        df = pd.DataFrame({'hydrophobic_contacts': hphob_ave}, index=self.residue_names)
        df['hydrophobic_contacts_error'] = hphob_be

        self.hydrophobic_contact_probability      = df
        self.hydrophobic_contact_frames           = hphob_contact_frames
        self.hydrophobic_atom_contact_probability = atom_contact_df
        self.hydrophobic_ligand_atom_probability  = ligand_atom_prob_df
        self.hydrophobic_distances_df             = hphob_distances_df

        return df

    def compute_hbond_contacts(self, ligand_hbond_donors=None,
                               distance_cutoff: float = 0.35,
                               angle_cutoff: float = 150,
                               save_pca: bool = False):
        """Compute H-bond contact probabilities between ligand and protein residues.

        Detects H-bonds per frame with Baker–Hubbard geometry criteria. Tracks:
          PD (protein donor) : protein N/O/S–H donates to ligand acceptor
          LD (ligand donor)  : ligand N/O/S–H donates to protein acceptor

        Parameters
        ----------
        ligand_hbond_donors : list of (int, int), optional
            Ligand H-bond donor pairs as (heavy_atom_RDKit_idx, H_RDKit_idx).
            Auto-detected from the ligand RDKit mol when not provided.
        distance_cutoff : float
            Donor–acceptor distance cutoff in nm. Default 0.35 nm (3.5 Å).
        angle_cutoff : float
            Donor–H–acceptor angle cutoff in degrees. Default 150°.
        save_pca : bool
            When True, store per-frame raw distances for downstream PCA in
            self.hbond_distances_df and self.hbond_residue_distances_df.

        Returns
        -------
        pd.DataFrame
            Indexed by residue name. Columns: Hbonds_average,
            Hbonds_average_error, Hbonds_PD_average, Hbonds_PD_average_error,
            Hbonds_LD_average, Hbonds_LD_average_error.
            Also stored on self.hbond_contact_probability.
        """
        if not MDTRAJ_AVAILABLE:
            raise ImportError("MDTraj required — install via conda-forge: mdtraj")
        if _get_bond_triplets is None:
            raise ImportError(
                "mdtraj.geometry.hbond._get_bond_triplets not importable — "
                "ensure MDTraj supports the lig_donors= parameter"
            )
        if not PANDAS_AVAILABLE:
            raise ImportError("pandas required — install: pip install pandas")

        n_frames   = self.prot_lig_traj.n_frames
        n_residues = self.protein_traj.n_residues

        # Auto-detect ligand H-bond donors from RDKit mol when not supplied
        if ligand_hbond_donors is None:
            ligand_hbond_donors = self.get_ligand_hbond_pairs()

        # Convert RDKit indices → MDTraj prot_lig indices via _ligand_sel_idx
        # RDKit index i maps to _ligand_sel_idx[i] (same atom ordering)
        ligand_hbond_donors_conv = [
            [int(self._ligand_sel_idx[heavy]), int(self._ligand_sel_idx[h])]
            for heavy, h in ligand_hbond_donors
        ]

        # Topology-level donor/acceptor inventory (frame 0 only)
        hbond_donors_acceptors_dict = print_donors_acceptors(
            self.prot_lig_traj[0],
            angle_cutoff=angle_cutoff,
            lig_donor_index=ligand_hbond_donors_conv,
            sidechain_only=True,
            offset=self.offset,
        )

        # O(1) membership sets — exclude last 3 protein atoms (C-terminal cap)
        protein_sel_set = set(self._protein_sel_idx[:-3])
        ligand_sel_set  = set(self._ligand_sel_idx)

        HBond_PD    = np.zeros((n_frames, n_residues), dtype=np.int8)
        HBond_LD    = np.zeros((n_frames, n_residues), dtype=np.int8)
        Hbond_pairs_PD: dict = {}
        Hbond_pairs_LD: dict = {}
        raw_distances, bond_triplets_raw_ref = [], None

        for frame in tqdm(range(n_frames)):
            hbonds, frame_raw = baker_hubbard2(
                self.prot_lig_traj[frame],
                angle_cutoff=angle_cutoff,
                distance_cutoff=distance_cutoff,
                lig_donor_index=ligand_hbond_donors_conv,
            )

            if save_pca:
                if bond_triplets_raw_ref is None:
                    bond_triplets_raw_ref = frame_raw[0]
                raw_distances.append(frame_raw[1])

            for hbond in hbonds:
                # PD: protein donates H → ligand acceptor
                if hbond[0] in protein_sel_set and hbond[2] in ligand_sel_set:
                    donor   = self.prot_lig_top.atom(hbond[0])
                    acc     = self.prot_lig_top.atom(hbond[2])
                    res_idx = donor.residue.index
                    HBond_PD[frame, res_idx] = 1
                    add_hbond_pair(donor, acc, Hbond_pairs_PD, res_idx)

                # LD: ligand donates H → protein acceptor
                if hbond[0] in ligand_sel_set and hbond[2] in protein_sel_set:
                    donor   = self.prot_lig_top.atom(hbond[0])
                    acc     = self.prot_lig_top.atom(hbond[2])
                    res_idx = acc.residue.index
                    HBond_LD[frame, res_idx] = 1
                    add_hbond_pair(donor, acc, Hbond_pairs_LD, res_idx)

        HB_Total = HBond_PD + HBond_LD  # 0, 1, or 2 when both types co-occur

        # ── per-ligand-atom H-bond probability ───────────────────────────────
        onLigand_hbonds = pd.DataFrame(
            index=[self.prot_lig_atom_names_dict.get(e, e) for e in self.all_ligand_atoms]
        )
        onLigand_hbonds.index = onLigand_hbonds.index.str.split('_').str[0]
        onLigand_hbonds['LD'] = 0.0
        onLigand_hbonds['PD'] = 0.0

        for res_idx, donor_data in Hbond_pairs_LD.items():
            for lig_donor, prot_data in donor_data.items():
                key = str(lig_donor).split('-')[1]
                for _, frames in prot_data.items():
                    onLigand_hbonds.loc[key, 'LD'] += frames / n_frames

        for res_idx, donor_data in Hbond_pairs_PD.items():
            for prot_donor, lig_data in donor_data.items():
                for lig_acc, frames in lig_data.items():
                    key = str(lig_acc).split('-')[1]
                    onLigand_hbonds.loc[key, 'PD'] += frames / n_frames

        # ── PCA distances (optional) ──────────────────────────────────────────
        hbond_distances_df   = None
        residue_distances_df = None
        if save_pca and bond_triplets_raw_ref is not None:
            index_atom = [
                f'{self.prot_lig_top.atom(t[0]).residue.name}_'
                f'{self.prot_lig_top.atom(t[0]).residue.resSeq + self.offset}'
                f'|{self.prot_lig_top.atom(t[2]).residue.name}_'
                f'{self.prot_lig_top.atom(t[2]).residue.resSeq + self.offset}'
                for t in bond_triplets_raw_ref
            ]
            hbond_distances_df = pd.DataFrame(
                np.concatenate(raw_distances, axis=0).reshape(len(index_atom), -1),
                index=index_atom,
                columns=self.simulation_times,
            )
            new_pairs, dist_means = [], []
            ligand_name = self.ligand_resname
            for p0, p1 in tqdm(product(self.all_residue_names_dict.values(), repeat=2)):
                key = f'{p0}|{p1}'
                if key not in index_atom:
                    continue
                if p0 == p1:
                    hbond_distances_df.drop(key, inplace=True)
                    continue
                try:
                    n0, n1 = int(p0.split('_')[1]), int(p1.split('_')[1])
                except (IndexError, ValueError):
                    n0, n1 = 0, 0
                if abs(n0 - n1) <= 4 and ligand_name not in p0 and ligand_name not in p1:
                    hbond_distances_df.drop(key, inplace=True)
                    continue
                new_pairs.append(key)
                dist_means.append(hbond_distances_df.loc[key].mean())
                hbond_distances_df.drop(key, inplace=True)
            residue_distances_df = pd.DataFrame(dist_means, index=new_pairs)

        # ── aggregate to per-residue probabilities ────────────────────────────
        HBond_PD_ave, HBond_PD_be = get_blockerrors_pyblock_nanskip(HBond_PD.astype(float), 1.0)
        HBond_LD_ave, HBond_LD_be = get_blockerrors_pyblock_nanskip(HBond_LD.astype(float), 1.0)
        HBond_ave,    HBond_be    = get_blockerrors_pyblock_nanskip(HB_Total.astype(float), 1.0)

        df = pd.DataFrame({
            'Hbonds_average':          HBond_ave,
            'Hbonds_average_error':    HBond_be,
            'Hbonds_PD_average':       HBond_PD_ave,
            'Hbonds_PD_average_error': HBond_PD_be,
            'Hbonds_LD_average':       HBond_LD_ave,
            'Hbonds_LD_average_error': HBond_LD_be,
        }, index=self.residue_names)

        self.hbond_contact_probability     = df
        self.hbond_contact_frames_pd       = HBond_PD
        self.hbond_contact_frames_ld       = HBond_LD
        self.hbond_pairs_pd                = Hbond_pairs_PD
        self.hbond_pairs_ld                = Hbond_pairs_LD
        self.hbond_donors_acceptors        = hbond_donors_acceptors_dict
        self.hbond_ligand_atom_probability = onLigand_hbonds
        self.hbond_distances_df            = hbond_distances_df
        self.hbond_residue_distances_df    = residue_distances_df

        return df

    # ── 4e. Intra-protein contact map ─────────────────────────────────────────

    def compute_contact_map(self, cutoff: float = 1.2, scheme: str = 'closest-heavy',
                            distance_raw: bool = False):
        """Compute the intra-protein residue contact map.

        Parameters
        ----------
        cutoff : float
            Distance cutoff in nm. Residue pairs below this threshold count as
            in contact (ignored when distance_raw=True).
        scheme : str
            MDTraj contact scheme: 'closest-heavy' (default) or 'ca'.
        distance_raw : bool
            If True, store raw per-frame distances instead of the mean binary
            contact probability matrix.

        Stores
        ------
        contact_map_df     : (n_res × n_res) symmetric probability DataFrame
                             (populated when distance_raw=False)
        contact_map_raw_df : (n_frames × n_pairs) raw distance DataFrame
                             (populated when distance_raw=True)

        Returns
        -------
        pd.DataFrame
            contact_map_df or contact_map_raw_df depending on distance_raw.
        """
        import time as _time
        t0 = _time.time()

        n_res = self.protein_traj.n_residues
        indices = np.stack(np.triu_indices(n_res, 1), 1)

        if distance_raw:
            raw = md.compute_contacts(self.protein_traj, indices, scheme='closest-heavy')[0]
            pair_labels = [
                f"{self.residue_names_dict[i]}|{self.residue_names_dict[j]}"
                for i, j in indices
            ]
            self.contact_map_raw_df = pd.DataFrame(
                raw,
                index=self.simulation_times,
                columns=pair_labels,
            )
            self.contact_map_df = None
            print(f'\tContact map (raw distances) done in {round(_time.time() - t0, 2)} s')
            return self.contact_map_raw_df

        distances = md.compute_contacts(self.protein_traj, indices, scheme=scheme)[0]
        contacts  = (distances < cutoff).astype(np.float32)   # (n_frames, n_pairs)
        matrix    = np.zeros((self.protein_traj.n_frames, n_res, n_res), dtype=np.float32)
        matrix[:, indices[:, 0], indices[:, 1]] = contacts
        matrix   += matrix.transpose(0, 2, 1)
        mean_mat  = matrix.mean(axis=0)
        self.contact_map_df = pd.DataFrame(
            mean_mat,
            index=self.residue_names,
            columns=self.residue_names,
        )
        self.contact_map_raw_df = None
        print(f'\tContact map done in {round(_time.time() - t0, 2)} s')
        return self.contact_map_df
