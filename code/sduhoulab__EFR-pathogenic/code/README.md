# **LMEFold: A Deep Learning Framework for Early Folding Residue Prediction and Disease Association Analysis**
## **Workflow**
![5d1acee5a92e6f8e6c24944b2813f7c2](https://github.com/user-attachments/assets/0eb80cac-3e3f-4e21-bc06-a8a6275390cb)


We established an integrated deep learning–biophysics–clinical framework to elucidate the role of Early Folding Residues (EFRs) in protein stability and disease.

**Model development:** LMEFold leverages ESM-2 embeddings to extract sequence-derived structural signals and is optimized using nested cross-validation.

**Benchmarking and validation:** The model was systematically compared with state-of-the-art sequence-based predictors and general PLMs, with evaluation spanning predictive performance, representation analysis, structural consistency, and biophysical generalization on an independent HDX-based dataset.

**Clinical application:** LMEFold was applied at scale to population and disease variant datasets to characterize the enrichment and clinical relevance of mutations occurring in EFRs.

## **Datasets**
### Training and Biophysical Validation
**Dataset 1 (Training - Benchmark30):** Derived from the Start2Fold database. Contains 30 proteins with high-quality experimental annotations (HDX/NMR) defining early folding sites.

Source: https://www.bio2byte.be/start2fold/


**Dataset 2 (PF-HDX-EvalSet):** Consists of 431 residues from 10 proteins with experimentally determined protection factors (PFs) measured via HDX-NMR to validate biophysical relevance.

Source: https://pubmed.ncbi.nlm.nih.gov/34739840/.


**Dataset 3 (Case Studies):** Structural data for myoglobin (PDB: 1MBC) and ubiquitin (PDB: 1UBQ).

Source: https://www.rcsb.org/

### Genomic and Clinical Cohorts
**Dataset 4 (Germline Variant Database):**

**Pathogenic Variants:** 23,369 pathogenic missense variants were extracted and retained from ClinVar.

Source: www.ncbi.nlm.nih.gov/clinvar/


**Population Control:** ~6.6 million common variants from gnomAD and UK Biobank (UKB).


gnomAD: A total of 4,667,175 variants were extracted and retained.


Source: https://gnomad.broadinstitute.org/


UK Biobank (UKB): A total of 1,952,086 variants were extracted and retained.


Source: https://www.ukbiobank.ac.uk/


**Dataset 5 (Somatic Variant  Database):**

MSK-MET Cohort:A total of 129,411 somatic non-synonymous single nucleotide variants were extracted, along with corresponding clinical records.

Source: https://www.cbioportal.org/

## **Methods**
### Core Framework
**LMEFold:** The proposed framework based on the ESM-2 protein language model for EFR prediction.

The complete source code, training and evaluation pipelines, and reproducibility resources are available in the main GitHub repository:

https://github.com/sduhoulab/EFR-pathogenic/tree/main/LMEFold

The 27 trained fold-specific LMEFold models are publicly available through Hugging Face:

https://huggingface.co/LMEFold/models

For convenient evaluation on new protein sequences, an online prediction interface integrating the 27 trained models is available at:

https://huggingface.co/spaces/sduhoulab/LMEFold_Agent

### Baselines & Comparators
**ESM-2:** Pre-trained evolutionary scale modeling.

Source: https://github.com/facebookresearch/esm

**ProtTrans (ProtBERT / ProtT5):** Transformer models trained on protein sequences.

Source: https://github.com/agemagician/ProtTrans

**EFoldMine:** The state-of-the-art sequence-based predictor for early folding residues using handcrafted features.

Source:  https://figshare.com/articles/EFoldMine_code/5649373 



### Variant Effect Prediction Tools
**FoldX 5.0:** Used for calculating folding free energy changes (ΔΔG).

Source: http://foldxsuite.crg.eu/

**VEP (Variant Effect Predictor):** Used for mapping genomic variants to protein residues and predicting their molecular consequences.

Source: https://www.ensembl.org/info/docs/tools/vep/index.html


**ConSurf:** Used for identifying functional regions in proteins by estimating evolutionary conservation through phylogenetic analysis.

Source: https://consurf.tau.ac.il/


**ConSurf 2016:** An improved methodology for estimating and visualizing evolutionary conservation in macromolecules.

Source: https://consurf.tau.ac.il/


**IUPred3:** Used for predicting intrinsic protein disorder, enhanced with experimental annotations.

Source: https://iupred3.elte.hu/


**SIFT:** Used for predicting whether an amino acid substitution affects protein function based on sequence homology.

Source: https://sift.bii.a-star.edu.sg/


**PolyPhen-2:** Used for predicting the potential impact of missense mutations on protein structure and function.

Source: http://genetics.bwh.harvard.edu/pph2/


**CD-HIT:** Used for clustering and comparing large sets of protein or nucleotide sequences to reduce redundancy.

Source: http://weizhong-lab.ucsd.edu/cd-hit/

### Environment & Requirements
The analysis scripts and model training pipelines require Python >= 3.8 and the following packages:

- torch >= 1.9.0
- transformers >= 4.12.0
- torchmetrics >= 0.6.0
- scikit-learn >= 0.24.0
- pandas >= 1.3.0
- numpy >= 1.21.0
- tqdm >= 4.62.0
- sentencepiece >= 0.1.96

### **Installation**

Before getting started, make sure you have Python 3.8+ and PyTorch installed. Running in a GPU environment is strongly recommended for better performance.

#### **Clone the repository**

```bash
git clone https://github.com/sduhoulab/EFR-pathogenic.git
cd EFR-pathogenic
```

#### **Install dependencies**

```bash
pip install torch transformers torchmetrics scikit-learn pandas numpy tqdm sentencepiece
```

##  **Quick Start**

The project mainly consists of two core workflows: Model Training (`main.py`) and Model Testing/Inference (`test.py`).

### **1. Model Training**

If you wish to train the model on your own dataset, you can run `main.py`. The script supports configuring hyperparameters (such as learning rate, dropout, batch size, etc.) via command-line arguments:

```bash
python main.py --task epi --lr 1e-5 --dropo 0.1 --BATCH_SIZE 1
```

**Key Arguments:**

- `--task`: Task name (e.g., epi, etc.)
- `--lr`: Learning rate (default 1e-5)
- `--dropo`: Dropout rate (default 0.1)
- `--BATCH_SIZE`: Batch size (default 1)

### **2. Model Inference & Testing**

Once you have a trained weight file (e.g., `./checkpoints/val_model_besteo_2_dp_0.1_lr_5e-05_bz_1.pkl`), you can evaluate the test set and output metrics and prediction results using `test.py`.

Verify that the path configurations in `test.py` are correct:

- `MODEL_PATH`: Pretrained model path (e.g., `"facebook/esm2_t30_150M_UR50D"`)
- `WEIGHTS_PATH`: Model weights path
- `TEST_FILE`: Test data CSV file path

Run the testing script:

```bash
python test.py
```

After execution, the evaluation metrics (AUC, Accuracy, F1 Score, etc.) and detailed prediction probabilities will be automatically saved in the `./outputs/` directory.

For users who prefer online evaluation, LMEFold can also be evaluated using the following web interface, which integrates the 27 trained models:

https://huggingface.co/spaces/sduhoulab/LMEFold_Agent

##  **Core File Structure**

- `main.py`: Main model training script, including cross-validation, early stopping, and optimizer configuration.
- `test.py`: Model inference and evaluation script, automatically loading weights and outputting classification metrics.
- `dataloader.py`: Data loading and preprocessing module (including sequence padding and PyTorch Dataset wrapping).
- `bert_optimization.py`: Learning rate schedulers (e.g., Cosine, Linear Warmup) and custom optimizers (e.g., BertAdam, EMA).

##  **Contribution & Feedback**

If you encounter any issues or have suggestions while using this project, feel free to submit Issues or open a Pull Request!
