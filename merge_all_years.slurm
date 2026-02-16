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

echo "1. Fetching ALL '_Final.csv' files from Box (Recursive)..."
# This downloads the directory structure but ONLY the final CSVs
# It will find things like: TokyoShi/1925/1925_TokyoShi_Final.csv
rclone copy "$BOX_ROOT" "$TEMP_DIR" --include "*_Final.csv" --transfers=10

echo "2. Running Metadata-Aware Python Merge with Staff ID + Office ID..."
module load python/3.10
source ~/tokyo_env/bin/activate

python -u <<'PYEOF'
import pandas as pd
import glob
import os
import re
from difflib import SequenceMatcher

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

# Try to use rapidfuzz if available, fall back to difflib
try:
    from rapidfuzz import fuzz
    def name_similarity(a, b):
        return fuzz.ratio(a, b) / 100.0
    print("     Using rapidfuzz for name matching.")
except ImportError:
    def name_similarity(a, b):
        return SequenceMatcher(None, a, b).ratio()
    print("     Using difflib for name matching (rapidfuzz not available).")

# Build name-office groups for staff ID assignment
staff_id_counter = 0
staff_id_col = pd.Series(pd.NA, index=master_df.index, dtype='Int64')

if has_is_name:
    name_mask = master_df['is_name'].astype(str).str.lower() == 'true'
else:
    # Fallback: treat all non-empty names as valid
    name_mask = master_df['name'].astype(str).str.strip() != ''

name_rows = master_df[name_mask].copy()

# Step 1: Exact match grouping by (name, office)
exact_groups = name_rows.groupby(['name', 'office']).groups
exact_id_map = {}  # (name, office) -> staff_id

for (name, office), indices in exact_groups.items():
    key = (name, office)
    if key not in exact_id_map:
        exact_id_map[key] = staff_id_counter
        staff_id_counter += 1
    for idx in indices:
        staff_id_col.iloc[idx] = exact_id_map[key]

# Step 2: Fuzzy match within each office (merge similar names)
print("     Running fuzzy name matching within offices...")
office_names = name_rows.groupby('office')['name'].apply(lambda x: list(x.unique()))

merge_map = {}  # old_staff_id -> new_staff_id (for merging clusters)

for office, names in office_names.items():
    if len(names) < 2:
        continue
    # Only fuzzy match names > 2 chars (short names are too risky)
    long_names = [n for n in names if len(n) > 2]
    for i in range(len(long_names)):
        for j in range(i + 1, len(long_names)):
            sim = name_similarity(long_names[i], long_names[j])
            if sim >= 0.85:
                id_i = exact_id_map.get((long_names[i], office))
                id_j = exact_id_map.get((long_names[j], office))
                if id_i is not None and id_j is not None and id_i != id_j:
                    # Merge: map the higher ID to the lower one
                    high, low = max(id_i, id_j), min(id_i, id_j)
                    merge_map[high] = low

# Apply merge map transitively
def resolve_id(sid, mmap):
    visited = set()
    while sid in mmap and sid not in visited:
        visited.add(sid)
        sid = mmap[sid]
    return sid

if merge_map:
    n_merges = len(merge_map)
    for idx in staff_id_col.dropna().index:
        old_id = staff_id_col.iloc[idx]
        new_id = resolve_id(old_id, merge_map)
        if new_id != old_id:
            staff_id_col.iloc[idx] = new_id
    print(f"     Merged {n_merges} fuzzy name clusters.")

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
