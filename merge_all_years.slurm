#!/bin/bash
#SBATCH --partition=IllinoisComputes
#SBATCH --account=keitaro2-ic
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --mem=64G
#SBATCH --time=01:00:00
#SBATCH --job-name=Tokyo_Master_Merge
#SBATCH --output=merge_all_%j.out

# --- CONFIGURATION ---
BOX_ROOT="uiucbox:Research Notes (keitaro2@illinois.edu)/Tokyo_Gender/Processed_Data"
TEMP_DIR="$HOME/scratch/master_merge_all"
OUTPUT_FILENAME="Tokyo_Personnel_Master_All_Years.csv"

# Clean start
rm -rf "$TEMP_DIR"
mkdir -p "$TEMP_DIR"

echo "=========================================================="
echo "   STARTING MASTER MERGE FOR ALL YEARS"
echo "=========================================================="

echo "1. Fetching ALL '_Final.csv' files from Box (Recursive)..."
# This downloads the directory structure but ONLY the final CSVs
# It will find things like: TokyoShi/1925/1925_TokyoShi_Final.csv
rclone copy "$BOX_ROOT" "$TEMP_DIR" --include "*_Final.csv" --transfers=10

echo "2. Running Metadata-Aware Python Merge..."
module load python/3.10
source ~/tokyo_env/bin/activate

python -u <<EOF
import pandas as pd
import glob
import os
import re

# Find all CSVs recursively inside the temp folder
search_path = os.path.join("$TEMP_DIR", "**", "*_Final.csv")
files = glob.glob(search_path, recursive=True)

print(f"Found {len(files)} files to merge.")

if len(files) == 0:
    print("[ERROR] No files found! Check rclone download.")
    exit(1)

all_dfs = []

# Sort to ensure some chronological order in processing
for f in sorted(files):
    fname = os.path.basename(f)
    print(f"  -> Processing: {fname}")
    
    # Extract Year and Level from filename
    # Matches: 1925_TokyoShi_Final.csv -> 1925, TokyoShi
    year_match = re.search(r'(19\d{2})', fname)
    level_match = re.search(r'(TokyoShi|TokyoFu|TokyoTo)', fname, re.IGNORECASE)
    
    file_year = year_match.group(1) if year_match else "Unknown"
    file_level = level_match.group(1) if level_match else "Unknown"
    
    try:
        df = pd.read_csv(f)
        
        # Enforce metadata consistency
        df['year'] = file_year
        df['gov_level'] = file_level
        
        all_dfs.append(df)
    except Exception as e:
        print(f"     [ERROR] Failed to read {fname}: {e}")

if all_dfs:
    print("  -> Concatenating dataframes...")
    master_df = pd.concat(all_dfs, ignore_index=True, sort=False)
    
    # Fill NAs to keep it clean
    master_df.fillna("", inplace=True)
    
    # Save to disk
    master_df.to_csv("$OUTPUT_FILENAME", index=False, encoding='utf-8-sig')
    
    print(f"\nSUCCESS: Created Master with {len(master_df)} records.")
    print(f"Years included: {sorted(master_df['year'].unique())}")
else:
    print("\n[CRITICAL ERROR] No dataframes were combined.")
EOF

echo "3. Uploading Master File to Box..."
if [ -f "$OUTPUT_FILENAME" ]; then
    rclone copy "$OUTPUT_FILENAME" "$BOX_ROOT/" --progress
    echo "DONE. File saved to: $BOX_ROOT/$OUTPUT_FILENAME"
else
    echo "Merge failed, no file to upload."
fi
