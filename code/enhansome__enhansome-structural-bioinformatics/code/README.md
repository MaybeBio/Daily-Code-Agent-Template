# Awesome Structural BioInformatics with stars

*A curated list of awesome structural bioinformatics frameworks, libraries, software and resources.*

> So let it not look strange if I claim that it is much easier to explain the movement of the giant celestial bodies than to interpret in mechanical terms the origination of just a single caterpillar or a tiny grass. - Immanuel Kant, *Natural History and the Theory of Heaven*, 1755

Books on Cheminformatics, [Bioinformatics](http://thegrantlab.org/teaching/material/Intro_Structural_Bioinformatics_Barry.pdf), Quantum Chemistry strangle the subject to sleep 😴 and command a wild price 🤑 for the naps they induce.

Want a better way to learn than some random repo on github?

Spend 4-12 years of your life and hundreds of thousands of dollars chasing a paper with a stamp on it 🥇.

Or feed yourself 🍼.

Information should be cheap, fast enjoyable, silly, shared, disproven, contested, and most of all free.

Knowledge hodlers, and innovation stifflers are boring and old. This is for the young of mind and young of spirit 🚼 that love to dock & fold.

[Proteins](https://github.com/Ramb0a/awesome-structural-bioinformatics#protein-bioinformatics) ⭐ 81 | 🐛 0 | 🌐 Python | 📅 2023-05-05

[Genomics](https://github.com/Ramb0a/awesome-structural-bioinformatics#genomics) ⭐ 81 | 🐛 0 | 🌐 Python | 📅 2023-05-05

# Proteomics

## Protein Folding

> Structure-function relationships are the fundamental object of knowledge in protein chemistry; they allow us to rationally design drugs, engineer proteins with new functions, and understand why mutations cause disease. [- On The Origin of Proteins](https://www.chemistryworld.com/features/on-the-origin-of-proteins/3004719.article)

> There is now a testable explanation for how a protein can fold so quickly: A protein solves its large global optimization problem as a series of smaller local optimization problems, growing and assembling the native structure from peptide fragments, local structures first. [- The Protein Folding Problem](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC2443096/)

![Simpsons](simpsons.gif)

The protein folding problem consists of three closely related puzzles:

* (a) What is the folding code?
* (b) What is the folding mechanism?
* (c) Can we predict the native structure of a protein from its amino acid sequence? [source](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC2443096/)

### Deep Learning Protein Folding

#### [AlphaFold 14](https://www.predictioncenter.org/casp14/doc/presentations/2020_12_01_TS_predictor_AlphaFold2.pdf)

* [:computer: Code](https://github.com/deepmind/alphafold) ⭐ 14,867 | 🐛 309 | 🌐 Python | 📅 2026-04-22
* [:book: Paper 2](https://www.nature.com/articles/s41586-021-03819-2_reference.pdf)
* [:book: Paper](https://www.nature.com/articles/s41586-019-1923-7.epdf?author_access_token=Z_KaZKDqtKzbE7Wd5HtwI9RgN0jAjWel9jnR3ZoTv0MCcgAwHMgRx9mvLjNQdB2TlQQaa7l420UCtGo8vYQ39gg8lFWR9mAZtvsN_1PrccXfIbc6e-tGSgazNL_XdtQzn1PHfy21qdcxV7Pw-k3htw%3D%3D)
* [:newspaper: article](https://deepmind.com/blog/article/AlphaFold-Using-AI-for-scientific-discovery)
* [AlpahFold 14 Results Discussion](https://dasher.wustl.edu/bio5357/discussion/oxford-alphafold2.pdf)
* [What AlphaFold means for Structural BioInformatics](https://ammiellewb.medium.com/what-alphafold-means-for-structural-bioinformatics-78117adb7d11)
* [AlphaFold 2 Explained](https://youtu.be/B9PL__gVxLI) - Yanick Video
* [Illustrated Transformer](kjalammar.github.io/illustrated-transformer/)
* [Transformers from Scratch](http://peterbloem.nl/blog/transformers)

#### [AlphaFold 13](https://www.predictioncenter.org/CASP13/doc/presentations/Pred_CASP13-Structure-AlphaFold-Jumper.pdf)

* [:floppy\_disk: Code](https://github.com/deepmind/deepmind-research/tree/master/alphafold_casp13) ⭐ 15,211 | 🐛 359 | 🌐 Jupyter Notebook | 📅 2026-06-17
* [:floppy\_disk: Code](https://github.com/dellacortelab/prospr) ⭐ 415 | 🐛 14 | 🌐 Python | 📅 2022-10-06 - Prospr - Open Source Implementation
* [:book: Prospr Paper](https://www.biorxiv.org/content/10.1101/830273v1)
* [AlphaFold @ Casp13: What Just Happened?](https://moalquraishi.wordpress.com/2018/12/09/alphafold-casp13-what-just-happened/)

#### [MiniFold](https://github.com/hypnopump/MiniFold) ⭐ 219 | 🐛 8 | 🌐 Jupyter Notebook | 📅 2021-03-25 - Open Source toy example of AlphaFold 13 algorithm

> The DeepMind work presented @ CASP was not a technological breakthrough (they did not invent any new type of AI) but an engineering one: they applied well-known AI algorithms to a problem along with lots of data and computing power and found a great solution through model design, feature engineering, model ensembling and so on...

> Based on the premise exposed before, the aim of this project is to build a model suitable for protein 3D structure prediction inspired by AlphaFold and many other AI solutions that may appear and achieve SOTA results.

![MiniFold](minifold.png)

> Two different residual neural networks (ResNets) are used to predict angles between adjacent aminoacids (AAs) and distance between every pair of AAs of a protein. For distance prediction a 2D Resnet was used while for angles prediction a 1D Resnet was used.

#### PDNet

> As deep learning algorithms drive the progress in protein structure prediction, a lot remains to be studied at this merging superhighway of deep learning and protein structure prediction. Recent findings show that inter-residue distance prediction, a more granular version of the well-known contact prediction problem, is a key to predicting accurate models. However, deep learning methods that predict these distances are still in the early stages of their development. To advance these methods and develop other novel methods, a need exists for a small and representative dataset packaged for faster development and testing. In this work, we introduce protein distance net (PDNET), a framework that consists of one such representative dataset along with the scripts for training and testing deep learning methods. The framework also includes all the scripts that were used to curate the dataset, and generate the input features and distance maps.

[ 💻 Github](https://github.com/ba-lab/pdnet/) ⭐ 36 | 🐛 2 | 🌐 Jupyter Notebook | 📅 2021-05-30

[ :book: Paper](https://www.nature.com/articles/s41598-020-70181-0)

[ :vhs: YouTube](https://youtu.be/uAIuA1O7iE8)

## Protein - Ligand Docking

*Tools for exploring how two or more molecular structures fit together*

[AutoDock](http://autodock.scripps.edu/) - suite of automated docking tools designed to predict how small molecules bind to a receptor of known 3D structure

[AutoDock Vina](http://vina.scripps.edu/) - significantly improves the average accuracy of the binding mode predictions compared to AutoDock

[AutoDock GPU](https://github.com/ccsb-scripps/AutoDock-GPU) ⭐ 614 | 🐛 89 | 🌐 C++ | 📅 2026-08-11

* [:book: Paper](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC3041641/)

[Gnina](https://github.com/gnina/gnina) ⭐ 985 | 🐛 24 | 🌐 C++ | 📅 2026-06-29 - deep learning framework for molecular docking -inside deepchem (/dock/pose\_generation.py)

[GOMoDo](https://gomodo.grs.kfa-juelich.de/php/about.php) - GPCR online modeling and docking server

[Smina](https://github.com/mwojcikowski/smina) ⭐ 151 | 🐛 0 | 🌐 C++ | 📅 2018-11-18 used for minimization (local\_only) as opposed to of docking, makes Vina much easer to use and 10-20x faster. Docking performance is about the same since partial charge calculation and file i/o isn't such a big part of the performance.

"Docking is a method which predicts the prefered orientation of one molecule to a second when bound to each other to form a stable complex. Knoweldge of the prefered orientation in turn may be used to predict the strength of association or binding affinity between two molecules using scoring functions."

* Pose - A conformation of the receptor and ligand molecules showing some intermolecular interactions (which may include hydrogen bonds as well as hydrophobic contacts

* Posings - The process of searching for a pose in which there are favorable interactions between the receptor and the ligand molecules.

* Scoring - The process of evaluating a particular pose using a number of descriptive features like number of intermolecular interactions including hydrogen bonds and hydrophobic contacts.

* The best docking algorithm should be the one with the best scoring function and
  the best searching algorithm
  [source](https://www.beilstein-journals.org/bjoc/articles/12/267)

* No single docking methods performs well for all targets and the quality of
  docking results is highly dependent on the ligand and binding site of
  interest [source](https://www.beilstein-journals.org/bjoc/articles/12/267)

In the early 1990s many approved HIV protease inhibitors were developed to target HIV infections using structure-based molecular docking. [source](https://www.beilstein-journals.org/bjoc/articles/12/267)

* Saquinavir
* Amprenavir

### [A Geometric Approach to MacroMolecule Ligand Interactions](https://www.sciencedirect.com/science/article/abs/pii/002228368290153X#:~:text=A%20geometric%20approach%20to%20macromolecule%2Dligand%20interactions%E2%98%86\&text=Algorithms%20are%20presented%20that%20examine,sites%20on%20a%20macromolecular%20surface.)

One of the first appearances of Molecular Docking is said to have been this 1982 paper.

They tell us Molecular Docking = "To position two molecules so that they interact favorably with one another..."

How???

> Our approach is to reduce the number of degrees of freedom using simplifying
> assumptions that still retain some correspondence to a situation of biochemical
> interest. Specifically, we treat the geometric (hard sphere) interactions of two rigid
> bodies, where one body (the “receptor”) contains “pockets” or “grooves” that form
> binding sites for the second object, which we will call the “ligand”. Our goal is to fix
> the six degrees of freedom (3 translations and 3 orientations) that determine the
> best relative positions of the two objects.

> Does the program reproduce known ligand-receptor geometries? If so, does it also provide alternative structures that are geometrically
> reasonable? To these ends, we have examined two systems for which the ligand receptor
> geometry has been established by crystallographic means.

What is the result of this Docking?

> (1) Structures quite near the “correct” structures are readily recovered and
> identified as feasible solutions.
> (2) Other families of structures are found that are geometrically reasonable and
> that can be tested by simple scoring schemes, chemical intuition, or visual
> inspection with computer graphics.

> Without allowing molecular flexibility, many aspects of ligand-receptor interactions are not properly described.

> A common approach to docking combines a scoring function with an optimization algorithm. The scoring function quantifies the favorability of the protein-ligand interactions in a single pose, whichcan be conceptualized as a point in a continuous conformation space. A stochastic global optimization algorithm is used to explore and sample this conformation space. Then, local optimization is employed on the sampled points, usually by iteratively adjusting the pose in search of a local extremum of the scoring function. Ideally, the scoring function is differentiable to support efficient gradient-based optimization.

> The information obtained from the docking technique can be used to suggest the binding energy, free energy and stability of complexes. At present, docking technique is utilized to predict the tentative binding parameters of ligand-receptor complex beforehand.

> There are various databases available, which offer information on small ligand molecules such as CSD (Cambridge Structural Database), ACD (Available Chemical Directory), MDDR (MDL Drug Data Report) and NCI (National Cancer Institute Database).

### Scoring Function

![Goal](goal.gif)

There are two common approaches to building a score function:

* **potentials of mean force**
  * often called statistics- or Boltzmann-based force fields
  * measuring distance as a reflection of statistical tendencies within proteins
  * . One takes a large set of proteins, collects statistics and converts them to a score function. One then expects this function to work well for proteins not included in its parameterisation.
* **an optimization calculation**
  * select underlying basis function
    * quasi-Lennard-Jones
    * various sigmoidal functions
  * We can say that the correct structure is whatever is given in the protein data bank, but unfortunately, there is almost an infinity of incorrect structures for a sequence and one would like the score function to penalize all of them
  * One way to encode this idea is to adopt a statistical approach and try to consider the distribution of incorrect structures
    [source](http://web.stanford.edu/class/cs273/refs/torda_chapter_proteomics.pdf)

Allowing gaps and insertions at any position and of any length leads to a combinatorial explosion of possibilities. The calculation can be made tractable by restricting the search space and forbidding gaps except in recognised loops in template structures.

There is a score function and a fast method for producing the best possible sequence to structure alignments and thus the best models possible. Unfortunately, the problem is still not solved,

Scoring Functions in MD can be categorized into:

* **knowledge based** - stastical potentials, frequency of interaction occurance,
  Boltzmann distribution, dataset dependent
* **force-field based** - energy functions via molecular mechanics, coulombic
  interactions, van der Waals interactions (Lennard-Jones potential)
  \* CHARMM (chemistry at Harvard macromolecular mechanics)
  \* AMBER (assisted model building and energy refinement)
* **empirical** - binding free energy calculated as the weighted sum of
  unccorrelated terms,(example - hydrogen bonds, hydrophobicity), Regression
  analysis find the best weights for each term
  \* HYDE (part of BioSolveIT tools)
  \* ChemScore
  \* SCORE
* **consensus** - combines scoring functions types into ensemble

  ```
  * X-CSCORE
  * MultiScore
  ```

## Protein Data Sources

![Prometheus](prometheus.gif)

[CATH/Gene3D](https://www.cathdb.info/) - 151 Million Protein Domains Classified into 5,481 Superfamilies

[NCBI Conserved Domains Database](https://www.ncbi.nlm.nih.gov/Structure/cdd/wrpsb.cgi) - resource for the annotation of functional units in proteins

[Protein Data Bank](https://www.rcsb.org/)

[Scop 2](https://scop.mrc-lmb.cam.ac.uk/) - Structural Classification of Proteins

[UniProt](https://www.uniprot.org/) -  comprehensive, high-quality and freely accessible resource of protein sequence and functional information.

[Fold@Home](https://foldingathome.org/about/)

## Fusion Proteins

### Software

[ChimPipe](https://github.com/Chimera-tools/ChimPipe#:~:text=ChimPipe%20is%20a%20computational%20method,junctions%20at%20base%2Dpair%20resolution.) ⭐ 15 | 🐛 1 | 🌐 Awk | 📅 2026-01-22 - ChimPipe is a computational method for the detection of novel transcription-induced chimeric transcripts and fusion genes from Illumina Paired-End RNA-seq data. It combines junction spanning and paired-end read information to accurately detect chimeric splice junctions at base-pair resolution.

[DeepNF](https://github.com/VGligorijevic/deepNF) ⭐ 32 | 🐛 6 | 🌐 Python | 📅 2020-05-04 - Deep network fusion for protein function prediction | 📖 [paper](https://academic.oup.com/bioinformatics/article/34/22/3873/5026651)

[DeepPrior](https://github.com/bioinformatics-polito/DEEPrior) ⭐ 7 | 🐛 4 | 🌐 Python | 📅 2023-05-22 - predicts the probability of a gene fusion being a driver of an oncogenic process by directly exploiting the amino acid sequence of the fused protein, and it can prioritize gene fusions from different tumors. Unlike state-of-the-art tools, it also supports easy retraining and re-adaptation of the model | 📖 [paper](https://academic.oup.com/bioinformatics/article/36/10/3248/5722203)

[DeFuse](https://github.com/amcpherson/defuse) ⭐ 8 | 🐛 3 | 🌐 C++ | 📅 2021-02-15 - gene fusion discovery using RNA-Seq data. The software uses clusters of discordant paired end alignments to inform a split read alignment analysis for finding fusion boundaries | 📖 [paper](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC3098195/)

[FusionCatcher](https://github.com/ndaniel/fusioncatcher) ⭐ 154 | 🐛 47 | 🌐 Python | 📅 2026-04-16 - Finder of somatic fusion-genes in RNA-seq data

[Jaffa](https://github.com/Oshlack/JAFFA) ⭐ 119 | 🐛 21 | 🌐 C++ | 📅 2026-08-25 - JAFFA is a multi-step pipeline that takes either raw RNA-Seq reads, or pre-assembled transcripts, then searches for gene fusions

[StarFusion](https://github.com/STAR-Fusion/STAR-Fusion/wiki) ⭐ 255 | 🐛 159 | 🌐 Perl | 📅 2026-04-18 | 📖 [paper](https://genomebiology.biomedcentral.com/articles/10.1186/s13059-019-1842-9)

### Groups

[The 5th Annual Fusion Protein Therapeutics Conference](https://www.pegsummit.com/Protein-Therapeutics)

[Fusion Oncoproteins in Childhood Cancers (FusOnC2) Consortium](https://www.cancer.gov/research/key-initiatives/moonshot-cancer-initiative/implementation/childhood-cancer-research)

### Articles and References

# Genomics

Human genome = 20K+ genes 👖 each responsible for the instructions of building a single protein; encoded within 6 feet of DNA.

DNA 🧬 is the 'instruction manual of life' (thankfully not written by Ikea 🪑 )

Life is encoded in digital form G/C || T/A nucleotide base pairs.

DNA is encoded ('transcribed) into mRNA and then decoded ('translated) into Proteins. Along the way alot of good and bad stuff happens in the [latent space](https://stats.stackexchange.com/questions/442352/what-is-a-latent-space).

To make the DNA -> RNA transcribing happen - RNA takes a DNA strands - the template strand that runs from 3' to 5' (prime) - and it is uses to form single stranded RNA with all T's replaced by U's. (Thymine replaced by Uracil). The RNA now runs 5' to 3' prime and is identical to the non-template strand DNA sequence (the coding strand), except again Thymine is replaced by Uracil.

```python

import Bio
from Bio.Seq import Seq

dna = Seq("ACGTTTATCGATCGA")
mRNA = dna.transcribe()
protein = mRNA.translate()

print(dna)
print(mRNA)
print(protein)

>>> ACGTTTATCGATCGA
>>> ACGUUUAUCGAUCGA
>>> TFIDR

```

From the template strand -> RNA strand transcription, translation happens when RNA is turned into proteins via the reading of codons - three letter RNA sequences that encode into specific amino acids. The tranlation looks like this codon table:

![Codon Table](https://upload.wikimedia.org/wikipedia/commons/thumb/7/70/Aminoacids_table.svg/1920px-Aminoacids_table.svg.png)

Genes come in **Alleles**, the variations of the gene (example gene = hair color, allele = red hair 👩‍🦰 ||  blonde hair 👱‍♂️)

> Geneomics is the study of all genes in an organism to understand their molecular organization, function, interaction and evolutionary history.

Genomics begins with the discoveries of [Gregor Mendel](https://www.britannica.com/biography/Gregor-Mendel)

![Griffith Experiment](https://upload.wikimedia.org/wikipedia/commons/thumb/6/6a/Griffith_experiment.svg/1432px-Griffith_experiment.svg.png)

## Genomics Software

[Deep Variant](https://github.com/google/deepvariant) ⭐ 3,814 | 🐛 6 | 🌐 Python | 📅 2026-09-30 - analysis pipeline that uses a deep neural network to call genetic variants from next-generation DNA sequencing data

[NVIDIA Clara Parabricks Pipelines](https://docs.nvidia.com/clara/parabricks/v3.5/text/software_overview.html) - perform secondary analysis of next generation sequencing (NGS) DNA and RNA data, blazing fast speeds and low cost. Can analyze whole human genomes in about 45 minutes. Includes Deep Variant.

* [AWS Clara Parabrick Pipeline Setup](https://aws.amazon.com/marketplace/pp/prodview-apbngojlskcyq) \~ $4 per hour.

[BioWasm](https://github.com/biowasm/biowasm) ⭐ 277 | 🐛 8 | 🌐 HTML | 📅 2026-10-01 - WebAssembly modules for genomics

[FastQ Bio](https://github.com/robertaboukhalil/fastq.bio) ⭐ 104 | 🐛 0 | 🌐 Svelte | 📅 2024-08-30 - An interactive web tool for quality control of DNA sequencing data

[Minimap2](https://github.com/lh3/minimap2) ⭐ 2,251 | 🐛 77 | 🌐 C | 📅 2026-05-19  - sequence alignment program that aligns DNA or mRNA sequences against a large reference database. For >100bp Illumina short reads, minimap2 is three times as fast as BWA-MEM and Bowtie2, and as accurate on simulated data. | [paper](https://academic.oup.com/bioinformatics/article/34/18/3094/4994778)

[gBWT](https://github.com/jltsiren/gbwt) ⭐ 63 | 🐛 1 | 🌐 C++ | 📅 2026-09-30 -  graph extension (gPBWT) of the positional Burrows-Wheeler transform (PBWT)

* [gBWT in Rust](https://github.com/jltsiren/gbwt-rs) ⭐ 46 | 🐛 1 | 🌐 Rust | 📅 2026-09-14

[VG](https://github.com/vgteam/vg) ⭐ 1,343 | 🐛 388 | 🌐 C++ | 📅 2026-10-02 - tools for working with genome variation graphs

[Cello](https://github.com/CIDARLAB/Cello-v2) ⭐ 74 | 🐛 33 | 🌐 Java | 📅 2022-05-16 - Genetic Circuit Design

## Genomics Resources

🍼 [Genome in a Bottle](https://www.nist.gov/programs-projects/genome-bottle) - develop the technical infrastructure (reference standards, reference methods, and reference data) to enable translation of whole human genome sequencing to clinical practice and innovations in technologies.

[Online Needleman-Wunsch Example](https://berthub.eu/nwunsch/) || [Example II](http://experiments.mostafa.io/public/needleman-wunsch/index.html) || [Great NW Colab](https://colab.research.google.com/github/zaneveld/full_spectrum_bioinformatics/blob/master/content/08_phylogenetic_trees/needleman_wunsch_alignment.ipynb)

## Genomics Learning Online

💭  [Rosalind](https://rosalind.info/problems/locations/)

💭 [Great Introduction to BioInformatics Course](https://gtpb.github.io/ELB19F/) - ELB19F

💭 [Learn BioInformatics in the Browser](https://sandbox.bio/) - Sandbox Bio

☁️ [Biological Modeling](https://biologicalmodeling.org/) - Free Online Course

☁️ [BioInformatic Algorithms Lecture Videos](https://www.bioinformaticsalgorithms.org/lecture-videos)

# Appendix

## Protein/Small Molecule References

(2021) [Highly accurate protein structure prediction with AlphaFold](https://www.nature.com/articles/s41586-021-03819-2)

(2021) [Deep molecular dreaming: inverse machine learning for de-novo molecular design and interpretability with surjective representations](https://iopscience.iop.org/article/10.1088/2632-2153/ac09d6)

(2021) [JANUS: Parallel Tempered Genetic Algorithm Guided by Deep Neural Networks for Inverse Molecular Design](https://arxiv.org/pdf/2106.04011.pdf) --> :computer: [code](https://github.com/aspuru-guzik-group/JANUS) ⭐ 92 | 🐛 2 | 🌐 Python | 📅 2022-07-27

(2021) [Transformer neural network for protein-specific de novo drug generation as a machine translation problem](https://www.nature.com/articles/s41598-020-79682-4)

(2021) [Using Gans With Adaptive Training Data to search for new molecules](https://jcheminf.biomedcentral.com/articles/10.1186/s13321-021-00494-3)

(2021) [Quantum Generative Models for Small Molecule Drug Discovery](https://arxiv.org/pdf/2101.03438.pdf) --> :computer: [QuantumGan code](https://github.com/jundeli/quantum-gan) ⭐ 95 | 🐛 0 | 🌐 Python | 📅 2024-08-12

(2021) [Machine learning designs non-hemolytic antimicrobial peptides](https://pubs.rsc.org/en/content/articlelanding/2021/sc/d1sc01713f)

(2021) [Few-Shot Graph Learning for Molecular Property Prediction](https://gitlab.com/7tm/smel/-/blob/master/papers/few_shot_graph_learning.pdf) --> :computer: [code](https://github.com/zhichunguo/Meta-MGNN) ⭐ 138 | 🐛 4 | 🌐 Python | 📅 2023-02-20

(2021) [Assigning Confidence To Molecular Property Prediction](https://gitlab.com/7tm/smel/-/blob/master/papers/assigning_confidence_molecular_property_prediction.pdf)

(2020) [Machine learning and AI-based approaches for bioactive ligand discovery and GPCR-ligand recognition](https://www.sciencedirect.com/science/article/pii/S1046202319302762)

(2020) [A Turing Test For Molecular Generation](https://gitlab.com/7tm/smel/-/blob/master/papers/turing_test_for_molecular_generators.pdf)

(2020) [Mol-CycleGAN: a generative model for molecular optimization](https://jcheminf.biomedcentral.com/articles/10.1186/s13321-019-0404-1) --> :computer: [code](https://github.com/ardigen/mol-cycle-gan) ⭐ 76 | 🐛 2 | 🌐 Jupyter Notebook | 📅 2019-02-06

(2020) [Protein Contact Map Denoising Using Generative Adversarial Networks](https://www.biorxiv.org/content/biorxiv/early/2020/06/27/2020.06.26.174300.full.pdf) --> :computer: [ContactGAN code](https://github.com/kiharalab/ContactGAN) ⭐ 8 | 🐛 0 | 🌐 Python | 📅 2021-06-07

(2020) [Hierarchical Generation of Molecular Graphs using Structural Motifs](https://arxiv.org/pdf/2002.03230.pdf) --> :computer: [code](https://github.com/wengong-jin/hgraph2graph/) ⭐ 445 | 🐛 44 | 🌐 Python | 📅 2022-06-28

(2020) [Relevant Applications of Generative Adversarial Networks in Drug Design and Discovery: Molecular De Novo Design, Dimensionality Reduction, and De Novo Peptide and Protein Design](https://arxiv.org/pdf/2101.03438.pdf)

(2020) [Deep Learning for Prediction and Optimization of Fast-Flow Peptide Synthesis](https://pubs.acs.org/doi/pdf/10.1021/acscentsci.0c00979)

(2020) [Curiosity in exploring chemical space: Intrinsic rewards for deep molecular reinforcement learning](https://arxiv.org/pdf/2012.11293.pdf)

(2020) [High-Throughput Docking Using Quantum Mechanical Scoring](https://www.frontiersin.org/articles/10.3389/fchem.2020.00246/full)

(2020) [Deep Learning Methods in Protein Structure Prediction](https://www.sciencedirect.com/science/article/pii/S2001037019304441)

(2020) [GraSeq: Graph and Sequence Fusion Learning for Molecular Property Prediction](https://gitlab.com/7tm/smel/-/blob/master/papers/graseq.pdf) --> :computer: [code](https://github.com/zhichunguo/GraSeq) ⭐ 15 | 🐛 1 | 🌐 Python | 📅 2021-02-10

(2020) [Revealing cytotoxic substructures in molecules using deep learning](https://link.springer.com/article/10.1007/s10822-020-00310-4)

(2020) [ChemBERTa: Large-Scale Self-Supervised Pretraining for Molecular Property Prediction](https://arxiv.org/pdf/2010.09885.pdf)

(2019)[From Machine Learning to Deep Learning: Advances in scoring functions for protein-ligand docking](https://onlinelibrary.wiley.com/doi/abs/10.1002/wcms.1429)

(2019) [The Unreasonable Effectiveness of Convolutional Neural Networks in Population Genetic Inference, Molecular Biology and Evolution](https://doi.org/10.1093/molbev/msy224)

(2019) [Deep Learning Enables Rapid Identification of Potent DDR1 Kinase Inhibitors](https://gitlab.com/7tm/smel/-/blob/master/papers/gentrl_paper.pdf) --> :computer: [GENTRL code](https://github.com/insilicomedicine/GENTRL) ⭐ 639 | 🐛 23 | 🌐 Python | 📅 2024-07-25

(2019) [Junction Tree Variational Autoencoder for Molecular Graph Generation](https://arxiv.org/pdf/1802.04364.pdf) --> :computer: [Code](https://github.com/wengong-jin/icml18-jtnn) ⭐ 566 | 🐛 30 | 🌐 Python | 📅 2022-12-01

(2019) [SMILES Transformer: Pre-trained Molecular Fingerprint for Low Data Drug Discovery](https://arxiv.org/pdf/1911.04738.pdf) --> [code](https://github.com/DSPsleeporg/smiles-transformer) ⭐ 357 | 🐛 15 | 🌐 Jupyter Notebook | 📅 2022-12-22 --> :computer: [code](https://github.com/DSPsleeporg/smiles-transformer) ⭐ 357 | 🐛 15 | 🌐 Jupyter Notebook | 📅 2022-12-22

(2019) [Molecular Property Prediction: A Multilevel Quantum Interactions Modeling Perspective](https://gitlab.com/7tm/smel/-/blob/master/papers/molecular_property_prediction.pdf) --> :computer: [code](https://github.com/awslabs/dgl-lifesci/blob/master/python/dgllife/model/model_zoo/mgcn_predictor.py) ⭐ 812 | 🐛 32 | 🌐 Python | 📅 2023-11-01 --> :computer: [more code](https://github.com/tencent-alchemy/Alchemy) ⭐ 114 | 🐛 6 | 🌐 Python | 📅 2024-07-25

(2019) [SMILES-BERT: Large Scale Unsupervised Pre-Training for Molecular Property Prediction](https://gitlab.com/7tm/smel/-/blob/master/papers/smiles_bert_2019.pdf)

(2019) [eToxPred: a machine learning-based approach to estimate the toxicity of drug candidates](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC6325674/) --> :computer: [eToxPred code](https://github.com/pulimeng/etoxpred) ⭐ 51 | 🐛 6 | 🌐 Python | 📅 2025-05-07

(2018) [Seq3Seq Fingerprint: Towards End-to-end Semi-supervised Deep Drug Discovery](https://gitlab.com/7tm/smel/-/blob/master/papers/seq3seq.pdf) --> :computer: [code](https://github.com/xysteve00/seq3seq-fingerprint-regression) ⭐ 2 | 🐛 0 | 🌐 Python | 📅 2018-11-21

(2018) [Chemi-Net: A molecular graph convolutional network for accurate drug property prediction](https://gitlab.com/7tm/smel/-/blob/master/papers/cheminet.pdf)

(2018) [Machine Learning of Toxicological Big Data Enables Read-Across Structure Activity Relationships (RASAR) Outperforming Animal Test Reproducibility](https://academic.oup.com/toxsci/article/165/1/198/5043469)

(2018) [DeepFam: deep learning based alignment-free method for protein family modeling and prediction](https://doi.org/10.1093/bioinformatics/bty275)

(2018) [Derivative-free neural network for optimizing the scoring functions associated with dynamic programming of pairwise-profile alignment](https://doi.org/10.1186/s13015-018-0123-6)

(2018) [(MOSES): A Benchmarking Platform for Molecular Generation Models](https://arxiv.org/abs/1811.12823) --> :computer: [code](https://github.com/molecularsets/moses) ⭐ 991 | 🐛 31 | 🌐 Python | 📅 2024-07-08

(2018) [DeepSMILES: An adaptation of SMILES for use in machine-learning of chemical structures](https://chemrxiv.org/engage/api-gateway/chemrxiv/assets/orp/resource/item/60c73ed6567dfe7e5fec388d/original/deep-smiles-an-adaptation-of-smiles-for-use-in-machine-learning-of-chemical-structures.pdf) --> :computer: [code](https://github.com/baoilleach/deepsmiles) ⭐ 146 | 🐛 6 | 🌐 Python | 📅 2021-05-24

(2017) [Protein-Ligand Scoring with CNN](https://pubs.acs.org/doi/10.1021/acs.jcim.6b00740)

(2017) [Quantum-chemical insights from deep tensor neural networks](https://www.nature.com/articles/ncomms13890)

(2016) [Incorporating QM and solvation into docking for applications to GPCR targets](https://gitlab.com/7tm/smel/-/blob/master/papers/qm_solvation_docking_gpcr.pdf)

(2014) [MRFalign: Protein Homology Detection through Alignment of Markov Random Fields](https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1003500)

(2012) [Molecular Docking: A powerful approach for structure-based drug discovery](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC3151162/#:~:text=The%20docking%20process%20involves%20two,assessment%20of%20the%20binding%20affinity.)

(2011) [The structural basis for agonist and partial agonist action on a β(1)-adrenergic receptor](https://pubmed.ncbi.nlm.nih.gov/21228877/)

(2011) [Molecular Dynamics Simulations of Protein Dynamics and their relevance to drug discovery](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC2981647/)

(2010) [AutoDock Vina: improving the speed and accuracy of docking with a new scoring function, efficient optimization and multithreading](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC3041641/)

(2009) [Amphipol-Assisted in Vitro Folding of G Protein-Coupled Receptors](https://pubs.acs.org/doi/10.1021/bi801729z)

(2005) [GPCR Folding and Maturation](https://link.springer.com/chapter/10.1007/978-1-59259-919-6_3) from [The G Protein-Coupled Receptors Handbook](https://link.springer.com/book/10.1007/978-1-59259-919-6)

(1996) [Double-mutant cycles: a powerful tool for analyzing protein structure and function](https://www.sciencedirect.com/science/article/pii/S1359027896000569)

(1982) [A Geometric Approach to MacroMolecule Ligand Interactions](https://www.sciencedirect.com/science/article/abs/pii/002228368290153X#:~:text=A%20geometric%20approach%20to%20macromolecule%2Dligand%20interactions%E2%98%86\&text=Algorithms%20are%20presented%20that%20examine,sites%20on%20a%20macromolecular%20surface.)

## Genomics References

(2021) [Re-identification of individuals in genomic datasets using public face images](https://www.science.org/doi/epdf/10.1126/sciadv.abg3296)

(2021) [Accurate, scalable cohort variant calls using DeepVariant and GLnexus](https://academic.oup.com/bioinformatics/article/36/24/5582/6064144)

(2021) [Ten simple rules for conducting a mendelian randomization study](https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1009238#sec002)

(2021) [Genetic determinants of blood-cell traits influence susceptibility to childhood acute lymphoblastic leukemia](https://github.com/sevenTMers/awesome-mendelian-randomisation/blob/main/resources/genetic_deterinmaants_of_blood_cell_traits.pdf) ⭐ 1 | 🐛 0 | 📅 2021-12-07

(2021) [The use of negative control outcomes in Mendelian randomization to detect potential population stratification](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC8407870/pdf/dyaa288.pdf)

(2020) [Secure large-scale genome-wide association studies using homomorphic encryption](https://www.pnas.org/content/117/21/11608.long)

(2020) [Optimized homomorphic encryption solution for secure genome-wide association studies](https://bmcmedgenomics.biomedcentral.com/articles/10.1186/s12920-020-0719-9)

(2020) [Genetic drug target validation using Mendelian randomisation](https://www.nature.com/articles/s41467-020-16969-0)

(2020) [Guidelines for performing Mendelian randomization investigations](https://wellcomeopenresearch.org/articles/4-186)

(2020) [Mendel’s laws, Mendelian randomization and causal inference in observational data: substantive and nomenclatural issues](https://link.springer.com/article/10.1007/s10654-020-00622-7)

(2020) [The use of Mendelian randomisation to identify causal cancer risk factors: promise and limitations](https://onlinelibrary.wiley.com/doi/full/10.1002/path.5421)

(2020) [A robust and efficient method for Mendelian randomization with hundreds of genetic variants](https://www.nature.com/articles/s41467-019-14156-4)

(2019) [Are drug targets with genetic support twice as likely to be approved? Revised estimates of the impact of genetic support for drug mechanisms on the probability of drug approval](https://journals.plos.org/plosgenetics/article?id=10.1371/journal.pgen.1008489)

(2019) [Learning Causal Biological Networks With the Principle of Mendelian Randomization](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC6536645/)

(2019) [Conducting a Reproducible Mendelian Randomization Analysis using the R analytic statistical environment](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC6424604/)

(2018) [A universal SNP and small-indel variant caller using deep neural networks](https://github.com/Ramb0a/awesome-genomics/blob/main/papers/universal_snp_small_indel_variant_caller_using_dnn.pdf)

(2018) [Secure genome-wide association analysis using multiparty computation](https://github.com/Ramb0a/awesome-genomics/blob/main/papers/secure_genome_wide_association_analysis_using_multiparty_computation.pdf)

(2018) [Minimap2: pairwise alignment for nucleotide sequences](https://academic.oup.com/bioinformatics/article/34/18/3094/4994778)

(2018) [Reading Mendelian randomisation studies: a guide, glossary, and checklist for clinicians](https://www.bmj.com/content/362/bmj.k601)

(2018) [Evaluating the current state of Mendelian randomization studies: a protocol for a systematic review on methodological and clinical aspects using neurodegenerative disorders as outcome](https://systematicreviewsjournal.biomedcentral.com/track/pdf/10.1186/s13643-018-0809-3.pdf)

(2016) [The sequence of sequencers: the history of sequencing dna](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC4727787/)

(2015) [Mendelian Randomization: New Applications in the Coming Age of Hypothesis-Free Causality](https://www.annualreviews.org/doi/10.1146/annurev-genom-090314-050016)

(2014) [MeRP: a high-throughput pipeline for Mendelian randomization analysis](https://academic.oup.com/bioinformatics/article/31/6/957/215107)

(2008) [Mendelian randomization: Using genes as instruments for making
causal inferences in epidemiology](http://jenni.uchicago.edu/ERC_2010/Lawlor_Harbord_Sterne_etal_2008_SiM_v27_n8.pdf)

(2007) [Capitalizing on Mendelian randomization to assess the effects of treatments](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC1963388/)

(2004) [Commentary: Mendelian randomization—an update on its use to evaluate allogeneic stem cell transplantation in leukaemia](https://academic.oup.com/ije/article/33/1/15/668135)

(2003) [‘Mendelian randomization’: can genetic epidemiology contribute to understanding environmental determinants of disease?](https://academic.oup.com/ije/article/32/1/1/642797)

# Important Technology in the Future of Structural BioInformatics

* [Polars](https://github.com/pola-rs/polars) ⭐ 39,914 | 🐛 2,930 | 🌐 Rust | 📅 2026-10-04 - everyone learns the hard way that Pandas doesn't cut it in the real world. Its like [Arrow](https://github.com/apache/arrow) ⭐ 17,174 | 🐛 2,467 | 🌐 C++ | 📅 2026-10-02 only Rusty.
* [Jax](https://github.com/google/jax) ⭐ 36,374 | 🐛 2,640 | 🌐 Python | 📅 2026-10-04 - the future? of domain specific ML compiling?
* [Annoy](https://github.com/spotify/annoy) ⭐ 14,311 | 🐛 90 | 🌐 C++ | 📅 2025-10-29 - the standard in production nearest neighbor
* [gRPC](https://grpc.io/) - connect your devices binary like
* [Kubernetes](https://kubernetes.io/) - make all your informatics container orchestration declarative
* [ONNX](https://onnx.ai/) - make all your models interoperable
* [ONNX Runtime](https://onnxruntime.ai/) - speed up your informatic inference

## Distributed Computing in Informatics

High Performance Computing (HPC) is often talked about as essential technology for the future and present of Bio/Chem Informatics. At its core HPC is now and forever really a special case of distributed computing.

Though there have been projects like [Fold@home](https://foldingathome.org/about/) it is highly likely that a lack of innovation in distributed informatics computing (and decentralization as well) will continue to hinder the progress of many grand challenges in this field.

AlphaFold revealed not the solution to folding but instead how the real problem is modelling dynamic rather than static protein events and just how far there is left to go before the surface of the problem is even scratched. One on hand, we could wait potentially forever for Quantum Computers to prove themselves useful - or on the other the juice can be squeezed out of parrellel and distributed computing.

(2022) [Deep distributed computing to reconstruct extremely large lineage trees](https://www.nature.com/articles/s41587-021-01111-2)

(2020) [Bioinformatics Application with Kubeflow for Batch Processing in Clouds](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC7571545/) -  together, Docker and Kubernetes become universal platforms for Infrastructure-as-a-Service (IaaS) for Bioinformatics pipelines and other workloads. Most of Bioinformatics pipelines assume local access to POSIX-like file systems for simplicity.

(1996) RFC 1958 [Architectural Principles of the Internet](https://datatracker.ietf.org/doc/html/rfc1958)

### Distributed Cloud

> In a distributed cloud, services are located or ‘distributed’ to specific locations to reduce latency and these services enjoy a single, consistent control place across public and private cloud environments

![Google Distributed Cloud](https://github.com/Ramb0a/awesome-structural-bioinformatics/blob/main/googleDistributedCloud.png)

## Brief Explanation of AlphaFold Jax Architecture

AlphaFold2 is Google's state of the art protein structure prediction model.

AF2 predicts 3D coordinates of all atoms of a protein, [using the amino acid sequence and aligned sequences homology.](https://github.com/b0mTrady/awesome-structural-bioinformatics) ⭐ 81 | 🐛 0 | 🌐 Python | 📅 2023-05-05

![image](https://user-images.githubusercontent.com/64801585/126504747-281b12dd-4157-4d73-a7f2-107c26494f1c.png)

* PreProcessing
  * Input Sequence
  * Multiple Sequence Alignments
  * Structural Templates
* Transformer (EvoFormer)
* Recycling
* Structure Module -> 3D coordinates

![image](https://user-images.githubusercontent.com/64801585/127316142-126458b5-edf4-4bc0-8aeb-d42a24d01750.png)

![Screenshot from 2021-07-28 07-58-02](https://user-images.githubusercontent.com/64801585/127318851-d3c5f87e-75ba-4632-aa13-7b68eee2f2f8.png)

![Screenshot from 2021-07-28 07-58-54](https://user-images.githubusercontent.com/64801585/127318883-b049f5c5-9415-40b6-9de0-9eac288dcb34.png)

```python

def softmax_cross_entropy(logits, labels):
  loss = -jnp.sum(labels * jax.nn.log_softmax(logits), axis=-1)
  return jnp.asarray(loss)
  
```

If you didn't know jax's [nn.logsoftmax](https://github.com/google/jax/blob/890a41f7191fa468e2f638ba4efb9e32ad26adaa/jax/_src/nn/functions.py#L264) ⭐ 36,374 | 🐛 2,640 | 🌐 Python | 📅 2026-10-04 AF2's implemenation would not mean much to you.

So going down the rabbit hole in Jax's nn we have the softmax function:

(The `LogSoftmax` function, rescales elements to the range <img src="https://render.githubusercontent.com/render/math?math=(-\infty, 0)">)

```python
def log_softmax(x: Array, axis: Optional[Union[int, Tuple[int, ...]]] = -1) -> Array:  
  shifted = x - lax.stop_gradient(x.max(axis, keepdims=True))
  return shifted - jnp.log(jnp.sum(jnp.exp(shifted), axis, keepdims=True))
```

The accepted arguments are:

* **x** : input array
* **axis**: the axis or axes along which the `log_softmax` should be computed. Either an integer or a tuple of integers.

and an array is returned.

Inside this function we go further down the lane to:

* [`lax.stop_gradient`](https://github.com/google/jax/blob/890a41f7191fa468e2f638ba4efb9e32ad26adaa/jax/_src/lax/lax.py#L1661) ⭐ 36,374 | 🐛 2,640 | 🌐 Python | 📅 2026-10-04 - is the identity function, that is, it returns argument `x` unchanged. However, `stop_gradient` prevents the flow of
  gradients during forward or reverse-mode automatic differentiation.

```python
def stop_gradient(x):
  def stop(x):
    if (dtypes.issubdtype(_dtype(x), np.floating) or
        dtypes.issubdtype(_dtype(x), np.complexfloating)):
      return ad_util.stop_gradient_p.bind(x)
    else:
      return x  # only bind primitive on inexact dtypes, to avoid some staging
  return tree_map(stop, x)
```

This in turn relies upon [`tree_map`](https://github.com/google/jax/blob/890a41f7191fa468e2f638ba4efb9e32ad26adaa/jax/_src/tree_util.py#L144) ⭐ 36,374 | 🐛 2,640 | 🌐 Python | 📅 2026-10-04

```python
def tree_map(f: Callable[..., Any], tree: Any, *rest: Any,
                    is_leaf: Optional[Callable[[Any], bool]] = None) -> Any:
  
  leaves, treedef = tree_flatten(tree, is_leaf)
  all_leaves = [leaves] + [treedef.flatten_up_to(r) for r in rest]
  return treedef.unflatten(f(*xs) for xs in zip(*all_leaves))
```

* `jnp.log`
* `jnp.sum`
* `jnp.exp`

[Automatic Differentiation Lecture Slides](https://www.cs.ubc.ca/~fwood/CS340/lectures/AD1.pdf)

[Gans in Jax](https://github.com/lweitkamp/GANs-JAX) ⭐ 34 | 🐛 1 | 🌐 Jupyter Notebook | 📅 2022-04-29

[Jax MD](https://github.com/google/jax-md) ⭐ 1,464 | 🐛 41 | 🌐 Jupyter Notebook | 📅 2026-08-18

## Other Free Books You Should Read Instead of This Repo

[Chemisty 2E](https://openstax.org/details/books/chemistry-2e) - :atom: Equivalent to 201 & 202 Level Chemistry Book

[Chemistry: Atoms First 2E](https://openstax.org/details/books/chemistry-atoms-first-2e) :atom: Fork of 2E but not with more Atoms!!!!

[Biology 2E](https://openstax.org/details/books/biology-2e) 👽 Like Chemistry 2E but Biology

[Artificial Intelligence: A Modern Approach](https://github.com/aimacode/aima-python) ⭐ 8,840 | 🐛 4 | 🌐 Jupyter Notebook | 📅 2026-06-30 🤖 The Gospel of Machine Learning

[Neural Networks and Deep Learning](http://neuralnetworksanddeeplearning.com/) 🤖 Michael Nielsen writes another masterpiece - About Deep Learning - if you are into that sort of thing.

[Reinforcement Learning](http://incompleteideas.net/book/RLbook2020.pdf) 🤖  The only book you need on the subject

[Pattern Recognition and Machine Learning](https://www.microsoft.com/en-us/research/uploads/prod/2006/01/Bishop-Pattern-Recognition-and-Machine-Learning-2006.pdf) 🤖 Another classic banger

***

> _Enhansomed by [enhansome](https://github.com/enhansome) on 2026-10-04._
