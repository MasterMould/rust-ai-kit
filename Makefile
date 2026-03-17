VENV       = venv
PIP        = $(VENV)/bin/pip
STREAMLIT  = $(VENV)/bin/streamlit
APP        = llm_factory_rustaikit.py
DESKTOP    = rust-ai-kit.desktop
LAUNCH     = launch.sh
DESKTOP_DIR   = $(HOME)/.local/share/applications
AUTOSTART_DIR = $(HOME)/.config/autostart

# ================================================================
#  setup  — install Python deps, add user to shadow group for PAM,
#            install desktop icon automatically
# ================================================================
setup:
	@echo "▶  Updating apt and installing system packages…"
	sudo apt update && sudo apt install -y \
	    python3-venv git intel-gpu-tools \
	    libpam-dev python3-dev gcc
	@echo "▶  Creating Python venv…"
	python3 -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install \
	    streamlit \
	    requests \
	    PyPDF2 \
	    python-pam \
	    bandit \
	    psutil \
	    py-cpuinfo \
	    black \
	    pylint \
	    pytest \
	    pandas
	@echo "▶  Creating workspace dirs…"
	mkdir -p workspace/logs workspace/.archive logs config
	touch config/.gitkeep workspace/.gitkeep logs/.gitkeep
	@echo "▶  Adding $$USER to shadow group (needed for PAM password verification)…"
	sudo usermod -aG shadow $$USER
	@echo "▶  Making scripts executable…"
	chmod +x $(LAUNCH)
	@echo "▶  Installing desktop icon…"
	$(MAKE) install-desktop
	@echo ""
	@echo "  ✅  Setup complete."
	@echo ""
	@echo "  ⚠️  IMPORTANT: Log out and back in (or reboot) for the"
	@echo "      shadow group change to take effect."
	@echo ""
	@echo "  Desktop icon installed — look for it in your app launcher."
	@echo "  To also add it to your Desktop folder:"
	@echo "    cp $(DESKTOP_DIR)/$(DESKTOP) ~/Desktop/ && chmod +x ~/Desktop/$(DESKTOP)"
	@echo ""
	@echo "  Then run:  make run   (or click the desktop icon)"

# ================================================================
#  run  — start Streamlit directly (stack must already be running)
# ================================================================
run:
	@if [ ! -d "$(VENV)" ]; then $(MAKE) setup; fi
	$(STREAMLIT) run $(APP) \
	    --server.port 8501 \
	    --server.headless true \
	    --server.address 0.0.0.0

# ================================================================
#  launch  — start everything (stack + Streamlit + browser)
# ================================================================
launch:
	@chmod +x $(LAUNCH)
	bash $(LAUNCH)

# ================================================================
#  install-desktop  — install .desktop icon to app launcher + Desktop
# ================================================================
install-desktop:
	@echo "▶  Installing desktop icon…"
	chmod +x $(LAUNCH)
	mkdir -p $(DESKTOP_DIR)
	@# Write the .desktop file with the real absolute path substituted in
	@sed \
	    -e "s|%k/../../launch.sh|$(CURDIR)/$(LAUNCH)|g" \
	    -e "s|Exec=bash|Exec=bash|" \
	    $(DESKTOP) > $(DESKTOP_DIR)/$(DESKTOP)
	chmod +x $(DESKTOP_DIR)/$(DESKTOP)
	@# Also put a copy on the Desktop if ~/Desktop exists
	@if [ -d "$(HOME)/Desktop" ]; then \
	    cp $(DESKTOP_DIR)/$(DESKTOP) $(HOME)/Desktop/$(DESKTOP); \
	    chmod +x $(HOME)/Desktop/$(DESKTOP); \
	    gio trust $(HOME)/Desktop/$(DESKTOP) 2>/dev/null || true; \
	    echo "  ✅  Copied to ~/Desktop/$(DESKTOP) (trusted)"; \
	fi
	@# Validate if the tool is present
	@command -v desktop-file-validate &>/dev/null && \
	    desktop-file-validate $(DESKTOP_DIR)/$(DESKTOP) && \
	    echo "  ✅  Desktop file validates OK" || true
	@# Refresh the app launcher database
	@command -v update-desktop-database &>/dev/null && \
	    update-desktop-database $(DESKTOP_DIR) 2>/dev/null || true
	@echo "  ✅  Installed to $(DESKTOP_DIR)/$(DESKTOP)"

