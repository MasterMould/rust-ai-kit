#!/bin/bash

install_intel_gpu() {
    STEP "Installing Intel GPU drivers"

    sudo apt-get install -y intel-opencl-icd libze-intel-gpu1 libze1

    if ! command -v icx &>/dev/null; then
        sudo apt-get install -y intel-oneapi-compiler-dpcpp-cpp
    fi

    source /opt/intel/oneapi/setvars.sh --force >/dev/null 2>&1 || true

    OK "Intel GPU + oneAPI ready"
}
