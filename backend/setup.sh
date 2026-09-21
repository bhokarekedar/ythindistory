#!/bin/bash

# Exit on error
set -e

echo "========================================="
echo " Setting up Models & Binaries for Mac M1 "
echo "========================================="

cd "$(dirname "$0")"

# 1. Setup Directories
mkdir -p bin
mkdir -p models
mkdir -p temp

# 2. Setup Piper TTS
echo "-----------------------------------------"
echo "Installing Piper TTS via pip..."
source venv/bin/activate
pip install piper-tts
echo "Piper installed."

# 3. Download Hindi Voice Model for Piper (Swara Medium)
echo "-----------------------------------------"
echo "Downloading Hindi Voice Model (hi_IN-swara-medium)..."
MODEL_URL="https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/hi/hi_IN/swara/medium/hi_IN-swara-medium.onnx"
JSON_URL="https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/hi/hi_IN/swara/medium/hi_IN-swara-medium.onnx.json"

if [ ! -f "models/hi_IN-swara-medium.onnx" ]; then
    curl -L -o models/hi_IN-swara-medium.onnx "$MODEL_URL"
    curl -L -o models/hi_IN-swara-medium.onnx.json "$JSON_URL"
    echo "Voice model downloaded to models/"
else
    echo "Voice model already exists."
fi


echo "========================================="
echo " Setup Complete! "
echo "========================================="
