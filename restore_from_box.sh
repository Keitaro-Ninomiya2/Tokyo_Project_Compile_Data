#!/bin/bash
# Logic to restore XML/JPG assets from Box to Cluster Scratch
BOX_ROOT="uiucbox:Research Notes (keitaro2@illinois.edu)/Tokyo_Gender"

declare -A TARGETS
TARGETS["Processed_Data/TokyoShi/1941"]="TokyoShi_1941_Raw"
TARGETS["Processed_Data/TokyoFu/1941"]="TokyoFu_1941_Raw"
TARGETS["Processed_Data/TokyoShi/1942"]="TokyoShi_1942_Raw"
TARGETS["Processed_Data/TokyoShi/1943"]="TokyoShi_1943_Raw"
TARGETS["Processed_Data/TokyoTo/1944"]="TokyoTo_1944_Raw"

for BOX_PATH in "${!TARGETS[@]}"; do
    DEST="$HOME/scratch/${TARGETS[$BOX_PATH]}"
    mkdir -p "$DEST"
    echo "Restoring XMLs for $BOX_PATH..."
    rclone copy "$BOX_ROOT/$BOX_PATH/" "$DEST/" --include "**/*.xml" --progress
done
