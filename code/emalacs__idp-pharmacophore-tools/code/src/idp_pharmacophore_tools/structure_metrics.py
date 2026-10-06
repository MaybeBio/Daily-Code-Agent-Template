import numpy as np

from ._deps import md, MDTRAJ_AVAILABLE, pd, PANDAS_AVAILABLE, tqdm
from ._stats import get_blockerrors_pyblock_nanskip


def dssp_convert(dssp: np.ndarray, secondary_motif: str,
                 get_over_time: bool = False,
                 weights=None) -> tuple:
    """Convert raw MDTraj DSSP strings to binary probabilities with block errors.

    Parameters
    ----------
    dssp : np.ndarray, shape (n_frames, n_residues)
        Raw DSSP array from md.compute_dssp (simplified=True).
        Values: 'H' helix, 'E' sheet, 'C' coil.
    secondary_motif : str
        'H' for helix or 'E' for sheet.
    get_over_time : bool
        When True, also compute per-frame fraction of residues in this motif
        (mean ± std across residues at each frame).
    weights : np.ndarray or str, optional
        Per-frame weights (1-D array) or path to a whitespace-delimited text
        file. Only applied when secondary_motif='H'.

    Returns
    -------
    (per_residue, per_frame, reweighted)
        per_residue : np.ndarray, shape (n_residues, 2) — [mean, block_error]
        per_frame   : np.ndarray, shape (n_frames, 2) or None — [mean, std] over residues
        reweighted  : list[float] — reweighted per-residue propensity (empty when no weights)
    """
    import time as _time
    t0 = _time.time()

    if secondary_motif not in {'H', 'E'}:
        raise ValueError("secondary_motif must be 'H' or 'E'")

    dssp_binary = (dssp == secondary_motif).astype(np.float32)  # (n_frames, n_residues)

    # Per-residue: mean + block error over the frames axis
    ave, be = get_blockerrors_pyblock_nanskip(dssp_binary, 1.0)
    per_residue = np.column_stack([ave, be])  # (n_residues, 2)

    # Optional reweighting (helix only)
    reweighted: list = []
    if weights is not None and secondary_motif == 'H':
        if isinstance(weights, str):
            weights = np.loadtxt(weights)
        n_fr = dssp_binary.shape[0]
        w = weights[: n_fr - 1] if weights.shape[0] == n_fr - 1 else weights[:n_fr]
        for i in range(dssp_binary.shape[1]):
            col = dssp_binary[: len(w), i]
            reweighted.append(float(np.dot(col, w)))

    # Per-frame: fraction of residues in this motif (mean ± std over residues per frame)
    per_frame = None
    if get_over_time:
        per_frame = np.column_stack([
            dssp_binary.mean(axis=1),
            dssp_binary.std(axis=1),
        ])  # (n_frames, 2)

    print(f'\tDSSP {secondary_motif} done in {round(_time.time() - t0, 2)} s')
    return per_residue, per_frame, reweighted


