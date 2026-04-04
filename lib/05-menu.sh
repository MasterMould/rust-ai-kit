#!/bin/bash

main_menu() {
    while true; do
        clear
        echo "🦀 Local AI Stack"
        echo "1) Full Install"
        echo "2) Build Engine"
        echo "3) Download Model"
        echo "4) Start AI"
        echo "5) Stop AI"
        echo "0) Exit"

        read -rp "Select: " opt

        case "$opt" in
            1)
                install_system_deps
                install_intel_gpu
                install_llamacpp
                download_model
                create_runtime_scripts
                ;;
            2) install_llamacpp ;;
            3) download_model ;;
            4) "$INSTALL_DIR/start_ai_stack.sh" ;;
            5) "$INSTALL_DIR/stop_ai_stack.sh" ;;
            0) exit 0 ;;
        esac

        PAUSE
    done
}
