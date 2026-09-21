# Automated English-to-Hindi Movie Recap Video Generator

## Overview
This project is an automated, locally-running pipeline designed to convert English movie explanation/recap videos from YouTube into Hindi-narrated versions. It downloads an authorized video, extracts and transcribes the audio, translates the script to natural-sounding Hindi, synthesizes it into speech, synchronizes it to the original video timeline, and renders a final MP4.

## Constraints & Requirements
- **Hardware:** Designed specifically for Apple Silicon (M1) with 8 GB RAM and 256 GB SSD. It optimizes memory and disk usage by running processes sequentially and cleaning up temporary files.
- **Cost:** 100% Free. Uses local models and open-source tools; no paid APIs or cloud dependencies.
- **Core Technology Stack:**
  - **Orchestration:** Python
  - **Downloader:** `yt-dlp`
  - **Transcription:** `Whisper` (base/small models via `mlx` or `mps` backend)
  - **Translation:** Local LLM via `Ollama` (e.g., `qwen2.5:3b` or `llama3.2`)
  - **Text-to-Speech:** `Piper` (lightweight, offline TTS)
  - **Audio/Video Processing:** `FFmpeg`
- **Quality & Sync:** Prioritizes natural translation over strict word-for-word accuracy and employs a segment-based synchronization algorithm to keep the Hindi narration aligned with the original video using intelligent duration matching and time-stretching.

## Project Structure
A modular structure allowing individual components (downloader, transcription, translation, TTS, sync, render) to be isolated, developed, and tested independently.

## Legal
The user must have permission to process/use the original videos or the material must be otherwise legally authorized. This tool is a technical automation pipeline, not a mechanism to bypass copyright policies.
