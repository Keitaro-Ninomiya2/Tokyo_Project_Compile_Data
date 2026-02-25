# Tokyo Personnel Directory Compiler

Pipeline for extracting, compiling, and structuring personnel records from digitized Tokyo Metropolitan Government directories (1937–1958). Covers three government levels — 東京市 (TokyoShi), 東京府 (TokyoFu), and 東京都 (TokyoTo) — across 21 year-level combinations.

## Pipeline Overview

```
OCR XML files (~/scratch/{Level}_{Year}_Raw/)
        │
        ▼
process_tokyo_directory.py   →  raw_{Year}_{Level}.csv
        │
        ▼
compile_tokyo_dataframe.py   →  {Year}_{Level}_Final.csv
        │                       (uploaded to Box per year)
        ▼
merge_all_years.slurm        →  Tokyo_Personnel_Master_All_Years_v2.csv
                                (uploaded to Box)
```

**Stage 1 — Extraction** (`process_tokyo_directory.py`): Parses NDL OCR XML files, splits name/position tokens using SudachiPy morphological analysis, and extracts salary, rank, and grade metadata embedded in raw text.

**Stage 2 — Compilation** (`compile_tokyo_dataframe.py`): Detects office headers and position titles, propagates them across rows, validates names (SudachiPy 人名 check with heuristic fallback), classifies gender, flags drafted staff, and infers the full office hierarchy (局→部→課→係).

**Stage 3 — Master Merge** (`merge_all_years.slurm`): Downloads all per-year Final CSVs from Box, concatenates them, assigns deterministic `office_id` and cross-year `staff_id`, and re-uploads the master file.

## Coverage

| Level | Years |
|---|---|
| TokyoFu (東京府) | 1938, 1939, 1940, 1941 |
| TokyoShi (東京市) | 1937, 1938, 1939, 1940, 1941, 1942, 1943 |
| TokyoTo (東京都) | 1944, 1946, 1948, 1950, 1951, 1952, 1953, 1954, 1955, 1958 |

## Running the Pipeline

**Full run (all available years):**
```bash
sbatch process_all_years.slurm
```
Loops through all `~/scratch/*_*_Raw/` directories, runs both extraction and compilation stages, and uploads each year's Final CSV to Box.

**Master merge** (after per-year CSVs are in Box):
```bash
sbatch merge_all_years.slurm
```
Or run directly without waiting for a cluster node:
```bash
source ~/tokyo_env/bin/activate
# Download fresh CSVs from Box first, then:
python merge_script.py   # inline Python block in merge_all_years.slurm
rclone copy Tokyo_Personnel_Master_All_Years_v2.csv "uiucbox:..."
```

**Single year (manual):**
```bash
python process_tokyo_directory.py \
    --input_dir ~/scratch/TokyoTo_1951_Raw \
    --crosswalk PositionCrosswalk.csv \
    --output raw_1951_TokyoTo.csv \
    --year_col 1951

python compile_tokyo_dataframe.py \
    --input_csv raw_1951_TokyoTo.csv \
    --crosswalk PositionCrosswalk.csv \
    --output 1951_TokyoTo_Final.csv \
    --year_col 1951
```

## Output Columns

See `DATA_DICTIONARY.md` for full details. Key columns:

| Column | Description |
|---|---|
| `year`, `gov_level` | Year and government level (TokyoShi/TokyoFu/TokyoTo) |
| `office` | Raw office/section name from OCR |
| `office_norm` | Normalized office name (旧字体→新字体, symbols stripped) |
| `off_level` | Hierarchy level: 1=局, 2=部, 3=課, 4=係 |
| `kyoku` / `bu` / `ka` / `kakari` | Forward-filled 局/部/課/係 assignment |
| `is_index_page` | `True` if page has 3+ distinct 局 (index page, not detail page) |
| `name` | Personal name after metadata extraction |
| `is_name` | `True` if name passes plausibility checks (use to filter to employees) |
| `position` | Position title matched against `PositionCrosswalk.csv` |
| `gender_legacy` / `gender_modern` | Heuristic gender classification |
| `salary`, `rank`, `grade` | Metadata extracted from raw OCR text |
| `staff_id` | Cross-year person identifier (exact + fuzzy name matching) |
| `office_id` | Deterministic numeric office ID for fixed-effects use |

Filter to employees only: `df[(df.is_name == True) & (~df.is_index_page)]`

## Office Hierarchy Inference

`compile_tokyo_dataframe.py` infers the 局→部→課→係 nesting from the sequence of office headers within each year. Normalization applies a 66-character 旧字体 map (e.g. 氣→気, 變→変, 廳→庁) and strips leading markers and parenthetical OCR artifacts before suffix matching. The diagnostic print at compile time lists unmatched Japanese office names to support iterative rule refinement.

## Requirements

- Python 3.10
- `sudachipy`, `sudachidict_core` — morphological analysis for name validation and splitting
- `pandas`, `tqdm`
- `rclone` configured with `uiucbox` remote — for Box upload/download
- SLURM cluster (IllinoisComputes, account `keitaro2-ic`) for batch runs

Install Python dependencies:
```bash
pip install -r requirements.txt
```

## Repository Structure

```
├── process_tokyo_directory.py   Stage 1: XML → raw CSV
├── compile_tokyo_dataframe.py   Stage 2: raw CSV → Final CSV with hierarchy
├── process_all_years.slurm      Full pipeline batch job (all years)
├── merge_all_years.slurm        Master merge + Box upload
├── run_batch_gpu.slurm          GPU job for OCR inference (NDL OCR v2)
├── PositionCrosswalk.csv        Position title lookup table (not in repo, on Box)
├── DATA_DICTIONARY.md           Column-level documentation for the master CSV
├── ocrcli/                      NDL OCR v2 CLI wrapper
└── submodules/                  NDL OCR component models (page sep, layout, OCR, etc.)
```
