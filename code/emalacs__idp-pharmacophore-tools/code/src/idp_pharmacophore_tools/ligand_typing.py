import os
import tempfile
from itertools import product
from typing import Dict, List, Optional, Tuple

import numpy as np

from ._deps import (
    mda, MDA_AVAILABLE,
    Chem, AllChem, rdMolDraw2D, io, Image, RDKIT_AVAILABLE,
    rdDetermineBonds, RDKIT_DETERMINE_BONDS_AVAILABLE,
)
from ._constants import _NON_LIGAND


def _fix_element_cap(element: str) -> str:
    """Normalize element symbol capitalization (e.g. 'CL' → 'Cl', 'c' → 'C')."""
    return element.strip().capitalize()


# ════════════════════════════════════════════════════════════════════════════
# Standalone topology utilities (callable from notebook or load())
# ════════════════════════════════════════════════════════════════════════════

def analyze_topology(topology_path: str, trajectory_path: Optional[str] = None) -> Dict:
    """Scan a topology file to detect ligands, protein composition, and cysteines.

    Parameters
    ----------
    topology_path : str
        Path to .gro or .pdb topology file.
    trajectory_path : str, optional
        Trajectory path (required for some topology formats).

    Returns
    -------
    dict
        Keys: has_ligand, ligand_resname, ligand_atom_names, all_ligands,
        cysteines, n_atoms, n_residues. On failure: {'error': str}.
    """
    if not MDA_AVAILABLE:
        return {'error': 'MDAnalysis not available — install: pip install MDAnalysis'}
    try:
        args = [topology_path] + ([trajectory_path] if trajectory_path else [])
        u = mda.Universe(*args)
        ligands, cysteines = [], []
        for residue in u.residues:
            resname = residue.resname.strip().upper()
            if resname in ('CYS', 'CYX'):
                cysteines.append({'resid': int(residue.resid), 'resname': resname})
            if resname not in _NON_LIGAND:
                ligands.append({
                    'resname': resname,
                    'resid': int(residue.resid),
                    'n_atoms': len(residue.atoms),
                    'atom_names': [a.name for a in residue.atoms],
                })
        has_ligand = bool(ligands)
        first = ligands[0] if has_ligand else None
        return {
            'has_ligand': has_ligand,
            'ligand_resname': first['resname'] if first else None,
            'ligand_atom_names': first['atom_names'] if first else [],
            'all_ligands': ligands,
            'cysteines': cysteines,
            'n_atoms': int(len(u.atoms)),
            'n_residues': int(len(u.residues)),
        }
    except Exception as e:
        return {'error': str(e)}


def extract_ligand_mol(topology_path: str, ligand_resname: str,
                       trajectory_path: Optional[str] = None):
    """Extract the ligand from a topology file and return an RDKit Mol object.

    Uses MDAnalysis to read the topology (handles .gro element guessing),
    writes a temporary PDB with correct element columns, then reads with RDKit.

    Parameters
    ----------
    topology_path : str
        Path to .gro or .pdb topology file.
    ligand_resname : str
        Residue name of the ligand.
    trajectory_path : str, optional
        Trajectory path (used if topology lacks coordinates).

    Returns
    -------
    rdkit.Chem.Mol
    """
    if not MDA_AVAILABLE:
        raise ImportError("MDAnalysis required — install: pip install MDAnalysis")
    if not RDKIT_AVAILABLE:
        raise ImportError("RDKit required — install: conda install -c conda-forge rdkit")

    args = [topology_path] + ([trajectory_path] if trajectory_path else [])
    u = mda.Universe(*args)
    ligand = u.select_atoms(f"resname {ligand_resname}")

    if len(ligand) == 0:
        raise ValueError(f"No atoms found for ligand resname '{ligand_resname}'")

    print(f"Extracting ligand '{ligand_resname}': {len(ligand)} atoms")

    # Guess element types — .gro files lack element info
    try:
        elements = [_fix_element_cap(a.element) for a in ligand.atoms]
    except Exception:
        from MDAnalysis.topology.guessers import guess_types
        elements = [_fix_element_cap(e) for e in guess_types(ligand.names)]
        for atom, elem in zip(ligand.atoms, elements):
            atom.type = elem

    # Write temporary PDB with explicit element columns (cols 77-78)
    with tempfile.NamedTemporaryFile(mode='w', suffix='.pdb', delete=False) as tmp:
        tmp_path = tmp.name

    coords = ligand.positions
    with open(tmp_path, 'w') as f:
        for i, (atom, elem) in enumerate(zip(ligand.atoms, elements)):
            x, y, z = coords[i]
            f.write(
                f"ATOM  {i+1:5d}  {atom.name:<4s}LIG     1    "
                f"{x:8.3f}{y:8.3f}{z:8.3f}  1.00  0.00          {elem:>2s}\n"
            )
        f.write("END\n")

    mol = Chem.MolFromPDBFile(tmp_path, removeHs=False, sanitize=False, proximityBonding=True)
    os.unlink(tmp_path)

    if mol is None:
        raise RuntimeError("RDKit could not parse the extracted ligand PDB")

    # .gro files carry no bond order info, so proximityBonding assigns all bonds as single.
    # DetermineBondOrders infers correct bond orders from 3D geometry + valence rules,
    # which is required for aromaticity perception to work during sanitization.
    # Assumes a neutral ligand (charge=0) — adjust if the ligand is charged.
    if rdDetermineBonds is not None:
        try:
            rdDetermineBonds.DetermineBondOrders(mol, charge=0)
        except Exception as e:
            print(f"Warning: bond order determination failed ({e}) — "
                  "aromaticity may not be detected correctly")

    try:
        Chem.SanitizeMol(mol, catchErrors=True)
    except Exception:
        try:
            Chem.SanitizeMol(mol, sanitizeOps=Chem.SANITIZE_ALL ^ Chem.SANITIZE_KEKULIZE)
        except Exception:
            print("Warning: molecule could not be fully sanitized — some features may be limited")

    print(f"Ligand RDKit mol: {mol.GetNumAtoms()} atoms")
    return mol


