#!/bin/bash
#SBATCH --job-name=NDL_1942
#SBATCH --partition=IllinoisComputes-GPU
#SBATCH --account=keitaro2-ic
#SBATCH --gres=gpu:1
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=32G
#SBATCH --time=24:00:00
#SBATCH --output=ocr_slurm_%j.log

# Move to your project directory
cd ~/ndlocr_v2_cluster

# Run the master batch script
./process_1942_final.sh
