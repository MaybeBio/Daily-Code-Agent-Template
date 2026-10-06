import os
from typing import Dict, List, Optional

import numpy as np

from ._deps import md, pd
from .voxel_maps import _jet_hex


class PymolExportMixin:

    def compute_residue_dot_positions(self,
                                      mask_key: str = 'full_shell_mask',
                                      stride: int = 1) -> Dict:
        """Collect per-frame protein atom positions for PyMOL dot visualization.

        Uses the same atom selections as compute_pharmacophore_maps():

          aromatic    : ring centroids (TYR/PHE/HIS/TRP) per frame per ring,
                        split into contact / non-contact using _stacked_full
          hydrophobic : sidechain carbon centroid per residue per frame (no split)
          hba         : protein O atom positions per frame (H-bond acceptors),
                        split via hbond_contact_frames_ld (ligand-donor frames)
          hbd         : H atoms bonded to N or O per frame (H-bond donors),
                        split via hbond_contact_frames_pd (protein-donor frames)

        Positions are in **absolute Å** — the same coordinate system used by
        the MRC voxel files.  No ligand-centroid subtraction is applied.
        (plot_3d_residues() subtracts the centroid for Plotly display only.)

        Contact/non-contact splits fall back gracefully: if the required
        compute_aromatic_contacts() / compute_hbond_contacts() result is not
        available, all points are placed in the non-contact bucket.

        Points are filtered to positions that fall inside the voxel mask
        defined by ``mask_key``.

        Parameters
        ----------
        mask_key : str
            Voxel mask used as spatial filter.
            One of 'full_shell_mask', 'growth_space_mask',
            'contested_space_mask'.
        stride : int
            Use every nth frame (1 = all frames).  Larger values reduce the
            number of dots saved to the PDB files.

        Stores
        ------
        residue_dot_positions : dict with keys:
            'aromatic_contact'     → np.ndarray (N, 3) Å
            'aromatic_non_contact' → np.ndarray (N, 3) Å
            'hydrophobic'          → np.ndarray (N, 3) Å
            'hba_contact'          → np.ndarray (N, 3) Å
            'hba_non_contact'      → np.ndarray (N, 3) Å
            'hbd_contact'          → np.ndarray (N, 3) Å
            'hbd_non_contact'      → np.ndarray (N, 3) Å

        Returns
        -------
        residue_dot_positions dict (same object as self.residue_dot_positions)
        """
        if self.negative_space_data is None:
            raise RuntimeError("Call compute_negative_space() first")
        if self.prot_lig_traj is None:
            raise RuntimeError("Call load() first")
        if mask_key not in self.negative_space_data:
            raise ValueError(
                f"mask_key '{mask_key}' not found. "
                f"Valid: {[k for k in self.negative_space_data if 'mask' in k]}"
            )

        import time as _time
        t0 = _time.time()

        grid_info = self.negative_space_data['grid_info']
        xmin  = grid_info['xmin']
        dx    = grid_info['dx']
        nbins = np.array(grid_info['nbins'])
        mask  = self.negative_space_data[mask_key]   # (nx, ny, nz) bool

        traj = self.prot_lig_traj[::stride]

        def _in_shell(pos_aa):
            """pos_aa : (N, 3) absolute Å → bool (N,)."""
            idx = np.round((pos_aa - xmin) / dx).astype(int)
            idx = np.clip(idx, 0, nbins - 1)
            fi  = idx[:, 0] * nbins[1] * nbins[2] + idx[:, 1] * nbins[2] + idx[:, 2]
            return mask.ravel()[fi]

        def _stack(lst):
            return np.vstack(lst) if lst else np.empty((0, 3), dtype=np.float32)

        # ── Aromatic: ring centroid per frame, contact/non-contact split ──
        protein_rings, protein_rings_index, _ = self.get_protein_rings()
        have_aro = (self._stacked_full is not None and len(protein_rings_index) > 0)
        if not have_aro and len(protein_rings_index) > 0:
            print("  compute_aromatic_contacts() not called — all aromatic dots "
                  "placed in non-contact bucket")

        aro_con_xyz, aro_ncon_xyz = [], []
        for ring_atoms, res_idx in zip(protein_rings, protein_rings_index):
            pos = traj.xyz[:, ring_atoms, :].mean(axis=1) * 10.0   # (F, 3) Å
            sel = _in_shell(pos)
            pos_sel = pos[sel]
            if len(pos_sel) == 0:
                continue
            if have_aro:
                flags = self._stacked_full[::stride][sel, res_idx].astype(bool)
                if flags.any():
                    aro_con_xyz.append(pos_sel[flags])
                if (~flags).any():
                    aro_ncon_xyz.append(pos_sel[~flags])
            else:
                aro_ncon_xyz.append(pos_sel)

        # ── Hydrophobic: sidechain carbon centroid per frame (no split) ───
        hph_xyz = []
        if self.hydrophobic_residue_atoms_dict:
            for res_label, atom_idx in self.hydrophobic_residue_atoms_dict.items():
                if len(atom_idx) == 0:
                    continue
                pos = traj.xyz[:, atom_idx, :].mean(axis=1) * 10.0
                sel = _in_shell(pos)
                if sel.any():
                    hph_xyz.append(pos[sel])

        # ── H-bond acceptors: protein O atoms, contact split via ld matrix ─
        acc_idx = self.prot_lig_top.select('protein and element O')
        have_hba = (self.hbond_contact_frames_ld is not None)
        if not have_hba and len(acc_idx) > 0:
            print("  compute_hbond_contacts() not called — all HBA dots "
                  "placed in non-contact bucket")

        hba_con_xyz, hba_ncon_xyz = [], []
        for atom_i in acc_idx:
            pos = traj.xyz[:, atom_i, :] * 10.0   # (F, 3)
            sel = _in_shell(pos)
            pos_sel = pos[sel]
            if len(pos_sel) == 0:
                continue
            if have_hba:
                r_idx = self.prot_lig_top.atom(atom_i).residue.index
                flags = self.hbond_contact_frames_ld[::stride][sel, r_idx].astype(bool)
                if flags.any():
                    hba_con_xyz.append(pos_sel[flags])
                if (~flags).any():
                    hba_ncon_xyz.append(pos_sel[~flags])
            else:
                hba_ncon_xyz.append(pos_sel)

        # ── H-bond donors: H on N/O, contact split via pd matrix ──────────
        hbd_indices = []
        for a0, a1 in self.prot_lig_top.bonds:
            pair_elems = {a0.element.symbol, a1.element.symbol}
            if pair_elems not in ({'N', 'H'}, {'O', 'H'}):
                continue
            if not (a0.residue.is_protein and a1.residue.is_protein):
                continue
            h_at = a1 if a1.element.symbol == 'H' else a0
            hbd_indices.append(h_at.index)

        have_hbd = (self.hbond_contact_frames_pd is not None)
        if not have_hbd and len(hbd_indices) > 0:
            print("  compute_hbond_contacts() not called — all HBD dots "
                  "placed in non-contact bucket")

        hbd_con_xyz, hbd_ncon_xyz = [], []
        for atom_i in hbd_indices:
            pos = traj.xyz[:, atom_i, :] * 10.0   # (F, 3)
            sel = _in_shell(pos)
            pos_sel = pos[sel]
            if len(pos_sel) == 0:
                continue
            if have_hbd:
                r_idx = self.prot_lig_top.atom(atom_i).residue.index
                flags = self.hbond_contact_frames_pd[::stride][sel, r_idx].astype(bool)
                if flags.any():
                    hbd_con_xyz.append(pos_sel[flags])
                if (~flags).any():
                    hbd_ncon_xyz.append(pos_sel[~flags])
            else:
                hbd_ncon_xyz.append(pos_sel)

        self.residue_dot_positions = {
            'aromatic_contact':     _stack(aro_con_xyz),
            'aromatic_non_contact': _stack(aro_ncon_xyz),
            'hydrophobic':          _stack(hph_xyz),
            'hba_contact':          _stack(hba_con_xyz),
            'hba_non_contact':      _stack(hba_ncon_xyz),
            'hbd_contact':          _stack(hbd_con_xyz),
            'hbd_non_contact':      _stack(hbd_ncon_xyz),
        }

        n_total = sum(len(v) for v in self.residue_dot_positions.values())
        print(f"compute_residue_dot_positions: {n_total:,} total points "
              f"(mask={mask_key}, stride={stride})")
        for cat, arr in self.residue_dot_positions.items():
            print(f"  {cat:22s}: {len(arr):,}")
        print(f"\tDone in {round(_time.time() - t0, 2)} s")
        return self.residue_dot_positions

    def save_aromatic_ring_trajectory(self, output_dir: str, stride: int = 1) -> Dict[str, str]:
        """Write a multi-model PDB of aromatic ring centroids for time-resolved PyMOL visualization.

        One MODEL block per frame (stride-subsampled). Each model contains:
        - Chain A: one pseudo-atom per protein aromatic ring (TYR/PHE/HIS/TRP)
        - Chain B: one pseudo-atom per ligand aromatic ring

        B-factor encodes per-frame contact status:
        - Protein rings: 1.0 if aromatic stacking contact in that frame, 0.0 otherwise
        - Ligand rings: 0.5 (constant landmark)

        The companion .pml colors spheres blue→red by B-factor and scales radius by contact
        strength, so scrubbing through PyMOL states shows contact timing.

        Requires compute_aromatic_contacts() for B-factor coloring; degrades to all-zero
        B-factor if not called.

        Parameters
        ----------
        output_dir : str
            Root output directory.
        stride : int
            Frame subsampling interval (default 1 = every frame).

        Returns
        -------
        dict with keys 'pdb' and 'pml' mapping to absolute file paths.
        """
        if self.prot_lig_traj is None:
            raise RuntimeError("Call load() first")

        os.makedirs(output_dir, exist_ok=True)

        protein_rings, protein_rings_index, _ = self.get_protein_rings()
        lig_rings = [r for r in self.get_ligand_rings() if r['aromatic']]

        # Build ligand ring atom index arrays in prot_lig context
        lig_ring_atom_idx = []
        for ring in lig_rings:
            idx_list = []
            for name in ring['atom_names']:
                idxs = self.convert_ligand_atom_name(name)
                if len(idxs) > 0:
                    idx_list.append(idxs[0])
            lig_ring_atom_idx.append(np.array(idx_list, dtype=int))

        traj     = self.prot_lig_traj[::stride]
        n_frames = traj.n_frames

        if self._stacked_full is not None:
            stacked = self._stacked_full[::stride]
        else:
            print("Warning: _stacked_full not set — call compute_aromatic_contacts() first. "
                  "All protein ring B-factors will be 0.0.")
            stacked = None

        pdb_path = os.path.abspath(os.path.join(f'{output_dir}/dots', 'aromatic_ring_centers.pdb'))
        pml_path = os.path.abspath(os.path.join(output_dir, 'view_aromatic_rings.pml'))

        with open(pdb_path, 'w') as f:
            for fi in range(n_frames):
                f.write(f"MODEL     {fi + 1:4d}\n")
                serial = 1

                # Chain A: protein aromatic ring centroids
                for ring_atoms, res_idx in zip(protein_rings, protein_rings_index):
                    xyz_nm   = traj.xyz[fi, ring_atoms, :]
                    centroid = xyz_nm.mean(axis=0) * 10.0   # nm → Å
                    bfac     = float(stacked[fi, res_idx]) if stacked is not None else 0.0
                    res      = self.prot_lig_top.residue(res_idx)
                    resname  = res.name[:3]
                    resseq   = res.resSeq + self.offset
                    f.write(
                        f"ATOM  {serial:5d}  CA  {resname:<3s} A{resseq:4d}    "
                        f"{centroid[0]:8.3f}{centroid[1]:8.3f}{centroid[2]:8.3f}"
                        f"  1.00{bfac:6.2f}\n"
                    )
                    serial += 1

                # Chain B: ligand aromatic ring centroids
                for li, atom_idx in enumerate(lig_ring_atom_idx):
                    if len(atom_idx) == 0:
                        continue
                    xyz_nm   = traj.xyz[fi, atom_idx, :]
                    centroid = xyz_nm.mean(axis=0) * 10.0
                    f.write(
                        f"ATOM  {serial:5d}  CA  LIG B{li + 1:4d}    "
                        f"{centroid[0]:8.3f}{centroid[1]:8.3f}{centroid[2]:8.3f}"
                        f"  1.00  0.50\n"
                    )
                    serial += 1

                f.write("ENDMDL\n")
            f.write("END\n")

        with open(pml_path, 'w') as f:
            f.write(f"load {pdb_path}, ring_centers\n")
            f.write("show spheres, ring_centers\n")
            f.write("set sphere_mode, 1\n")
            # VDW is a global atom property (not per-state) — fixed sizes by chain
            f.write("alter ring_centers and chain A, vdw=0.4\n")
            f.write("alter ring_centers and chain B, vdw=0.6\n")
            f.write("rebuild\n")
            f.write("bg_color white\n")
            f.write("\n")
            # mdo commands fire on every frame change (scrubbing or playback).
            # At frame s, ring_centers shows state s, so 'b > 0.6' evaluates
            # against that state's B-factors — this is the correct per-frame
            # coloring mechanism in PyMOL (cmd.color has no 'state' parameter).
            f.write("python\n")
            f.write("from pymol import cmd\n")
            f.write("n = cmd.count_states('ring_centers')\n")
            f.write("cmd.mclear()\n")
            f.write("cmd.do('mset 1 -' + str(n))\n")
            f.write("_recolor = (\n")
            f.write("    'color gray70, ring_centers ;'\n")
            f.write("    'color red,    ring_centers and b > 0.6 ;'\n")
            f.write("    'color blue,   ring_centers and b < 0.1 ;'\n")
            f.write("    'color gold,   ring_centers and b > 0.3 and b < 0.6'\n")
            f.write(")\n")
            f.write("for s in range(1, n + 1):\n")
            f.write("    cmd.mdo(s, _recolor)\n")
            f.write("print(f'ring_centers: {n} frames. '\n")
            f.write("      'Use the Frame slider or mplay to navigate.')\n")
            f.write("python end\n")
            f.write("\n")
            f.write("# Static initial coloring for frame 1\n")
            f.write("color gray70, ring_centers\n")
            f.write("color red,    ring_centers and b > 0.6\n")
            f.write("color blue,   ring_centers and b < 0.1\n")
            f.write("color gold,   ring_centers and b > 0.3 and b < 0.6\n")

        n_prot = len(protein_rings)
        n_lig  = len(lig_rings)
        print(f"save_aromatic_ring_trajectory: {n_frames} frames (stride={stride}), "
              f"{n_prot} protein ring(s), {n_lig} ligand ring(s)")
        print(f"  PDB: {pdb_path}")
        print(f"  PML: {pml_path}")

        return {'pdb': pdb_path, 'pml': pml_path}

    def save_dots_pdb(self, output_dir: str) -> Dict[str, str]:
        """Write per-category dot-cloud PDB files for PyMOL visualization.

        Each contact/non-contact split is written as a **separate PDB file**
        so they become independent PyMOL objects that can be toggled on/off
        individually (``enable dots_aromatic_contact`` etc.).

        Creates ``{output_dir}/dots/`` and writes up to 7 PDB files:
          aromatic_contact.pdb     (residue ARO — frames with stacking contact)
          aromatic_non_contact.pdb (residue ARO — frames without stacking contact)
          hydrophobic.pdb          (residue HPH — all frames, no split)
          hba_contact.pdb          (residue HBA — frames with H-bond acceptor contact)
          hba_non_contact.pdb      (residue HBA — frames without H-bond acceptor contact)
          hbd_contact.pdb          (residue HBD — frames with H-bond donor contact)
          hbd_non_contact.pdb      (residue HBD — frames without H-bond donor contact)

        Files are skipped silently if the corresponding array is empty.

        Requires compute_residue_dot_positions() to have been called first.

        Parameters
        ----------
        output_dir : str
            Root output directory (same as used for save_mrc_files()).

        Returns
        -------
        dict mapping file stem → absolute path of written PDB file.
        """
        if self.residue_dot_positions is None:
            raise RuntimeError("Call compute_residue_dot_positions() first")

        dots_dir = os.path.join(output_dir, 'dots')
        os.makedirs(dots_dir, exist_ok=True)

        rdp = self.residue_dot_positions
        elem_C = md.element.Element.getBySymbol('C')

        def _write_pdb(coords_aa, res_name, fname):
            """Write a single-category PDB (all C atoms); return fname or None."""
            n = len(coords_aa)
            if n == 0:
                return None
            top   = md.Topology()
            chain = top.add_chain()
            res   = top.add_residue(res_name, chain)
            for _ in range(n):
                top.add_atom('C', elem_C, res)
            xyz_nm = (coords_aa / 10.0).reshape(1, -1, 3)
            md.Trajectory(xyz_nm, top).save_pdb(fname)
            return fname

        written = {}

        _categories = [
            ('aromatic_contact',     'ARO', 'aromatic_contact.pdb'),
            ('aromatic_non_contact', 'ARO', 'aromatic_non_contact.pdb'),
            ('hydrophobic',          'HPH', 'hydrophobic.pdb'),
            ('hba_contact',          'HBA', 'hba_contact.pdb'),
            ('hba_non_contact',      'HBA', 'hba_non_contact.pdb'),
            ('hbd_contact',          'HBD', 'hbd_contact.pdb'),
            ('hbd_non_contact',      'HBD', 'hbd_non_contact.pdb'),
        ]
        for key, res_name, pdb_name in _categories:
            coords = rdp.get(key, np.empty((0, 3)))
            fname  = os.path.join(dots_dir, pdb_name)
            result = _write_pdb(coords, res_name, fname)
            if result:
                written[key] = result
                print(f"  {pdb_name:<28}: {len(coords):,} atoms")

        print(f"save_dots_pdb: wrote {len(written)} file(s) to {dots_dir}")
        return written

    def write_pymol_script(self, output_dir: str,
                           score_percentile_tiers: Optional[List[int]] = None,
                           set_view: Optional[str] = None,
                           load_trajectory: bool = False) -> str:
        """Write a PyMOL .pml script loading all MRC volumes from save_mrc_files().

        Reconstructs file paths from the same deterministic directory structure
        written by save_mrc_files(). Missing files are silently skipped so the
        script works regardless of which analysis methods were called.

        Loads:
          - ligand_centroid.pdb as sticks
          - growth_space.mrc and contested_space.mrc as volumetric renders
          - Pharmacophore occupancy maps (contested) as isomesh at level 0.3
          - Growth-feature score maps as isomesh at level 0.3 (full maps shown;
            percentile-tiered maps loaded but hidden — enable with 'enable <name>')

        Requires save_mrc_files() to have been called with the same output_dir.

        Parameters
        ----------
        output_dir : str
            Same root directory passed to save_mrc_files().
        score_percentile_tiers : list of int, optional
            Tiers to load (default: [1, 5, 10, 20]).  Must match what was used
            in save_mrc_files() to find the tiered .mrc files.
        set_view : str, optional
            Camera orientation as a raw string copied directly from PyMOL's
            ``get_view`` command output. Use a raw Python string to preserve
            the backslashes, e.g.::

                r\"\"\"set_view (\\
                    -0.055,  -0.422,   0.904,\\
                    ...
                    82.718, 127.118, -20.000 )\"\"\"

            When provided the active ``set_view`` command is written to the
            script. When None (default) a commented-out template is written.
        load_trajectory : bool, optional
            When True, prepend ``load`` commands for the topology and trajectory
            files that were used to construct this object (self._topology_path and
            self._trajectory_path). Default False.

        Returns
        -------
        str — absolute path of the written .pml script.
        """
        if score_percentile_tiers is None:
            score_percentile_tiers = [1, 5, 10, 20]

        # Reconstruct expected subdirectory paths
        ns_dir = os.path.join(output_dir, 'negative_space')
        gf_dir = os.path.join(output_dir, 'growth_features')
        pc_dir = os.path.join(output_dir, 'pharmacophore_contested')

        ligand_pdb       = os.path.join(output_dir, 'ligand_centroid.pdb')
        growth_space_mrc = os.path.join(ns_dir, 'growth_space.mrc')
        contested_mrc    = os.path.join(ns_dir, 'contested_space.mrc')

        pymol_script = os.path.join(output_dir, 'view_pharmacophore.pml')
        with open(pymol_script, 'w') as f:
            f.write("# PyMOL pharmacophore visualization script\n")
            f.write(f"# Generated by PharmacophoreTrajectory.write_pymol_script()\n\n")

            # ── Trajectory ───────────────────────────────────────────────────
            if load_trajectory:
                f.write("# MD trajectory\n")
                f.write(f"load {self._topology_path}\n")
                f.write(f"load_traj {self._trajectory_path}, {os.path.splitext(os.path.basename(self._topology_path))[0]}\n\n")
                f.write(f"hide spheres, {os.path.splitext(os.path.basename(self._topology_path))[0]}\n")
                f.write(f"disable {os.path.splitext(os.path.basename(self._topology_path))[0]}\n")
                f.write("show sticks, resn PHE+TYR+TRP+HIS\n")
                f.write("hide cartoon\n")

            # ── Ligand ────────────────────────────────────────────────────────
            if os.path.exists(ligand_pdb):
                f.write("# Ligand centroid structure\n")
                f.write(f"load {ligand_pdb}, ligand\n")
                f.write("show sticks, ligand\n")
                f.write("util.cbag ligand\n")
                f.write("set stick_radius, 0.15\n\n")

                # ── SASA Jet coloring (overrides element colors if computed) ──
                if self.sasa_ligand_atoms_df is not None:
                    f.write(
                        "# Ligand SASA coloring (Jet: darkblue=buried → red=exposed)\n"
                        "# Computed on protein+ligand trajectory — no explicit solvent:\n"
                        "# low SASA = atom embedded in protein pocket;\n"
                        "# high SASA = atom pointing outward / solvent-accessible.\n"
                    )
                    mean_sasa = self.sasa_ligand_atoms_df.mean(axis=0)
                    smin, smax = float(mean_sasa.min()), float(mean_sasa.max())
                    span = smax - smin if smax > smin else 1.0
                    f.write(
                        f"# SASA range: {smin*100:.2f}–{smax*100:.2f} Å²\n"
                    )
                    for atom_name, sasa_val in mean_sasa.items():
                        t = (float(sasa_val) - smin) / span
                        hex_col = _jet_hex(t)
                        f.write(
                            f"color 0x{hex_col}, ligand and name {atom_name}\n"
                        )
                    f.write("\n")

            # ── Growth space volume ────────────────────────────────────────────
            if os.path.exists(growth_space_mrc):
                f.write("# Growth space (protein occupancy < 30%)\n")
                f.write(f"load {growth_space_mrc}, growth_space\n")
                f.write("volume growth_vol, growth_space\n")
                f.write("cmd.volume_ramp_new('ramp816', [\\\n")
                f.write("     -0.21, 0.33, 1.00, 1.00, 0.02, \\\n")
                f.write("      0.07, 0.00, 0.00, 1.00, 0.02, \\\n")
                f.write("    ])\n")
                f.write("volume_color growth_vol, ramp816\n\n")

            # ── Contested space volume ─────────────────────────────────────────
            if os.path.exists(contested_mrc):
                f.write("# Contested space (protein occupancy >= 30%)\n")
                f.write(f"load {contested_mrc}, contested_space\n")
                f.write("volume contested_vol, contested_space\n")
                f.write("cmd.volume_ramp_new('ramp505', [\\\n")
                f.write("      0.10, 1.00, 0.47, 0.00, 0.18, \\\n")
                f.write("      0.61, 1.00, 0.55, 0.04, 0.05, \\\n")
                f.write("    ])\n")
                f.write("volume_color contested_vol, ramp505\n\n")

            # ── Pharmacophore maps (contested space) ──────────────────────────
            f.write("# PHARMACOPHORE FROM CONTESTED SPACE\n")
            contested_occ = [
                ('aromatic_occupancy',                     'black'),
                ('aromatic_occupancy_contacts',            'purpleblue'),
                ('aromatic_occupancy_non_contacts',        'deepsalmon'),
                ('hydrophobic_occupancy',                  'forest'),
                ('hbond_donors_occupancy',                 'firebrick'),
                ('hbond_donors_occupancy_contacts',        'purpleblue'),
                ('hbond_donors_occupancy_non_contacts',    'deepsalmon'),
                ('hbond_acceptors_occupancy',              'firebrick'),
                ('hbond_acceptors_occupancy_contacts',     'purpleblue'),
                ('hbond_acceptors_occupancy_non_contacts', 'deepsalmon'),
            ]
            for key, color in contested_occ:
                mrc_path = os.path.join(pc_dir, f'{key}.mrc')
                if not os.path.exists(mrc_path):
                    continue
                f.write(f"load {mrc_path}, {key}\n")
                f.write(f"isomesh {key}_mesh, {key}, 0.3\n")
                f.write(f"color {color}, {key}_mesh\n")
                for tier in score_percentile_tiers:
                    tier_mrc = os.path.join(pc_dir, f'{key}_top{tier}pct.mrc')
                    if os.path.exists(tier_mrc):
                        tier_obj = f'{key}_top{tier}pct'
                        f.write(f"load {tier_mrc}, {tier_obj}\n")
                        f.write(f"isomesh {tier_obj}_mesh, {tier_obj}, 0.01\n")
                        f.write(f"color {color}, {tier_obj}_mesh\n")
                        f.write(f"disable {tier_obj}_mesh\n")
            f.write("\n")

            # ── Growth space chemical feature maps ────────────────────────────
            f.write("# CHEMICAL FEATURES (GROWTH SPACE)\n")
            f.write("# Full maps shown; tiered maps loaded but hidden.\n")
            f.write("# Toggle tiers: enable <name>_mesh / disable <name>_mesh\n\n")

            feature_vis = [
                ('aromatic_sites',        'aromatic',   'black',    'Aromatic sites'),
                ('hydrophobic_sites',     'hydrophobic','forest',   'Hydrophobic sites'),
                ('hbond_acceptor_sites',  'hbond_acc',  'firebrick','H-bond acceptor sites'),
                ('hbond_donor_sites',     'hbond_don',  'firebrick','H-bond donor sites'),
                ('negative_charge_sites', 'neg_charge', 'purple',   'Negative charge sites'),
                ('positive_charge_sites', 'pos_charge', 'magenta',  'Positive charge sites'),
            ]
            for fname_base, obj_name, color, comment in feature_vis:
                full_mrc = os.path.join(gf_dir, f'{fname_base}.mrc')
                if not os.path.exists(full_mrc):
                    continue
                f.write(f"# {comment}\n")
                f.write(f"load {full_mrc}, {obj_name}\n")
                f.write(f"isomesh {obj_name}_mesh, {obj_name}, 0.3\n")
                f.write(f"color {color}, {obj_name}_mesh\n")
                for tier in score_percentile_tiers:
                    tier_mrc = os.path.join(gf_dir, f'{fname_base}_top{tier}pct.mrc')
                    if os.path.exists(tier_mrc):
                        tier_obj = f'{obj_name}_top{tier}pct'
                        f.write(f"load {tier_mrc}, {tier_obj}\n")
                        f.write(f"isomesh {tier_obj}_mesh, {tier_obj}, 0.01\n")
                        f.write(f"color {color}, {tier_obj}_mesh\n")
                        f.write(f"disable {tier_obj}_mesh\n")
                f.write("\n")

            # ── Residue dot-cloud PDB files (save_dots_pdb output) ───────────
            # Each contact/non-contact split is a separate PyMOL object so it
            # can be toggled independently with enable/disable.
            # All objects are disabled by default; toggle with e.g.:
            #   enable dots_aromatic_contact
            #   enable dots_aromatic_non_contact
            dots_dir = os.path.join(output_dir, 'dots')
            _dot_cfg = [
                ('aromatic_contact',     'aromatic_contact.pdb',      'magenta', 0.10),
                ('aromatic_non_contact', 'aromatic_non_contact.pdb',  'grey60',  0.07),
                ('hydrophobic',          'hydrophobic.pdb',           'orange',  0.07),
                ('hba_contact',          'hba_contact.pdb',           'forest',  0.07),
                ('hba_non_contact',      'hba_non_contact.pdb',       'grey60',  0.05),
                ('hbd_contact',          'hbd_contact.pdb',           'blue',    0.07),
                ('hbd_non_contact',      'hbd_non_contact.pdb',       'grey60',  0.05),
            ]
            any_dots = False
            for stem, pdb_file, color, sphere_scale in _dot_cfg:
                pdb_path = os.path.join(dots_dir, pdb_file)
                if not os.path.exists(pdb_path):
                    continue
                if not any_dots:
                    f.write("# Per-frame residue atom positions (PDB dot clouds)\n")
                    f.write("# Each object is independently togglable:\n")
                    f.write("#   enable dots_aromatic_contact / dots_aromatic_non_contact\n")
                    f.write("#   enable dots_hba_contact / dots_hba_non_contact  etc.\n\n")
                    any_dots = True
                obj = f'dots_{stem}'
                f.write(f"load {pdb_path}, {obj}\n")
                f.write(f"hide licorice, {obj}\n")
                f.write(f"show spheres, {obj}\n")
                f.write(f"set sphere_scale, {sphere_scale}, {obj}\n")
                f.write(f"color {color}, {obj}\n")
                f.write(f"disable {obj}\n\n")

            # ── Aromatic ring centroid trajectory ────────────────────────────
            ring_centers_pdb = os.path.join(output_dir, 'aromatic_ring_centers.pdb')
            if os.path.exists(ring_centers_pdb):
                f.write(f"load {ring_centers_pdb}, ring_centers\n")
                f.write("show nb_spheres, ring_centers\n")
                f.write("color yellow, ring_centers\n")

            f.write('hide cartoon\n\n')
            # ── View settings ─────────────────────────────────────────────────
            f.write('disable contested_vol\n')
            f.write('disable aromatic_occupancy_mesh\n')
            f.write('disable aromatic_occupancy_contacts_mesh\n')
            f.write('disable aromatic_occupancy_non_contacts_mesh\n')
            f.write('disable hydrophobic_occupancy_mesh\n')
            f.write('disable hbond_donors_occupancy_mesh\n')
            f.write('disable hbond_acceptors_occupancy_mesh\n')
            f.write('disable aromatic_mesh\n')
            f.write('disable hydrophobic_mesh\n')
            f.write('disable hbond_acc_mesh\n')
            f.write('disable hbond_don_mesh\n')
            f.write('disable hbond_donors_occupancy_contacts_mesh\n')
            f.write('disable hbond_donors_occupancy_non_contacts_mesh\n')
            f.write('disable hbond_acceptors_occupancy_contacts_mesh\n')
            f.write('disable hbond_acceptors_occupancy_non_contacts_mesh\n')
            f.write('disable neg_charge_mesh\n')
            f.write('disable pos_charge_mesh\n')
            f.write('disable ring_centers\n\n')

            f.write("# View settings\n")
            f.write("bg_color white\n")
            f.write("set depth_cue, 0\n")
            if os.path.exists(ligand_pdb):
                f.write("center ligand\n")
            f.write("refresh\n\n")
            if os.path.exists(growth_space_mrc):
                f.write("zoom growth_vol\n")
            if set_view is not None and set_view.strip():
                f.write(set_view.strip() + "\n\n")
            else:
                f.write("# Uncomment and adjust for a custom saved view:\n")
                f.write("# set_view (\\\n")
                f.write("#     -0.055175416,   -0.422412157,    0.904722989,\\\n")
                f.write("#      0.977541029,   -0.207427859,   -0.037231173,\\\n")
                f.write("#      0.203391120,    0.882350326,    0.424371362,\\\n")
                f.write("#      0.000000000,    0.000000000, -104.918716431,\\\n")
                f.write("#     27.569999695,  -10.580001831,   42.870002747,\\\n")
                f.write("#     82.718719482,  127.118713379,  -20.000000000 )\n\n")
            f.write("set ray_trace_mode, 3\n")
            f.write("set ray_volume, 1\n")
            
            # ── Production images ───────────────────────────────────────────────
            f.write("enable contested_vol\n")
            f.write("refresh\n")
            f.write(f"png {output_dir}/pharmacophore.png, 1090, 1090\n")
            f.write("disable contested_vol\n")
            
            f.write("enable aromatic_occupancy_top10pct_mesh\n")
            f.write("refresh\n")
            f.write(f"png {output_dir}/pharmacophore_aromatics.png, 1090, 1090\n")
            f.write("disable aromatic_occupancy_top10pct_mesh\n")
            
            f.write("enable aromatic_occupancy_contacts_top10pct_mesh\n")
            f.write("refresh\n")
            f.write(f"png {output_dir}/pharmacophore_aromatics_contacts.png, 1090, 1090\n")
            f.write("disable aromatic_occupancy_contacts_top10pct_mesh\n")
            
            f.write("enable aromatic_occupancy_non_contacts_top10pct_mesh\n")
            f.write("refresh\n")
            f.write(f"png {output_dir}/pharmacophore_aromatics_non_contacts.png, 1090, 1090\n")
            f.write("disable aromatic_occupancy_non_contacts_top10pct_mesh\n")
            
            f.write("enable hydrophobic_occupancy_top10pct_mesh\n")
            f.write("refresh\n")
            f.write(f"png {output_dir}/pharmacophore_hydrophobic.png, 1090, 1090\n")
            f.write("disable hydrophobic_occupancy_top10pct_mesh\n")
            
            f.write("enable hbond_donors_occupancy_top10pct_mesh\n")
            f.write("refresh\n")
            f.write(f"png {output_dir}/pharmacophore_hbd.png, 1090, 1090\n")
            f.write("disable hbond_donors_occupancy_top10pct_mesh\n")
            
            f.write("enable hbond_donors_occupancy_contacts_top10pct_mesh\n")
            f.write("refresh\n")
            f.write(f"png {output_dir}/pharmacophore_hbd_contacts.png, 1090, 1090\n")
            f.write("disable hbond_donors_occupancy_contacts_top10pct_mesh\n")
            
            f.write("enable hbond_donors_occupancy_non_contacts_top10pct_mesh\n")
            f.write("refresh\n")
            f.write(f"png {output_dir}/pharmacophore_hbd_non_contacts.png, 1090, 1090\n")
            f.write("disable hbond_donors_occupancy_non_contacts_top10pct_mesh\n")
            
            f.write("enable hbond_acceptors_occupancy_top10pct_mesh\n")
            f.write("refresh\n")
            f.write(f"png {output_dir}/pharmacophore_hba.png, 1090, 1090\n")
            f.write("disable hbond_acceptors_occupancy_top10pct_mesh\n")
            
            f.write("enable hbond_acceptors_occupancy_contacts_top10pct_mesh\n")
            f.write("refresh\n")
            f.write(f"png {output_dir}/pharmacophore_hba_contacts.png, 1090, 1090\n")
            f.write("disable hbond_acceptors_occupancy_contacts_top10pct_mesh\n")
            
            f.write("enable hbond_acceptors_occupancy_non_contacts_top10pct_mesh\n")
            f.write("refresh\n")
            f.write(f"png {output_dir}/pharmacophore_hba_non_contacts.png, 1090, 1090\n")
            f.write("disable hbond_acceptors_occupancy_non_contacts_top10pct_mesh\n")
            
            f.write("# disable contested_vol\n")
            
            f.write("# quit\n")

        print(f"✓ PyMOL script: {pymol_script}")
        print(f"  Open with: pymol {pymol_script}")
        return pymol_script
