#!/bin/bash
set -euo pipefail

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────
REPO_URL="https://github.com/MasterMould/rust-ai-kit.git"
BRANCH="${BRANCH:-dev}"

INSTALL_DIR="$HOME/ai_stack"
SRC_DIR="$INSTALL_DIR/src"
LIB_DIR="$SRC_DIR/lib"

# ─────────────────────────────────────────────
# UI Helpers
# ─────────────────────────────────────────────
R='\033[0;31m' G='\033[0;32m' Y='\033[1;33m'
C='\033[0;36m' W='\033[1m' N='\033[0m'

OK()   { echo -e "${G}  ✅  $*${N}"; }
INFO() { echo -e "${C}  ℹ️   $*${N}"; }
WARN() { echo -e "${Y}  ⚠️   $*${N}"; }
ERR()  { echo -e "${R}  ❌  $*${N}"; exit 1; }

# ─────────────────────────────────────────────
# Clone or Update Repo
# ─────────────────────────────────────────────
fetch_repo() {
    mkdir -p "$INSTALL_DIR"

    if [[ ! -d "$SRC_DIR/.git" ]]; then
        INFO "Cloning AI stack repo..."
        git clone -b "$BRANCH" "$REPO_URL" "$SRC_DIR"
    else
        INFO "Updating existing repo..."
        cd "$SRC_DIR"
        git fetch origin
        git reset --hard "origin/$BRANCH"
    fi

    OK "Repository ready"
}

# ─────────────────────────────────────────────
# Load Modules
# ─────────────────────────────────────────────
load_modules() {
    [[ -d "$LIB_DIR" ]] || ERR "lib directory missing"

    shopt -s nullglob
    local files=("$LIB_DIR"/[0-9][0-9]-*.sh)
    shopt -u nullglob

    [[ ${#files[@]} -eq 0 ]] && ERR "No modules found in $LIB_DIR"

    for f in "${files[@]}"; do
        source "$f"
    done

    OK "Loaded ${#files[@]} modules"
}

# ─────────────────────────────────────────────
# Entry
# ─────────────────────────────────────────────
main() {
    fetch_repo
    load_modules

    if declare -f main_menu >/dev/null; then
        main_menu
    elif declare -f main >/dev/null; then
        main
    else
        ERR "No entry function (main_menu or main) found in modules"
    fi
}

main "$@"
