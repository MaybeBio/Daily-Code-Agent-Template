import os
from typing import Dict, List, Optional, Set, Tuple

import numpy as np

from ._constants import DIFF_CATEGORIES, DIFF_MAP_SETS
from ._deps import (
    md, MDTRAJ_AVAILABLE,
    mrcfile, MRCFILE_AVAILABLE,
    _scipy_ndimage,
    SKLEARN_AVAILABLE, _sklearn_pairwise_distances,
    tqdm,
    torch, USE_GPU, GPU_DEVICE,
    _MplFigure, _MplFigureCanvasAgg,
)

def _read_mrc_field(path: str) -> Tuple[np.ndarray, float, Tuple[float, float, float]]:
    """Read an MRC volume back into (data, voxel_size, origin), undoing the
    ZYX transpose applied on write so the array is XYZ again (matches nbins
    from compute_negative_space()). Companion reader to _write_mrc_field()."""
    if not MRCFILE_AVAILABLE:
        raise ImportError("mrcfile required — install: pip install mrcfile")
    with mrcfile.open(path, permissive=True) as mrc:
        data = np.asarray(mrc.data, dtype=np.float32).T.copy()
        voxel_size = float(mrc.voxel_size.x)
        origin = (float(mrc.header.origin.x),
                  float(mrc.header.origin.y),
                  float(mrc.header.origin.z))
    return data, voxel_size, origin


def _write_mrc_field(field: np.ndarray, xmin, dx: float, fname: str,
                     gaussian_sigma: float = None) -> None:
    """Write a 3D scalar field as an MRC volume file for PyMOL visualization.

    Parameters
    ----------
    field : np.ndarray, shape (nx, ny, nz)
        3D array of scalar values.
    xmin : array-like, shape (3,)
        Physical coordinates (Å) of the grid origin.
    dx : float
        Voxel edge length in Å.
    fname : str
        Output path (.mrc).
    gaussian_sigma : float, optional
        Gaussian smoothing in voxels applied before writing.
        Typical range: 0.5 (subtle) to 2.0 (heavy). None = no smoothing.
    """
    if not MRCFILE_AVAILABLE:
        raise ImportError("mrcfile required — install: pip install mrcfile")
    data = np.asarray(field, dtype=np.float32)
    if gaussian_sigma is not None and gaussian_sigma > 0:
        if _scipy_ndimage is not None:
            data = _scipy_ndimage.gaussian_filter(
                data, sigma=gaussian_sigma).astype(np.float32)
        else:
            print(f"Warning: scipy not available — Gaussian smoothing skipped for {fname}")
    with mrcfile.new(fname, overwrite=True) as mrc:
        mrc.set_data(data.T)   # MRC convention: ZYX order
        mrc.voxel_size = dx
        mrc._set_nstart(0, 0, 0)
        mrc.header.origin.flags.writeable = True
        mrc.header.origin.x = float(xmin[0])
        mrc.header.origin.y = float(xmin[1])
        mrc.header.origin.z = float(xmin[2])
        mrc.update_header_from_data()
        mrc.update_header_stats()


def _jet_hex(t: float) -> str:
    """Map a normalised value in [0, 1] to a Jet colormap hex string.

    Jet anchors (darkblue → blue → cyan → yellow → red):
        0.000 → #000080   0.125 → #0000ff   0.375 → #00ffff
        0.625 → #ffff00   0.875 → #ff0000   1.000 → #800000
    Returns a 6-character lowercase hex string without the leading '#'.
    """
    anchors = [
        (0.000, 0.0, 0.0, 0.5),
        (0.125, 0.0, 0.0, 1.0),
        (0.375, 0.0, 1.0, 1.0),
        (0.625, 1.0, 1.0, 0.0),
        (0.875, 1.0, 0.0, 0.0),
        (1.000, 0.5, 0.0, 0.0),
    ]
    v = float(np.clip(t, 0.0, 1.0))
    for i in range(len(anchors) - 1):
        t0, r0, g0, b0 = anchors[i]
        t1, r1, g1, b1 = anchors[i + 1]
        if v <= t1 + 1e-9:
            f = (v - t0) / (t1 - t0) if (t1 - t0) > 0 else 0.0
            r = int((r0 + f * (r1 - r0)) * 255)
            g = int((g0 + f * (g1 - g0)) * 255)
            b = int((b0 + f * (b1 - b0)) * 255)
            return f"{r:02x}{g:02x}{b:02x}"
    r, g, b = (int(v * 255) for v in anchors[-1][1:])
    return f"{r:02x}{g:02x}{b:02x}"


# ── MRC diff maps (contact vs non-contact) ───────────────────────────────────
# Post-hoc analysis of the contacts/non-contacts occupancy pairs written by
# save_mrc_files() — cancels rotational/rotameric noise shared between the
# two (a residue that librates/flips locally can cross the contact-geometry
# cutoff frame-to-frame without actually leaving the site). Only reads/writes
# MRC files already on disk from a prior save_mrc_files() call — no
# dependency on a live PharmacophoreTrajectory instance, so these stay
# module-level functions rather than VoxelMapsMixin methods. DIFF_CATEGORIES/
# DIFF_MAP_SETS live in _constants.py, re-exported from the package top level.

def diff_category(map_dir: str, category: str,
                  gaussian_sigma: Optional[float] = None,
                  grid_tol: float = 1e-3,
                  score_percentile_tiers: Optional[List[int]] = None) -> Optional[dict]:
    """Compute both the raw and ratio-normalized contacts/non-contacts diff
    for one category in one map-set directory. Returns a dict with both
    written paths plus the in-memory arrays (for plot_diff_histogram()/
    plot_diff_magnitude_scatter()), or None if either source file is missing
    (category not computed for that run).

    Two diff quantities, both computed here since they're cheap once
    contact/non_contact are loaded (no extra I/O):

    - 'diff' (raw, unclipped, range [-1, 1]): non_contact - contact. Only
      meaningful when the two source maps have comparable overall magnitude
      to begin with — see 'ratio' below for why that's often not the case.
    - 'ratio' (range [-1, 1], every signal voxel): (non_contact - contact) /
      (non_contact + contact). Per-voxel normalized asymmetry, independent of
      how much total occupancy that voxel saw. +1 = voxel only ever touched
      in non-contact state, -1 = only ever contact, 0 = perfectly balanced.

    Why both exist: plotting raw diff against total occupancy
    (contact+non_contact) shows every point confined to the wedge
    |diff| <= magnitude (algebraic necessity, not a trend) — points sitting
    exactly on that wedge's edge have contact=0 (or non_contact=0) exactly,
    i.e. that voxel was NEVER touched in the other state at all. When one
    category's overall base rate is much rarer than the other across the
    whole trajectory, most signal voxels pile up on that edge and the raw
    diff reads as "non-contact-dominant everywhere," which conflates a
    genuine trajectory-wide base-rate imbalance with the local
    rotational/rotameric-noise overlap this technique was actually built to
    cancel. 'ratio' divides that imbalance out per voxel, so it separates
    "barely sampled, noisy either way" from "genuinely balanced between both
    states" independent of overall magnitude."""
    contact_path    = os.path.join(map_dir, f'{category}_contacts.mrc')
    non_contact_path = os.path.join(map_dir, f'{category}_non_contacts.mrc')

    if not (os.path.exists(contact_path) and os.path.exists(non_contact_path)):
        print(f"  Skipping {category} (contacts/non_contacts MRC not both present)")
        return None

    contact, con_voxel, con_origin       = _read_mrc_field(contact_path)
    non_contact, ncon_voxel, ncon_origin = _read_mrc_field(non_contact_path)

    if contact.shape != non_contact.shape:
        raise ValueError(
            f"{category}: grid shape mismatch {contact.shape} vs {non_contact.shape} — "
            f"contacts/non_contacts MRCs must come from the same compute_pharmacophore_maps() run"
        )
    if abs(con_voxel - ncon_voxel) > grid_tol:
        raise ValueError(f"{category}: voxel_size mismatch {con_voxel} vs {ncon_voxel}")
    if any(abs(a - b) > grid_tol for a, b in zip(con_origin, ncon_origin)):
        raise ValueError(f"{category}: grid origin mismatch {con_origin} vs {ncon_origin}")

    diff = non_contact - contact  # signed, unclipped: [-1, 1]

    magnitude = contact + non_contact
    with np.errstate(divide='ignore', invalid='ignore'):
        ratio = np.where(magnitude > 0, diff / magnitude, 0.0).astype(np.float32)

    out_path       = os.path.join(map_dir, f'{category}_diff.mrc')
    ratio_out_path = os.path.join(map_dir, f'{category}_diff_ratio.mrc')
    _write_mrc_field(diff, con_origin, con_voxel, out_path, gaussian_sigma)
    _write_mrc_field(ratio, con_origin, con_voxel, ratio_out_path, gaussian_sigma)

    # ── Sign-split, non-negative ratio maps ─────────────────────────────────
    # Same ratio values, split into two strictly->=0 fields instead of one
    # signed one — lets each side be isomeshed in PyMOL independently (sharp
    # polygon surface at a fixed level, vs. the inherently soft/diffuse
    # `volume` density-cloud representation a single signed map is stuck
    # with), and at its own level: contact-dominant and non-contact-dominant
    # values aren't guaranteed to sit at comparable magnitudes, so a single
    # shared +/-level on one signed map is often a compromise for one side or
    # the other. Elementwise np.clip, not boolean masking — voxels with the
    # "wrong" sign are already exactly 0.0 in the other map, not merely
    # absent, so both stay on the same grid/shape as everything else.
    ratio_noncontact_path = os.path.join(map_dir, f'{category}_ratio_noncontact_dominant.mrc')
    ratio_contact_path    = os.path.join(map_dir, f'{category}_ratio_contact_dominant.mrc')
    ratio_noncontact_dominant = np.clip(ratio, 0, None)
    ratio_contact_dominant    = np.clip(-ratio, 0, None)
    _write_mrc_field(ratio_noncontact_dominant, con_origin, con_voxel,
                     ratio_noncontact_path, gaussian_sigma)
    _write_mrc_field(ratio_contact_dominant, con_origin, con_voxel,
                     ratio_contact_path, gaussian_sigma)

    n_pos = int(np.count_nonzero(diff > 0))
    n_neg = int(np.count_nonzero(diff < 0))
    line1 = (f"{category}: diff range [{diff.min():+.3f}, {diff.max():+.3f}] — "
            f"{n_pos:,} non-contact-dominant voxels, {n_neg:,} contact-dominant voxels")
    line2 = f"saved {out_path}"
    line2b = f"saved {ratio_out_path}"
    line2c = f"saved {ratio_noncontact_path}"
    line2d = f"saved {ratio_contact_path}"
    print(f"  {line1}")
    print(f"    {line2}")
    print(f"    {line2b}")
    print(f"    {line2c}")
    print(f"    {line2d}")

    # ── Empty-map check ──────────────────────────────────────────────────────
    # A category where n_pos or n_neg is 0 has an entirely-zero split map on
    # that side (e.g. hbond_donors/hbond_acceptors: non-contact's atom pool is
    # so much broader than contact's that contact never locally wins anywhere
    # in some subsets). Flagged here so you know at a glance whether it's
    # worth adding that side to the PyMOL script at all, without having to
    # load it and check manually.
    tier_lines = []
    empty_lines = []
    if n_neg == 0:
        empty_lines.append(f"EMPTY: {category}_ratio_contact_dominant — 0 contact-dominant voxels, "
                           f"skip in PyMOL")
    if n_pos == 0:
        empty_lines.append(f"EMPTY: {category}_ratio_noncontact_dominant — 0 non-contact-dominant "
                           f"voxels, skip in PyMOL")
    for l in empty_lines:
        print(f"    ⚠ {l}")

    # ── Percentile-tiered variants of the split maps ────────────────────────
    # Same top-N%-of-nonzero-voxels convention as save_mrc_files() (growth
    # features / pharmacophore occupancy maps): only meaningful on a
    # non-negative field, which is exactly why the sign-split above exists —
    # raw diff/ratio are signed, so this is applied to the two split maps,
    # not to diff/ratio themselves.
    if score_percentile_tiers is None:
        score_percentile_tiers = [1, 5, 10, 20]

    def _write_tiers(field, base_path, label):
        paths = {}
        nonzero = field[field > 0]
        if len(nonzero) == 0:
            tier_lines.append(f"(skipping tiers for {label}: no nonzero voxels)")
            return paths
        for tier in score_percentile_tiers:
            threshold  = float(np.percentile(nonzero, 100 - tier))
            filtered   = np.where(field >= threshold, field, 0.0).astype(np.float32)
            tier_path  = base_path[:-4] + f'_top{tier}pct.mrc'  # strip '.mrc', re-append
            _write_mrc_field(filtered, con_origin, con_voxel, tier_path, gaussian_sigma)
            paths[tier] = tier_path
            n_sur = int(np.count_nonzero(filtered))
            tier_lines.append(f"saved {tier_path} ({n_sur:,}/{len(nonzero):,} voxels, "
                              f"threshold={threshold:.4f})")
        return paths

    ratio_noncontact_tier_paths = _write_tiers(
        ratio_noncontact_dominant, ratio_noncontact_path, f'{category}_ratio_noncontact_dominant')
    ratio_contact_tier_paths = _write_tiers(
        ratio_contact_dominant, ratio_contact_path, f'{category}_ratio_contact_dominant')
    for l in tier_lines:
        print(f"    {l}")

    # ── Noise-floor diagnostic ──────────────────────────────────────────────
    # Restricted to voxels with actual occupancy signal (contact>0 or
    # non_contact>0), NOT the full grid — most of the grid lies outside the
    # analysis shell and is identically 0.0 in both source maps, which would
    # swamp any histogram/percentile with trivial "never scored" zeros rather
    # than the "scored, but cancels out" voxels this diagnostic is meant to
    # characterize. Use these percentiles to pick a min_abs_diff cutoff for a
    # display dead-zone (PyMOL ramp) or a future thresholded export, instead
    # of eyeballing one.
    signal_mask = (contact > 0) | (non_contact > 0)
    n_signal = int(np.count_nonzero(signal_mask))
    stats = {'n_pos': n_pos, 'n_neg': n_neg, 'n_signal': n_signal,
             'diff_min': float(diff.min()), 'diff_max': float(diff.max()),
             'contact_dominant_empty': (n_neg == 0), 'noncontact_dominant_empty': (n_pos == 0)}
    if n_signal > 0:
        abs_diff_signal = np.abs(diff[signal_mask])
        percentiles = [50, 75, 90, 95, 99]
        pvals = np.percentile(abs_diff_signal, percentiles)
        pct_str = "  ".join(f"p{p}={v:.4f}" for p, v in zip(percentiles, pvals))
        stats['abs_diff_mean'] = float(abs_diff_signal.mean())
        stats['abs_diff_std']  = float(abs_diff_signal.std())
        stats['abs_diff_percentiles'] = dict(zip(percentiles, (float(v) for v in pvals)))
        line3 = (f"|diff| over {n_signal:,} signal voxels: "
                f"mean={abs_diff_signal.mean():.4f}  std={abs_diff_signal.std():.4f}  {pct_str}")

        abs_ratio_signal = np.abs(ratio[signal_mask])
        rvals = np.percentile(abs_ratio_signal, percentiles)
        rpct_str = "  ".join(f"p{p}={v:.4f}" for p, v in zip(percentiles, rvals))
        stats['abs_ratio_mean'] = float(abs_ratio_signal.mean())
        stats['abs_ratio_std']  = float(abs_ratio_signal.std())
        stats['abs_ratio_percentiles'] = dict(zip(percentiles, (float(v) for v in rvals)))
        line4 = (f"|ratio| over {n_signal:,} signal voxels: "
                f"mean={abs_ratio_signal.mean():.4f}  std={abs_ratio_signal.std():.4f}  {rpct_str}")
    else:
        line3 = "(no signal voxels — contact and non_contact both all-zero)"
        line4 = None
    print(f"    {line3}")
    if line4 is not None:
        print(f"    {line4}")

    summary_text = f"  {line1}\n    {line2}\n    {line2b}\n    {line2c}\n    {line2d}\n    {line3}"
    if line4 is not None:
        summary_text += f"\n    {line4}"
    for l in empty_lines:
        summary_text += f"\n    ⚠ {l}"
    for l in tier_lines:
        summary_text += f"\n    {l}"

    return {'path': out_path, 'ratio_path': ratio_out_path,
            'ratio_noncontact_path': ratio_noncontact_path, 'ratio_contact_path': ratio_contact_path,
            'ratio_noncontact_tier_paths': ratio_noncontact_tier_paths,
            'ratio_contact_tier_paths': ratio_contact_tier_paths,
            'diff': diff, 'ratio': ratio, 'contact': contact, 'non_contact': non_contact,
            'ratio_noncontact_dominant': ratio_noncontact_dominant,
            'ratio_contact_dominant': ratio_contact_dominant,
            'signal_mask': signal_mask, 'n_signal': n_signal, 'stats': stats,
            'summary_text': summary_text}


