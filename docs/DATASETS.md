# Datasets

## Overview

This project uses four top-level CSV assets plus 15 experiment-specific files in `Individual Files/`.

Top-level file sizes (line counts):

- `Stress_Binary_Matrix.csv`: 1,631 lines (header + 1,630 genes)
- `Ca_Peptide_Sequences.csv`: 28,270 lines (header + 28,269 sequences)
- `BiochemicalProperties.csv`: 28,270 lines (header + 28,269 entries)
- `mapping.csv`: 27,079 lines (header + 27,078 mappings)

## Core files

### `Stress_Binary_Matrix.csv`

Schema:

- `Ca_ID`
- `Stress`
- `Num_Stresses`
- `Cold`
- `Drought`
- `Salinity`
- `Heat`

Meaning:

- each stress column is binary (0/1)
- `Num_Stresses` is count of stress columns with value 1
- `Stress` is text summary of active stresses

Used by:

- `gene_collector.py` (stress-state classification)
- `gene_search_agent.py` (candidate filtering and tier-weighted random sampling for list queries)

### `Ca_Peptide_Sequences.csv`

Schema:

- `Ca_ID`
- `Peptide_Sequence`

Meaning:

- one peptide sequence per gene ID (where available)
- independent of expression availability

Used by:

- `gene_collector.py` peptide retrieval

### `BiochemicalProperties.csv`

Schema:

- `Transcript id` (canonical `Ca_XXXXX`)
- `Peptide`
- `Total Amino Acids`
- `Molecular Weight (Da)`
- `Theoretical pI`
- `Instability Index`
- `Aliphatic Index`
- `GRAVY`
- `Status` (Stable/Unstable based on instability index threshold of 40)
- `Total C Atoms`, `Total H Atoms`, `Total N Atoms`, `Total O Atoms`, `Total S Atoms`

Meaning:

- pre-computed biochemical properties for each peptide sequence
- eliminates the need for runtime calculation or BioPython dependency
- properties were computed from peptide sequences using standard ProtParam-equivalent methods

Used by:

- `biochem_properties.py` (LRU-cached lookup by gene ID)
- provides MW, pI, GRAVY, instability, aliphatic index, and atomic composition to the LLM for biological interpretation

### `mapping.csv`

Schema:

- `Transcript id` (canonical `Ca_XXXXX`)
- `LOC id` (LOC accession or alias/symbol)

Meaning:

- enables ID resolution from LOC/symbol to canonical transcript ID

Used by:

- `id_mapper.py`
- `gene_collector.py` (indirectly via `id_mapper`)

## Individual expression files

Folder: `Individual Files/` (15 CSVs)

Includes stress studies for:

- Cold
- Drought
- Salinity
- Heat (multi-cultivar)

Examples:

- `Cold_Top.csv`
- `Drought_53711_Top.csv`
- `SalinityRootShoot53711_Top.csv`
- `Cultivar_92944_filtered.csv`

Notes:

- gene identifier column names vary by file
- control/stress column names vary by experiment
- `gene_collector.py` maintains a registry mapping each file to valid control/stress pairs

## GEO/BioProject accession mapping

Expression data originates from public RNA-seq datasets. The pipeline maps each stress type to its source accession IDs:

| Stress | Accession IDs |
|---|---|
| Heat | PRJNA748749 |
| Cold | GSE53711 |
| Drought | GSE53711, GSE104609, GSE193077 |
| Salinity | GSE53711, GSE70377, GSE110127, GSE204727 |

These are displayed in expression tables (Source column) and rendered as clickable NCBI links in the GUI.

## Data interpretation rules

Rules are implemented in code and mirrored in `rag_pipeline/rules.md`.

1. ID normalization:
- standard canonical form is `Ca_XXXXX`

2. Log2FC formula:
- `log2((stress_fpkm + 1) / (control_fpkm + 1))`

3. Significance thresholds:
- `>= 1.5`: `UPREGULATED`
- `<= -1.5`: `DOWNREGULATED`
- otherwise: `NOT_SIGNIFICANT`

4. Missing values:
- NaN/non-numeric pairs are skipped
- no missing-value imputation is allowed

5. Three-state stress status:
- `RESPONSIVE`
- `NOT_RESPONSIVE`
- `UNKNOWN`

## Practical data caveats

- Binary matrix labels and expression evidence can diverge due to thresholding/statistical differences.
- A gene can have a peptide sequence even when expression data is missing.
- Not all files contain every gene ID; absence in one file does not imply global absence.
- BiochemicalProperties.csv covers all 28,269 peptide sequences; lookup returns None only for gene IDs without a peptide sequence.
