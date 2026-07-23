#!/bin/bash

INSTALL_DIR="${INSTALL_DIR:-$HOME/ai_stack}"
MODEL_DIR="$INSTALL_DIR/models"
LLAMACPP_DIR="$INSTALL_DIR/llama.cpp"
LLAMACPP_BIN="$LLAMACPP_DIR/build/bin/llama-server"

CPU_CORES=$(nproc)

OK()   { echo -e "\033[0;32m✅ $*\033[0m"; }
INFO() { echo -e "\033[0;36mℹ️  $*\033[0m"; }
WARN() { echo -e "\033[1;33m⚠️  $*\033[0m"; }
ERR()  { echo -e "\033[0;31m❌ $*\033[0m"; exit 1; }

STEP() { echo -e "\n\033[1m━━━ $* ━━━\033[0m"; }
PAUSE() { read -rp "Press Enter to continue..."; }
