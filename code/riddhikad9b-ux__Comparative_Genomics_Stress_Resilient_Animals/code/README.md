# 🧬 Comparative Genomics and Structural Biophysics of Tardigrade Stress Proteins

**Author:** Riddhika D  
**Email:** riddhika.d9b@gmail.com  

A comprehensive computational pipeline exploring the evolutionary divergence, electrostatic shielding, and intrinsic disorder of extremotolerant tardigrade proteins (*Ramazzottius varieornatus* and *Hypsibius exemplaris*) relative to model metazoan organisms.

---

## 📌 Project Overview
Tardigrades exhibit extraordinary tolerance to ionizing radiation, extreme desiccation, and oxidative stress. This repository contains automated Python scripts to:
1. **Construct Multi-FASTA datasets** of stress-resilient proteins (Dsup, CAHS1) alongside mitochondrial antioxidant orthologs (MnSOD).
2. **Compute global sequence identity matrices** and neighbor-joining phylogenetic trees.
3. **Quantify biophysical properties** (molecular weight, theoretical isoelectric points, and basic amino acid enrichment) using Biopython.
4. **Analyze AlphaFold 3D structures** to evaluate per-residue confidence (pLDDT) and intrinsic disorder (IDR).
5. **Map electrostatic sliding-window basic residue densities** directly into PDB B-factor columns for structural visualization.

---

## 🗂️ Repository Structure

* `extremophile_targets.fasta` — Multi-FASTA database of target and ortholog sequences
* `sequence_identity_matrix.csv` — Pairwise percentage identity matrix
* `biophysical_properties.csv` — Molecular weights, pI, and basic residue percentages
* `conservation_heatmap.png` — Sequence identity heatmap visualization
* `phylogenetic_tree.png` — Neighbor-joining evolutionary tree
* `basic_residue_enrichment.png` — Comparative basic residue bar chart
* `dsup_plddt_profile.png` — AlphaFold pLDDT disorder profile for Dsup
* `dsup_sliding_window_basic_density.png` — Sliding-window electrostatic density curve
* `AF-P0DOW4-F1.pdb` — Raw AlphaFold predicted structure for Dsup (P0DOW4)
* `dsup_electrostatic_mapped.pdb` — Custom PDB with electrostatic sliding-window scores in B-factor

---

## 🚀 Key Findings & Results

*   **Sequence Conservation vs. Divergence:** Housekeeping antioxidant enzymes like MnSOD remain strictly conserved ($>82\%$ identity across species), whereas tardigrade resilience factors (Dsup, CAHS1) exhibit rapid lineage-specific divergence ($<23\%$ identity).
*   **Electrostatic Shielding:** Damage Suppressor (Dsup) is enriched with basic residues ($>34\%$ Lys + Arg) and possesses an elevated isoelectric point ($pI \approx 10.45$), enabling it to form a net positive electrostatic cloud that shields negatively charged DNA from radiation-induced damage.
*   **Intrinsic Disorder:** AlphaFold pLDDT profiling reveals an average confidence score of **52.30** with over **54% disordered residues**, confirming that Dsup functions as an Intrinsically Disordered Protein (IDP) capable of flexible, dynamic chromatin binding.

---

## 💻 Running the Analysis
All analyses can be reproduced using Google Colab or a local Python environment with the required dependencies:
```bash
pip install biopython pandas numpy matplotlib seaborn requests