def plot_diff_histogram(diff: np.ndarray, signal_mask: np.ndarray, category: str,
                        title: str = '', nbins: int = 60,
                        xlabel: str = 'diff = non_contact − contact') -> '_MplFigure':
    """Histogram of a signed per-voxel quantity (diff_category()'s 'diff' or
    'ratio') restricted to signal voxels (contact>0 or non_contact>0) — the
    same population diff_category() reports percentiles for, so a shape seen
    here matches the numbers already printed. Bars are colored by sign
    (contact-dominant vs non-contact-dominant) rather than a single hue,
    since both quantities are signed/diverging with a meaningful zero — same
    red/blue convention as viewing the map in PyMOL with the 'esp' ramp.
    Dotted lines mark the +/-90th/95th/99th percentile of the absolute value
    (same numbers as the printed diagnostic) as a visual guide for picking a
    noise-floor cutoff. Pass ratio_category's array with
    xlabel='ratio = (non_contact − contact) / (non_contact + contact)' to
    reuse this for the ratio instead of raw diff.

    matplotlib rather than Plotly — built via the plain Figure/Axes OO API
    (not pyplot.subplots()) so it never touches pyplot's global figure-stack
    state; display with show_figure() in a notebook.

    Returns an empty, annotated figure rather than raising if there are no
    signal voxels."""
    values = diff[signal_mask]

    fig = _MplFigure(figsize=(7, 4.5))
    ax  = fig.add_subplot(111)

    if len(values) == 0:
        ax.text(0.5, 0.5, "no signal voxels", ha='center', va='center', transform=ax.transAxes)
        ax.set_title(title or f'{category} distribution')
        fig.tight_layout()
        return fig

    neg = values[values < 0]
    pos = values[values > 0]
    bin_edges = np.histogram_bin_edges(values, bins=nbins)

    ax.hist(neg, bins=bin_edges, color='crimson', alpha=0.75, label='contact-dominant (<0)')
    ax.hist(pos, bins=bin_edges, color='royalblue', alpha=0.75, label='non-contact-dominant (>0)')
    ax.axvline(0, color='gray', linestyle='--', linewidth=1)

    abs_values = np.abs(values)
    for p, alpha in zip([90, 95, 99], [0.5, 0.35, 0.2]):
        edge = float(np.percentile(abs_values, p))
        for sign in (1, -1):
            ax.axvline(sign * edge, color='gray', linestyle=':', alpha=alpha, linewidth=1)
        ax.text(edge, 1.01, f'p{p}', transform=ax.get_xaxis_transform(),
               ha='center', va='bottom', fontsize=8, color='gray')

    ax.set_title(title or f'{category} distribution ({len(values):,} signal voxels)')
    ax.set_xlabel(xlabel)
    ax.set_ylabel('voxel count')
    ax.legend(fontsize=8)
    fig.tight_layout()
    return fig


def plot_diff_magnitude_scatter(diff: np.ndarray, contact: np.ndarray, non_contact: np.ndarray,
                                signal_mask: np.ndarray, category: str,
                                title: str = '',
                                ylabel: str = 'diff = non_contact − contact') -> '_MplFigure':
    """Per-voxel scatter of a signed quantity (diff_category()'s 'diff' or
    'ratio', pick via which array you pass + matching ylabel) vs total
    occupancy magnitude (contact + non_contact), restricted to signal voxels.

    With raw diff: |diff| alone can't distinguish two very different
    situations that both produce a small value — (a) contact and non_contact
    both substantial and close (genuine rotational/rotameric-noise
    cancellation — the case this whole diff technique targets) vs (b) both
    tiny and coincidentally close (background voxels barely sampled at all,
    not "cancelled"). Note the whole point cloud is mathematically confined
    to the wedge |diff| <= magnitude (diff = non_contact-contact, magnitude =
    non_contact+contact, both built from the same two non-negative numbers)
    — points sitting exactly on that wedge's edge have contact=0 (or
    non_contact=0) exactly, i.e. never touched in the other state at all;
    that edge being densely populated reflects a category-wide base-rate
    imbalance (see diff_category()'s docstring), not evidence against
    cancellation elsewhere in the cloud.

    With ratio instead: the wedge constraint doesn't apply (ratio is already
    bounded to [-1,1] independent of magnitude) — this view instead shows
    whether ratio is more volatile at low magnitude (few frames ever touched
    that voxel, so its ratio is small-sample noise) and settles toward a
    stable value as magnitude grows, the usual "more data, less noise"
    pattern for any sample proportion.

    Same red/blue sign convention as plot_diff_histogram().

    matplotlib rather than Plotly — points are rasterized (small,
    semi-transparent) since signal populations here run into the hundreds of
    thousands of voxels; built via the plain Figure/Axes OO API, display with
    show_figure() in a notebook.

    Returns an empty, annotated figure rather than raising if there are no
    signal voxels."""
    d = diff[signal_mask]

    fig = _MplFigure(figsize=(7, 4.5))
    ax  = fig.add_subplot(111)

    if len(d) == 0:
        ax.text(0.5, 0.5, "no signal voxels", ha='center', va='center', transform=ax.transAxes)
        ax.set_title(title or f'{category} vs magnitude')
        fig.tight_layout()
        return fig

    magnitude = (contact + non_contact)[signal_mask]
    neg_mask  = d < 0
    pos_mask  = d > 0

    ax.scatter(magnitude[neg_mask], d[neg_mask], s=3, alpha=0.35, color='crimson',
              label='contact-dominant (<0)', rasterized=True, linewidths=0)
    ax.scatter(magnitude[pos_mask], d[pos_mask], s=3, alpha=0.35, color='royalblue',
              label='non-contact-dominant (>0)', rasterized=True, linewidths=0)
    ax.axhline(0, color='gray', linestyle='--', linewidth=1)

    ax.set_title(title or f'{category} vs total occupancy ({len(d):,} signal voxels)')
    ax.set_xlabel('total occupancy = contact + non_contact')
    ax.set_ylabel(ylabel)
    ax.legend(fontsize=8, markerscale=3)
    fig.tight_layout()
    return fig


def show_figure(fig: '_MplFigure', dpi: int = 100) -> None:
    """Render a Figure to a PNG buffer via the Agg canvas and display it
    inline with IPython.display.Image, bypassing IPython's matplotlib-inline
    backend/formatter detection entirely. plot_diff_histogram()/
    plot_diff_magnitude_scatter() build figures via the plain Figure/Axes API
    (never import pyplot), so the usual auto-detection that activates the
    inline backend on `import matplotlib.pyplot` never fires — `display(fig)`
    then falls back to Figure's plain text repr instead of rendering an
    image. Rendering to PNG bytes ourselves sidesteps that: Agg needs no
    display server/GUI/WebGL, and IPython.display.Image's formatter is core
    IPython, not backend-dependent, so this works the same regardless of
    what (if anything) configured matplotlib's global backend."""
    import io as _io
    from IPython.display import Image, display as _display
    canvas = _MplFigureCanvasAgg(fig)
    buf = _io.BytesIO()
    canvas.print_figure(buf, dpi=dpi, format='png')
    _display(Image(data=buf.getvalue()))


