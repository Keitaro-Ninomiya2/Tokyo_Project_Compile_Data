#!/bin/bash
#SBATCH --job-name=Tokyo_Archive_OCR
#SBATCH --partition=IllinoisComputes-GPU
#SBATCH --account=keitaro2-ic
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=32G
#SBATCH --gres=gpu:1
#SBATCH --time=3-00:00:00
#SBATCH --output=ocr_archive_%j.log
#SBATCH --mail-user=keitaro2@illinois.edu
#SBATCH --mail-type=BEGIN,END,FAIL

# --- Environment Setup ---
source activate ndlocr

# Navigate to project root
cd $HOME/ndlocr_v2_cluster

# Ensure the master script is executable and run it
chmod +x process_archive_master.sh
./process_archive_master.sh
