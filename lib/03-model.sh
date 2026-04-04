#!/bin/bash

MODEL_NAME="gemma-2-9b-it-Q6_K.gguf"
MODEL_URL="https://huggingface.co/bartowski/gemma-2-9b-it-GGUF/resolve/main/gemma-2-9b-it-Q6_K.gguf"
MODEL_PATH="$MODEL_DIR/$MODEL_NAME"
DEFAULT_CTX=16384

download_model() {
    STEP "Downloading model"
    mkdir -p "$MODEL_DIR"

    if [[ ! -f "$MODEL_PATH" ]]; then
        wget -O "$MODEL_PATH" "$MODEL_URL"
    fi

    OK "Model ready"
}
