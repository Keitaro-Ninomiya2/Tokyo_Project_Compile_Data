#!/bin/bash
#SBATCH --partition=IllinoisComputes
#SBATCH --account=keitaro2-ic
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --mem=32G
#SBATCH --time=12:00:00
#SBATCH --job-name=Tokyo_Auto_Process
#SBATCH --output=production_auto_%j.out

# --- CONFIGURATION ---
REPO_DIR="$HOME/Tokyo_Project_Compile_Data"
SCRATCH_BASE="$HOME/scratch"
BOX_BASE="uiucbox:Research Notes (keitaro2@illinois.edu)/Tokyo_Gender/Processed_Data"
CROSSWALK="$REPO_DIR/PositionCrosswalk.csv"

# Load Environment
module load python/3.10
export LD_LIBRARY_PATH=/sw/apps/python/3.10.16/lib:$LD_LIBRARY_PATH
source ~/tokyo_env/bin/activate

echo "=========================================================="
echo "   STARTING AUTOMATED DISCOVERY & PRODUCTION RUN"
echo "=========================================================="

# Ensure latest scripts are in the repo directory
cp "$HOME/Tokyo_Project/name_split/process_tokyo_directory.py" "$REPO_DIR/" 2>/dev/null
cp "$HOME/Tokyo_Project/name_split/compile_tokyo_dataframe.py" "$REPO_DIR/" 2>/dev/null

# Loop through ALL directories in scratch matching the pattern "Name_Year_Raw"
for DIR_PATH in "$SCRATCH_BASE"/*_*_Raw; do

    # 1. Validation: Ensure it is a directory
    if [ ! -d "$DIR_PATH" ]; then
        continue
    fi

    # Get just the folder name (remove the full path)
    DIR_NAME=$(basename "$DIR_PATH")

    # 2. Parsing: Extract Level and Year using Regex
    # Matches format: "TokyoShi_1925_Raw" -> Level="TokyoShi", Year="1925"
    if [[ "$DIR_NAME" =~ ^([A-Za-z]+)_([0-9]{4})_Raw$ ]]; then
        LEVEL="${BASH_REMATCH[1]}"
        YEAR="${BASH_REMATCH[2]}"
        
        DATA_DIR="$DIR_PATH"
        BOX_DEST="$BOX_BASE/$LEVEL/$YEAR/"
        
        echo "------------------------------------------------"
        echo "PROCESSING: $LEVEL $YEAR (Found in $DIR_NAME)"
        echo "------------------------------------------------"

        # --- STEP 1: UNIVERSAL REPAIR & FLATTEN ---
        # Rescue nested 'input_data.sorted.xml' files (depth 2+)
        find "$DATA_DIR" -mindepth 2 -name "input_data.sorted.xml" | while read filepath; do
            PAGENAME=$(echo "$filepath" | grep -o "Page[0-9]*" | head -n1)
            if [ ! -z "$PAGENAME" ]; then
                mv "$filepath" "$DATA_DIR/${PAGENAME}.xml"
            fi
        done

        # Remove empty subdirectories
        find "$DATA_DIR" -maxdepth 1 -type d -not -path "$DATA_DIR" -exec rm -rf {} +
        
        # Check file count
        XML_COUNT=$(ls "$DATA_DIR"/*.xml 2>/dev/null | wc -l)
        if [ "$XML_COUNT" -eq 0 ]; then
            echo "   [SKIP] No XML files found."
            continue
        fi
        echo "   -> Ready to process $XML_COUNT XML files."

        # --- STEP 2: RUN EXTRACTION ---
        RAW_CSV="raw_${YEAR}_${LEVEL}.csv"
        FINAL_CSV="${YEAR}_${LEVEL}_Final.csv"

        python -u "$REPO_DIR/process_tokyo_directory.py" \
            --input_dir "$DATA_DIR" \
            --crosswalk "$CROSSWALK" \
            --output "$RAW_CSV" \
            --year_col "$YEAR"

        # --- STEP 3: RUN COMPILATION ---
        if [ -f "$RAW_CSV" ] && [ -s "$RAW_CSV" ]; then
            echo "   -> Compiling..."
            python -u "$REPO_DIR/compile_tokyo_dataframe.py" \
                --input_csv "$RAW_CSV" \
                --crosswalk "$CROSSWALK" \
                --output "$FINAL_CSV" \
                --year_col "$YEAR"
                
            # --- STEP 4: UPLOAD ---
            if [ -f "$FINAL_CSV" ]; then
                echo "   -> Uploading to Box..."
                rclone copy "$FINAL_CSV" "$BOX_DEST" --ignore-times
                echo "   [SUCCESS] $YEAR complete."
                
                # Cleanup CSVs to save space
                rm "$RAW_CSV" "$FINAL_CSV"
            else
                echo "   [ERROR] Compilation failed."
            fi
        else
            echo "   [ERROR] Extraction failed or produced no data."
        fi
    fi
done

echo "=========================================================="
echo "   ALL DISCOVERED YEARS FINISHED"
echo "=========================================================="
