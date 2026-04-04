main() {
    while true; do
        echo "1) Full Install"
        echo "2) Config"
        echo "0) Exit"
        read -rp "Choice: " c
        case "$c" in
            1) run_full_install ;;
            2) configuration_menu ;;
            0) exit 0 ;;
        esac
    done
}

configuration_menu() {
    echo "Toggle features not fully implemented here (stub safe)"
}
