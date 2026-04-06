#!/bin/bash

MODEL_DIR="$INSTALL_DIR/models"
mkdir -p "$MODEL_DIR"

# ─────────────────────────────────────────────
# Model Registry
# ─────────────────────────────────────────────
declare -A MODEL_REGISTRY

MODEL_REGISTRY["1"]="Gemma 2 9B (Q6_K)|https://huggingface.co/bartowski/gemma-2-9b-it-GGUF/resolve/main/gemma-2-9b-it-Q6_K.gguf|16384"
MODEL_REGISTRY["2"]="Llama 3.1 8B (Q4_K_M)|https://huggingface.co/bartowski/Meta-Llama-3.1-8B-Instruct-GGUF/resolve/main/Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf|8192"
MODEL_REGISTRY["3"]="Mistral 7B Instruct (Q4_K_M)|https://huggingface.co/TheBloke/Mistral-7B-Instruct-v0.2-GGUF/resolve/main/mistral-7b-instruct-v0.2.Q4_K_M.gguf|8192"

# Current selection (defaults)
MODEL_NAME=""
MODEL_URL=""
MODEL_PATH=""
DEFAULT_CTX=8192

# ─────────────────────────────────────────────
# Model Selection Menu
# ─────────────────────────────────────────────
model_menu() {
    while true; do
        clear
        echo "🧠 Model Manager"
        echo "────────────────────────────"

        for key in "${!MODEL_REGISTRY[@]}"; do
            IFS="|" read -r name _ _ <<< "${MODEL_REGISTRY[$key]}"
            echo "$key) $name"
        done

        echo "C) Custom Model URL"
        echo "D) Download Selected Model"
        echo "0) Back"

        echo "────────────────────────────"
        [[ -n "$MODEL_NAME" ]] && echo "Selected: $MODEL_NAME"
        echo ""

        read -rp "Select option: " choice

        case "$choice" in
            [1-9])
                select_model "$choice"
                ;;
            [Cc])
                custom_model
                ;;
            [Dd])
                download_model
                ;;
            0)
                return
                ;;
        esac
    done
}

# ─────────────────────────────────────────────
# Select Predefined Model
# ─────────────────────────────────────────────
select_model() {
    local entry="${MODEL_REGISTRY[$1]}"
    IFS="|" read -r name url ctx <<< "$entry"

    MODEL_NAME="$name"
    MODEL_URL="$url"
    DEFAULT_CTX="$ctx"

    MODEL_FILE=$(basename "$MODEL_URL")
    MODEL_PATH="$MODEL_DIR/$MODEL_FILE"

    OK "Selected: $MODEL_NAME"
}

# ─────────────────────────────────────────────
# Custom Model Input
# ─────────────────────────────────────────────
custom_model() {
    read -rp "Enter direct .gguf URL: " url

    [[ -z "$url" ]] && return

    MODEL_URL="$url"
    MODEL_FILE=$(basename "$url")
    MODEL_PATH="$MODEL_DIR/$MODEL_FILE"
    MODEL_NAME="Custom Model"
    DEFAULT_CTX=8192

    OK "Custom model set: $MODEL_FILE"
}

# ─────────────────────────────────────────────
# Download Model
# ─────────────────────────────────────────────
download_model() {
    [[ -z "$MODEL_URL" ]] && {
        WARN "No model selected"
        return
    }

    STEP "Downloading model"

    mkdir -p "$MODEL_DIR"

    if [[ -f "$MODEL_PATH" ]]; then
        INFO "Model already exists: $MODEL_PATH"
        return
    fi

    wget -c --show-progress -O "$MODEL_PATH" "$MODEL_URL" || ERR "Download failed"

    OK "Model downloaded → $MODEL_PATH"
}
