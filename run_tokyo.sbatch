#!/bin/bash
#SBATCH --time=04:00:00
#SBATCH --mem=16G
#SBATCH --account=keitaro2-ic
#SBATCH --partition=IllinoisComputes
#SBATCH --output=tokyo_full_pipeline_%j.out

# --- Stage 0: Syncing Inputs ---
echo "Syncing Crosswalk from Box..."
/usr/bin/rclone copy "uiucbox:Research Notes (keitaro2@illinois.edu)/Tokyo_Gender/Processed_Data/PositionCrosswalk.csv" . -q

# --- Stage 1: Load Environment ---
module load python/3.10
source ~/tokyo_env/bin/activate

# --- Stage 2: Raw Extraction & Labeling ---
# This produces the raw line-by-line labeled file
echo "Running Stage 1: Extraction and Labeling..."
python ./process_tokyo_directory.py \
    --input_dir "$HOME/scratch/TokyoShi_1937" \
    --crosswalk "./PositionCrosswalk.csv" \
    --output "raw_labeled_1937.csv" \
    --year_col "DuringWar"

# --- Stage 3: Hierarchical Compilation ---
# This pivots the data into 1 Name Per Row and links Office/Position
echo "Running Stage 2: Hierarchical Compilation..."
python ./compile_tokyo_dataframe.py \
    --input_csv "raw_labeled_1937.csv" \
    --crosswalk "./PositionCrosswalk.csv" \
    --output "1937_TokyoShi_Final_Research_Data.csv" \
    --year_col "DuringWar"

# --- Stage 4: Syncing Outputs to Box ---
echo "Uploading final data to Box..."
/usr/bin/rclone copy "1937_TokyoShi_Final_Research_Data.csv" "uiucbox:Research Notes (keitaro2@illinois.edu)/Tokyo_Gender/Processed_Data/TokyoShi/1937/" -P

echo "Pipeline Complete."
