#!/bin/bash
#SBATCH --time=04:00:00
#SBATCH --mem=16G
#SBATCH --account=keitaro2-ic
#SBATCH --partition=IllinoisComputes
#SBATCH --output=tokyo_full_pipeline_%j.out

# --- Stage 1: Load Environment ---
module load python/3.10
source ~/tokyo_env/bin/activate

# --- Stage 2: Extraction & Labeling ---
echo "Running Stage 1: Extraction and Labeling..."
python ./process_tokyo_directory.py \
    --input_dir "$HOME/scratch/TokyoShi_1937" \
    --crosswalk "./PositionCrosswalk.csv" \
    --output "raw_labeled_1937.csv" \
    --year_col "DuringWar"

# --- Stage 3: Layout-Aware Compilation ---
# This uses the new grouping logic to catch salaries and structural shifts
echo "Running Stage 2: Hierarchical Compilation..."
python ./compile_tokyo_dataframe.py \
    --input_csv "raw_labeled_1937.csv" \
    --crosswalk "./PositionCrosswalk.csv" \
    --output "1937_TokyoShi_Final_Research_Data.csv" \
    --year_col "DuringWar"

# --- Stage 4: Syncing Outputs to Box ---
echo "Uploading final data to Box..."
# FIX: Removed /usr/bin/ to allow the module environment to locate rclone
rclone copy "1937_TokyoShi_Final_Research_Data.csv" "uiucbox:Research Notes (keitaro2@illinois.edu)/Tokyo_Gender/Processed_Data/TokyoShi/1937/" -P

echo "Pipeline Complete."
