import pandas as pd
import os
import subprocess
import sys

# --- Configuration ---
BOX_BASE = "uiucbox:Research Notes (keitaro2@illinois.edu)/Tokyo_Gender/Processed_Data"
OUTPUT_FILE = "Tokyo_Gender_Master_Panel_ALL_YEARS.csv"

def get_box_folders(remote_path):
    """
    Uses rclone to list subdirectories in a given Box folder.
    Returns a list of folder names (e.g., ['1937', '1938']).
    """
    try:
        # 'lsf --dirs-only' returns cleaner output than 'lsd'
        cmd = ["rclone", "lsf", "--dirs-only", remote_path]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        # rclone returns "Foldername/", so we strip the slash
        folders = [line.strip('/') for line in result.stdout.splitlines()]
        return folders
    except subprocess.CalledProcessError:
        print(f"   [!] Could not list folders in: {remote_path}")
        return []

print("==========================================================")
print("   DYNAMIC DISCOVERY & MERGE PROTOCOL")
print("==========================================================")

all_data = []

# 1. Discover Government Levels (TokyoShi vs TokyoFu)
print(f"\nStep 1: Scanning Box at {BOX_BASE}...")
levels = get_box_folders(BOX_BASE)

if not levels:
    print("Error: No folders found in Box path. Check your rclone config.")
    sys.exit()

print(f"Found Levels: {levels}")

# 2. Iterate through Levels and Years
for level in levels:
    level_path = f"{BOX_BASE}/{level}"
    print(f"\n--> Scanning {level}...")
    
    # Discover Years dynamically
    years = get_box_folders(level_path)
    print(f"    Found Years: {years}")
    
    for year in years:
        # Construct the expected filename based on our convention
        # Format: 1937_TokyoShi_Final_Research_Data.csv
        csv_filename = f"{year}_{level}_Final_Research_Data.csv"
        box_file_path = f"{level_path}/{year}/{csv_filename}"
        
        # Download
        print(f"    Processing {year}...", end=" ", flush=True)
        
        # Check if file exists in Box before trying to copy
        # We use 'rclone ls' to verify existence to avoid creating empty files
        check_cmd = ["rclone", "ls", box_file_path]
        check = subprocess.run(check_cmd, capture_output=True)
        
        if check.returncode == 0:
            # File exists, download it
            subprocess.run(["rclone", "copy", box_file_path, "."], check=True)
            
            if os.path.exists(csv_filename):
                try:
                    df = pd.read_csv(csv_filename)
                    
                    # Tag metadata
                    df['Gov_Level'] = level
                    df['Year_Source'] = year
                    
                    all_data.append(df)
                    print(f"[OK] ({len(df)} rows)")
                    
                    # Cleanup local file to keep folder clean
                    os.remove(csv_filename)
                    
                except Exception as e:
                    print(f"[Error Reading CSV] {e}")
            else:
                print("[Download Failed]")
        else:
            print("[Skipping] (No Final Data CSV found)")

# 3. Merge and Save
if all_data:
    print("\nStep 3: Compiling Final Master Panel...")
    master_df = pd.concat(all_data, ignore_index=True)
    
    # Sort for tidiness
    if 'Year_Source' in master_df.columns:
        master_df = master_df.sort_values(by=['Year_Source', 'Gov_Level'])
    
    # Save locally
    master_df.to_csv(OUTPUT_FILE, index=False)
    
    print("="*50)
    print(f"SUCCESS! Master Panel saved: {OUTPUT_FILE}")
    print(f"Total Records: {len(master_df)}")
    print(f"Years Covered: {sorted(master_df['Year_Source'].unique())}")
    print("="*50)
    
    # 4. Upload to Box
    print("Uploading to Box...")
    subprocess.run(["rclone", "copy", OUTPUT_FILE, "uiucbox:Research Notes (keitaro2@illinois.edu)/Tokyo_Gender/"], check=True)
    print("Done.")
    
else:
    print("\n[FAILURE] No data found to merge.")
