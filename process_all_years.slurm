#!/bin/bash
#SBATCH --partition=IllinoisComputes
#SBATCH --account=keitaro2-ic
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --mem=32G
#SBATCH --time=12:00:00
#SBATCH --job-name=Tokyo_Full_Repair
#SBATCH --output=production_%j.out

# --- CONFIGURATION ---
REPO_DIR="$HOME/Tokyo_Project_Compile_Data"
SCRATCH_BASE="$HOME/scratch"
BOX_BASE="uiucbox:Research Notes (keitaro2@illinois.edu)/Tokyo_Gender/Processed_Data"
CROSSWALK="$REPO_DIR/PositionCrosswalk.csv"

module load python/3.10
source ~/tokyo_env/bin/activate

echo "=========================================================="
echo "   STARTING REPAIR & PRODUCTION RUN: 1937 - 1944"
echo "=========================================================="

# Comprehensive list based on your scratch diagnostic
YEARS=(
    "TokyoShi|1937"
    "TokyoFu|1938"
    "TokyoShi|1938"
    "TokyoFu|1939"
    "TokyoShi|1939"
    "TokyoFu|1940"
    "TokyoShi|1940"
    "TokyoFu|1941"
    "TokyoShi|1941"
    "TokyoShi|1942"
    "TokyoShi|1943"
    "TokyoTo|1944"
)

for ENTRY in "${YEARS[@]}"; do
    IFS="|" read -r LEVEL YEAR <<< "$ENTRY"
    
    DATA_DIR="$SCRATCH_BASE/${LEVEL}_${YEAR}_Raw"
    BOX_DEST="$BOX_BASE/$LEVEL/$YEAR/"
    
    echo "------------------------------------------------"
    echo "TARGET: $LEVEL $YEAR"
    echo "------------------------------------------------"

    if [ ! -d "$DATA_DIR" ]; then
        echo "   [!] Folder missing in scratch. Skipping $YEAR."
        continue
    fi

    # --- STEP 1: UNIVERSAL REPAIR & FLATTEN ---
    echo "   -> Cleaning and Flattening structure..."
    
    # 1. Find 'input_data.sorted.xml' inside subfolders (depth 2+) and move them out
    # This specifically rescues the "Trapped" data in 1938 and 1943
    find "$DATA_DIR" -mindepth 2 -name "input_data.sorted.xml" | while read filepath; do
        PAGENAME=$(echo "$filepath" | grep -o "Page[0-9]*" | head -n1)
        if [ ! -z "$PAGENAME" ]; then
            mv "$filepath" "$DATA_DIR/${PAGENAME}.xml"
        fi
    done

    # 2. Cleanup: Remove subdirectories to fix "Dirty/Mixed" states
    # This leaves top-level XMLs and the 'Big Merged Files' alone
    find "$DATA_DIR" -maxdepth 1 -type d -not -path "$DATA_DIR" -exec rm -rf {} +
    
    # Check final file state
    XML_COUNT=$(ls "$DATA_DIR"/*.xml 2>/dev/null | wc -l)
    echo "   -> Ready to process $XML_COUNT XML files."

    # --- STEP 2: RUN EXTRACTION ---
    RAW_CSV="raw_${YEAR}_${LEVEL}.csv"
    FINAL_CSV="${YEAR}_${LEVEL}_Final.csv"

    # Note: Using the updated python script that handles both single and multi-page XMLs
    python -u "$REPO_DIR/process_tokyo_directory.py" \
        --input_dir "$DATA_DIR" \
        --crosswalk "$CROSSWALK" \
        --output "$RAW_CSV" \
        --year_col "DuringWar"

    # --- STEP 3: RUN COMPILATION ---
    if [ -f "$RAW_CSV" ] && [ -s "$RAW_CSV" ]; then
        echo "   -> Compiling..."
        python -u "$REPO_DIR/compile_tokyo_dataframe.py" \
            --input_csv "$RAW_CSV" \
            --crosswalk "$CROSSWALK" \
            --output "$FINAL_CSV" \
            --year_col "DuringWar"
            
        # --- STEP 4: UPLOAD ---
        if [ -f "$FINAL_CSV" ]; then
            echo "   -> Uploading to Box..."
            rclone copy "$FINAL_CSV" "$BOX_DEST" --ignore-times
            echo "   [SUCCESS] $YEAR complete."
            # Clean up temporary CSVs to save scratch space
            rm "$RAW_CSV" "$FINAL_CSV"
        else
            echo "   [ERROR] Compilation failed."
        fi
    else
        echo "   [ERROR] Extraction failed or produced no data."
    fi
done

echo "=========================================================="
echo "   ALL YEARS FINISHED"
echo "=========================================================="
