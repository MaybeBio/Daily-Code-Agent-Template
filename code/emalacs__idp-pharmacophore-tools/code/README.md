# idp-pharmacophore-tools

Pharmacophore definition from molecular dynamics (MD) simulations of intrinsically disordered
proteins (IDPs). Extracts chemical interaction patterns (aromatic, hydrophobic, H-bond
donor/acceptor, charged) between a small-molecule ligand and an IDP ensemble, computes
contact/occupancy probabilities across a trajectory, and produces pharmacophore models
visualized in PyMOL and Plotly.

This is the installable pipeline package accompanying the paper *"Dynamic Pharmacophore Mapping
for Intrinsically Disordered Drug Targets."* For the interactive Mol* viewer and curated
pharmacophore maps from the paper, see
[Scalone_IDP_Pharmacophore_Mapping_2026](https://github.com/emalacs/Scalone_IDP_Pharmacophore_Mapping_2026).

## Installation

```
pip install idp-pharmacophore-tools
```

RDKit and MDTraj are also available via conda-forge if you prefer conda:

```
conda install -c conda-forge mdtraj rdkit
pip install idp-pharmacophore-tools
```

Optional extras:

```
pip install idp-pharmacophore-tools[gpu]         # torch, for GPU-accelerated voxel analysis
pip install idp-pharmacophore-tools[stats]       # pyblock, for block error estimation
pip install idp-pharmacophore-tools[clustering]  # hdbscan, for the optional graph-clustering backend
pip install idp-pharmacophore-tools[all]         # everything above
```

`deeptime` is a core dependency (not an extra) since `compute_pca_trajectory()` requires it directly, with
no fallback path.

## Usage as a library

```python
from idp_pharmacophore_tools import PharmacophoreTrajectory

sim = PharmacophoreTrajectory("system.gro", "traj.xtc")
sim.load(stride=1)
sim.ligand_align()  # aligns on the entire ligand by default

sim.compute_aromatic_contacts()
sim.compute_contact_probability()
sim.compute_negative_space()
sim.define_pharmacophore()

sim.write_pymol_script("./output")
```

## Usage from the CLI

```
idp-pharmacophore \
    --topology  path/to/system.gro \
    --trajectory path/to/traj.xtc \
    [--ligand-resname LIG] \
    [--align-selection "resname LIG and name C1"] \
    [--contact-threshold 0.3] \
    [--output-dir ./output] \
    [--stride 1] \
    [--offset 0]
```

`--ligand-resname` is auto-detected from the topology if not provided. `--align-selection` is an
MDTraj selection string for the alignment reference atoms; if omitted, the trajectory is aligned
on the entire ligand.

## License

MIT — see [LICENSE](LICENSE).
