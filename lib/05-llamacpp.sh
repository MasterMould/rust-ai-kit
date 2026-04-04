install_llamacpp() {
    DIR="$HOME/ai_stack/llama.cpp"

    [[ -d "$DIR" ]] || git clone https://github.com/ggerganov/llama.cpp "$DIR"

    generate_cmake_flags

    cmake -B "$DIR/build" -S "$DIR" -G Ninja "${CMAKE_FLAGS[@]}"
    cmake --build "$DIR/build" -j"$(nproc)"
}
