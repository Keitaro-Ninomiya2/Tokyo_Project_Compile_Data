#!/bin/bash

# --- RA Configuration ---
PYTHON_BIN="$HOME/.conda/envs/ndlocr/bin/python3"
REMOTE="uiucbox"
BOX_BASE="Research Notes (keitaro2@illinois.edu)/Tokyo_Gender/Processed_Data"
LOCAL_ROOT="$HOME/ndlocr_v2_cluster"

# --- The Grand Loop (Years 1937 to 1945) ---
for YEAR in {1937..1945}; do
    echo "📅 YEAR: $YEAR"

    # --- Sub-Loop (Administrative Units) ---
    for TYPE in TokyoShi TokyoFu TokyoTo; do
        BOX_ROOT="$BOX_BASE/$TYPE/$YEAR"
        
        echo "🔍 Checking for data in: $TYPE/$YEAR"
        PAGES=$(rclone lsf "$REMOTE:$BOX_ROOT" --dirs-only 2>/dev/null)
        
        if [ -z "$PAGES" ]; then
            continue
        fi

        # --- Page Loop ---
        for PAGE in $PAGES; do
            PAGE_CLEAN=${PAGE%/}
            echo "------------------------------------------------"
            echo "📂 TARGET: $TYPE/$YEAR/$PAGE_CLEAN"
            
            # Skip if XML results already exist
            CHECK_OUT=$(rclone lsl "$REMOTE:$BOX_ROOT/$PAGE_CLEAN/NDLoutput" --include "*.xml" 2>/dev/null | wc -l)
            if [ "$CHECK_OUT" -gt 0 ]; then
                echo "⏭️  Skipping: XML already exists."
                continue
            fi

            # Clean & Prep Local Space
            rm -rf "$LOCAL_ROOT/input_data/img"/*
            mkdir -p "$LOCAL_ROOT/input_data/img"

            # Download
            echo "📥 Downloading images..."
            rclone copy "$REMOTE:$BOX_ROOT/$PAGE_CLEAN/img" "$LOCAL_ROOT/input_data/img"

            # Execute OCR
            echo "🤖 Running NDL OCR (XML Mode)..."
            $PYTHON_BIN main.py infer input_data output_data_final -x

            # Detect and Upload Timestamped Folder
            REAL_OUTPUT=$(ls -td output_data_final_* 2>/dev/null | head -n 1)
            if [ -n "$REAL_OUTPUT" ]; then
                echo "📤 Uploading to Box..."
                rclone copy "$REAL_OUTPUT" "$REMOTE:$BOX_ROOT/$PAGE_CLEAN/NDLoutput"
            fi

            # Cleanup Local Temp Files
            rm -rf "$LOCAL_ROOT/input_data/img"/*
            rm -rf output_data_final_*
            
            echo "✅ Finished $TYPE/$YEAR/$PAGE_CLEAN"
        done
    done
done
