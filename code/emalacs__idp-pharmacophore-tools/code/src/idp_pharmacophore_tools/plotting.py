import os

import numpy as np

from ._deps import pd, go


class PlottingMixin:

    def plot_3d_residues(self, mask_key: str = 'full_shell_mask',
                         stride: int = 1,
                         marker_size: int = 1,
                         title: str = '') -> 'go.Figure':
        """3D scatter of per-frame residue atom positions around the ligand.

        One point per (trajectory frame, residue representative atom), filtered
        to positions that fall inside the voxel region defined by mask_key.
        The mean ligand centroid (over all frames) is placed at the origin.

        Categories
        ----------
        Ligand       : mean heavy-atom positions — one point per atom (static)
        Aromatic     : ring centroid per frame  (TYR / PHE / HIS / TRP)
        Hydrophobic  : sidechain C/S centroid per residue per frame
        HB acceptor  : protein O atom positions per frame
        HB donor     : protein H atoms bonded to N or O, per frame

        Parameters
        ----------
        mask_key : str
            Key in negative_space_data selecting the voxel region to display.
            Valid values: 'full_shell_mask', 'growth_space_mask',
            'contested_space_mask'.
        stride : int
            Use every nth frame (1 = all frames).
        marker_size : int
            Marker radius for residue dots.
        title : str
            Figure title.  Auto-generated when empty.

        Returns
        -------
        plotly.graph_objects.Figure
        """
        if go is None:
            raise ImportError("plotly required — install: pip install plotly")
        if self.negative_space_data is None:
            raise RuntimeError("Call compute_negative_space() first")
        if self.prot_lig_traj is None:
            raise RuntimeError("Call load() first")
        if mask_key not in self.negative_space_data:
            raise ValueError(
                f"mask_key '{mask_key}' not in negative_space_data. "
                f"Valid: {[k for k in self.negative_space_data if 'mask' in k]}")

        grid_info = self.negative_space_data['grid_info']
        xmin  = grid_info['xmin']
        dx    = grid_info['dx']
        nbins = np.array(grid_info['nbins'])
        mask  = self.negative_space_data[mask_key]     # (nx, ny, nz) bool

        traj     = self.prot_lig_traj[::stride]
        n_frames = traj.n_frames

        # ── Shell membership test (vectorised) ───────────────────────────────
        def _in_shell(pos_aa):
            """pos_aa : (N, 3) absolute Å → bool (N,)."""
            idx = np.round((pos_aa - xmin) / dx).astype(int)
            idx = np.clip(idx, 0, nbins - 1)
            fi  = idx[:, 0] * nbins[1] * nbins[2] + idx[:, 1] * nbins[2] + idx[:, 2]
            return mask.ravel()[fi]

        # ── Centering: mean ligand heavy-atom centroid over all frames ────────
        lig_aa  = traj.xyz[:, self.all_ligand_atoms_noh, :] * 10.0  # (F, L, 3)
        centroid = lig_aa.mean(axis=(0, 1))                          # (3,)  Å

        # ── Ligand trace: mean atom positions (one point per heavy atom) ──────
        lig_mean = lig_aa.mean(axis=0) - centroid                    # (L, 3)
        lig_names = [self.prot_lig_top.atom(int(i)).name
                     for i in self.all_ligand_atoms_noh]

        # ── Aromatic: ring centroid per frame ─────────────────────────────────
        protein_rings, protein_rings_index, _ = self.get_protein_rings()
        aro_xyz, aro_text = [], []
        for ring_atoms, res_idx in zip(protein_rings, protein_rings_index):
            res   = self.prot_lig_top.residue(res_idx)
            label = f"{res.name} {res.resSeq + self.offset}"
            pos   = traj.xyz[:, ring_atoms, :].mean(axis=1) * 10.0  # (F, 3)
            sel   = _in_shell(pos)
            if sel.any():
                aro_xyz.append(pos[sel] - centroid)
                aro_text.extend([label] * int(sel.sum()))

        # ── Hydrophobic: per-residue sidechain C/S centroid per frame ─────────
        hph_xyz, hph_text = [], []
        if self.hydrophobic_residue_atoms_dict:
            for res_label, atom_idx in self.hydrophobic_residue_atoms_dict.items():
                if len(atom_idx) == 0:
                    continue
                pos = traj.xyz[:, atom_idx, :].mean(axis=1) * 10.0  # (F, 3)
                sel = _in_shell(pos)
                if sel.any():
                    hph_xyz.append(pos[sel] - centroid)
                    hph_text.extend(
                        [res_label.replace('_', ' ')] * int(sel.sum()))

        # ── H-bond acceptors: protein O atom positions per frame ──────────────
        acc_idx = self.prot_lig_top.select('protein and element O')
        hba_xyz, hba_text = [], []
        for atom_i in acc_idx:
            at  = self.prot_lig_top.atom(int(atom_i))
            lbl = (f"{at.name} "
                   f"{at.residue.name} {at.residue.resSeq + self.offset}")
            pos = traj.xyz[:, atom_i, :] * 10.0   # (F, 3)
            sel = _in_shell(pos)
            if sel.any():
                hba_xyz.append(pos[sel] - centroid)
                hba_text.extend([lbl] * int(sel.sum()))

        # ── H-bond donors: H atoms bonded to N or O, per frame ───────────────
        # MDTraj bonds live on the Topology object, not on individual atoms.
        donor_pairs = []   # list of (h_atom_index, label)
        for a0, a1 in self.prot_lig_top.bonds:
            pair_elems = {a0.element.symbol, a1.element.symbol}
            if pair_elems not in ({'N', 'H'}, {'O', 'H'}):
                continue
            if not (a0.residue.is_protein and a1.residue.is_protein):
                continue
            h_at     = a1 if a1.element.symbol == 'H' else a0
            heavy_at = a0 if a0.element.symbol != 'H' else a1
            lbl = (f"{h_at.name}→{heavy_at.name} "
                   f"{h_at.residue.name} {h_at.residue.resSeq + self.offset}")
            donor_pairs.append((h_at.index, lbl))

        hbd_xyz, hbd_text = [], []
        for atom_i, lbl in donor_pairs:
            pos = traj.xyz[:, atom_i, :] * 10.0   # (F, 3)
            sel = _in_shell(pos)
            if sel.any():
                hbd_xyz.append(pos[sel] - centroid)
                hbd_text.extend([lbl] * int(sel.sum()))

        # ── Stack lists ───────────────────────────────────────────────────────
        def _stack(lst):
            return np.vstack(lst) if lst else np.empty((0, 3))

        aro_xyz = _stack(aro_xyz)
        hph_xyz = _stack(hph_xyz)
        hba_xyz = _stack(hba_xyz)
        hbd_xyz = _stack(hbd_xyz)

        # ── Build figure ──────────────────────────────────────────────────────
        fig = go.Figure()

        def _add_trace(xyz, text, name, color):
            if len(xyz) == 0:
                return
            fig.add_trace(go.Scatter3d(
                x=xyz[:, 0], y=xyz[:, 1], z=xyz[:, 2],
                mode='markers',
                name=name,
                marker=dict(size=marker_size, color=color, opacity=0.2,
                            line=dict(width=0)),
                text=text,
                hovertemplate='%{text}<extra>' + name + '</extra>',
            ))

        fig.add_trace(go.Scatter3d(
            x=lig_mean[:, 0], y=lig_mean[:, 1], z=lig_mean[:, 2],
            mode='markers',
            name='Ligand',
            marker=dict(size=5, color='white',
                        line=dict(color='grey', width=1)),
            text=lig_names,
            hovertemplate='%{text}<extra>Ligand</extra>',
        ))
        _add_trace(aro_xyz, aro_text, 'Aromatic',    '#e377c2')
        _add_trace(hph_xyz, hph_text, 'Hydrophobic', '#ff7f0e')
        _add_trace(hba_xyz, hba_text, 'HB acceptor', '#2ca02c')
        _add_trace(hbd_xyz, hbd_text, 'HB donor',    '#1f77b4')

        n_total = sum(len(a) for a in [aro_xyz, hph_xyz, hba_xyz, hbd_xyz])
        print(f"plot_3d_residues: {n_total:,} points "
              f"({n_frames} frames × stride {stride}, mask={mask_key})")

        fig.update_layout(
            title=title or f'3D residue map — {mask_key}',
            scene=dict(
                xaxis_title='X (Å)',
                yaxis_title='Y (Å)',
                zaxis_title='Z (Å)',
                aspectmode='data',
            ),
            legend=dict(yanchor='top', y=0.99, xanchor='left', x=0.01,
                        itemsizing='constant'),
        )
        return fig

    def plot_contact_probability(self, df=None, data: str = 'aromatic_stacking',
                                 title: str = '', add_error_bars: bool = False):
        """Return a Plotly figure of per-residue contact probability.

        Parameters
        ----------
        df : pd.DataFrame, optional
            DataFrame to plot. Pass sim.aromatic_contact_probability for aromatic
            contacts or sim.contact_probability for general contacts. When None,
            falls back to sim.contact_probability.
        data : str
            Column in df to plot. Typical values: 'aromatic_stacking',
            'aromatic_pstacking', 'aromatic_tstacking', 'contact_probability',
            or a per-ring column like '0', '1', or 'hydrophobic_contacts'.
        title : str
            Figure title (empty string shows no title).
        add_error_bars : bool
            When True, draws a shaded band using the matching '{data}_error' column.

        Returns
        -------
        plotly.graph_objects.Figure
        """
        if go is None:
            raise ImportError("plotly required — install: pip install plotly")
        if df is None:
            df = self.contact_probability
        if df is None:
            raise RuntimeError(
                "Pass a DataFrame or call a compute_*_contact*() method first")
        fig = go.Figure()

        if add_error_bars:
            x_labels = df.index.str.replace('_', ' ')
            fig.add_trace(go.Scatter(
                x=x_labels, y=df[data] + df[f'{data}_error'],
                showlegend=False, mode='lines', line=dict(width=0), name='',
            ))
            fig.add_trace(go.Scatter(
                x=x_labels, y=df[data] - df[f'{data}_error'],
                showlegend=False, mode='lines', line=dict(width=0),
                fillcolor='rgba(226, 226, 226, 0.5)', fill='tonexty', name='',
            ))

        fig.add_trace(go.Scattergl(
            x=df.index.str.replace('_', ' '),
            y=df[data],
            name=data,
            showlegend=True,
        ))
        fig.update_xaxes(
            title='Residues', showline=True, linecolor='black', linewidth=2,
            tickfont=dict(size=18), title_font=dict(size=22),
        )
        fig.update_yaxes(
            title='Probability', showgrid=True, gridwidth=1,
            gridcolor='rgb(226, 226, 226)',
            showline=True, linecolor='black', linewidth=2,
            tickfont=dict(size=18), title_font=dict(size=22),
        )
        fig.update_layout(
            title=title,
            hovermode='x unified',
            legend=dict(yanchor='bottom', y=0.99, orientation='h'),
        )
        return fig

    def plot_dssp(self, df=None, title: str = '',
                  add_error_bars: bool = True) -> 'go.Figure':
        """Return a Plotly figure of per-residue DSSP helix/sheet probabilities.

        Parameters
        ----------
        df : pd.DataFrame, optional
            DataFrame with DSSP columns. Defaults to self.dssp_df.
            Must contain 'DSSP_helix' and/or 'DSSP_sheet' columns.
        title : str
            Figure title.
        add_error_bars : bool
            When True, draw shaded error bands using *_error_up / *_error_low columns.

        Returns
        -------
        plotly.graph_objects.Figure
        """
        if go is None:
            raise ImportError("plotly required — install: pip install plotly")
        if df is None:
            df = self.dssp_df
        if df is None:
            raise RuntimeError("Call compute_dssp() first or pass a DataFrame")

        fig = go.Figure()
        x_labels = df.index.str.replace('_', ' ')

        for col, err_up, err_low, color, name in [
            ('DSSP_helix', 'DSSP_helix_error_up', 'DSSP_helix_error_low', '#e377c2', 'Helix'),
            ('DSSP_sheet', 'DSSP_sheet_error_up', 'DSSP_sheet_error_low', '#1f77b4', 'Sheet'),
        ]:
            if col not in df.columns:
                continue
            if add_error_bars and err_up in df.columns and err_low in df.columns:
                fig.add_trace(go.Scatter(
                    x=x_labels, y=df[err_up],
                    mode='lines', line=dict(width=0), showlegend=False, name='',
                ))
                fig.add_trace(go.Scatter(
                    x=x_labels, y=df[err_low],
                    mode='lines', line=dict(width=0), showlegend=False,
                    fill='tonexty', fillcolor='rgba(128,128,128,0.2)', name='',
                ))
            fig.add_trace(go.Scattergl(
                x=x_labels, y=df[col],
                name=name, line=dict(color=color),
            ))

        if 'DSSP_helix_reweighted' in df.columns:
            fig.add_trace(go.Scattergl(
                x=x_labels, y=df['DSSP_helix_reweighted'],
                name='Helix (reweighted)', line=dict(color='#e377c2', dash='dash'),
            ))

        fig.update_xaxes(
            title='Residues', showline=True, linecolor='black', linewidth=2,
            tickfont=dict(size=18), title_font=dict(size=22),
        )
        fig.update_yaxes(
            title='Probability', range=[0, 1],
            showgrid=True, gridwidth=1, gridcolor='rgb(226, 226, 226)',
            showline=True, linecolor='black', linewidth=2,
            tickfont=dict(size=18), title_font=dict(size=22),
        )
        fig.update_layout(
            title=title,
            hovermode='x unified',
            legend=dict(yanchor='bottom', y=0.99, orientation='h'),
        )
        return fig

    def plot_gyration_salpha_fes(self, df=None, title: str = '',
                                  colorscale: str = 'RdBu_r',
                                  max_dG: float = None,
                                  ncontours: int = 20) -> 'go.Figure':
        """Plot the 2D Rg vs Sα free energy surface as a Plotly filled contour map.

        Parameters
        ----------
        df : pd.DataFrame, optional
            FES DataFrame (rows=Sα, columns=Rg in nm, values in kcal/mol).
            Defaults to self.gyration_salpha_fes_df.
        title : str
            Figure title.
        colorscale : str
            Plotly colorscale. Default 'RdBu_r' (blue=low ΔG).
        max_dG : float, optional
            Clip the color scale at this ΔG value (kcal/mol). Useful for
            focusing contrast on the low-energy basin.
        ncontours : int
            Number of contour levels. Default 20.

        Returns
        -------
        plotly.graph_objects.Figure
        """
        if go is None:
            raise ImportError("plotly required — install: pip install plotly")
        if df is None:
            df = self.gyration_salpha_fes_df
        if df is None:
            raise RuntimeError(
                "Call compute_gyration_salpha() first or pass a DataFrame")

        z = df.values.T.copy()   # transpose: rows→Rg, cols→Sα  (x=Sα, y=Rg)
        if max_dG is not None:
            z = np.clip(z, 0.0, float(max_dG))

        fig = go.Figure(go.Contour(
            z=z,
            x=df.index.to_numpy(),     # Sα bin centres (x-axis)
            y=df.columns.to_numpy(),   # Rg bin centres (y-axis, nm)
            colorscale=colorscale,
            ncontours=ncontours,
            contours=dict(showlabels=True, labelfont=dict(size=10)),
            colorbar=dict(title='ΔG (kcal/mol)', titleside='right'),
        ))
        fig.update_xaxes(
            title='S<sub>α</sub>',
            showline=True, linecolor='black', linewidth=2,
            tickfont=dict(size=16), title_font=dict(size=20),
        )
        fig.update_yaxes(
            title='R<sub>g</sub> (nm)',
            showline=True, linecolor='black', linewidth=2,
            tickfont=dict(size=16), title_font=dict(size=20),
        )
        fig.update_layout(title=title, width=650, height=550)
        return fig

    def plot_contact_map(self, df=None, title: str = '') -> 'go.Figure':
        """Plot the intra-protein residue contact probability map as a heatmap.

        Parameters
        ----------
        df : pd.DataFrame, optional
            Contact probability matrix. Defaults to self.contact_map_df.
        title : str
            Figure title.

        Returns
        -------
        go.Figure
        """
        if go is None:
            raise ImportError("plotly required — install: pip install plotly")
        if df is None:
            if self.contact_map_df is None:
                raise ValueError("Run compute_contact_map() first (distance_raw=False).")
            df = self.contact_map_df

        labels = df.columns.str.replace('_', ' ').tolist()
        fig = go.Figure()
        fig.add_trace(go.Heatmap(
            z=df.values,
            x=labels,
            y=labels,
            colorscale='Jet',
            colorbar=dict(title='Probability'),
        ))
        fig.update_xaxes(
            showline=True, linecolor='black', linewidth=2,
            tickfont=dict(size=12), title_font=dict(size=18),
            tickangle=45,
        )
        fig.update_yaxes(
            showline=True, linecolor='black', linewidth=2,
            tickfont=dict(size=12), title_font=dict(size=18),
        )
        fig.update_layout(
            title=title,
            font=dict(size=18),
            plot_bgcolor='rgb(255,255,255)',
            width=700,
            height=650,
        )
        return fig

    def save_plot(self, fig, output_path: str) -> None:
        """Save a Plotly figure as a self-contained HTML file."""
        if go is None:
            raise ImportError("plotly required — install: pip install plotly")
        outstring = '/'.join(output_path.split('/')[:-1])
        print('Saving plot in: ', outstring)
        os.makedirs(outstring, exist_ok=True)
        fig.write_html(output_path)

    # ── Memory management ────────────────────────────────────────────────────
