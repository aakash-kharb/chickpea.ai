# chickpea_knowledge.md
# Chickpea Stress-Responsive Genes (SRG) RAG Pipeline - Domain Knowledge Base
# Version 3 — Updated: biochemical properties (MW, pI, GRAVY, instability, aliphatic, atomic)
#              replaced manual amino acid composition analysis (proline/cysteine thresholds)
# ===================================================================================

## 1. Species Overview

**Cicer arietinum** (desi and kabuli chickpea) is the world's third-largest legume crop,
cultivated across South Asia, the Middle East, and Mediterranean regions. It is critically
sensitive to abiotic stresses: heat, drought, and salinity during flowering/podding can
reduce yields by 30-80%. Understanding stress-responsive genes is essential for molecular
breeding of climate-resilient varieties.

Gene nomenclature in this pipeline: **Ca_XXXXX** (5-digit zero-padded integer), e.g. Ca_00011.
These identifiers correspond to the Cicer arietinum reference genome v1.0 (ICCC 4958).

---

## 2. Experimental Datasets and GEO Accession Summaries

### 2.1 GSE53711 — Multi-Stress Root and Shoot Profiling
- **Accession:** GEO GSE53711
- **Citation:** Garg et al. (2016) "Transcriptome analyses reveal genotype and developmental 
  stage-specific molecular responses to drought and salinity stresses in chickpea"
- **Platform:** Illumina HiSeq 2000
- **Expression units:** FPKM (reads per kilobase per million mapped reads)
- **Tissues:** Root and Shoot, separately
- **Stresses covered:** Drought (Root-DS, Shoot-DS), Salinity (Root-SS, Shoot-SS), Cold (Root-CS, Shoot-CS)
- **Controls:** Root-Control, Shoot-Control (well-watered, unstressed)
- **Design note:** Single genotype (ICC 4958), 14-day-old seedlings. Root and shoot 
  tissues were harvested independently after stress treatment.
- **Interpretation guidance:** 
  - Root-DS / Root-SS responses reflect primary perception organs.
  - Shoot-DS / Shoot-SS responses reflect systemic signalling and stomatal regulation.
  - Discordant root/shoot Log2FC is biologically meaningful — many genes are tissue-specific responders.

### 2.2 GSE70377 — Salinity Stress: Tolerant vs. Sensitive Genotypes
- **Accession:** GEO GSE70377
- **Citation:** Hiremath et al. / Related to ICRISAT chickpea transcriptome project
- **Platform:** Illumina RNA-seq
- **Expression units:** FPKM
- **Genotypes:** 
  - **Stol** = Salinity-Tolerant genotype
  - **Ssen** = Salinity-Sensitive genotype
- **Stages:** 
  - **veg** = Vegetative growth stage
  - **rep** = Reproductive (flowering/podding) stage
- **Conditions:** CT = Control (unstressed), SS = Salt Stress
- **Full column naming:** `[Genotype]-[Stage]-[Condition]_FPKM`
  e.g. `Stol-veg-CT_FPKM` = Tolerant genotype, vegetative stage, control
- **Interpretation guidance:**
  - Compare Stol vs Ssen to identify tolerance mechanisms.
  - Genes upregulated ONLY in Stol (not Ssen) are strong tolerance candidates.
  - Genes upregulated in Ssen under SS may represent sensitivity markers or damage-response.
  - Stage differences (veg vs rep) indicate whether a gene's role is developmental or universal.

### 2.3 ICCV/JG62 Salinity Dataset — Leaf Stage Comparison
- **Source:** ICCV-10 and JG-62 cultivars, salinity stress in leaves
- **Tissues:** Leaf at normal and late growth stages
- **Column naming:** `[Cultivar]_Control`, `[Cultivar]_Stress`, `[Cultivar]_L[Control/Stress]`
  where L prefix = late stage
- **Interpretation:** Normal vs late-stage response shows whether salt tolerance 
  is constitutive (both stages) or developmentally regulated (late stage only).

### 2.4 ICCV2/JG62 Salinity Dataset — Shoot and Root
- **Source:** ICCV-2 and JG-62 cultivars, root and shoot tissues
- **Column naming:** `FPKM-SS-[C/S]` (Shoot: Control/Stress), `FPKM-ST-[C/S]` (Root: Control/Stress)
- **Interpretation:** Complementary to GSE70377 — provides organ-level salinity data across cultivars.