class VoxelMapsMixin:

    def compute_negative_space(self,
                               shell_inner_radius: float = 1.5,
                               shell_outer_radius: float = 5.0,
                               dx: float = 0.5,
                               protein_vdw_radius: float = 1.5,
                               min_free_fraction: float = 0.7):
        """Compute voxel-based protein occupancy and space classification around the ligand.

        Builds a 3D grid over the ligand + surrounding region, calculates the
        fraction of trajectory frames each voxel is occupied by protein, and
        classifies every shell voxel into one of four categories.

        GPU-accelerated when PyTorch + CUDA are available; falls back to NumPy.

        Parameters
        ----------
        shell_inner_radius : float
            Inner boundary of the analysis shell (Å from ligand surface). Default 1.5 Å.
        shell_outer_radius : float
            Outer boundary of the analysis shell (Å from ligand). Default 5.0 Å.
        dx : float
            Voxel edge length in Å. Default 0.5 Å.
        protein_vdw_radius : float
            Exclusion radius used to decide whether a protein atom occupies a voxel (Å).
            Default 1.5 Å.
        min_free_fraction : float
            Threshold separating growth space from contested space (0–1).
            Default 0.7: voxels free ≥ 70% of frames → growth space (protein occ < 30%).
            Set to 0.0 to treat the entire shell as growth space.

        Returns
        -------
        dict with keys:
          growth_space_mask    : (nx,ny,nz) bool  — protein occ < 30% (free ≥ min_free_fraction)
          contested_space_mask : (nx,ny,nz) bool  — protein occ ≥ 30% (free <  min_free_fraction)
          occupied_space_mask  : (nx,ny,nz) bool  — protein occ > 70%  (diagnostic, IDP-rarely-useful)
          full_shell_mask      : (nx,ny,nz) bool  — all shell voxels, no threshold
          free_fraction        : (nx,ny,nz) float — fraction of frames voxel is unoccupied
          protein_occupancy    : (nx,ny,nz) float — fraction of frames protein present
          min_dist_to_ligand   : (nx,ny,nz) float — Å to nearest ligand atom ever
          grid_info            : dict — xmin, xmax, nbins, dx, shell radii
          volumes              : dict — volumes in Å³ for each region
        Stored on self.negative_space_data.
        """
        if not MDTRAJ_AVAILABLE:
            raise ImportError("MDTraj required — install via conda-forge: mdtraj")
        if self.prot_lig_traj is None:
            raise RuntimeError("Call load() before compute_negative_space()")

        trajectory    = self.prot_lig_traj
        ligand_atoms  = self._ligand_sel_idx
        protein_atoms = self._protein_sel_idx

        print(f"Shell: {shell_inner_radius}–{shell_outer_radius} Å | "
              f"voxel {dx} Å | excl. radius {protein_vdw_radius} Å | "
              f"free threshold {min_free_fraction*100:.0f}%")

        # ── Step 1: Grid setup ────────────────────────────────────────────────
        # Positions in Å (MDTraj stores nm)
        # Shape: (n_frames, n_atoms, 3)
        # Converts trajectory coordinates from nanometers to Angstroms (1 nm = 10 Å)
        ligand_pos  = trajectory.xyz[:, ligand_atoms,  :] * 10.0
        protein_pos = trajectory.xyz[:, protein_atoms, :] * 10.0

        # Define bounding box for grid (around ligand + shell)
        # Flatten all ligand atom positions across all frames into a 2D array
        # xyz coordinates of all ligand atoms across all frames
        # Shape: (n_frames * n_ligand_atoms, 3)
        # This combines all frames and atoms into one list of XYZ coordinates

            #  INPUT  ligand_pos  ── shape: (n_frames, n_ligand_atoms, 3)
        #
        #  ┌─ frame 0 ──────────────────────┐
        #  │  atom₀  │  x  │  y  │  z  │   │
        #  │  atom₁  │  x  │  y  │  z  │   │
        #  │   ...   │  .  │  .  │  .  │   │
        #  └─────────────────────────────── ┘
        #  ┌─ frame 1 ──────────────────────┐
        #  │  atom₀  │  x  │  y  │  z  │   │
        #  │  atom₁  │  x  │  y  │  z  │   │
        #  │   ...   │  .  │  .  │  .  │   │
        #  └────────────────────────────────┘
        #        ⋮
        #  ┌─ frame N ──────────────────────┐
        #  │  atom₀  │  x  │  y  │  z  │   │
        #  │   ...   │  .  │  .  │  .  │   │
        #  └────────────────────────────────┘
        #
        #                 │
        #       .reshape(-1, 3)       (-1 = n_frames × n_ligand_atoms)
        #                 │
        #                 ▼
        #
        #  OUTPUT  all_ligand_pos  ── shape: (n_frames × n_ligand_atoms, 3)
        #
        #  ┌─────────────────────────────────┐
        #  │  atom₀  │  x  │  y  │  z  │  ← frame 0
        #  │  atom₁  │  x  │  y  │  z  │
        #  │   ...   │  .  │  .  │  .  │
        #  ├─────────────────────────────────┤
        #  │  atom₀  │  x  │  y  │  z  │  ← frame 1
        #  │  atom₁  │  x  │  y  │  z  │
        #  │   ...   │  .  │  .  │  .  │
        #  ├─────────────────────────────────┤
        #  │   ...   │  .  │  .  │  .  │  ← frame N
        #  └─────────────────────────────────┘
        #
        #  → min/max over axis=0 gives global bounding box
        #    across ALL atoms and ALL frames in one step
        all_ligand_pos = ligand_pos.reshape(-1, 3)
               
        # Calculate grid extents - these define the 3D box containing everything
        # Find minimum X, Y, Z coordinates across all ligand atom positions
        # Then subtract the shell radii + 2Å buffer to create padding
        # Shape: (3,) - one value for X, one for Y, one for Z minimum
        # Result: e.g., [-15.2, -8.5, -22.3]

        #  all_ligand_pos  ── shape: (n_frames × n_ligand_atoms, 3)
        #
        #         col→     X        Y        Z
        #               ┌────────┬────────┬────────┐
        #  row 0        │ -12.1  │  -6.3  │ -19.8  │
        #  row 1        │  -8.4  │  -5.1  │ -21.0  │
        #  row 2        │ -10.7  │  -7.9  │ -18.5  │
        #   ⋮          │   ⋮    │   ⋮   │   ⋮   │
        #  row N        │  -9.2  │  -6.8  │ -20.1  │
        #               └────────┴────────┴────────┘
        #                    │         │        │
        #              min() ↓   min() ↓  min() ↓     .min(axis=0)  →  collapse rows
        #               ┌────────┬────────┬────────┐
        #               │ -12.1  │  -7.9  │ -21.0  │  shape: (3,)
        #               └────────┴────────┴────────┘
        #                    │         │        │
        #          - 5.0 Å   ↓  - 5.0  ↓  - 5.0 ↓    shell_outer_radius = 5.0
        #          - 2.0 Å   ↓  - 2.0  ↓  - 2.0 ↓    buffer
        #               ┌────────┬────────┬────────┐
        #         xmin  │ -19.1  │ -14.9  │ -28.0  │  shape: (3,)
        #               └────────┴────────┴────────┘
        #
        #  → defines the lower-left-front corner of the 3D voxel grid

            #   Y
        #   ▲
        #   │                                                          
        #   │   xmin                                         xmax     
        #   │    ├──────────────────────────────────────────────┤     
        #   │    │◄─ 2Å ─►◄───── shell_outer_radius ─────►│    │     
        #   │    │         │                               │    │     
        #   │    │         │    · · ligand atoms · ·       │    │     
        #   │    │         │  ·   ╔═══════════╗   ·        │    │     
        #   │    │         │ ·    ║  ·  ·  ·  ║    ·       │    │     
        #   │    │         │ ·    ║ · ligand· ║    ·       │    │     
        #   │    │         │ ·    ║  ·  ·  ·  ║    ·       │    │     
        #   │    │         │  ·   ╚═══════════╝   ·        │    │     
        #   │    │         │    · · · · · · · ·             │    │     
        #   │    │         │                               │    │     
        #   │    │         │◄── growth space shell ────────►│    │
        #   │    │◄────────── voxel grid bounding box ─────────►│     
        #   │    │                                              │     
        #   └────┴──────────────────────────────────────────────────► X
        #
        #   ╔═══╗  ligand heavy atoms (min/max define raw extent)
        #   · · ·  shell region  (shell_outer_radius from any ligand atom)
        #   │   │  2 Å safety buffer  (ensures no voxel falls outside grid)
        #
        #   xmin[X] = min(all atom X coords)  - shell_outer_radius  - 2.0
        #   xmin[Y] = min(all atom Y coords)  - shell_outer_radius  - 2.0
        #   xmin[Z] = min(all atom Z coords)  - shell_outer_radius  - 2.0
        xmin = all_ligand_pos.min(axis=0) - shell_outer_radius - 2.0
        
        # Find maximum X, Y, Z coordinates across all ligand atom positions  
        # Then add the shell radii + 2Å buffer to create padding
        # Shape: (3,) - one value for X, one for Y, one for Z maximum
        # Result: e.g., [18.7, 12.3, 25.1]
        xmax = all_ligand_pos.max(axis=0) + shell_outer_radius + 2.0
        
        # Determine number of voxels in each dimension
        # nbins = ceil((xmax - xmin) / dx)
        # Example: if X-range = 34 Å and dx = 0.5 Å, nbins[0] = 68
        nbins = np.ceil((xmax - xmin) / dx).astype(int)

        print(f"Grid: {nbins}  ({np.prod(nbins):,} voxels)")

        # Create coordinate arrays for each dimension
        # x, y, z are 1D arrays of voxel center coordinates
        # Example for X: [-15.2, -14.7, -14.2, ..., 18.2, 18.7]
        x, y, z = (np.arange(nbins[i]) * dx + xmin[i] for i in range(3))
        
        # Create 3D meshgrid of all voxel positions
        # xx, yy, zz each have shape (nbins[0], nbins[1], nbins[2])
        # Each element is the coordinate value at that grid position
        xx, yy, zz    = np.meshgrid(x, y, z, indexing='ij')
        
        # Stack the three coordinate grids into one 4D array
        # voxel_coords has shape (nbins[0], nbins[1], nbins[2], 3)
        # Each element is [x_coord, y_coord, z_coord] for that voxel center
        voxel_coords  = np.stack([xx, yy, zz], axis=-1)
        
        # Reshape voxel grid for distance calculation
        # From 4D array (nbins[0], nbins[1], nbins[2], 3)
        # To 2D array (n_voxels, 3) where n_voxels = product of nbins
        voxel_flat    = voxel_coords.reshape(-1, 3)

        # ── Step 2: Minimum ligand distance per voxel ────────────────────────
        print("Step 1/3: ligand distance map …")

        # Initialize distance array with infinity
        # Will be progressively updated with actual distances
        # Shape: (nbins[0], nbins[1], nbins[2])
        #  min_dist_to_ligand  ── shape: (nbins[0], nbins[1], nbins[2])
        #
        #              Z
        #             ╱
        #            ╱
        #    ┌──────┬──────┬──────┐
        #   ╱  ∞   ╱  ∞   ╱  ∞  ╱│
        #  ┌──────┬──────┬──────┐ │  Y
        #  │  ∞   │  ∞   │  ∞   │ ┤ ──►
        #  │      │      │      │╱│
        #  ├──────┼──────┼──────┤ │
        #  │  ∞   │  ∞   │  ∞   │ ┤
        #  │      │      │      │╱│
        #  ├──────┼──────┼──────┤ │
        #  │  ∞   │  ∞   │  ∞   │ ┘
        #  └──────┴──────┴──────┘
        #  │
        #  ▼ X
        #
        #  Every voxel starts at ∞.
        #  As we loop over frames, each voxel is updated with the distance
        #  to the nearest ligand atom found so far  →  running minimum:
        #
        #  frame 0 ──► min_dist = min( ∞,   d₀ )  =  d₀
        #  frame 1 ──► min_dist = min( d₀,  d₁ )  =  d₀  (if d₀ < d₁)
        #  frame 2 ──► min_dist = min( d₀,  d₂ )  =  d₂  (if d₂ < d₀)
        #    ⋮
        #  frame N ──► min_dist = closest the ligand ever came to this voxel
        min_dist_to_ligand = np.full(nbins, np.inf, dtype=np.float32)

        if USE_GPU:
            # ---- GPU-ACCELERATED PATH (PyTorch + CUDA) ----
            # Move voxel grid to GPU once (stays resident for all frames)
            voxel_flat_gpu = torch.tensor(voxel_flat, dtype=torch.float32, device=GPU_DEVICE)
            min_dist_gpu   = torch.full((len(voxel_flat),), float('inf'),
                                        dtype=torch.float32, device=GPU_DEVICE)
            
            # With ~50 ligand atoms, the full distance matrix fits in GPU memory
            # (1M voxels × 50 atoms × 4 bytes = ~200 MB)
            gpu_chunk = 500_000

            #  trajectory.xyz  ── shape: (n_frames, n_atoms, 3)  [CPU, NumPy]
            #
            #  ┌─ frame 0 ─┐  ┌─ frame 1 ─┐       ┌─ frame N ─┐
            #  │ all atoms │  │ all atoms │  · · · │ all atoms │
            #  └───────────┘  └───────────┘       └───────────┘
            #        │               │                   │
            #        │  tqdm loop ───┴───────────────────┘
            #        │  frame_idx = 0, 1, 2, ... N
            #        ▼
            #
            #  ligand_pos[frame_idx]  ── shape: (n_ligand_atoms, 3)  [CPU, NumPy]
            #
            #  ┌─────────┬──────┬──────┬──────┐
            #  │  atom₀  │  x   │  y   │  z   │
            #  │  atom₁  │  x   │  y   │  z   │
            #  │   ...   │  .   │  .   │  .   │
            #  │  atomₙ  │  x   │  y   │  z   │
            #  └─────────┴──────┴──────┴──────┘
            #        │
            #        │  torch.tensor(..., device=GPU_DEVICE)
            #        │  ← copies this slice from RAM to VRAM each frame
            #        ▼
            #
            #  frame_ligand_gpu  ── shape: (n_ligand_atoms, 3)  [GPU, torch.float32]
            #
            #  ┌─────────┬──────┬──────┬──────┐
            #  │  atom₀  │  x   │  y   │  z   │  ┐
            #  │  atom₁  │  x   │  y   │  z   │  │ VRAM
            #  │   ...   │  .   │  .   │  .   │  │
            #  │  atomₙ  │  x   │  y   │  z   │  ┘
            #  └─────────┴──────┴──────┴──────┘
            #
            #  NOTE: only one frame is resident on GPU at a time → low VRAM footprint.
            #        the voxel grid (voxel_flat_gpu) stays loaded across all frames.
            #
            for fi in tqdm(range(trajectory.n_frames)):
                frame_lig = torch.tensor(ligand_pos[fi], dtype=torch.float32, device=GPU_DEVICE)
                
                #  voxel_flat_gpu  ── shape: (n_voxels, 3)  [GPU]
                #
                #  ┌────────────────────────────────────────────────┐
                #  │ voxel₀  │ voxel₁  │ · · · │ voxel_M │ · · ·  │
                #  └────────────────────────────────────────────────┘
                #   └────────────────┘ └───────────────────────────┘
                #      chunk i=0              chunk i=1  · · ·
                #      size: gpu_chunk_size
                #           │
                #           ▼
                #  chunk  ── shape: (gpu_chunk_size, 3)
                #
                #  ┌──────┬───┬───┬───┐       frame_ligand_gpu  ── shape: (n_ligand_atoms, 3)
                #  │  v₀  │ x │ y │ z │
                #  │  v₁  │ x │ y │ z │       ┌──────┬───┬───┬───┐
                #  │  v₂  │ x │ y │ z │       │  a₀  │ x │ y │ z │
                #  │  ... │ . │ . │ . │       │  a₁  │ x │ y │ z │
                #  │  vₙ  │ x │ y │ z │       │  ... │ . │ . │ . │
                #  └──────┴───┴───┴───┘       └──────┴───┴───┴───┘
                #           │                          │
                #           └──────── cdist ───────────┘
                #                        │
                #                        ▼
                #  dists  ── shape: (gpu_chunk_size, n_ligand_atoms)
                #
                #            a₀      a₁      a₂    · · ·   aₙ
                #  v₀  ┌  [ 3.2  │  7.1  │  4.5  │ · · · │ 2.1 ]
                #  v₁  │  [ 5.8  │  2.3  │  8.0  │ · · · │ 6.4 ]
                #  v₂  │  [ 1.9  │  4.7  │  3.3  │ · · · │ 5.2 ]
                #  ... │  [  .   │   .   │   .   │       │  .  ]
                #  vₙ  └  [ 6.1  │  3.9  │  2.7  │ · · · │ 4.8 ]
                #                        │
                #              .min(dim=1).values   ← minimum over atoms (columns)
                #                        │
                #                        ▼
                #  min_dist_chunk  ── shape: (gpu_chunk_size,)
                #
                #  [ 2.1,  2.3,  1.9, · · · ]   ← closest ligand atom per voxel
                #                        │
                #              torch.minimum(current, new)   ← running min across frames
                #                        │
                #                        ▼
                #  min_dist_gpu[i:i+gpu_chunk_size]  updated in-place

                #  ════════════════════════════════════════════════════════════════
                #  GOAL: for every voxel in the grid, find the closest distance
                #        that ANY ligand atom ever reached across ALL frames.
                #  ════════════════════════════════════════════════════════════════
                #
                #  INPUT
                #  ─────
                #  voxel_flat_gpu  ── (n_voxels, 3)      fixed grid of 3D points [GPU]
                #  ligand_pos      ── (n_frames, n_ligand_atoms, 3)  trajectory   [CPU]
                #
                #  PROCESS  (two nested loops)
                #  ───────
                #  outer loop → one frame at a time  (upload ligand slice to GPU)
                #  inner loop → one chunk of voxels at a time  (fit in VRAM)
                #
                #  for each (frame, chunk):
                #    cdist  →  full (chunk_size × n_ligand_atoms) distance matrix
                #    min(dim=1)  →  closest atom per voxel  for this frame
                #    torch.minimum  →  update running minimum across all frames
                #
                #  OUTPUT
                #  ──────
                #  min_dist_gpu  ── (n_voxels,)  [GPU]
                #
                #  each element = the shortest distance ever recorded between
                #  that voxel and any ligand atom, over the entire trajectory.
                #
                #  Example:
                #  ┌──────────┬───────────────────────────────────────────────┐
                #  │ voxel 0  │  0.3 Å  → inside ligand body                 │
                #  │ voxel 1  │  1.8 Å  → just outside ligand surface        │
                #  │ voxel 2  │  3.4 Å  → in shell region  ← growth candidate│
                #  │ voxel 3  │  8.1 Å  → far from ligand, outside shell     │
                #  └──────────┴───────────────────────────────────────────────┘
                #
                #  This map is then thresholded in Step 3 to define the shell:
                #  shell_inner_radius ≤ min_dist ≤ shell_outer_radius
                # Transfer result back to CPU
                for i in range(0, len(voxel_flat_gpu), gpu_chunk):
                    chunk = voxel_flat_gpu[i:i+gpu_chunk]
                    # torch.cdist uses optimised GEMM-based algorithm on GPU
                    # Result shape: (chunk_size, n_ligand_atoms)
                    dists = torch.cdist(chunk, frame_lig)
                    min_dist_gpu[i:i+gpu_chunk] = torch.minimum(
                        min_dist_gpu[i:i+gpu_chunk], dists.min(dim=1).values)
            min_dist_to_ligand = min_dist_gpu.cpu().numpy().reshape(nbins)
            del voxel_flat_gpu, min_dist_gpu, frame_lig
            torch.cuda.empty_cache()
        else:
            chunk = 10_000
            for fi in tqdm(range(trajectory.n_frames)):
                fp = ligand_pos[fi]
                for i in range(0, len(voxel_flat), chunk):
                    ch = voxel_flat[i:i+chunk]
                    d  = np.linalg.norm(
                        ch[:, np.newaxis, :] - fp[np.newaxis, :, :], axis=2
                    ).min(axis=1)
                    sl = min_dist_to_ligand.ravel()[i:i+chunk]
                    min_dist_to_ligand.ravel()[i:i+chunk] = np.minimum(sl, d)

        # ── Step 3: Shell mask ────────────────────────────────────────────────
            
        # Define shell: voxels within the shell distance from ligand
        # in_shell = True only for voxels between inner & outer radius
        # Shape: (nbins[0], nbins[1], nbins[2]) of Boolean values
        # Example:
        #   - distance = 0.5 Å → in_shell = False (inside ligand)
        #   - distance = 2.0 Å → in_shell = True (in shell)
        #   - distance = 6.0 Å → in_shell = False (outside shell)
            #  CROSS-SECTION VIEW (any 2D slice through the ligand centre)
        #
        #  ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░
        #  ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░
        #  ░░░░░░░░░░   ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓   ░░░░░░░░░░░░░░░░
        #  ░░░░░░░  ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓  ░░░░░░░░░░░░░
        #  ░░░░░  ▓▓▓▓▓▓▓▓▓   ┌─────────┐   ▓▓▓▓▓▓▓  ░░░░░░░░░░░
        #  ░░░░  ▓▓▓▓▓▓▓▓   ╔═══════════╗   ▓▓▓▓▓▓▓▓  ░░░░░░░░░░
        #  ░░░░ ▓▓▓▓▓▓▓▓  ╔═╝           ╚═╗  ▓▓▓▓▓▓▓▓ ░░░░░░░░░░
        #  ░░░ ▓▓▓▓▓▓▓▓  ║   · ligand ·  ║  ▓▓▓▓▓▓▓▓ ░░░░░░░░░░
        #  ░░░ ▓▓▓▓▓▓▓▓  ║   · atoms  ·  ║  ▓▓▓▓▓▓▓▓ ░░░░░░░░░░
        #  ░░░ ▓▓▓▓▓▓▓▓  ╚═╗           ╔═╝  ▓▓▓▓▓▓▓▓ ░░░░░░░░░░
        #  ░░░░ ▓▓▓▓▓▓▓▓  ╚═══════════╝   ▓▓▓▓▓▓▓▓ ░░░░░░░░░░
        #  ░░░░  ▓▓▓▓▓▓▓▓   └─────────┘   ▓▓▓▓▓▓▓▓  ░░░░░░░░░░
        #  ░░░░░  ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓  ░░░░░░░░░░░
        #  ░░░░░░░  ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓  ░░░░░░░░░░░░░
        #  ░░░░░░░░░░░   ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓   ░░░░░░░░░░░░░░░░
        #  ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░
        #
        #  ╔═══╗  ligand body         dist < shell_inner_radius   in_shell = False
        #  ▓▓▓▓▓  shell region        shell_inner ≤ dist ≤ shell_outer  in_shell = True  ← growth candidates
        #  ░░░░░  outside shell       dist > shell_outer_radius   in_shell = False
        #
        #  ◄────────────────────────────────────────────────────────►
        #        │◄── inner (1.5Å) ──►│◄──── shell (3.5Å) ────►│
        #        0                   1.5Å                      5.0Å
        #
        in_shell = ((min_dist_to_ligand >= shell_inner_radius) &
                    (min_dist_to_ligand <= shell_outer_radius))
        print(f"Shell voxels: {in_shell.sum():,}")

        # ── Step 4: Protein occupancy within shell ────────────────────────────
        print("Step 2/3: protein occupancy …")
        
        # For each voxel in shell, count how many frames protein occupies it
        # Shape: (nbins[0], nbins[1], nbins[2]) of integer counts (0 to n_frames)
        protein_occupancy = np.zeros(nbins, dtype=np.float32)
        
        # Only check shell voxels (much faster - skip interior & exterior)
        #  voxel_coords  ── shape: (nbins[0], nbins[1], nbins[2], 3)   [ALL voxels]
        #  in_shell      ── shape: (nbins[0], nbins[1], nbins[2])      [Bool mask]
        #
        #   in_shell (2D slice shown):
        #
        #   ┌─────────────────────────────────────┐
        #   │  F  F  F  F  F  F  F  F  F  F   F  │
        #   │  F  F  F  T  T  T  T  T  F  F   F  │
        #   │  F  F  T  T  F  F  F  T  T  F   F  │
        #   │  F  T  T  F  F  F  F  F  T  T   F  │
        #   │  F  T  F  F  F  F  F  F  F  T   F  │  F = outside shell (skip)
        #   │  F  T  F  F  F ╔══╗ F  F  F  T  F  │  T = in shell     (keep)
        #   │  F  T  F  F  F ║  ║ F  F  F  T  F  │
        #   │  F  T  T  F  F ╚══╝ F  F  T  T  F  │
        #   │  F  F  T  T  F  F  F  T  T  F   F  │
        #   │  F  F  F  T  T  T  T  T  F  F   F  │
        #   │  F  F  F  F  F  F  F  F  F  F   F  │
        #   └─────────────────────────────────────┘
        #                    │
        #          boolean indexing / np.where
        #                    │
        #          ┌─────────┴──────────────────────┐
        #          ▼                                ▼
        #
        #  shell_coords                     shell_indices
        #  shape: (n_shell_voxels, 3)       shape: (n_shell_voxels,)
        #
        #  ┌──────┬───┬───┬───┐             ┌──────────────────────┐
        #  │  v₀  │ x │ y │ z │             │  42                  │  ← flat index in
        #  │  v₁  │ x │ y │ z │             │  43                  │    ravel()ed grid
        #  │  v₂  │ x │ y │ z │             │  57                  │
        #  │  ... │ . │ . │ . │             │  ...                 │
        #  │  vₙ  │ x │ y │ z │             │  N                   │
        #  └──────┴───┴───┴───┘             └──────────────────────┘
        #  3D coordinates of                position in the flat 1D
        #  each shell voxel                 array  →  used later to
        #  → input to cdist                 scatter results back into
        #                                   protein_occupancy grid
        #
        #  WHY: avoids computing protein distances for interior voxels
        #       (always blocked) and exterior voxels (always free) —
        #       only the shell ~10-20% of the grid actually matters.
        shell_coords  = voxel_coords[in_shell]
        shell_indices = np.where(in_shell.ravel())[0]

        if USE_GPU:
            shell_coords_gpu  = torch.tensor(shell_coords,  dtype=torch.float32, device=GPU_DEVICE)
            shell_indices_gpu = torch.tensor(shell_indices, dtype=torch.long,    device=GPU_DEVICE)
            occupancy_gpu     = torch.zeros(int(np.prod(nbins)), dtype=torch.float32, device=GPU_DEVICE)
            # Allocates a 1D accumulator array on GPU, length = total number of voxels.
            # Flat (1D) rather than 3D to allow direct indexed assignment later.
            # Initialized to zeros.

            # Chunk size depends on n_protein_atoms to avoid GPU OOM
            # Budget ~4 GB for the distance matrix: chunk × n_protein × 4 bytes
            n_prot    = len(protein_atoms)
            gpu_chunk = max(1_000, min(200_000, int(4e9 / (n_prot * 4))))
            for fi in tqdm(range(trajectory.n_frames)):
                # Uploads the protein atom coordinates for the current frame to GPU. Shape: (n_protein_atoms, 3)
                frame_prot = torch.tensor(protein_pos[fi], dtype=torch.float32, device=GPU_DEVICE)
                
                #  ════════════════════════════════════════════════════════════════
                #  GOAL: for every shell voxel, count in how many frames at least
                #        one protein atom is within protein_vdw_radius (1.5 Å).
                #  ════════════════════════════════════════════════════════════════
                #
                #  shell_coords_gpu  ── (n_shell_voxels, 3)  [GPU]   coordinates
                #  shell_indices_gpu ── (n_shell_voxels,)    [GPU]   flat positions in full grid
                #
                #  ┌──────────────────────────────────────────────────────────┐
                #  │ v₀ │ v₁ │ v₂ │ · · · │ vₘ │ vₘ₊₁ │ · · · │ vₙ │ · · · │  shell_coords_gpu
                #  └──────────────────────────────────────────────────────────┘
                #   └──────────────────┘ └────────────────────┘
                #        chunk i=0              chunk i=1  · · ·
                #              │
                #              ▼
                #  chunk  ── (gpu_chunk_size, 3)        idx ── (gpu_chunk_size,)  flat indices
                #
                #  ┌──────┬───┬───┬───┐                ┌────────────────────┐
                #  │  v₀  │ x │ y │ z │                │  42                │
                #  │  v₁  │ x │ y │ z │                │  43                │
                #  │  ... │ . │ . │ . │                │  ...               │
                #  └──────┴───┴───┴───┘                └────────────────────┘
                #              │
                #              │   torch.cdist(chunk, frame_protein_gpu)
                #              ▼
                #
                #  dists  ── shape: (gpu_chunk_size, n_protein_atoms)
                #
                #            p₀      p₁      p₂    · · ·   pₙ
                #  v₀  ┌  [ 0.9  │  4.2  │  6.1  │ · · · │ 3.3 ]
                #  v₁  │  [ 3.1  │  1.1  │  2.8  │ · · · │ 5.7 ]   each cell = distance
                #  v₂  │  [ 5.4  │  6.0  │  0.7  │ · · · │ 4.1 ]   voxel → protein atom
                #  ... │  [  .   │   .   │   .   │       │  .  ]
                #  vₙ  └  [ 2.2  │  7.3  │  5.5  │ · · · │ 1.4 ]
                #              │
                #              │  (dists < protein_vdw_radius).any(dim=1)
                #              │  collapse columns: is ANY atom closer than 1.5 Å?
                #              ▼
                #
                #  protein_nearby  ── shape: (gpu_chunk_size,)  Bool
                #
                #  v₀ │ v₁ │ v₂ │ v₃ │ · · ·
                #  ─────────────────────────
                #   T  │  T  │  T  │  F  │ · · ·    T = protein overlaps voxel (blocked)
                #                                    F = voxel is free this frame
                #              │
                #              │  occupancy_gpu[ idx[protein_nearby] ] += 1
                #              │  only blocked voxels get their counter incremented
                #              ▼
                #
                #  occupancy_gpu  ── shape: (n_voxels,)  flat accumulator  [GPU]
                #
                #  ┌────┬────┬────┬────┬────┬────┐
                #  │ .. │ 3  │ 5  │ 0  │ 2  │ .. │   after N frames:
                #  └────┴────┴────┴────┴────┴────┘   value = number of frames
                #              ▲                      protein occupied this voxel
                #    idx[protein_nearby]
                #    maps blocked voxels back to their
                #    position in the full flat grid
                for i in range(0, len(shell_coords_gpu), gpu_chunk):
                    chunk = shell_coords_gpu[i:i+gpu_chunk]
                    idx   = shell_indices_gpu[i:i+gpu_chunk]
                    
                    # torch.cdist computes pairwise distances on GPU
                    # Computes all pairwise Euclidean distances between chunk voxels and protein atoms on GPU.
                    # Result shape: (chunk_size, n_protein_atoms).
                    # Each row [i] contains distances from voxel i to every protein atom.
                    dists = torch.cdist(chunk, frame_prot)

                    # Check if any protein atom within exclusion radius
                    near  = (dists < protein_vdw_radius).any(dim=1)

                    # Increment occupancy for occupied voxels
                    occupancy_gpu[idx[near]] += 1
            protein_occupancy = occupancy_gpu.cpu().numpy().reshape(nbins)
            del shell_coords_gpu, shell_indices_gpu, occupancy_gpu, frame_prot
            torch.cuda.empty_cache()
        else:
            chunk    = 5_000
            occ_flat = protein_occupancy.ravel()
            for fi in tqdm(range(trajectory.n_frames)):
                fp = protein_pos[fi]
                for i in range(0, len(shell_coords), chunk):
                    ch   = shell_coords[i:i+chunk]
                    ci   = shell_indices[i:i+chunk]
                    d    = np.linalg.norm(
                        ch[:, np.newaxis, :] - fp[np.newaxis, :, :], axis=2)
                    near = (d < protein_vdw_radius).any(axis=1)
                    occ_flat[ci[near]] += 1

        # Convert counts to fractions (0 to 1)
        # fraction = count / n_frames
        # 0.0 = always free, 1.0 = always occupied
        protein_occupancy /= trajectory.n_frames

        # ── Step 5: Classify space ────────────────────────────────────────────
        print("Step 3/3: classifying space …")

        #  protein_occupancy ── fraction of frames each voxel was BLOCKED (0→1)
        #
        #  free_fraction = 1.0 - protein_occupancy
        #
        #  0.0 ◄────────────────────────────────────────────────────► 1.0
        #  always                                                   always
        #  blocked                                                   free
        #
        #  ├──────────────────┼──────────────────────┼──────────────────┤
        #  │    occupied      │      contested        │   growth space   │
        #  │   (< 0.3 free)   │   (0.3 – 0.7 free)   │   (≥ 0.7 free)   │
        #  ├──────────────────┼──────────────────────┼──────────────────┤
        #        0.0        0.3    free_fraction    0.7               1.0
        #                                         min_free_fraction
        #
        #  Each mask = in_shell  AND  threshold condition on free_fraction
        #
        #                     in_shell
        #                         │
        #          ┌──────────────┼──────────────┐
        #          ▼              ▼              ▼
        #   free < 0.3     0.3 ≤ free < 0.7   free ≥ 0.7
        #          │              │              │
        #          ▼              ▼              ▼
        #   occupied_space  contested_space  growth_space
        #      _mask             _mask           _mask
        #
        #  CROSS-SECTION VIEW (2D slice, same frame as shell diagram):
        #
        #   ┌─────────────────────────────────────┐
        #   │  ·  ·  ·  ·  ·  ·  ·  ·  ·  ·  ·  │  · outside shell (all masks False)
        #   │  ·  ·  ·  ░  ░  ▒  ▒  ░  ·  ·  ·  │
        #   │  ·  ·  ░  ░  ▒  ▒  ▒  ▒  ░  ·  ·  │
        #   │  ·  ░  ░  ▒  ▓  ▓  ▓  ▒  ░  ░  ·  │
        #   │  ·  ░  ▒  ▓  ╔══════╗  ▓  ▒  ░  ·  │  ░ growth_space     (free ≥ 0.7)
        #   │  ·  ░  ▒  ▓  ║ligand║  ▓  ▒  ░  ·  │  ▒ contested       (0.3–0.7)
        #   │  ·  ░  ▒  ▓  ╚══════╝  ▓  ▒  ░  ·  │  ▓ occupied        (free < 0.3)
        #   │  ·  ░  ░  ▒  ▓  ▓  ▓  ▒  ░  ░  ·  │
        #   │  ·  ·  ░  ░  ▒  ▒  ▒  ▒  ░  ·  ·  │
        #   │  ·  ·  ·  ░  ░  ▒  ▒  ░  ·  ·  ·  │
        #   │  ·  ·  ·  ·  ·  ·  ·  ·  ·  ·  ·  │
        #   └─────────────────────────────────────┘
        #
        
        # Calculate fraction of time each voxel is FREE (not occupied)
        # Shape: (nbins[0], nbins[1], nbins[2]) of values 0-1
        free_fraction = 1.0 - protein_occupancy


        # Growth space = in shell AND protein-free most of the time
        # Typically use 70% threshold: "reliably free" for growth
        # Shape: (nbins[0], nbins[1], nbins[2]) of Boolean
        growth_space_mask    = in_shell & (free_fraction >= min_free_fraction)
        # growth_space_mask = in_shell & (free_fraction >= min_free_fraction) & (free_fraction != 1.0)

        # Also identify "contested space" - sometimes free, sometimes occupied
        # Useful for more aggressive modifications or flexible residues
        # Typically 30-70% free: moderate confidence
        # contested_space_mask = in_shell & (free_fraction >= 0.3) & (free_fraction < min_free_fraction)
        contested_space_mask = in_shell & (free_fraction <  min_free_fraction)
        
        # Protein-occupied space in shell
        # Usually blocked: <30% free
        occupied_space_mask  = in_shell & (protein_occupancy > 0.7)
        full_shell_mask      = in_shell

        vv = dx ** 3
        print(f"  Growth space    : {growth_space_mask.sum():,} voxels  "
              f"({growth_space_mask.sum() * vv:.1f} Å³)")
        print(f"  Contested space : {contested_space_mask.sum():,} voxels  "
              f"({contested_space_mask.sum() * vv:.1f} Å³)")
        print(f"  Occupied >70%   : {occupied_space_mask.sum():,} voxels  [diagnostic]")
        print(f"  Full shell      : {full_shell_mask.sum():,} voxels")

        result = {
            'growth_space_mask':    growth_space_mask,
            'contested_space_mask': contested_space_mask,
            'occupied_space_mask':  occupied_space_mask,
            'full_shell_mask':      full_shell_mask,
            'free_fraction':        free_fraction,
            'protein_occupancy':    protein_occupancy,
            'min_dist_to_ligand':   min_dist_to_ligand,
            'grid_info': {
                'xmin':                xmin,
                'xmax':                xmax,
                'nbins':               nbins,
                'dx':                  dx,
                'shell_inner_radius':  shell_inner_radius,
                'shell_outer_radius':  shell_outer_radius,
            },
            'volumes': {
                'growth_space': growth_space_mask.sum()    * vv,
                'contested':    contested_space_mask.sum() * vv,
                'occupied':     occupied_space_mask.sum()  * vv,
                'full_shell':   full_shell_mask.sum()      * vv,
                'voxel_size':   vv,
            },
        }
        self.negative_space_data = result
        return result

    def compute_growth_space_features(self,
                                      aromatic_cutoff: float = 4.5,
                                      hbond_cutoff: float = 3.5,
                                      hydrophobic_cutoff: float = 5.0):
        """Score each growth-space voxel by proximity to protein chemical feature types.

        For each voxel in the growth space (protein occupancy < 30%), computes a
        linear proximity score to six protein atom categories per trajectory frame,
        then averages over all frames:
            score = 1 − (min_distance / cutoff)   if min_distance < cutoff
            score = 0                               otherwise

        Protein atom categories:
          - aromatic        : ring atoms of TYR, PHE, TRP, HIS
          - hydrophobic     : side-chain C of ALA, VAL, LEU, ILE, MET, PHE, TRP, PRO
          - hbond_donor     : near protein H-bond acceptors (suggest donor in ligand)
          - hbond_acceptor  : near protein H-bond donors   (suggest acceptor in ligand)
          - positive_charge : near protein negative charges (ASP/GLU carboxylates)
          - negative_charge : near protein positive charges (LYS/ARG/HIS)

        Charge score arrays remain zero if the protein has no charged residues
        of that sign (common in IDPs — no failure).

        GPU-accelerated when PyTorch + CUDA are available; falls back to NumPy/CPU.

        Requires compute_negative_space() to have been called first.

        Parameters
        ----------
        aromatic_cutoff : float
            Distance cutoff for aromatic interactions (Å). Default 4.5 Å.
        hbond_cutoff : float
            Distance cutoff for H-bond and charge interactions (Å). Default 3.5 Å.
        hydrophobic_cutoff : float
            Distance cutoff for hydrophobic contacts (Å). Default 5.0 Å.

        Returns
        -------
        dict with keys:
          aromatic_score        : (nx,ny,nz) float
          hydrophobic_score     : (nx,ny,nz) float
          hbond_donor_score     : (nx,ny,nz) float  (high near protein H-bond acceptors)
          hbond_acceptor_score  : (nx,ny,nz) float  (high near protein H-bond donors)
          positive_charge_score : (nx,ny,nz) float  (high near protein negative charges)
          negative_charge_score : (nx,ny,nz) float  (high near protein positive charges)
          grid_info             : dict
          feature_names         : list[str]
        Stored on self.growth_space_features.
        """
        if self.negative_space_data is None:
            raise RuntimeError(
                "Call compute_negative_space() before compute_growth_space_features()"
            )

        trajectory  = self.prot_lig_traj
        grid_info   = self.negative_space_data['grid_info']
        xmin        = grid_info['xmin']
        dx          = grid_info['dx']
        nbins       = grid_info['nbins']
        growth_mask = self.negative_space_data['growth_space_mask']

        # ========================================================================
        # STEP 1: IDENTIFY AND CATEGORIZE PROTEIN ATOMS BY CHEMICAL TYPE
        # ========================================================================
        # Six categories, mirroring the six score arrays returned below:
        #   aromatic          — ring atoms of TRP/TYR/PHE/HIS (π-π / CH-π contacts)
        #   hydrophobic       — nonpolar side-chain carbons (van der Waals contacts)
        #   hbond_donor_atoms / hbond_acceptor_atoms — protein groups that can
        #       give/receive an H-bond; scored in reverse (see Step 4)
        #   positive_atoms / negative_atoms — salt-bridge partners; scored in
        #       reverse (see Step 5)
        # ── Atom selections ( all indices in prot_lig context) ─────────────────
        
        # Aromatic ring atoms via get_protein_rings() rather than a hardcoded
        # atom-name list: it selects the correct ring atoms per residue type
        # (including ring nitrogens — HIS ND1/NE2, TRP NE1), so no ring atom
        # is missed the way a single shared name list would.
        protein_rings, _, _ = self.get_protein_rings()
        aromatic_atoms = (np.concatenate(protein_rings).astype(int)
                          if protein_rings else np.array([], dtype=int))

        # Hydrophobic side-chain carbons (selective: named carbons in nonpolar residues)
        hydrophobic_atoms = self.prot_lig_top.select(
            'protein and (resname ALA VAL LEU ILE MET PHE TRP PRO) '
            'and (name CB CG CG1 CG2 CD CD1 CD2 CE CE1 CE2 CZ)'
        )

        # H-bond donors (protein side): backbone/sidechain N (has an N-H to give)
        # plus hydroxyl O in SER/THR/TYR/ASN/GLN. These atoms are scored against
        # hbond_acceptor_score, NOT hbond_donor_score — see Step 4.
        hbond_donor_atoms = np.union1d(
            self.prot_lig_top.select('protein and element N'),
            self.prot_lig_top.select(
                'protein and element O and resname SER THR TYR ASN GLN'
            ),
        )

        # H-bond acceptors (protein side): every O/N has a lone pair, so no
        # residue filter is needed here (unlike donors, which need the -OH/-NH
        # check). Scored against hbond_donor_score — see Step 4.
        hbond_acceptor_atoms = self.prot_lig_top.select(
            'protein and (element O or element N)'
        )

        # Charged atoms: only the specific side-chain atom that carries the
        # charge (LYS NZ, ARG NH1/NH2, HIS NE2 / ASP OD1/OD2, GLU OE1/OE2).
        # Either array can be empty for an IDP lacking that charge type —
        # the corresponding score array is simply left at all-zero (Step 6).
        positive_atoms = self.prot_lig_top.select(
            'protein and resname LYS ARG HIS and name NZ NH1 NH2 NE2'
        )
        negative_atoms = self.prot_lig_top.select(
            'protein and resname ASP GLU and name OD1 OD2 OE1 OE2'
        )

        print(f"  Aromatic ring atoms   : {len(aromatic_atoms)}")
        print(f"  Hydrophobic C atoms   : {len(hydrophobic_atoms)}")
        print(f"  H-bond donor atoms    : {len(hbond_donor_atoms)}")
        print(f"  H-bond acceptor atoms : {len(hbond_acceptor_atoms)}")
        print(f"  Positive charge atoms : {len(positive_atoms)}"
              + (" [none — score stays zero]" if len(positive_atoms) == 0 else ""))
        print(f"  Negative charge atoms : {len(negative_atoms)}"
              + (" [none — score stays zero]" if len(negative_atoms) == 0 else ""))

        # ========================================================================
        # STEP 2: RECREATE THE 3D VOXEL GRID AND EXTRACT GROWTH-SPACE VOXELS
        # ========================================================================
        # Same grid definition used in compute_negative_space(): voxel centers
        # spaced dx apart starting at xmin. growth_voxel_coords holds only the
        # coordinates of voxels flagged True in growth_mask; growth_indices are
        # their flat (ravelled) positions, used to scatter scores back into the
        # full (nx,ny,nz) array without ever materializing a full dense grid.
        # ── Voxel grid for growth space ────────────────────────────────────────
        x, y, z      = (np.arange(nbins[i]) * dx + xmin[i] for i in range(3))
        xx, yy, zz   = np.meshgrid(x, y, z, indexing='ij')
        voxel_coords = np.stack([xx, yy, zz], axis=-1)

        growth_voxel_coords = voxel_coords[growth_mask]          # (n_growth, 3)
        growth_indices      = np.where(growth_mask.ravel())[0]   # flat indices into ravelled grid

        print(f"\nScoring {len(growth_voxel_coords):,} growth-space voxels …")

        # ========================================================================
        # STEP 3: INITIALIZE FEATURE SCORE FIELDS
        # ========================================================================
        # Full-grid arrays, zero everywhere except growth-space voxels that end
        # up within cutoff of a protein atom of that type. Convention:
        #   0.0 = no atom of this type within cutoff, or voxel not in growth space
        #   1.0 = an atom of this type sits right at the voxel center
        #   otherwise = 1.0 − (min_distance_to_nearest_atom / cutoff)
        # ── Initialize score arrays (zeros = no feature / out of cutoff) ──────
        aromatic_score        = np.zeros(nbins, dtype=np.float32)
        hydrophobic_score     = np.zeros(nbins, dtype=np.float32)
        hbond_donor_score     = np.zeros(nbins, dtype=np.float32)
        hbond_acceptor_score  = np.zeros(nbins, dtype=np.float32)
        positive_charge_score = np.zeros(nbins, dtype=np.float32)
        negative_charge_score = np.zeros(nbins, dtype=np.float32)

        n_frames = trajectory.n_frames
        n_voxels = int(np.prod(nbins))

        # ── GPU tensors shared across all feature loops ────────────────────────
        if USE_GPU:
            voxels_gpu     = torch.tensor(
                growth_voxel_coords, dtype=torch.float32, device=GPU_DEVICE)
            growth_idx_gpu = torch.tensor(
                growth_indices, dtype=torch.long, device=GPU_DEVICE)

        # ========================================================================
        # STEP 4: SHARED SCORING KERNEL (GPU / CPU)
        # ========================================================================
        # Same linear-decay scoring used for all six feature types — factored
        # into one helper instead of repeating it per category (as the legacy
        # version did) since the only thing that changes per call is which atom
        # indices and cutoff are passed in.
        #
        #  score = 1.0 − (min_distance / cutoff)      if min_distance < cutoff
        #  score = 0.0                                  if min_distance ≥ cutoff
        #
        #  score
        #   1.0 ┤╲
        #       │  ╲
        #   0.5 ┤    ╲
        #       │      ╲
        #   0.0 ┤────────╲──────────────────────────── distance (Å)
        #       0        cutoff
        #
        # For every negative/growth-space voxel and every frame: find the
        # nearest atom of the given category, score it, and accumulate; the
        # final /n_frames average gives the trajectory-averaged suggestion
        # strength at that voxel (Step 3 in the legacy version's per-feature
        # comments — here it happens once, generically, per call).
        # ── Scoring helpers (close over shared state) ─────────────────────────
        def _score_gpu(atom_indices, cutoff):
            accum      = torch.zeros(n_voxels, dtype=torch.float32, device=GPU_DEVICE)
            n_atoms    = len(atom_indices)
            chunk_size = max(1_000, min(200_000, int(4e9 / (n_atoms * 4))))
            for fi in tqdm(range(n_frames)):
                frame_atoms = torch.tensor(
                    trajectory.xyz[fi, atom_indices, :] * 10.0,
                    dtype=torch.float32, device=GPU_DEVICE,
                )
                for i in range(0, len(voxels_gpu), chunk_size):
                    chunk    = voxels_gpu[i:i+chunk_size]
                    idx      = growth_idx_gpu[i:i+chunk_size]
                    dists    = torch.cdist(chunk, frame_atoms)
                    min_d, _ = torch.min(dists, dim=1)
                    within   = min_d <= cutoff
                    scores   = torch.zeros(len(chunk), dtype=torch.float32, device=GPU_DEVICE)
                    scores[within] = 1.0 - min_d[within] / cutoff
                    accum[idx] += scores
                del frame_atoms
            out = accum.cpu().numpy().reshape(nbins) / n_frames
            del accum
            torch.cuda.empty_cache()
            return out

        def _score_cpu(atom_indices, cutoff):
            pos_all    = trajectory.xyz[:, atom_indices, :] * 10.0  # (n_frames, n_atoms, 3) Å
            accum      = np.zeros(nbins, dtype=np.float32)
            chunk_size = 5_000
            for fi in tqdm(range(n_frames)):
                fp = pos_all[fi]
                for i in range(0, len(growth_voxel_coords), chunk_size):
                    ch   = growth_voxel_coords[i:i+chunk_size]
                    ci   = growth_indices[i:i+chunk_size]
                    d    = np.linalg.norm(
                        ch[:, np.newaxis, :] - fp[np.newaxis, :, :], axis=2)
                    md   = d.min(axis=1)
                    w    = md <= cutoff
                    s    = np.zeros(len(ch), dtype=np.float32)
                    s[w] = 1.0 - md[w] / cutoff
                    accum.ravel()[ci] += s
            return accum / n_frames

        _score = _score_gpu if USE_GPU else _score_cpu

        # ========================================================================
        # STEP 5: SCORE EACH FEATURE TYPE
        # ========================================================================
        # aromatic / hydrophobic are scored directly (protein feature → same
        # ligand feature suggested at that voxel).
        #
        # hbond and charge scoring is COMPLEMENTARY — the protein group present
        # determines the OPPOSITE ligand group to suggest:
        #   protein H-bond donor    → suggest ligand H-bond ACCEPTOR here
        #   protein H-bond acceptor → suggest ligand H-bond DONOR here
        #   protein positive charge → suggest ligand NEGATIVE group here (salt bridge)
        #   protein negative charge → suggest ligand POSITIVE group here (salt bridge)
        # ── Per-feature scoring ────────────────────────────────────────────────
        if len(aromatic_atoms) > 0:
            print("Aromatic …")
            aromatic_score = _score(aromatic_atoms, aromatic_cutoff)

        if len(hydrophobic_atoms) > 0:
            print("Hydrophobic …")
            hydrophobic_score = _score(hydrophobic_atoms, hydrophobic_cutoff)

        if len(hbond_donor_atoms) > 0:
            # Protein donors → suggest ligand acceptor at this location
            print("H-bond donors (→ acceptor score) …")
            hbond_acceptor_score = _score(hbond_donor_atoms, hbond_cutoff)

        if len(hbond_acceptor_atoms) > 0:
            # Protein acceptors → suggest ligand donor at this location
            print("H-bond acceptors (→ donor score) …")
            hbond_donor_score = _score(hbond_acceptor_atoms, hbond_cutoff)

        if len(positive_atoms) > 0:
            # Protein positive charges → suggest negative ligand group
            print("Positive charges (→ negative charge score) …")
            negative_charge_score = _score(positive_atoms, hbond_cutoff)

        if len(negative_atoms) > 0:
            # Protein negative charges → suggest positive ligand group
            print("Negative charges (→ positive charge score) …")
            positive_charge_score = _score(negative_atoms, hbond_cutoff)

        # GPU cleanup — unconditional to avoid tensor leaks if charge atoms are absent
        if USE_GPU:
            del voxels_gpu, growth_idx_gpu
            torch.cuda.empty_cache()

        # ========================================================================
        # STEP 6: PACKAGE RESULTS
        # ========================================================================
        # Charge/hbond score arrays for a missing category stay all-zero
        # (initialized in Step 3, never written to) rather than raising —
        # expected for IDPs that may lack, e.g., any negatively charged residue.
        result = {
            'aromatic_score':        aromatic_score,
            'hydrophobic_score':     hydrophobic_score,
            'hbond_donor_score':     hbond_donor_score,
            'hbond_acceptor_score':  hbond_acceptor_score,
            'positive_charge_score': positive_charge_score,
            'negative_charge_score': negative_charge_score,
            'grid_info':             grid_info,
            'feature_names': [
                'Aromatic', 'Hydrophobic',
                'H-bond Donor', 'H-bond Acceptor',
                'Positive Charge', 'Negative Charge',
            ],
        }
        self.growth_space_features = result
        return result

    # ── 5. Pharmacophore definition ───────────────────────────────────────────

    def compute_pharmacophore_maps(self, protein_vdw_radius: float = 1.5):
        """Compute residue-type protein occupancy maps for pharmacophore definition.

        For each voxel in the analysis shell, accumulates per-frame binary
        occupancy (is an atom of this chemical type within protein_vdw_radius?)
        and averages over the trajectory. The algorithm runs once on the full
        shell and derives the contested-space result by masking.

        Six residue-type occupancy maps are produced:
          - aromatic         : ring-center occupancy (with contact/non-contact split
                               when compute_aromatic_contacts() has been called)
          - hydrophobic      : side-chain C atoms of nonpolar residues
          - hbond_donors     : backbone/sidechain N + polar hydroxyl O
          - hbond_acceptors  : all protein O and N
          - positive_charge  : LYS/ARG/HIS charged N atoms
          - negative_charge  : ASP/GLU carboxylate O atoms

        Aromatic occupancy uses per-frame ring centroids (not individual atoms)
        and is split into:
          - aromatic_occupancy_contacts     : voxel blocked by a ring in active
                                             ligand contact that frame
          - aromatic_occupancy_non_contacts : voxel blocked by a ring NOT in
                                             active contact (transient passage)
        Requires compute_aromatic_contacts() for the contact split; gracefully
        sets both to None if that method has not been called.

        Charged-residue maps remain all-zero if no such residues exist (IDP
        fallback — no failure).

        GPU-accelerated when PyTorch + CUDA are available; falls back to
        NumPy/CPU.

        Requires compute_negative_space() to have been called first.

        Parameters
        ----------
        protein_vdw_radius : float
            Atom exclusion radius used to decide voxel occupancy (Å).
            Default 1.5 Å — matches compute_negative_space() convention.

        Returns
        -------
        (maps_contested, maps_full) — two dicts with identical keys:
          aromatic_occupancy              : (nx,ny,nz) float
          aromatic_occupancy_contacts     : (nx,ny,nz) float or None
          aromatic_occupancy_non_contacts : (nx,ny,nz) float or None
          hydrophobic_occupancy           : (nx,ny,nz) float
          hbond_donors_occupancy          : (nx,ny,nz) float
          hbond_acceptors_occupancy       : (nx,ny,nz) float
          positive_occupancy              : (nx,ny,nz) float
          negative_occupancy              : (nx,ny,nz) float
          grid_info                       : dict
        Stored on self.pharmacophore_maps_contested and self.pharmacophore_maps_full.
        """
        if self.negative_space_data is None:
            raise RuntimeError(
                "Call compute_negative_space() before compute_pharmacophore_maps()"
            )

        # ========================================================================
        # STEP 1: EXTRACT GRID INFORMATION
        # ========================================================================
        # Grid parameters and both masks come from compute_negative_space():
        # full_shell_mask defines every voxel the algorithm scores; contested_mask
        # is a subset of it. Scoring runs ONCE over the full shell — the
        # contested-space result is derived afterward by zeroing everything
        # outside contested_mask (see _mask_to_contested below), instead of
        # repeating the whole scoring pass a second time over a smaller mask.
        trajectory        = self.prot_lig_traj
        grid_info         = self.negative_space_data['grid_info']
        xmin              = grid_info['xmin']
        dx                = grid_info['dx']
        nbins             = grid_info['nbins']
        full_shell_mask   = self.negative_space_data['full_shell_mask']
        contested_mask    = self.negative_space_data['contested_space_mask']

        n_frames = trajectory.n_frames
        n_voxels = int(np.prod(nbins))

        # ========================================================================
        # STEP 2: IDENTIFY PROTEIN ATOMS BY CHEMICAL TYPE + AROMATIC RING GROUPS
        # ========================================================================
        # Same six categories as the legacy version (aromatic ring atoms,
        # hydrophobic side-chain carbons, H-bond donors/acceptors, +/- charges),
        # but built from get_protein_rings()/MDTraj select() strings instead of
        # a manual per-residue loop over topology.residues — see the earlier
        # comparison of get_protein_rings() vs. the hardcoded ring atom names.
        # ── Atom selections (prot_lig context) ────────────────────────────────
        protein_rings, protein_rings_index, _ = self.get_protein_rings()

        # Ring CENTROIDS, not individual ring atoms: for each aromatic residue,
        # average the position of its ring atoms every frame. One centroid per
        # residue per frame — this is what gets tested for proximity to a voxel,
        # exactly like the legacy ring_centers_pos array.
        # Per-frame ring centroids: (n_frames, n_aro_residues, 3) in Å
        n_aro_residues = len(protein_rings)
        ring_centers_pos = np.zeros((n_frames, n_aro_residues, 3), dtype=np.float32)
        for res_idx, atom_indices in enumerate(protein_rings):
            ring_centers_pos[:, res_idx, :] = (
                trajectory.xyz[:, atom_indices, :].mean(axis=1) * 10.0
            )

        # Per-residue, per-frame contact flags — the legacy version read these
        # from a hardcoded pickle path (config["aromatic_contacts_pickle"]);
        # here they come directly from self._stacked_full, populated by
        # compute_aromatic_contacts() earlier in the pipeline. If that method
        # was never called, the contact/non-contact split is skipped rather
        # than failing (there is no separate pickle to fall back to).
        # Aromatic contact flags: (n_frames, n_aro_residues) — from compute_aromatic_contacts()
        # Columns ordered identically to protein_rings / ring_centers_pos.
        have_aro_contacts = (self._stacked_full is not None
                             and len(protein_rings_index) > 0)
        if have_aro_contacts:
            aromatic_contacts = self._stacked_full[:, self._protein_rings_index].astype(bool)
        else:
            aromatic_contacts = None
            print("  compute_aromatic_contacts() not called — contact/non-contact "
                  "split will be skipped")

        # Same optional-split idea, but for H-bond donors/acceptors instead of
        # aromatics — the legacy version had no equivalent for H-bonds at all;
        # this is new behavior enabled by compute_hbond_contacts() upstream.
        have_hbond_contacts = (self.hbond_contact_frames_pd is not None and
                               self.hbond_contact_frames_ld is not None)
        if not have_hbond_contacts:
            print("  compute_hbond_contacts() not called — H-bond contact/non-contact "
                  "split will be skipped")

        hydrophobic_atoms = self.prot_lig_top.select(
            'protein and (resname ALA VAL LEU ILE MET PHE TRP PRO) '
            'and (name CB CG CG1 CG2 CD CD1 CD2 CE CE1 CE2 CZ)'
        )
        hbond_donor_atoms = np.union1d(
            self.prot_lig_top.select('protein and element N'),
            self.prot_lig_top.select(
                'protein and element O and resname SER THR TYR ASN GLN'
            ),
        )
        hbond_acceptor_atoms = self.prot_lig_top.select(
            'protein and (element O or element N)'
        )
        positive_atoms = self.prot_lig_top.select(
            'protein and resname LYS ARG HIS and name NZ NH1 NH2 NE2'
        )
        negative_atoms = self.prot_lig_top.select(
            'protein and resname ASP GLU and name OD1 OD2 OE1 OE2'
        )

        print(f"  Aromatic ring groups  : {n_aro_residues}")
        print(f"  Hydrophobic C atoms   : {len(hydrophobic_atoms)}")
        print(f"  H-bond donor atoms    : {len(hbond_donor_atoms)}")
        print(f"  H-bond acceptor atoms : {len(hbond_acceptor_atoms)}")
        print(f"  Positive charge atoms : {len(positive_atoms)}"
              + (" [none — score stays zero]" if len(positive_atoms) == 0 else ""))
        print(f"  Negative charge atoms : {len(negative_atoms)}"
              + (" [none — score stays zero]" if len(negative_atoms) == 0 else ""))

        # Atom-to-residue index arrays for the H-bond contact split.
        # residue.index in prot_lig_top for protein-only selections falls in
        # [0, n_protein_residues-1], matching the column space of
        # hbond_contact_frames_pd / hbond_contact_frames_ld.
        donor_atom_to_res = np.array(
            [self.prot_lig_top.atom(a).residue.index for a in hbond_donor_atoms],
            dtype=int,
        )
        acceptor_atom_to_res = np.array(
            [self.prot_lig_top.atom(a).residue.index for a in hbond_acceptor_atoms],
            dtype=int,
        )

        # ========================================================================
        # STEP 3: CREATE 3D VOXEL GRID (FULL SHELL, NOT JUST CONTESTED)
        # ========================================================================
        # Same grid reconstruction as the legacy version's Step 3, but built
        # over full_shell_mask rather than contested_mask directly — scoring
        # the whole shell once and masking down to contested afterward avoids
        # ever needing a second full pass restricted to contested voxels.
        # ── Voxel grid — full shell (contested is a subset, derived by masking) ─
        x, y, z      = (np.arange(nbins[i]) * dx + xmin[i] for i in range(3))
        xx, yy, zz   = np.meshgrid(x, y, z, indexing='ij')
        voxel_coords = np.stack([xx, yy, zz], axis=-1)

        shell_voxel_coords = voxel_coords[full_shell_mask]
        shell_indices      = np.where(full_shell_mask.ravel())[0]

        print(f"\nScoring {len(shell_voxel_coords):,} shell voxels "
              f"(full shell — contested derived by masking) …")

        # ========================================================================
        # STEP 4: INITIALIZE OCCUPANCY ACCUMULATORS
        # ========================================================================
        # Every _occ array is 0.0 by construction (full-shell shape) — a voxel
        # only becomes nonzero if a protein atom of that type sits within
        # protein_vdw_radius of it on at least one frame. The *_contacts_occ /
        # *_non_contacts_occ arrays are left as None (not zero arrays) when the
        # corresponding compute_*_contacts() step wasn't run, so downstream code
        # can distinguish "never computed" from "computed, always zero".
        # ── Initialize accumulators (full shell only) ──────────────────────────
        aromatic_occ      = np.zeros(nbins, dtype=np.float32)
        aromatic_contacts_occ     = (np.zeros(nbins, dtype=np.float32)
                                     if have_aro_contacts else None)
        aromatic_non_contacts_occ = (np.zeros(nbins, dtype=np.float32)
                                     if have_aro_contacts else None)
        hydrophobic_occ   = np.zeros(nbins, dtype=np.float32)
        hbond_donors_occ              = np.zeros(nbins, dtype=np.float32)
        hbond_donors_contacts_occ     = (np.zeros(nbins, dtype=np.float32)
                                         if have_hbond_contacts else None)
        hbond_donors_non_contacts_occ = (np.zeros(nbins, dtype=np.float32)
                                         if have_hbond_contacts else None)
        hbond_acceptors_occ              = np.zeros(nbins, dtype=np.float32)
        hbond_acceptors_contacts_occ     = (np.zeros(nbins, dtype=np.float32)
                                            if have_hbond_contacts else None)
        hbond_acceptors_non_contacts_occ = (np.zeros(nbins, dtype=np.float32)
                                            if have_hbond_contacts else None)
        positive_occ      = np.zeros(nbins, dtype=np.float32)
        negative_occ      = np.zeros(nbins, dtype=np.float32)

        # ── GPU shared tensors ─────────────────────────────────────────────────
        if USE_GPU:
            voxels_gpu     = torch.tensor(
                shell_voxel_coords, dtype=torch.float32, device=GPU_DEVICE)
            shell_idx_gpu  = torch.tensor(
                shell_indices, dtype=torch.long, device=GPU_DEVICE)

        # ========================================================================
        # STEP 5: BINARY OCCUPANCY KERNEL (no contact/non-contact split)
        # ========================================================================
        # For every shell voxel and every frame: is ANY atom of this category
        # within protein_vdw_radius? If yes, +1 to that voxel's accumulator.
        # After all frames, dividing by n_frames turns the count into an
        # occupancy FRACTION (0 → never occupied, 1 → occupied every frame) —
        # same accumulate-then-divide pattern as the legacy occupancy_gpu.
        # ── Binary occupancy helper: non-aromatic features ─────────────────────
        def _occ_gpu(atom_indices):
            accum      = torch.zeros(n_voxels, dtype=torch.float32, device=GPU_DEVICE)
            n_atoms    = len(atom_indices)
            chunk_size = max(1_000, min(200_000, int(4e9 / (n_atoms * 4))))
            for fi in tqdm(range(n_frames)):
                frame_atoms = torch.tensor(
                    trajectory.xyz[fi, atom_indices, :] * 10.0,
                    dtype=torch.float32, device=GPU_DEVICE,
                )
                for i in range(0, len(voxels_gpu), chunk_size):
                    chunk = voxels_gpu[i:i+chunk_size]
                    idx   = shell_idx_gpu[i:i+chunk_size]
                    dists = torch.cdist(chunk, frame_atoms)
                    near  = (dists < protein_vdw_radius).any(dim=1)
                    accum[idx[near]] += 1
                del frame_atoms
            out = accum.cpu().numpy().reshape(nbins) / n_frames
            del accum
            torch.cuda.empty_cache()
            return out

        def _occ_cpu(atom_indices):
            pos_all    = trajectory.xyz[:, atom_indices, :] * 10.0
            accum      = np.zeros(nbins, dtype=np.float32)
            occ_flat   = accum.ravel()
            chunk_size = 5_000
            for fi in tqdm(range(n_frames)):
                fp = pos_all[fi]
                for i in range(0, len(shell_voxel_coords), chunk_size):
                    ch   = shell_voxel_coords[i:i+chunk_size]
                    ci   = shell_indices[i:i+chunk_size]
                    d    = np.linalg.norm(
                        ch[:, np.newaxis, :] - fp[np.newaxis, :, :], axis=2)
                    near = (d < protein_vdw_radius).any(axis=1)
                    occ_flat[ci[near]] += 1
            return accum / n_frames

        _occ = _occ_gpu if USE_GPU else _occ_cpu

        # for each frame, per-residue-type: which shell voxels does it block?
        #  ════════════════════════════════════════════════════════════════
        #  GOAL: for every shell voxel, measure how often it is blocked
        #        by an aromatic ring — and whether that ring is actively
        #        contacting the ligand or just transiently passing through.
        #        (Contested-space values are a subset of this, taken by
        #        masking in Step 9 — the loop below never restricts to
        #        contested_mask directly.)
        #  ════════════════════════════════════════════════════════════════
        #
        #  THREE accumulators (all flat, shape: n_voxels):
        #
        #  occ_gpu   → voxel blocked by ANY aromatic ring centre
        #  con_gpu   → voxel blocked by a ring that IS   contacting ligand
        #  ncon_gpu  → voxel blocked by a ring that IS NOT contacting ligand
        #
        #  PER-FRAME INPUTS:
        #
        #  ring_centers_pos[fi]   ── shape: (n_aro_residues, 3)
        #  ┌────────────┬───┬───┬───┐
        #  │  Phe 42    │ x │ y │ z │  ← centroid of aromatic ring
        #  │  Tyr 87    │ x │ y │ z │
        #  │  Trp 113   │ x │ y │ z │
        #  └────────────┴───┴───┴───┘
        #
        #  aromatic_contacts[fi]  ── shape: (n_aro_residues,)  Bool
        #  ┌────────────┬────────┐
        #  │  Phe 42    │  True  │  ← ring is within contact distance of ligand
        #  │  Tyr 87    │  False │  ← ring is NOT contacting ligand this frame
        #  │  Trp 113   │  True  │
        #  └────────────┴────────┘
        #
        #  CHUNK LOOP LOGIC  (per chunk of shell voxels):
        #
        #  dists  ── (chunk_size, n_aro_residues)   cdist output
        #
        #              Phe42   Tyr87   Trp113
        #  voxel₀  [ [ 0.8  │  3.9  │  5.2 ]   near = dists < protein_vdw_radius
        #  voxel₁    [ 4.1  │  1.1  │  2.3 ]        ↓ .any(dim=1)
        #  voxel₂    [ 6.0  │  5.5  │  1.3 ] ]  ┌──────────────────┐
        #              │                          │  T  │  T  │  T  │  → occ_gpu
        #              │                          └──────────────────┘
        #              │
        #  near  ── (chunk_size, n_aro_residues)  Bool
        #
        #              Phe42   Tyr87  Trp113        frame_flags
        #  voxel₀  [ [  T   │   F  │   F  ]  AND  [  T  │  F  │  T  ]
        #  voxel₁    [  F   │   T  │   F  ]       [  T  │  F  │  T  ]
        #  voxel₂    [  F   │   F  │   T  ] ]     [  T  │  F  │  T  ]
        #              ↓ .any(dim=1)                   ↓ .any(dim=1)
        #         ┌──────────────────┐           ┌──────────────────┐
        #         │  T  │  F  │  T  │           │  F  │  F  │  T  │
        #         └──────────────────┘           └──────────────────┘
        #               con_gpu                       ncon_gpu
        #               (ring nearby                  (ring nearby BUT
        #                AND in contact)               not in contact)
        #
        #  AFTER ALL FRAMES  (divide by n_frames → occupancy fraction 0→1):
        #
        #  aromatic_occ              ── how often ANY ring blocks the voxel
        #  aromatic_contacts_occ     ── how often a BINDING ring blocks it
        #                               high → residue is a stable π-contact
        #                                      with the ligand → likely to
        #                                      compete for this space
        #  aromatic_non_contacts_occ ── transient ring passages only
        #                               high → flexible loop / solvent
        #                                      exposed ring swinging in
        #
        # Full-shell maps produced here; contested-space maps (nonzero only
        # inside contested_mask) are derived from these afterward — see
        # _mask_to_contested() in Step 9.
        #
        #  SPATIAL VIEW  (2D cross-section, shell region)
        #
        #  ┌──────────────────────────────────────────────────────────────┐
        #  │                                                              │
        #  │     ·  ·  ·  ·  ·  ·  ·  ·  ·  ·  ·  ·  ·  ·  ·          │
        #  │     ·  ·  ▒  ▒  ▒  ▒  ▒  ▒  ▒  ▒  ▒  ▒  ·  ·  ·          │
        #  │     ·  ▒  ▒  C  C  ▒  ▒  ▒  ▒  ▒  ▒  ▒  ▒  ·  ·          │
        #  │     ·  ▒  C  C [Phe42] C  ▒  ▒  ▒  ▒  ▒  ▒  ·  ·         │
        #  │     ·  ▒  C  C  C  C  ▒  ╔══════════╗  ▒  ·  ·  ·         │
        #  │     ·  ▒  ▒  C  C  ▒  ▒  ║          ║  ▒  ·  ·  ·         │
        #  │     ·  ▒  ▒  ▒  ▒  ▒  ▒  ║  ligand  ║  ▒  ·  ·  ·         │
        #  │     ·  ▒  ▒  ▒  ▒  ▒  ▒  ║          ║  ▒  ·  ·  ·         │
        #  │     ·  ▒  N  N  N  N  ▒  ╚══════════╝  ▒  ·  ·  ·         │
        #  │     ·  ▒  ▒  N  N  ▒  ▒  ▒  ▒  ▒  ▒  ▒  ·  ·  ·          │
        #  │     ·  ·  ▒  ▒  ▒  ▒  ▒  ▒  ▒  ▒  ▒  ▒  ·  ·  ·          │
        #  │     ·  ·  ·  ·  ·  ·  ·  ·  ·  ·  ·  ·  ·  ·  ·          │
        #  │                                                              │
        #  └──────────────────────────────────────────────────────────────┘
        #
        #  ·  outside shell (not visited)
        #  ▒  shell voxel, no aromatic ring nearby this frame
        #  C  shell voxel, blocked by Phe42 AND Phe42 contacts ligand
        #     → increments occ_gpu + con_gpu
        #  N  shell voxel, blocked by a ring NOT contacting ligand
        #     → increments occ_gpu + ncon_gpu
        #
        #  TWO REPRESENTATIVE FRAMES:
        #
        #  frame A  (Phe42 rotated toward ligand — in contact)
        #
        #       [Phe42]──────►  ╔════╗
        #        ring centre    ║lig.║     voxels between ring and ligand:
        #                       ╚════╝     near = T, contact = T  → C
        #
        #  frame B  (Phe42 swung away — NOT in contact)
        #
        #       [Phe42]
        #        ring                      voxels near ring:
        #           ↘  (away from ligand)  near = T, contact = F  → N
        #              ╔════╗
        #              ║lig.║
        #              ╚════╝
        #
        #  After N frames, the ratio C/(C+N) per voxel — restricted to
        #  contested_mask downstream — tells you:
        #  → high C  : ring is stably docked against ligand here
        #              → structural π-contact, hard to displace
        #  → high N  : ring only passes through transiently
        #              → flexible residue, voxel recoverable for ligand growth
        # ── Split occupancy helper: returns (total, contact, non_contact) ──────
        # Used for H-bond donors and acceptors.  contact_flags_2d is
        # (n_frames, n_protein_residues); atom_to_res maps each atom to its
        # residue column so we can look up the per-frame H-bond flag per atom.
        def _occ_split_gpu(atom_indices, atom_to_res, contact_flags_2d):
            accum_total = torch.zeros(n_voxels, dtype=torch.float32, device=GPU_DEVICE)
            accum_con   = torch.zeros(n_voxels, dtype=torch.float32, device=GPU_DEVICE)
            accum_ncon  = torch.zeros(n_voxels, dtype=torch.float32, device=GPU_DEVICE)
            n_atoms    = len(atom_indices)
            chunk_size = max(1_000, min(200_000, int(4e9 / (n_atoms * 4))))
            for fi in tqdm(range(n_frames)):
                frame_atoms = torch.tensor(
                    trajectory.xyz[fi, atom_indices, :] * 10.0,
                    dtype=torch.float32, device=GPU_DEVICE,
                )
                frame_contact_mask = torch.tensor(
                    contact_flags_2d[fi, atom_to_res].astype(bool),
                    dtype=torch.bool, device=GPU_DEVICE,
                )
                for i in range(0, len(voxels_gpu), chunk_size):
                    chunk = voxels_gpu[i:i+chunk_size]
                    idx   = shell_idx_gpu[i:i+chunk_size]
                    dists = torch.cdist(chunk, frame_atoms)        # (chunk, n_atoms)
                    near  = dists < protein_vdw_radius             # (chunk, n_atoms)
                    accum_total[idx[near.any(dim=1)]] += 1
                    accum_con[idx[
                        torch.logical_and(near, frame_contact_mask.unsqueeze(0)).any(dim=1)
                    ]] += 1
                    accum_ncon[idx[
                        torch.logical_and(near, ~frame_contact_mask.unsqueeze(0)).any(dim=1)
                    ]] += 1
                del frame_atoms, frame_contact_mask
            total = accum_total.cpu().numpy().reshape(nbins) / n_frames
            con   = accum_con.cpu().numpy().reshape(nbins) / n_frames
            ncon  = accum_ncon.cpu().numpy().reshape(nbins) / n_frames
            del accum_total, accum_con, accum_ncon
            torch.cuda.empty_cache()
            return total, con, ncon

        def _occ_split_cpu(atom_indices, atom_to_res, contact_flags_2d):
            pos_all    = trajectory.xyz[:, atom_indices, :] * 10.0
            accum_total = np.zeros(nbins, dtype=np.float32)
            accum_con   = np.zeros(nbins, dtype=np.float32)
            accum_ncon  = np.zeros(nbins, dtype=np.float32)
            flat_total  = accum_total.ravel()
            flat_con    = accum_con.ravel()
            flat_ncon   = accum_ncon.ravel()
            chunk_size = 5_000
            for fi in tqdm(range(n_frames)):
                fp           = pos_all[fi]
                contact_mask = contact_flags_2d[fi, atom_to_res].astype(bool)
                for i in range(0, len(shell_voxel_coords), chunk_size):
                    ch   = shell_voxel_coords[i:i+chunk_size]
                    ci   = shell_indices[i:i+chunk_size]
                    d    = np.linalg.norm(
                        ch[:, np.newaxis, :] - fp[np.newaxis, :, :], axis=2)
                    near = d < protein_vdw_radius
                    flat_total[ci[near.any(axis=1)]] += 1
                    flat_con[ci[  (near &  contact_mask[np.newaxis, :]).any(axis=1)]] += 1
                    flat_ncon[ci[ (near & ~contact_mask[np.newaxis, :]).any(axis=1)]] += 1
            return accum_total / n_frames, accum_con / n_frames, accum_ncon / n_frames

        _occ_split = _occ_split_gpu if USE_GPU else _occ_split_cpu

        # ========================================================================
        # STEP 7: AROMATIC OCCUPANCY (ring centroids, own inline split)
        # ========================================================================
        # Same three-accumulator contact/non-contact logic as Step 6, but using
        # ring_centers_pos / aromatic_contacts (one centroid + one contact flag
        # per aromatic RESIDUE, already frame-aligned — no atom_to_res lookup
        # needed) instead of _occ_split, since aromatic contacts are tracked
        # per ring rather than per raw atom:
        #
        #  ring_centers_pos[fi]   ── (n_aro_residues, 3)   one centroid per ring
        #  aromatic_contacts[fi]  ── (n_aro_residues,) bool  ring in ligand contact?
        #
        #  dists ── cdist(voxel_chunk, ring_centers)   (chunk, n_aro)
        #  near  ── dists < protein_vdw_radius
        #
        #  occ_gpu  += voxels where near.any(ring axis)              → any ring nearby
        #  con_gpu  += voxels where (near AND frame_flags).any(...)  → nearby ring IS in contact
        #  ncon_gpu += voxels where (near AND ~frame_flags).any(...) → nearby ring NOT in contact
        #
        #  SPATIAL INTERPRETATION (unchanged from the legacy version):
        #  high con  : ring stably docked against the ligand here →
        #              structural π-contact, hard to displace
        #  high ncon : ring only swings through this voxel transiently →
        #              flexible residue, space recoverable for ligand growth
        # ── Aromatic: ring centers + contact split ─────────────────────────────
        if n_aro_residues > 0:
            print("Aromatic ring-center occupancy …")
            if USE_GPU:
                occ_gpu  = torch.zeros(n_voxels, dtype=torch.float32, device=GPU_DEVICE)
                con_gpu  = (torch.zeros(n_voxels, dtype=torch.float32, device=GPU_DEVICE)
                            if have_aro_contacts else None)
                ncon_gpu = (torch.zeros(n_voxels, dtype=torch.float32, device=GPU_DEVICE)
                            if have_aro_contacts else None)
                chunk_size = max(1_000, min(200_000, int(4e9 / (n_aro_residues * 4))))

                for fi in tqdm(range(n_frames)):
                    frame_aro = torch.tensor(
                        ring_centers_pos[fi], dtype=torch.float32, device=GPU_DEVICE)
                    if have_aro_contacts:
                        frame_flags = torch.tensor(
                            aromatic_contacts[fi], dtype=torch.bool, device=GPU_DEVICE)

                    for i in range(0, len(voxels_gpu), chunk_size):
                        chunk = voxels_gpu[i:i+chunk_size]
                        idx   = shell_idx_gpu[i:i+chunk_size]
                        dists = torch.cdist(chunk, frame_aro)         # (chunk, n_aro)
                        near  = dists < protein_vdw_radius             # (chunk, n_aro) bool
                        occ_gpu[idx[near.any(dim=1)]] += 1

                        if have_aro_contacts:
                            con_gpu[idx[
                                torch.logical_and(near, frame_flags.unsqueeze(0)).any(dim=1)
                            ]] += 1
                            ncon_gpu[idx[
                                torch.logical_and(near, ~frame_flags.unsqueeze(0)).any(dim=1)
                            ]] += 1

                    del frame_aro
                    if have_aro_contacts:
                        del frame_flags

                aromatic_occ = occ_gpu.cpu().numpy().reshape(nbins) / n_frames
                del occ_gpu
                if have_aro_contacts:
                    aromatic_contacts_occ     = con_gpu.cpu().numpy().reshape(nbins) / n_frames
                    aromatic_non_contacts_occ = ncon_gpu.cpu().numpy().reshape(nbins) / n_frames
                    del con_gpu, ncon_gpu
                torch.cuda.empty_cache()

            else:  # CPU path
                occ_flat  = aromatic_occ.ravel()
                con_flat  = aromatic_contacts_occ.ravel()     if have_aro_contacts else None
                ncon_flat = aromatic_non_contacts_occ.ravel() if have_aro_contacts else None
                chunk_size = 5_000
                for fi in tqdm(range(n_frames)):
                    fp    = ring_centers_pos[fi]               # (n_aro, 3)
                    flags = aromatic_contacts[fi] if have_aro_contacts else None
                    for i in range(0, len(shell_voxel_coords), chunk_size):
                        ch   = shell_voxel_coords[i:i+chunk_size]
                        ci   = shell_indices[i:i+chunk_size]
                        d    = np.linalg.norm(
                            ch[:, np.newaxis, :] - fp[np.newaxis, :, :], axis=2)
                        near = d < protein_vdw_radius          # (chunk, n_aro)
                        occ_flat[ci[near.any(axis=1)]] += 1
                        if have_aro_contacts:
                            con_flat[ci[ (near & flags[np.newaxis, :]).any(axis=1)]] += 1
                            ncon_flat[ci[(near & ~flags[np.newaxis, :]).any(axis=1)]] += 1
                aromatic_occ /= n_frames
                if have_aro_contacts:
                    aromatic_contacts_occ     /= n_frames
                    aromatic_non_contacts_occ /= n_frames

        # ========================================================================
        # STEP 8: REMAINING FEATURE TYPES
        # ========================================================================
        # Hydrophobic/positive/negative always use the plain (no-split) kernel —
        # there's no notion of "hydrophobic contact" or "charge contact" tracked
        # upstream, only aromatic and H-bond have a contact/non-contact source.
        # H-bond donor/acceptor use the split kernel only when
        # compute_hbond_contacts() was actually run (have_hbond_contacts),
        # falling back to the plain kernel otherwise.
        # ── Non-aromatic features ──────────────────────────────────────────────
        if len(hydrophobic_atoms) > 0:
            print("Hydrophobic occupancy …")
            hydrophobic_occ = _occ(hydrophobic_atoms)

        if len(hbond_donor_atoms) > 0:
            print("H-bond donor occupancy …")
            if have_hbond_contacts:
                hbond_donors_occ, hbond_donors_contacts_occ, hbond_donors_non_contacts_occ = \
                    _occ_split(hbond_donor_atoms, donor_atom_to_res,
                               self.hbond_contact_frames_pd)
            else:
                hbond_donors_occ = _occ(hbond_donor_atoms)

        if len(hbond_acceptor_atoms) > 0:
            print("H-bond acceptor occupancy …")
            if have_hbond_contacts:
                hbond_acceptors_occ, hbond_acceptors_contacts_occ, hbond_acceptors_non_contacts_occ = \
                    _occ_split(hbond_acceptor_atoms, acceptor_atom_to_res,
                               self.hbond_contact_frames_ld)
            else:
                hbond_acceptors_occ = _occ(hbond_acceptor_atoms)

        if len(positive_atoms) > 0:
            print("Positive charge occupancy …")
            positive_occ = _occ(positive_atoms)

        if len(negative_atoms) > 0:
            print("Negative charge occupancy …")
            negative_occ = _occ(negative_atoms)

        # GPU cleanup — unconditional
        if USE_GPU:
            del voxels_gpu, shell_idx_gpu
            torch.cuda.empty_cache()

        # ========================================================================
        # STEP 9: DERIVE CONTESTED-SPACE MAPS FROM THE FULL-SHELL RESULT
        # ========================================================================
        # Zero out every voxel outside contested_mask rather than recomputing —
        # the full-shell arrays already contain the contested voxels' correct
        # values, since contested_mask ⊆ full_shell_mask.
        # ── Derive contested maps by masking full-shell results ────────────────
        def _mask_to_contested(arr):
            if arr is None:
                return None
            out = arr.copy()
            out[~contested_mask] = 0.0
            return out

        full_maps = {
            'aromatic_occupancy':                     aromatic_occ,
            'aromatic_occupancy_contacts':            aromatic_contacts_occ,
            'aromatic_occupancy_non_contacts':        aromatic_non_contacts_occ,
            'hydrophobic_occupancy':                  hydrophobic_occ,
            'hbond_donors_occupancy':                 hbond_donors_occ,
            'hbond_donors_occupancy_contacts':        hbond_donors_contacts_occ,
            'hbond_donors_occupancy_non_contacts':    hbond_donors_non_contacts_occ,
            'hbond_acceptors_occupancy':              hbond_acceptors_occ,
            'hbond_acceptors_occupancy_contacts':     hbond_acceptors_contacts_occ,
            'hbond_acceptors_occupancy_non_contacts': hbond_acceptors_non_contacts_occ,
            'positive_occupancy':                     positive_occ,
            'negative_occupancy':                     negative_occ,
            'grid_info':                              grid_info,
        }
        contested_maps = {k: _mask_to_contested(v) if k != 'grid_info' else v
                          for k, v in full_maps.items()}

        self.pharmacophore_maps_full      = full_maps
        self.pharmacophore_maps_contested = contested_maps
        return contested_maps, full_maps

    def define_pharmacophore(self):
        """Compute residue-type pharmacophore maps on contested and full-shell spaces.

        Thin orchestration wrapper around compute_pharmacophore_maps().
        Requires compute_negative_space() first; compute_aromatic_contacts()
        is optional but enables the aromatic contact/non-contact split.

        Returns
        -------
        (maps_contested, maps_full) — same as compute_pharmacophore_maps().
        """
        if self.negative_space_data is None:
            raise RuntimeError("Call compute_negative_space() before define_pharmacophore()")
        return self.compute_pharmacophore_maps()

    # ── 6. Output ─────────────────────────────────────────────────────────────

    def save_mrc_files(self, output_dir: str,
                       gaussian_sigma: Optional[float] = None,
                       score_percentile_tiers: Optional[List[int]] = None) -> Dict:
        """Export all computed maps as MRC volume files for PyMOL visualization.

        Writes MRC files organised into subdirectories:
          negative_space/          space masks + free fraction + ligand distance
          growth_features/         chemical feature score maps for growth space
                                   (if compute_growth_space_features() was called)
          pharmacophore_contested/ residue-type occupancy on contested space
          pharmacophore_full/      residue-type occupancy on full shell
                                   (if define_pharmacophore() was called)

        Also writes ligand_centroid.pdb (most representative ligand frame,
        requires scikit-learn).

        Requires compute_negative_space() to have been called first.

        Parameters
        ----------
        output_dir : str
            Root directory for all output files.
        gaussian_sigma : float, optional
            Gaussian smoothing applied to all maps before writing (in voxels).
            None = no smoothing.  Recommended range: 0.5–1.5.
        score_percentile_tiers : list of int, optional
            For each tier N in this list, an additional filtered growth-feature
            map is written retaining only the top-N% highest-scoring voxels.
            Default: [1, 5, 10, 20].

        Returns
        -------
        dict mapping descriptive key → absolute file path for every file written.
        """
        if not MRCFILE_AVAILABLE:
            raise ImportError("mrcfile required — install: pip install mrcfile")
        if self.negative_space_data is None:
            raise RuntimeError(
                "Call compute_negative_space() before save_mrc_files()")

        if score_percentile_tiers is None:
            score_percentile_tiers = [1, 5, 10, 20]

        os.makedirs(output_dir, exist_ok=True)
        mrc_files: Dict = {}

        grid_info = self.negative_space_data['grid_info']
        xmin = grid_info['xmin']
        dx   = grid_info['dx']

        # ── Ligand centroid PDB ───────────────────────────────────────────────
        if SKLEARN_AVAILABLE and self.ligand_traj is not None:
            print("Computing ligand centroid PDB …")
            lig_xyz     = self.ligand_traj.xyz.reshape(self.ligand_traj.n_frames, -1)
            dists_mat   = _sklearn_pairwise_distances(lig_xyz)
            centroid_fi = int(dists_mat.sum(axis=1).argmin())
            ligand_pdb  = os.path.join(output_dir, 'ligand_centroid.pdb')
            self.ligand_traj[centroid_fi].save_pdb(ligand_pdb)
            mrc_files['ligand_centroid_pdb'] = ligand_pdb
            print(f"  ✓ ligand_centroid.pdb")
        elif not SKLEARN_AVAILABLE:
            print("  Warning: scikit-learn not available — ligand centroid PDB skipped")

        # ── Section A: Negative space maps ────────────────────────────────────
        ns_dir = os.path.join(output_dir, 'negative_space')
        os.makedirs(ns_dir, exist_ok=True)
        nd = self.negative_space_data
        print("\nExporting negative space MRC files …")

        for key, filename in [
            ('growth_space_mask',    'growth_space.mrc'),
            ('contested_space_mask', 'contested_space.mrc'),
            ('occupied_space_mask',  'occupied_space.mrc'),
            ('free_fraction',        'free_fraction.mrc'),
        ]:
            fname = os.path.join(ns_dir, filename)
            _write_mrc_field(nd[key].astype(np.float32), xmin, dx, fname, gaussian_sigma)
            mrc_files[key] = fname
            print(f"  ✓ {filename}")

        # Distance to ligand (inf → 0 for MRC compatibility)
        dist_field = np.where(nd['min_dist_to_ligand'] < np.inf,
                              nd['min_dist_to_ligand'], 0.0).astype(np.float32)
        fname = os.path.join(ns_dir, 'distance_to_ligand.mrc')
        _write_mrc_field(dist_field, xmin, dx, fname, gaussian_sigma)
        mrc_files['distance_to_ligand'] = fname
        print(f"  ✓ distance_to_ligand.mrc")

        # Combined categorical: 0=outside shell, 1=growth, 2=contested, 3=occupied
        combined = np.zeros(nd['growth_space_mask'].shape, dtype=np.float32)
        combined[nd['growth_space_mask']]    = 1.0
        combined[nd['contested_space_mask']] = 2.0
        combined[nd['occupied_space_mask']]  = 3.0
        fname = os.path.join(ns_dir, 'combined_space.mrc')
        _write_mrc_field(combined, xmin, dx, fname, gaussian_sigma)
        mrc_files['combined_space'] = fname
        print(f"  ✓ combined_space.mrc")

        # ── Section B: Growth space feature maps ──────────────────────────────
        if self.growth_space_features is not None:
            gf_dir = os.path.join(output_dir, 'growth_features')
            os.makedirs(gf_dir, exist_ok=True)
            print("\nExporting growth feature MRC files …")

            feature_files = [
                ('aromatic_score',        'aromatic_sites.mrc'),
                ('hydrophobic_score',     'hydrophobic_sites.mrc'),
                ('hbond_donor_score',     'hbond_donor_sites.mrc'),
                ('hbond_acceptor_score',  'hbond_acceptor_sites.mrc'),
                ('positive_charge_score', 'positive_charge_sites.mrc'),
                ('negative_charge_score', 'negative_charge_sites.mrc'),
            ]
            for key, filename in feature_files:
                score_arr = self.growth_space_features[key]

                # Full map (all nonzero voxels)
                fname = os.path.join(gf_dir, filename)
                _write_mrc_field(score_arr, xmin, dx, fname)
                mrc_files[f'growth_{key}'] = fname
                print(f"  ✓ {filename}")

                # Percentile-tiered maps: top-N% of nonzero voxels only
                nonzero = score_arr[score_arr > 0]
                if len(nonzero) == 0:
                    print(f"    (skipping tiers for {key}: no nonzero voxels)")
                    continue
                for tier in score_percentile_tiers:
                    threshold     = np.percentile(nonzero, 100 - tier)
                    filtered      = np.where(score_arr >= threshold,
                                             score_arr, 0.0).astype(np.float32)
                    base, ext     = os.path.splitext(filename)
                    tier_filename = f'{base}_top{tier}pct{ext}'
                    tier_fname    = os.path.join(gf_dir, tier_filename)
                    _write_mrc_field(filtered, xmin, dx, tier_fname)
                    mrc_files[f'growth_{key}_top{tier}pct'] = tier_fname
                    n_sur = int(np.count_nonzero(filtered))
                    print(f"    ✓ {tier_filename} "
                          f"({n_sur}/{len(nonzero)} voxels, "
                          f"threshold={threshold:.3f})")

        # ── Section C: Pharmacophore occupancy maps ────────────────────────────
        pharm_targets = [
            ('pharmacophore_contested', self.pharmacophore_maps_contested),
            ('pharmacophore_full',      self.pharmacophore_maps_full),
        ]
        occ_keys = [
            'aromatic_occupancy',
            'aromatic_occupancy_contacts',
            'aromatic_occupancy_non_contacts',
            'hydrophobic_occupancy',
            'hbond_donors_occupancy',
            'hbond_donors_occupancy_contacts',
            'hbond_donors_occupancy_non_contacts',
            'hbond_acceptors_occupancy',
            'hbond_acceptors_occupancy_contacts',
            'hbond_acceptors_occupancy_non_contacts',
            'positive_occupancy',
            'negative_occupancy',
        ]
        for subdir_name, maps_dict in pharm_targets:
            if maps_dict is None:
                continue
            pm_dir = os.path.join(output_dir, subdir_name)
            os.makedirs(pm_dir, exist_ok=True)
            print(f"\nExporting {subdir_name} MRC files …")
            add_tiers = (subdir_name == 'pharmacophore_contested')
            for key in occ_keys:
                field = maps_dict.get(key)
                if field is None:
                    print(f"  Skipping {key} (not computed)")
                    continue
                fname = os.path.join(pm_dir, f'{key}.mrc')
                _write_mrc_field(field.astype(np.float32), xmin, dx,
                                 fname, gaussian_sigma)
                mrc_files[f'{subdir_name}/{key}'] = fname
                print(f"  ✓ {key}.mrc")

                if add_tiers:
                    nonzero = field[field > 0]
                    if len(nonzero) == 0:
                        print(f"    (skipping tiers for {key}: no nonzero voxels)")
                        continue
                    for tier in score_percentile_tiers:
                        threshold  = np.percentile(nonzero, 100 - tier)
                        filtered   = np.where(field >= threshold,
                                              field, 0.0).astype(np.float32)
                        tier_fname = os.path.join(pm_dir, f'{key}_top{tier}pct.mrc')
                        _write_mrc_field(filtered, xmin, dx, tier_fname, gaussian_sigma)
                        mrc_files[f'{subdir_name}/{key}_top{tier}pct'] = tier_fname
                        n_sur = int(np.count_nonzero(filtered))
                        print(f"    ✓ {key}_top{tier}pct.mrc "
                              f"({n_sur}/{len(nonzero)} voxels, "
                              f"threshold={threshold:.3f})")

        return mrc_files
