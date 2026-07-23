#!/bin/bash

install_system_deps() {
    STEP "Installing system dependencies"
    sudo apt-get update -qq
    sudo apt-get install -y \
        git cmake build-essential ninja-build \
        libopenblas-dev libssl-dev pkg-config \
        curl wget python3.12-venv clinfo
}

install_llamacpp() {
    STEP "Building llama.cpp"

    [[ -d "$LLAMACPP_DIR" ]] || git clone https://github.com/ggerganov/llama.cpp "$LLAMACPP_DIR"

    cmake -B "$LLAMACPP_DIR/build" -S "$LLAMACPP_DIR" -G Ninja \
        -DGGML_SYCL=ON \
        -DGGML_SYCL_F16=ON \
        -DCMAKE_BUILD_TYPE=Release \
        -DCMAKE_C_COMPILER=icx \
        -DCMAKE_CXX_COMPILER=icpx

    cmake --build "$LLAMACPP_DIR/build" -j"$CPU_CORES"

    [[ -f "$LLAMACPP_BIN" ]] || ERR "llama-server build failed"
    OK "llama.cpp built"
}