### 2.5 ICC4958/1882 Drought Dataset — Tolerant vs. Sensitive Shoot
- **Source:** ICC 4958 (tolerant) and ICC 1882 (sensitive), shoot tissue under drought
- **Column naming:** `FPKM-DS-[C/D]` (Drought-Sensitive cultivar), `FPKM-DT-[C/D]` (Drought-Tolerant)
- **Interpretation:** Direct tolerant-vs-sensitive comparison. Genes upregulated in DT but not DS 
  are primary drought tolerance candidates.

### 2.6 ICC2861/ICC283 Drought Dataset — Two Cultivars
- **Source:** ICC 2861 and ICC 283 cultivars
- **Column naming:** `ICC2861_Control`, `ICC2861_Stress`, `ICC283_Control`, `ICC283_Stress`
- **Interpretation:** Cross-cultivar validation. Genes significant in both cultivars 
  have higher reliability for breeding programmes.

### 2.7 PRJNA748749 — Heat Stress: Comprehensive 6-Cultivar Study
- **Accession:** NCBI BioProject PRJNA748749
- **Citation:** Kudapa H, Barmukh R, Garg V, et al. (2023) "Comprehensive Transcriptome 
  Profiling Uncovers Molecular Mechanisms and Potential Candidate Genes Associated with 
  Heat Stress Response in Chickpea." *Int J Mol Sci* 24(2).
- **Platform:** Illumina MiSeq, pheatmap analysis
- **Expression units:** FPKM
- **Cultivars studied (6 total):**

| Cultivar Code | ICRISAT ID    | Known trait             |
|---------------|---------------|-------------------------|
| 92944         | ICCV 92944    | Heat-tolerant           |
| 15614         | ICC 15614     | Reference line          |
| 10685         | ICC 10685     | Heat-sensitive          |
| 5912          | ICC 5912      | Reference line          |
| 4567          | ICC 4567      | Reference line          |
| 1356          | ICC 1356      | Reference line          |

- **Sample naming convention:** `[CultivarCode]_[TissueStage]_[Treatment]`
  - `AFL` = Above-ground Leaf, reproductive (Flowering) stage
  - `AFR` = Above-ground Root, reproductive (Flowering) stage  
  - `BFL` = Below-ground Leaf, Vegetative stage
  - `BFR` = Below-ground Root, Vegetative stage
  - `_C`  = Control (ambient temperature ~25°C)
  - `_S`  = Stress (heat treatment, typically 40-45°C)
- **Interpretation guidance:**
  - Leaf reproductive (AFL) responses are most critical for yield — this is when heat causes 
    pollen sterility and pod abortion.
  - Root reproductive (AFR) responses reflect systemic heat sensing.
  - Vegetative stage (BF) responses indicate constitutive vs stress-inducible expression.
  - Genes upregulated in ≥4/6 cultivars are high-confidence pan-cultivar heat responders.
  - Cultivar 92944 (ICCV 92944) responses are of special interest as it is heat-tolerant.

---

## 3. Log2FC Interpretation Guide

| Log2FC Range    | Direction       | Fold Change (approx.) | Biological Significance             |
|-----------------|-----------------|----------------------|--------------------------------------|
| > 3.0           | STRONG UP       | > 8×                 | Major stress response gene           |
| 1.5 to 3.0      | UPREGULATED     | 2.8× – 8×            | Significant upregulation (threshold) |
| 0.5 to 1.5      | MILD UP         | 1.4× – 2.8×          | Below threshold — not significant    |
| -0.5 to 0.5     | STABLE          | ~1×                  | Constitutively expressed             |
| -1.5 to -0.5    | MILD DOWN       | 0.35× – 0.71×        | Below threshold                      |
| -1.5 to -3.0    | DOWNREGULATED   | 0.12× – 0.35×        | Significant downregulation           |
| < -3.0          | STRONG DOWN     | < 0.12×              | Severely repressed under stress      |

**Pseudo-count formula:** `log2((stress_FPKM + 1) / (control_FPKM + 1))`  
The +1 pseudo-count prevents log(0) for non-expressed genes and slightly moderates extreme ratios.

---

## 4. Stress Binary Matrix Interpretation

The Stress_Binary_Matrix.csv assigns binary labels based on whether a gene is significantly 
differentially expressed under each stress condition:
- **1** = Gene is classified as stress-responsive (DE at adjusted p < threshold)
- **0** = Not classified as stress-responsive for that condition
- **Num_Stresses** = Total number of stresses for which the gene is labelled 1

**Important caveats:**
- A binary label of 0 does not mean the gene is completely unresponsive — it may show 
  sub-threshold Log2FC values.