# ================================================================
#  install-autostart  — start the stack automatically on login
# ================================================================
install-autostart:
	@echo "▶  Installing autostart entry…"
	chmod +x $(LAUNCH)
	mkdir -p $(AUTOSTART_DIR)
	@sed \
	    -e "s|%k/../../launch.sh|$(CURDIR)/$(LAUNCH)|g" \
	    -e "s|Terminal=false|Terminal=false|" \
	    $(DESKTOP) > $(AUTOSTART_DIR)/$(DESKTOP)
	chmod +x $(AUTOSTART_DIR)/$(DESKTOP)
	@echo "  ✅  Autostart installed — stack will start at login"

# ================================================================
#  git-sync  — commit and push everything (respects .gitignore)
# ================================================================
git-sync:
	git add .
	git commit -m "Station Sync: $$(date)"
	git push origin main

# ================================================================
#  stop  — kill Streamlit and the AI stack
# ================================================================
stop:
	@echo "▶  Stopping Streamlit…"
	@pkill -f "streamlit run" 2>/dev/null && echo "  Stopped Streamlit" || echo "  Streamlit not running"
	@if [ -f logs/.streamlit_pid ]; then \
	    kill $$(cat logs/.streamlit_pid) 2>/dev/null || true; \
	    rm -f logs/.streamlit_pid; \
	fi
	@echo "▶  Stopping AI stack (delegating to ai_stack_manager.sh)…"
	@echo "3" | bash ai_stack_manager.sh 2>/dev/null || true

# ================================================================
#  status  — quick health check
# ================================================================
status:
	@echo ""
	@echo "  ── Service ports ──"
	@curl -sf -H "Authorization: Bearer local" \
	    http://localhost:8080/v1/models &>/dev/null && \
	    echo "  🟢 Engine     :8080" || echo "  🔴 Engine     :8080  (offline)"
	@curl -sf http://localhost:8090/health &>/dev/null && \
	    echo "  🟢 Proxy      :8090" || echo "  🔴 Proxy      :8090  (offline)"
	@curl -sf http://localhost:8000/health &>/dev/null && \
	    echo "  🟢 Memory     :8000" || echo "  🔴 Memory     :8000  (offline)"
	@curl -sf http://localhost:8081 &>/dev/null && \
	    echo "  🟢 SearXNG    :8081" || echo "  🔴 SearXNG    :8081  (offline)"
	@curl -sf http://localhost:8501 &>/dev/null && \
	    echo "  🟢 Streamlit  :8501" || echo "  🔴 Streamlit  :8501  (offline)"
	@echo ""

# ================================================================
#  add-user  — add a local fallback user (used when PAM is off)
# ================================================================
add-user:
	@echo "Adding local fallback user to config/users.json"
	@read -p "Username: " u; \
	 read -sp "Password: " p; echo; \
	 read -p "Role [user/admin]: " r; \
	 $(VENV)/bin/python3 -c "\
	from llm_factory_rustaikit import AuthManager; \
	ok = AuthManager.add_local_user('$$u', '$$p', '$$r'); \
	print('Added!' if ok else 'Failed')"

# ================================================================
#  lint / test
# ================================================================
lint:
	$(VENV)/bin/black --check $(APP)
	$(VENV)/bin/pylint $(APP) --disable=all --enable=E

test:
	$(VENV)/bin/pytest tests/ -v 2>/dev/null || echo "No tests yet"

.PHONY: setup run launch install-desktop install-autostart git-sync stop status add-user lint test
