#!/bin/bash
#SBATCH --partition=IllinoisComputes
#SBATCH --account=keitaro2-ic
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --mem=64G
#SBATCH --time=00:30:00
#SBATCH --job-name=Tokyo_Fixed_Merge
#SBATCH --output=merge_fixed_%j.out

# --- CONFIGURATION ---
BOX_ROOT="uiucbox:Research Notes (keitaro2@illinois.edu)/Tokyo_Gender/Processed_Data"
TEMP_DIR="$HOME/scratch/master_merge_fixed"
mkdir -p "$TEMP_DIR"

echo "1. Fetching files from Box..."
# Explicitly grabbing the 12 files
rclone copy "$BOX_ROOT/TokyoShi/1937/1937_TokyoShi_Final.csv" "$TEMP_DIR/"
rclone copy "$BOX_ROOT/TokyoFu/1938/1938_TokyoFu_Final.csv" "$TEMP_DIR/"
rclone copy "$BOX_ROOT/TokyoShi/1938/1938_TokyoShi_Final.csv" "$TEMP_DIR/"
rclone copy "$BOX_ROOT/TokyoFu/1939/1939_TokyoFu_Final.csv" "$TEMP_DIR/"
rclone copy "$BOX_ROOT/TokyoShi/1939/1939_TokyoShi_Final.csv" "$TEMP_DIR/"
rclone copy "$BOX_ROOT/TokyoFu/1940/1940_TokyoFu_Final.csv" "$TEMP_DIR/"
rclone copy "$BOX_ROOT/TokyoShi/1940/1940_TokyoShi_Final.csv" "$TEMP_DIR/"
rclone copy "$BOX_ROOT/TokyoFu/1941/1941_TokyoFu_Final.csv" "$TEMP_DIR/"
rclone copy "$BOX_ROOT/TokyoShi/1941/1941_TokyoShi_Final.csv" "$TEMP_DIR/"
rclone copy "$BOX_ROOT/TokyoShi/1942/1942_TokyoShi_Final.csv" "$TEMP_DIR/"
rclone copy "$BOX_ROOT/TokyoShi/1943/1943_TokyoShi_Final.csv" "$TEMP_DIR/"
rclone copy "$BOX_ROOT/TokyoTo/1944/1944_TokyoTo_Final.csv" "$TEMP_DIR/"

echo "2. Running Metadata-Aware Python Merge..."
module load python/3.10
source ~/tokyo_env/bin/activate

python -u <<EOF
import pandas as pd
import glob
import os
import re

files = glob.glob("$TEMP_DIR/*.csv")
print(f"Found {len(files)} files. Starting merge...")

all_dfs = []

for f in sorted(files):
    fname = os.path.basename(f)
    print(f"  -> Processing: {fname}")
    
    # Extract Year and Level from filename using Regex
    # Matches 4 digits (Year) and the specific Tokyo levels
    year_match = re.search(r'(19\d{2})', fname)
    level_match = re.search(r'(TokyoShi|TokyoFu|TokyoTo)', fname, re.IGNORECASE)
    
    file_year = year_match.group(1) if year_match else "Unknown"
    file_level = level_match.group(1) if level_match else "Unknown"
    
    try:
        # Read the CSV
        df = pd.read_csv(f)
        
        # OVERWRITE the 'year' column with the actual year from the filename
        df['year'] = file_year
        # ADD the gov_level column
        df['gov_level'] = file_level
        
        all_dfs.append(df)
    except Exception as e:
        print(f"     [ERROR] Failed to read {fname}: {e}")

if all_dfs:
    master_df = pd.concat(all_dfs, ignore_index=True, sort=False)
    master_df.fillna("", inplace=True)
    master_df.to_csv("Tokyo_Personnel_Master_1937_1944.csv", index=False, encoding='utf-8-sig')
    print(f"\nSUCCESS: Created Master with {len(master_df)} records.")
    print(f"Years found: {master_df['year'].unique()}")
else:
    print("\n[CRITICAL ERROR] No dataframes were combined.")
EOF

echo "3. Uploading to Box..."
rclone copy "Tokyo_Personnel_Master_1937_1944.csv" "$BOX_ROOT/" --progress
echo "DONE."