- A binary label of 1 + expression Log2FC > 1.5 = high-confidence stress responder.
- Discrepancy (label=1 but no |Log2FC| > 1.5 in individual files) can occur because the 
  binary matrix was generated from a different statistical threshold or combined dataset.

---

## 5. Biochemical Property Interpretation Guide

Pre-computed biochemical properties are available for all 28,269 peptide sequences
via `BiochemicalProperties.csv`. These are looked up by gene ID (no runtime calculation
or BioPython dependency). Properties provided per gene:

### 5.1 Molecular Weight (Da)
- **Small peptide:** < 10,000 Da (< ~90 amino acids)
- **Medium protein:** 10,000–50,000 Da
- **Large protein:** > 50,000 Da
- **Context:** Stress-responsive proteins range widely. sHSPs are 15–25 kDa; HSP70s are
  ~70 kDa; LEA proteins are typically 10–30 kDa. Size alone does not determine function
  but constrains which protein family the gene may belong to.

### 5.2 Theoretical pI (Isoelectric Point)
- **Acidic (pI < 7):** Net negative charge at physiological pH (~7.4). Common in
  activation domains, calcium-binding proteins (EF-hand), and some LEA proteins.
- **Neutral (pI ~7):** Balanced charge.
- **Basic (pI > 7):** Net positive charge at physiological pH. Common in DNA/RNA-binding
  proteins, transcription factors, histones, and nuclear-localized proteins.
- **Strongly basic (pI > 10):** Likely nucleic acid binding or membrane interaction.

### 5.3 Instability Index
- **Stable (< 40):** Predicted to be stable in vitro. Structural proteins, enzymes.
- **Unstable (≥ 40):** Predicted to be unstable. This does not mean the protein is
  non-functional; many regulatory and signalling proteins are inherently unstable and
  rapidly turned over (e.g., transcription factors, kinase substrates).
- **Stress relevance:** Unstable proteins under normal conditions may be stabilised by
  chaperones (HSPs) under stress, or rapidly degraded as part of stress signalling.

### 5.4 Aliphatic Index
- **Higher values (> 80):** Suggest greater thermostability due to higher proportion of
  aliphatic side chains (Ala, Val, Ile, Leu). Relevant to heat stress tolerance.
- **Lower values (< 60):** Less thermostable, more flexible structure.
- **Heat stress context:** Genes with high aliphatic index that are also upregulated under
  heat are strong candidates for thermostability-related protection.

### 5.5 GRAVY (Grand Average of Hydropathicity)
- **Negative GRAVY:** Hydrophilic protein. Likely cytoplasmic, soluble, or in aqueous
  compartments. Most stress-responsive enzymes and transcription factors are hydrophilic.
- **Positive GRAVY:** Hydrophobic protein. Likely membrane-associated or contains
  transmembrane domains. Aquaporins, ion channels, membrane-embedded receptors.
- **Near zero:** Balanced; globular proteins with typical hydrophobic core and hydrophilic surface.

### 5.6 Atomic Composition (C, H, N, O, S)
- **Sulfur (S) count:** Primary indicator of cysteine and methionine content.
  High S count (> 10) suggests potential for disulfide bonds (cysteine pairs) which
  stabilise protein structure. Relevant for metallothioneins, thioredoxins, and
  ferredoxin-like redox proteins.
- **General note:** Total atom counts scale with protein size. Normalise mentally
  against total amino acid count when comparing across genes.

### 5.7 Common stress-protein signatures (with biochemical property context)

| Protein class     | Size (aa) | Typical pI  | Typical GRAVY | Stability  | Key features                           |
|-------------------|-----------|-------------|---------------|------------|----------------------------------------|
| HSP70/HSP90       | 600–700   | Acidic      | Negative      | Stable     | High aliphatic index, chaperone        |
| Small HSP (sHSP)  | 150–250   | Variable    | Negative      | Stable     | α-crystallin domain, high aliphatic    |
| Dehydrin (DHN)    | 100–300   | Basic       | Very negative | Unstable   | Intrinsically disordered, K-segments   |
| LEA protein       | 50–200    | Variable    | Very negative | Unstable   | Hydrophilic, unstructured under normal |
| Metallothionein   | 50–100    | Neutral     | Negative      | Stable     | Very high S (Cys-rich, >15% Cys)      |
| DREB/ERF TF       | 200–400   | Basic       | Negative      | Unstable   | AP2 domain, DNA-binding                |
| MYB TF            | 200–500   | Basic       | Negative      | Unstable   | R2R3 repeat, DNA-binding               |
| P5CS (proline syn)| 700+      | Acidic      | Negative      | Stable     | Large enzyme, balanced composition     |

