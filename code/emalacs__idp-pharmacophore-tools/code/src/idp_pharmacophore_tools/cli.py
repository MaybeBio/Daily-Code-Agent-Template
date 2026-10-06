import argparse
import os

from .core import PharmacophoreTrajectory
from ._constants import DEFAULT_CONTACT_THRESHOLD, DEFAULT_OUTPUT_DIR


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Compute pharmacophores from an MD simulation of an IDP.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--topology",   required=True, help="Topology file (.gro or .pdb)")
    p.add_argument("--trajectory", required=True, help="Trajectory file (.xtc or .dcd)")
    p.add_argument("--ligand-resname", default=None,
                   help="Ligand residue name (auto-detected if not provided)")
    p.add_argument("--contact-threshold", type=float, default=DEFAULT_CONTACT_THRESHOLD,
                   help="Minimum contact probability for pharmacophore inclusion")
    p.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR,
                   help="Directory for output files")
    p.add_argument("--stride", type=int, default=1,
                   help="Load every N-th trajectory frame")
    p.add_argument("--offset", type=int, default=0,
                   help="Residue number offset for experimental numbering convention")
    p.add_argument("--align-selection", default=None,
                   help="MDTraj selection string for ligand_align() reference atoms "
                        "(default: align on the entire ligand)")
    return p


def main(argv=None) -> None:
    args = _build_parser().parse_args(argv)
    os.makedirs(args.output_dir, exist_ok=True)

    sim = PharmacophoreTrajectory(args.topology, args.trajectory)
    sim.load(
        ligand_resname=args.ligand_resname,
        stride=args.stride,
        offset=args.offset,
    )

    # Contact Probabilities
    sim.compute_aromatic_contacts()
    sim.compute_contact_probability()
    sim.compute_hydrophobic_contacts()
    sim.compute_hbond_contacts()

    # Pharmacophore definitions
    sim.ligand_align(args.align_selection)
    sim.compute_negative_space()
    sim.define_pharmacophore()
    sim.compute_growth_space_features()


    sim.write_pymol_script(args.output_dir)
    print(f"PyMOL output  → {args.output_dir}")

    # html_path = os.path.join(args.output_dir, "contact_probability.html")
    # fig = sim.plot_contact_probability()
    # sim.save_plot(fig, html_path)
    # print(f"Plotly figure → {html_path}")


if __name__ == "__main__":
    main()
