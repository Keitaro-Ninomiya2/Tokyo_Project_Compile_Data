#!/bin/bash
#SBATCH --partition=IllinoisComputes
#SBATCH --account=keitaro2-ic
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --mem=16G
#SBATCH --time=04:00:00
#SBATCH --job-name=Restore_Confirmed
#SBATCH --output=restore_confirmed_%j.out

# Source: Box path
BOX_ROOT="uiucbox:Research Notes (keitaro2@illinois.edu)/Tokyo_Gender"

# Targeted list of years found in rclone lsd
YEARS=(1950 1951 1952 1953 1954 1955 1958)

echo "Starting Targeted Restore for: ${YEARS[*]}"

for YEAR in "${YEARS[@]}"; do
    # Define Source and Destination
    BOX_PATH="Processed_Data/TokyoTo/$YEAR"
    DEST="$HOME/scratch/TokyoTo_${YEAR}_Raw"
    
    echo "------------------------------------------------"
    echo "Processing Year: $YEAR"
    echo "   Source: $BOX_PATH"
    echo "   Dest:   $DEST"
    
    mkdir -p "$DEST"
    
    # Run rclone copy
    # Removing '--include' restriction to ensure we get everything in the folder
    rclone copy "$BOX_ROOT/$BOX_PATH/" "$DEST/" --progress
    
    # Check if files arrived
    COUNT=$(ls "$DEST" | wc -l)
    echo "   -> File count in scratch: $COUNT"
done

echo "=========================================================="
echo "   RESTORE COMPLETE"
echo "=========================================================="