---

## 6. Confidence Assessment Framework

| Level    | Criteria                                                                 |
|----------|--------------------------------------------------------------------------|
| HIGH     | ≥ 2 independent experiments (different GEO/BioProject) consistently agree on direction |
| MODERATE | 1 experiment with clear signal, OR 2+ experiments with mixed direction   |
| LOW      | Only 1 borderline experiment, single dataset, or all NaN/missing         |

**Additional confidence boosters:**
- Consistent across ≥ 3 cultivars in PRJNA748749 → +HIGH
- Consistent in both tissue types (root AND shoot) → +HIGH
- Consistent in both tolerant AND sensitive genotypes (GSE70377) → +MODERATE
- Labelled in Stress_Binary_Matrix (independent statistical test) → +HIGH

---

## 7. Biological Pathways Relevant to Chickpea Stress Response

### 7.1 Heat Stress Response
- **HSF-HSP signalling:** Heat Shock Factors (HSFs) activate HSP genes within minutes.
  sHSPs (small heat shock proteins) are often the most strongly induced (Log2FC > 4).
- **Protein quality control:** Ubiquitin-proteasome pathway genes are upregulated to 
  degrade misfolded proteins.
- **Membrane stability:** Fatty acid desaturases adjust membrane fluidity.
- **ROS detoxification:** SOD, CAT, APX, GPX upregulated to counteract oxidative burst.

### 7.2 Drought Stress Response
- **ABA signalling:** Abscisic acid biosynthesis (NCED) and signalling (SnRK2, PP2C) central.
- **Osmotic adjustment:** P5CS (proline synthesis), Δ1-pyrroline-5-carboxylate reductase.
- **Late Embryogenesis Abundant (LEA) proteins:** Group 1-7 LEAs protect cellular structures.
- **Aquaporins:** PIPs and TIPs regulate water transport, often downregulated under drought.
- **DREB/CBF TFs:** Drought-Responsive Element Binding proteins induce downstream gene networks.

### 7.3 Salinity Stress Response
- **Ion exclusion:** SOS1 (plasma membrane Na+/H+ antiporter), HKT1 (high-affinity K+ transporter).
- **Vacuolar compartmentalisation:** NHX antiporters sequester Na+ in vacuoles.
- **Osmotic component:** Same as drought — LEA proteins, proline synthesis.
- **Reactive oxygen species:** Elevated NaCl triggers ROS burst; antioxidant genes upregulated.

### 7.4 Cold Stress Response
- **CBF/DREB pathway:** C-repeat Binding Factors induce Cold-Regulated (COR) genes.
- **Cryoprotection:** Dehydrins, antifreeze proteins, compatible solutes.
- **Membrane modification:** FAD genes (fatty acid desaturases) increase unsaturation.
- **Calcium signalling:** Cold activates Ca2+ influx → calmodulin → downstream TFs.

---

## 8. Agricultural and Breeding Context

- **Target stresses:** Heat during reproductive stage is the #1 yield-limiting stress.
  Global warming projections indicate average chickpea yield losses of 5-8% per °C rise.
- **High-value genes for breeding:** Multi-stress responsive genes (Num_Stresses ≥ 3) are 
  preferred for genetic engineering as they confer broad tolerance.
- **Tissue priority for heat tolerance:** Leaf Reproductive stage (AFL samples) — this is when 
  pollen viability is compromised. AFL-upregulated genes protect pollen and ovules.
- **Genotype specificity:** Genes consistently upregulated in ICCV 92944 (heat-tolerant 
  cultivar) are higher-priority candidates than those only seen in sensitive cultivars.
- **Marker-assisted selection:** Binary stress labels from Stress_Binary_Matrix can be 
  used to identify candidate genes for QTL co-localisation.

---

## 9. Common Analysis Pitfalls to Avoid

1. **Do not interpret Log2FC in isolation** — always cross-reference binary stress labels.
2. **Tissue context matters** — root upregulation ≠ shoot upregulation; they may reflect 
   opposing roles (perception vs signalling).
3. **Genotype matters** — an expression change only in sensitive genotypes may indicate 
   a damage response, not a tolerance mechanism.
4. **Zero FPKM values** — log2((0+1)/(x+1)) = log2(1/(x+1)) which can be strongly negative; 
   treat with caution — may indicate the gene is not expressed in that tissue/condition.
5. **Pseudo-count effect** — for very low FPKM values (<1), the pseudo-count dominates 
   and Log2FC values are moderated (compressed toward 0). Report actual FPKM values.
