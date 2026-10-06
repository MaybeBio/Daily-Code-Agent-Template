# ── Default settings ─────────────────────────────────────────────────────────
DEFAULT_LIGAND_RESNAME    = "LIG"
DEFAULT_AROMATIC_CUTOFF   = 5.5   # Å  (MDTraj uses nm: multiply by 0.1)
DEFAULT_CONTACT_CUTOFF      = 0.60   # nm (6 Å) — distance-based contact cutoff
DEFAULT_HYDROPHOBIC_CUTOFF  = 0.40   # nm (4.0 Å) — hydrophobic contact cutoff
DEFAULT_CONTACT_THRESHOLD = 0.30
DEFAULT_OUTPUT_DIR        = "./output"

# ── MRC diff maps (contact vs non-contact) ────────────────────────────────────
DIFF_CATEGORIES = [
    'aromatic_occupancy',
    'hbond_donors_occupancy',
    'hbond_acceptors_occupancy',
]
DIFF_MAP_SETS = ['pharmacophore_full', 'pharmacophore_contested']

# ── Residue classification (used by analyze_topology) ────────────────────────
_STANDARD_AA = {
    'ALA', 'ARG', 'ASN', 'ASP', 'CYS', 'GLN', 'GLU', 'GLY',
    'HIS', 'ILE', 'LEU', 'LYS', 'MET', 'PHE', 'PRO', 'SER',
    'THR', 'TRP', 'TYR', 'VAL', 'CYX', 'HID', 'HIE', 'HIP',
}
_CAPS   = {'ACE', 'NME', 'NHE', 'NMF', 'NH2', 'CT3', 'CT2', 'CT1'}
_WATER  = {'HOH', 'WAT', 'TIP3', 'SOL', 'TIP3P', 'TIP4P', 'SPC'}
_IONS   = {'NA', 'CL', 'K', 'CA', 'MG', 'ZN', 'NA+', 'CL-', 'K+', 'CA2+', 'MG2+'}
_NON_LIGAND = _STANDARD_AA | _CAPS | _WATER | _IONS