class StructureMetricsMixin:

    # ── 4c. DSSP secondary structure ──────────────────────────────────────────

    def compute_dssp(self, get_over_time: bool = False, weights=None):
        """Compute DSSP secondary structure probabilities per residue.

        Uses MDTraj compute_dssp (simplified scheme: H=helix, E=sheet, C=coil).
        Block errors computed with pyblock; falls back to zero error if unavailable.

        Parameters
        ----------
        get_over_time : bool
            When True, also compute per-frame mean helix/sheet fraction across all
            residues, stored as self.dssp_over_time_df (indexed by simulation time).
        weights : np.ndarray or str, optional
            Per-frame weights array or path to a text file. When provided, a
            'DSSP_helix_reweighted' column is added to the output DataFrame.

        Returns
        -------
        pd.DataFrame
            Indexed by residue name. Columns: DSSP_helix, DSSP_helix_error_up,
            DSSP_helix_error_low, DSSP_sheet, DSSP_sheet_error_up,
            DSSP_sheet_error_low (plus DSSP_helix_reweighted when weights given).
            Stored on self.dssp_df.

        Also stores
        -----------
        self.dssp_over_time_df : pd.DataFrame or None
            Indexed by simulation time (ps). Columns: DSSP_helix, DSSP_helix_error,
            DSSP_sheet, DSSP_sheet_error. Only populated when get_over_time=True.
        """
        if not MDTRAJ_AVAILABLE:
            raise ImportError("MDTraj required — install via conda-forge: mdtraj")
        if not PANDAS_AVAILABLE:
            raise ImportError("pandas required — install: pip install pandas")

        print("Computing DSSP …")
        dssp = md.compute_dssp(self.protein_traj, simplified=True)
        print(f"  DSSP array: {dssp.shape}  (frames × residues)")

        helix_res, helix_time, helix_rew = dssp_convert(dssp, 'H', get_over_time, weights)
        sheet_res, sheet_time, _         = dssp_convert(dssp, 'E', get_over_time, weights)

        df = pd.DataFrame({
            'DSSP_helix':           helix_res[:, 0],
            'DSSP_helix_error_up':  helix_res[:, 0] + helix_res[:, 1],
            'DSSP_helix_error_low': helix_res[:, 0] - helix_res[:, 1],
            'DSSP_sheet':           sheet_res[:, 0],
            'DSSP_sheet_error_up':  sheet_res[:, 0] + sheet_res[:, 1],
            'DSSP_sheet_error_low': sheet_res[:, 0] - sheet_res[:, 1],
        }, index=self.residue_names)

        if helix_rew and len(helix_rew) == len(df):
            df['DSSP_helix_reweighted'] = helix_rew

        over_time_df = None
        if get_over_time and helix_time is not None and sheet_time is not None:
            over_time_df = pd.DataFrame({
                'DSSP_helix':       helix_time[:, 0],
                'DSSP_helix_error': helix_time[:, 1],
                'DSSP_sheet':       sheet_time[:, 0],
                'DSSP_sheet_error': sheet_time[:, 1],
            }, index=self.simulation_times)

        self.dssp_df           = df
        self.dssp_over_time_df = over_time_df
        return df

    # ── 4d. Gyration radius & Sα free energy surface ─────────────────────────

    def compute_gyration_salpha(self, helix_pdb, T: float = 300.0, nbins: int = 60,
                                rg_range: tuple = (0.9, 6.0),
                                salpha_range: tuple = (0.0, 60.0)):
        """Compute per-frame gyration radius + Sα and their 2D free energy surface.

        Gyration radius is computed on Cα atoms with equal weights.

        Sα measures local helical propensity via a 6-residue sliding-window RMSD
        switching function against a reference helix structure, summed over all
        windows:

            Sα_frame = Σ_i (1 − (rmsd_i/0.08)^8) / (1 − (rmsd_i/0.08)^12)

        where rmsd_i is the Cα RMSD of window i vs. the helix reference (nm) and
        0.08 nm is the switching threshold.

        The 2D FES is: ΔG = −k_B T ln P(Rg, Sα)  (kcal/mol), shifted so the
        minimum is zero.

        Parameters
        ----------
        helix_pdb : str or md.Trajectory
            Path to a PDB file (or an already-loaded MDTraj Trajectory) of the
            reference ideal helix. Must have the same number of residues as the
            protein trajectory.
        T : float
            Temperature in Kelvin for the ΔG calculation. Default 300 K.
        nbins : int
            Number of histogram bins along each axis. Default 30.
        rg_range : (float, float)
            Rg axis range in nm. Default (0.9, 6.0).
        salpha_range : (float, float)
            Sα axis range. Default (0.0, 60.0).

        Returns
        -------
        pd.DataFrame
            2D FES in kcal/mol. Index = Sα bin centres, columns = Rg bin
            centres (nm). Stored on self.gyration_salpha_fes_df.

        Also stores
        -----------
        self.rg_over_time     : np.ndarray, shape (n_frames,) — Rg in nm
        self.salpha_over_time : np.ndarray, shape (n_frames,) — total Sα per frame
        """
        if not MDTRAJ_AVAILABLE:
            raise ImportError("MDTraj required — install via conda-forge: mdtraj")
        if not PANDAS_AVAILABLE:
            raise ImportError("pandas required — install: pip install pandas")

        # ── Gyration radius (Cα equal weights) ────────────────────────────
        print("Computing gyration radius (Cα) …")
        mass_ca = np.zeros(self.protein_traj.topology.n_atoms, dtype=np.float64)
        for i in self.protein_traj.topology.select("name CA"):
            mass_ca[i] = 1.0
        rg = md.compute_rg(self.protein_traj, masses=mass_ca)  # (n_frames,) nm
        print(f"  Rg: {rg.min():.3f} – {rg.max():.3f} nm  (mean {rg.mean():.3f})")

        # ── Sα: local helical propensity ───────────────────────────────────
        print("Computing Sα …")
        helix_traj = md.load(helix_pdb) if isinstance(helix_pdb, str) else helix_pdb

        ca_sel_prot  = self.protein_traj.topology.select("name CA")
        ca_sel_helix = helix_traj.topology.select("name CA")
        prot_ca      = self.protein_traj.atom_slice(ca_sel_prot)
        helix_ca     = helix_traj.atom_slice(ca_sel_helix)

        if prot_ca.n_atoms != helix_ca.n_atoms:
            raise ValueError(
                f"Protein has {prot_ca.n_atoms} Cα atoms but helix reference has "
                f"{helix_ca.n_atoms} — they must match."
            )

        n_ca = prot_ca.n_atoms
        window_rmsds = np.stack([
            md.rmsd(prot_ca, helix_ca,
                    atom_indices=helix_ca.topology.select(f"resid {i} to {i + 5}"))
            for i in tqdm(range(n_ca - 5), desc="Sα windows")
        ])  # (n_windows, n_frames) in nm

        x      = window_rmsds / 0.08
        sa     = (1.0 - x**8) / (1.0 - x**12)   # switching function per window
        salpha = sa.sum(axis=0)                   # (n_frames,) total Sα
        print(f"  Sα: {salpha.min():.2f} – {salpha.max():.2f}  (mean {salpha.mean():.2f})")

        # ── 2D free energy surface ────────────────────────────────────────
        print("Computing 2D FES (Rg vs Sα) …")
        counts, rg_edges, sa_edges = np.histogram2d(
            rg, salpha, bins=nbins,
            range=[rg_range, salpha_range],
            density=True,
        )
        kBT = 0.001987 * T
        fes  = -kBT * np.log(counts + 1e-6)
        fes -= fes.min()

        rg_centers = 0.5 * (rg_edges[:-1] + rg_edges[1:])
        sa_centers = 0.5 * (sa_edges[:-1] + sa_edges[1:])

        fes_df = pd.DataFrame(fes.T, index=sa_centers, columns=rg_centers)

        self.rg_over_time           = rg
        self.salpha_over_time       = salpha
        self.gyration_salpha_fes_df = fes_df
        return fes_df

    # ── 4c. SASA ──────────────────────────────────────────────────────────────

    def compute_sasa(self, n_points: int = 960, probe_radius: float = 0.14):
        """Compute per-atom / per-residue protein SASA and per-atom ligand SASA.

        Uses the Shrake-Rupley rolling-probe algorithm.  Because the simulations
        are run without explicit solvent, SASA here is a *geometric occlusion*
        measure rather than a literal water-contact area:

        - **Protein SASA** (``protein_traj`` only): how much of each protein
          atom / residue surface is unobstructed by neighbouring protein atoms.
        - **Ligand SASA in protein context** (``prot_lig_traj``): the probe is
          blocked by both protein and ligand atoms, so the result answers "how
          buried is this ligand atom inside the protein pocket?"
          Low SASA → deeply embedded / well-protected.
          High SASA → pointing outward / solvent-exposed if water were present.

        Parameters
        ----------
        n_points : int
            Number of sphere points for Shrake-Rupley (higher = more accurate,
            slower). Default 960.
        probe_radius : float
            Probe sphere radius in nm (default 0.14 nm = 1.4 Å, water probe).

        Stores
        ------
        sasa_atoms_df        : DataFrame, shape (n_frames, n_protein_atoms), nm²
        sasa_residues_df     : DataFrame, shape (n_frames, n_protein_residues), nm²
        sasa_ligand_atoms_df : DataFrame, shape (n_frames, n_ligand_atoms), nm²
                               Columns are bare atom names (e.g. 'C1', 'N2') for
                               direct use in PyMOL selections.

        Returns
        -------
        (sasa_atoms_df, sasa_residues_df, sasa_ligand_atoms_df)
        """
        import time as _time
        t0 = _time.time()

        # ── Strip virtual sites (element 'VS') — not in MDTraj's radius table ─
        def _strip_vs(traj):
            real = [a.index for a in traj.topology.atoms
                    if a.element is not None and a.element.symbol != 'VS']
            if len(real) == traj.n_atoms:
                return traj, None          # nothing to strip
            return traj.atom_slice(real), real

        prot_traj_sasa, _    = _strip_vs(self.protein_traj)
        pl_traj_sasa,   pl_real = _strip_vs(self.prot_lig_traj) \
            if self.prot_lig_traj is not None else (None, None)

        # ── Protein: per-atom SASA ────────────────────────────────────────────
        sasa_atoms = md.shrake_rupley(
            prot_traj_sasa,
            probe_radius=probe_radius,
            n_sphere_points=n_points,
            mode='atom',
        )
        atom_labels = [
            f'sasa_atom_{a.index}_{a.name}_{a.residue.name}{a.residue.resSeq}'
            for a in prot_traj_sasa.topology.atoms
        ]
        self.sasa_atoms_df = pd.DataFrame(
            sasa_atoms,
            columns=atom_labels,
            index=self.simulation_times,
        )

        # ── Protein: per-residue SASA ─────────────────────────────────────────
        sasa_residues = md.shrake_rupley(
            prot_traj_sasa,
            probe_radius=probe_radius,
            n_sphere_points=n_points,
            mode='residue',
        )
        residue_labels = [
            f'sasa_residue_{r.index}_{r.name}{r.resSeq}'
            for r in prot_traj_sasa.topology.residues
        ]
        self.sasa_residues_df = pd.DataFrame(
            sasa_residues,
            columns=residue_labels,
            index=self.simulation_times,
        )

        # ── Ligand: per-atom SASA in protein context ──────────────────────────
        # Protein atoms occlude the probe → low SASA means buried in pocket.
        self.sasa_ligand_atoms_df = None
        if pl_traj_sasa is not None and self.all_ligand_atoms is not None:
            sasa_prot_lig = md.shrake_rupley(
                pl_traj_sasa,
                probe_radius=probe_radius,
                n_sphere_points=n_points,
                mode='atom',
            )
            # Remap ligand atom indices to the VS-stripped trajectory
            if pl_real is not None:
                orig2new = {orig: new for new, orig in enumerate(pl_real)}
                lig_indices_sasa = [orig2new[i] for i in self.all_ligand_atoms
                                    if i in orig2new]
            else:
                lig_indices_sasa = list(self.all_ligand_atoms)
            lig_sasa = sasa_prot_lig[:, lig_indices_sasa]
            lig_labels = [
                self.prot_lig_top.atom(idx).name
                for idx in self.all_ligand_atoms
                if pl_real is None or idx in set(pl_real)
            ]
            self.sasa_ligand_atoms_df = pd.DataFrame(
                lig_sasa,
                columns=lig_labels,
                index=self.simulation_times,
            )

        print(f'\tSASA done in {round(_time.time() - t0, 2)} s')
        return self.sasa_atoms_df, self.sasa_residues_df, self.sasa_ligand_atoms_df
