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
OUTPUT_FILENAME="Tokyo_Personnel_Master_All_Years_v2.csv"

# Clean start
rm -rf "$TEMP_DIR"
mkdir -p "$TEMP_DIR"

echo "=========================================================="
echo "   STARTING MASTER MERGE FOR ALL YEARS (v2)"
echo "=========================================================="

echo "1. Fetching Final CSVs from Box (direct per-year download)..."
# Download each year directly to avoid slow recursive tree scan
for level in TokyoFu TokyoShi TokyoTo; do
  for year_dir in $(rclone lsf "$BOX_ROOT/$level/" --dirs-only 2>/dev/null); do
    year=$(echo "$year_dir" | tr -d '/')
    src="$BOX_ROOT/$level/$year/${year}_${level}_Final.csv"
    dst="$TEMP_DIR/$level/$year/"
    mkdir -p "$dst"
    rclone copy "$src" "$dst" --ignore-times 2>/dev/null &
  done
done
wait
echo "   Downloads complete."

echo "2. Running Metadata-Aware Python Merge with Staff ID + Office ID..."
module load python/3.10
source ~/tokyo_env/bin/activate

python -u <<'PYEOF'
import pandas as pd
import glob
import os
import re

# Find all CSVs recursively inside the temp folder
temp_dir = os.environ.get("TEMP_DIR", os.path.expanduser("~/scratch/master_merge_all"))
search_path = os.path.join(temp_dir, "**", "*_Final.csv")
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

if not all_dfs:
    print("\n[CRITICAL ERROR] No dataframes were combined.")
    exit(1)

print("  -> Concatenating dataframes...")
master_df = pd.concat(all_dfs, ignore_index=True, sort=False)

# Fill NAs to keep it clean
master_df.fillna("", inplace=True)

# --- Office ID ---
print("  -> Assigning office IDs...")
unique_offices = sorted(master_df['office'].unique())
office_id_map = {name: i for i, name in enumerate(unique_offices)}
master_df['office_id'] = master_df['office'].map(office_id_map)
print(f"     {len(unique_offices)} unique offices assigned IDs.")

# --- Staff ID ---
print("  -> Assigning staff IDs...")

# Check if is_name column exists (from updated compile_tokyo_dataframe.py)
has_is_name = 'is_name' in master_df.columns

# Exact match grouping by name only (employees move between offices)
staff_id_counter = 0
staff_id_col = pd.Series(pd.NA, index=master_df.index, dtype='Int64')

if has_is_name:
    name_mask = master_df['is_name'].astype(str).str.lower() == 'true'
else:
    name_mask = master_df['name'].astype(str).str.strip() != ''

name_rows = master_df[name_mask].copy()

exact_groups = name_rows.groupby('name').groups
exact_id_map = {}  # name -> staff_id

for name, indices in exact_groups.items():
    if name not in exact_id_map:
        exact_id_map[name] = staff_id_counter
        staff_id_counter += 1
    for idx in indices:
        staff_id_col.iloc[idx] = exact_id_map[name]

master_df['staff_id'] = staff_id_col

n_unique_staff = master_df['staff_id'].dropna().nunique()
print(f"     {n_unique_staff} unique staff IDs assigned.")

# --- Save ---
output_filename = os.environ.get("OUTPUT_FILENAME", "Tokyo_Personnel_Master_All_Years_v2.csv")
master_df.to_csv(output_filename, index=False, encoding='utf-8-sig')

print(f"\nSUCCESS: Created Master v2 with {len(master_df)} records.")
print(f"Years included: {sorted(master_df['year'].unique())}")
print(f"Columns: {list(master_df.columns)}")
PYEOF

echo "3. Uploading Master File to Box..."
if [ -f "$OUTPUT_FILENAME" ]; then
    rclone copy "$OUTPUT_FILENAME" "$BOX_ROOT/" --progress
    echo "DONE. File saved to: $BOX_ROOT/$OUTPUT_FILENAME"
else
    echo "Merge failed, no file to upload."
fi