def draw_molecule_with_labels(mol, width: int = 900, height: int = 900):
    """Draw the ligand as a 2D structure with atom indices labeled.

    Designed for inline display in Jupyter (returns a PIL Image — no file saved).

    Parameters
    ----------
    mol : rdkit.Chem.Mol
        RDKit molecule (e.g. sim.ligand_mol or from extract_ligand_mol()).
    width, height : int
        Image dimensions in pixels.

    Returns
    -------
    (PIL.Image, rdkit.Chem.Mol) or None
    """
    if not RDKIT_AVAILABLE:
        print("Warning: RDKit/PIL not available")
        return None
    if mol is None:
        print("Warning: mol is None")
        return None
    try:
        mol = Chem.AddHs(mol, addCoords=True)
        AllChem.Compute2DCoords(mol)
        for atom in mol.GetAtoms():
            if atom.GetAtomicNum() == 1:
                continue
            info = atom.GetMonomerInfo()
            name = info.GetName().strip() if info else ''
            if name:
                atom.SetProp('atomNote', name)
        drawer = rdMolDraw2D.MolDraw2DCairo(width, height)
        drawer.drawOptions().addAtomIndices = True
        drawer.DrawMolecule(mol)
        drawer.FinishDrawing()
        img = Image.open(io.BytesIO(drawer.GetDrawingText()))
        return img, mol
    except Exception as e:
        print(f"Error drawing molecule: {e}")
        return None


