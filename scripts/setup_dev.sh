#!/bin/bash

# Activate conda environment if it exists
if conda info --envs | grep -q "^podcast_env"; then
    echo "Activating conda environment: podcast_env"
    conda activate podcast_env
fi

# Install package in development mode
echo "Installing podcast_service in development mode..."
pip install -e .

# Create necessary directories
mkdir -p data/users
mkdir -p data/downloads
mkdir -p data/transcripts
mkdir -p data/summaries

echo "Setup complete!" 