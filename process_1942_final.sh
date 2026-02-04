#!/bin/bash

# --- 1. Meticulous RA Configuration ---
# Direct path to your conda environment's python
PYTHON_BIN="$HOME/.conda/envs/ndlocr/bin/python3"

# Box Paths (Tailored to your specific directory structure)
REMOTE="uiucbox"
BOX_ROOT="Research Notes (keitaro2@illinois.edu)/Tokyo_Gender/Processed_Data/TokyoShi/1942"
LOCAL_ROOT="$HOME/ndlocr_v2_cluster"

# --- 2. Initial Setup ---
echo "🔄 Initializing Environment..."
if [ ! -f "$PYTHON_BIN" ]; then
    echo "❌ ERROR: Python engine not found at $PYTHON_BIN"
    exit 1
fi

# Clean up any leftover 'ghost' folders from previous runs
rm -rf "$LOCAL_ROOT/output_data_final_2026"*

echo "🔍 Scanning Box for 1942 directories..."
PAGES=$(rclone lsf "$REMOTE:$BOX_ROOT" --dirs-only)

if [ -z "$PAGES" ]; then
    echo "❌ ERROR: No directories found at $REMOTE:$BOX_ROOT"
    exit 1
fi

echo "🚀 Starting High-Quality Batch Processing (XML Mode)..."

# --- 3. Main Loop ---
for PAGE in $PAGES; do
    PAGE_CLEAN=${PAGE%/}
    echo "------------------------------------------------"
    echo "📂 TARGET: $PAGE_CLEAN"
    
    # Check if XMLs already exist on Box (Prevents re-doing work)
    CHECK_OUT=$(rclone lsl "$REMOTE:$BOX_ROOT/$PAGE_CLEAN/NDLoutput" --include "*.xml" | wc -l)
    if [ "$CHECK_OUT" -gt 0 ]; then
        echo "⏭️  Skipping: XML results already exist on Box."
        continue
    fi

    # Prep Local Workspace
    rm -rf "$LOCAL_ROOT/input_data/img"/*
    mkdir -p "$LOCAL_ROOT/input_data/img"

    # Download images from Box
    echo "📥 Downloading images for $PAGE_CLEAN..."
    rclone copy "$REMOTE:$BOX_ROOT/$PAGE_CLEAN/img" "$LOCAL_ROOT/input_data/img"

    # Execute OCR with XML Layout (-x)
    echo "🤖 Running NDL OCR (XML + Text)..."
    $PYTHON_BIN main.py infer input_data output_data_final -x

    # --- TIMESTAMP HANDLING ---
    # Find the folder NDL OCR just created (the most recent one)
    REAL_OUTPUT=$(ls -td output_data_final_* 2>/dev/null | head -n 1)

    if [ -z "$REAL_OUTPUT" ]; then
        echo "⚠️  WARNING: OCR process finished but no output folder was found."
    else
        echo "📤 Uploading results from $REAL_OUTPUT to Box..."
        # Copying the entire folder structure (xml/ and txt/)
        rclone copy "$REAL_OUTPUT" "$REMOTE:$BOX_ROOT/$PAGE_CLEAN/NDLoutput"
    fi

    # Cleanup: Wipe local temporary data to keep the cluster happy
    rm -rf "$LOCAL_ROOT/input_data/img"/*
    rm -rf output_data_final_*
    
    echo "✅ Finished $PAGE_CLEAN"
done

echo "🎉 YEAR 1942 COMPLETED SUCCESSFULLY."