class LigandTypingMixin:

    # ── 2. Ligand feature typing (RDKit) ─────────────────────────────────────

    def get_ligand_rings(self) -> List[Dict]:
        """Detect aromatic and aliphatic rings in the ligand using RDKit.

        Also populates self._ligand_aromatic_atom_names (atom names from the
        PDB monomer info) for use by get_atom_property().

        Returns
        -------
        list of dicts: [{'atoms': [idx, ...], 'atom_names': [str, ...], 'size': int, 'aromatic': bool}, ...]

        Note
        ----
        Atom indices are RDKit indices, not MDTraj indices.
        Index-name consistency to be validated during benchmarking.

        Manual override
        ---------------
        If auto-detection gives wrong results, assign a replacement list to
        ``self._manual_rings`` before calling this method (or before calling
        ``compute_aromatic_contacts``).  Each entry requires only
        ``'atom_names'`` and ``'aromatic'``; ``'size'`` is filled in
        automatically::

            sim._manual_rings = [
                {'atom_names': ['C1', 'C2', 'C3', 'C4', 'C5', 'C6'], 'aromatic': True},
                {'atom_names': ['C7', 'C8', 'N1', 'C9', 'C10'],       'aromatic': True},
            ]

        Set ``sim._manual_rings = None`` to revert to automatic detection.
        """
        if self._manual_rings is not None:
            aromatic_names = set()
            normalised = []
            for entry in self._manual_rings:
                names = list(entry['atom_names'])
                is_aromatic = bool(entry.get('aromatic', True))
                normalised.append({
                    'atoms':      list(entry.get('atoms', [])),
                    'atom_names': names,
                    'size':       len(names),
                    'aromatic':   is_aromatic,
                })
                if is_aromatic:
                    aromatic_names.update(names)
            self._ligand_aromatic_atom_names = aromatic_names
            print(f"get_ligand_rings: using {len(normalised)} manual ring(s) "
                  f"({sum(r['aromatic'] for r in normalised)} aromatic)")
            return normalised

        if self.ligand_mol is None:
            return []
        ring_info = self.ligand_mol.GetRingInfo()
        rings, aromatic_names = [], set()
        for ring_atoms in ring_info.AtomRings():
            ring_list   = list(ring_atoms)
            is_aromatic = all(
                self.ligand_mol.GetAtomWithIdx(i).GetIsAromatic() for i in ring_list
            )
            atom_names = []
            for idx in ring_list:
                atom = self.ligand_mol.GetAtomWithIdx(idx)
                info = atom.GetMonomerInfo()
                name = info.GetName().strip() if info else atom.GetSymbol()
                atom_names.append(name)
            rings.append({
                'atoms': ring_list,
                'atom_names': atom_names,
                'size': len(ring_list),
                'aromatic': is_aromatic,
            })
            if is_aromatic:
                aromatic_names.update(atom_names)
        self._ligand_aromatic_atom_names = aromatic_names
        return rings

    def get_ligand_hbond_pairs(self) -> List[Tuple[int, int]]:
        """Detect H-bond donor pairs (heavy atom, H) in the ligand using RDKit.

        Returns
        -------
        list of (heavy_atom_idx, hydrogen_idx) tuples — RDKit indices.

        Note
        ----
        RDKit indices ≠ MDTraj indices — validate during benchmarking.
        """
        if self.ligand_mol is None:
            return []
        pairs = []
        for atom in self.ligand_mol.GetAtoms():
            if atom.GetSymbol() in ('N', 'O'):
                for neighbor in atom.GetNeighbors():
                    if neighbor.GetSymbol() == 'H':
                        pairs.append((atom.GetIdx(), neighbor.GetIdx()))
        return pairs

    def get_atom_property(self, atom_name: str) -> str:
        """Classify a ligand atom by chemical property.

        Parameters
        ----------
        atom_name : str
            Atom name as it appears in the MDTraj topology.

        Returns
        -------
        'aromatic' | 'nonpolar' | 'polar'

        Note
        ----
        Call get_ligand_rings() before this method to populate the aromatic
        atom name set. Name matching between MDTraj and RDKit to be validated
        during benchmarking.
        """
        in_ring = atom_name in self._ligand_aromatic_atom_names
        if 'C' in atom_name:
            return 'aromatic' if in_ring else 'nonpolar'
        return 'aromatic' if in_ring else 'polar'

    # ── 3. Protein topology helpers ───────────────────────────────────────────

    def get_protein_rings(self) -> Tuple:
        """Get aromatic ring atom indices for all aromatic protein residues.

        Returns
        -------
        (protein_rings, protein_rings_index, ring_atoms_by_resname)
        - protein_rings        : list of atom index arrays (prot_lig context)
        - protein_rings_index  : list of residue indices
        - ring_atoms_by_resname: dict mapping residue name to MDTraj selection string
        """
        ring_atoms_by_resname = {
            'TYR': 'name CG CD1 CD2 CE1 CE2 CZ',
            'TRP': 'name CG CD1 NE1 CE2 CD2 CZ2 CE3 CZ3 CH2',
            'HIS': 'name CG ND1 CE1 NE2 CD2',
            'PHE': 'name CG CD1 CD2 CE1 CE2 CZ',
        }

        # Residues with aromatic rings - good for π-π interactions
        # TRP = Tryptophan (indole ring)
        # TYR = Tyrosine (phenol ring)
        # PHE = Phenylalanine (benzyl ring)
        # HIS = Histidine (imidazole ring)
        protein_rings, protein_rings_index = [], []
        aro_ca = self.prot_lig_top.select("resname TYR PHE HIS TRP and name CA")
        for i in aro_ca:
            atom = self.prot_lig_top.atom(i)
            sel  = ring_atoms_by_resname.get(atom.residue.name)
            if sel:
                ring = self.prot_lig_top.select(f"resid {atom.residue.index} and {sel}")
                protein_rings.append(ring)
                protein_rings_index.append(atom.residue.index)
        return protein_rings, protein_rings_index, ring_atoms_by_resname

    def get_protein_ligand_pairs(self) -> np.ndarray:
        """Return all (protein_residue_idx, ligand_residue_idx) index pairs."""
        return np.array(list(product(self.protein_residue_numbers, self.ligand_residue_numbers)))

    def get_residue_atoms_dict(self) -> Dict:
        """Map each protein residue label to its atom index array."""
        return {
            f'{r.name}_{r.resSeq + self.offset}': self.protein_top.select(f'resid {r.index}')
            for r in self.protein_top.residues
        }

    def get_hbonded_atoms_dict(self) -> Dict:
        """Map each heavy atom (bonded to H) to its hydrogen partner.

        Used when reconstructing H-bond pharmacophore features.
        """
        atom_withH = {}
        for bond in self.protein_traj.topology.bonds:
            if bond[1].element.symbol == 'H':
                atom_withH[bond[0]] = bond[1]
        return atom_withH

    def get_atom_name_dict(self) -> Dict:
        """Map atom index to '{name}_{resname}_{resSeq}' label (prot_lig context)."""
        return {
            atom.index: f'{atom.name}_{atom.residue.name}_{atom.residue.resSeq + self.offset}'
            for atom in self.prot_lig_top.atoms
        }

    def convert_ligand_atom_name(self, ligand_atom: str) -> np.ndarray:
        """Return MDTraj atom indices for a ligand atom name (prot_lig context)."""
        return self.prot_lig_top.select(f'resname {self.ligand_resname} and name {ligand_atom}')
