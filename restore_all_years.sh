#!/bin/bash
# Iterates 1937-1960 for TokyoShi, TokyoFu, and TokyoTo
# Skips download if XML files are already present locally.

BOX_ROOT="uiucbox:Research Notes (keitaro2@illinois.edu)/Tokyo_Gender"
PREFIXES=("TokyoShi" "TokyoFu" "TokyoTo")

echo "Starting data restoration for 1937-1960..."

for YEAR in {1937..1960}; do
    for PREFIX in "${PREFIXES[@]}"; do

        # Construct paths
        # Source: .../Processed_Data/TokyoShi/1937
        BOX_PATH="Processed_Data/${PREFIX}/${YEAR}"
        # Dest: .../TokyoShi_1937_Raw
        DEST="$HOME/scratch/${PREFIX}_${YEAR}_Raw"

        # 1. Check if we should skip (Idempotency)
        if [ -d "$DEST" ] && [ -n "$(find "$DEST" -name "*.xml" -print -quit 2>/dev/null)" ]; then
            echo "[SKIP] ${PREFIX} ${YEAR} already exists in scratch."
            continue
        fi

        # 2. Attempt Download
        # We use '|| true' so the script keeps going if a specific folder is missing on Box
        echo "[CHECKING] Attempting to download ${PREFIX}/${YEAR}..."

        mkdir -p "$DEST"
        rclone copy "$BOX_ROOT/$BOX_PATH/" "$DEST/" --include "**/*.xml" --progress || true

        # Cleanup: remove directory if it's empty (path didn't exist on Box)
        if [ -z "$(ls -A "$DEST")" ]; then
            rmdir "$DEST"
        fi

    done
done

echo "Restoration process complete."
