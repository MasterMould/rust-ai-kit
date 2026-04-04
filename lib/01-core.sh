install_system_deps() {
    sudo apt-get update -qq
    sudo apt-get install -y git cmake ninja-build curl wget build-essential
}

run_full_install() {
    detect_hardware
    configuration_menu
    install_system_deps
    install_llamacpp
    download_model
    write_scripts
    echo "✅ Install complete"
}
