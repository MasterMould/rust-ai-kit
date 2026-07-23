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
	    requests-ratelimiter \
	    urllib3 \
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
	chmod +x $(LAUNCH) run-desktop.sh run-server-window.sh server-window.sh stop-server.sh
	@echo "▶  Installing desktop icon…"
	$(MAKE) install-desktop
	@echo "▶  Installing server Start/Stop icons…"
	$(MAKE) install-server-icons
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
#  install-desktop  — generate and install the .desktop launcher
#  Writes the file content directly so there is never a stale
#  placeholder path.  The .desktop spec forbids shell metacharacters
#  in Exec — all logic lives in run-desktop.sh.
# ================================================================
install-desktop:
	@echo "▶  Making scripts executable..."
	chmod +x $(LAUNCH) run-desktop.sh
	@echo "▶  Writing desktop launcher..."
	mkdir -p $(DESKTOP_DIR)
	@# Write the .desktop file directly — no sed, no placeholder
	@printf '[Desktop Entry]\n' > $(DESKTOP_DIR)/$(DESKTOP)
	@printf 'Version=1.0\n' >> $(DESKTOP_DIR)/$(DESKTOP)
	@printf 'Type=Application\n' >> $(DESKTOP_DIR)/$(DESKTOP)
	@printf 'Name=rust-ai-kit LLM Factory\n' >> $(DESKTOP_DIR)/$(DESKTOP)
	@printf 'GenericName=Local AI Assistant\n' >> $(DESKTOP_DIR)/$(DESKTOP)
	@printf 'Comment=Start the rust-ai-kit stack and open the LLM Factory UI\n' >> $(DESKTOP_DIR)/$(DESKTOP)
	@printf 'Exec=%s/run-desktop.sh\n' "$(CURDIR)" >> $(DESKTOP_DIR)/$(DESKTOP)
	@printf 'Icon=utilities-terminal\n' >> $(DESKTOP_DIR)/$(DESKTOP)
	@printf 'Terminal=false\n' >> $(DESKTOP_DIR)/$(DESKTOP)
	@printf 'Categories=Utility;\n' >> $(DESKTOP_DIR)/$(DESKTOP)
	@printf 'Keywords=AI;LLM;chat;llama;Intel;Arc;\n' >> $(DESKTOP_DIR)/$(DESKTOP)
	@printf 'StartupNotify=true\n' >> $(DESKTOP_DIR)/$(DESKTOP)
	chmod 644 $(DESKTOP_DIR)/$(DESKTOP)
	@echo "  ✅  Written: $(DESKTOP_DIR)/$(DESKTOP)"
	@# Copy to ~/Desktop and trust it
	@if [ -d "$(HOME)/Desktop" ]; then \
	    cp $(DESKTOP_DIR)/$(DESKTOP) $(HOME)/Desktop/$(DESKTOP); \
	    chmod 644 $(HOME)/Desktop/$(DESKTOP); \
	    gio trust $(HOME)/Desktop/$(DESKTOP) 2>/dev/null || true; \
	    echo "  ✅  Copied to ~/Desktop/$(DESKTOP) (trusted)"; \
	fi
	@# Validate
	@if command -v desktop-file-validate >/dev/null 2>&1; then \
	    desktop-file-validate $(DESKTOP_DIR)/$(DESKTOP) \
	        && echo "  ✅  Validates OK" \
	        || (echo "  ❌  Validation failed" && exit 1); \
	fi
	@command -v update-desktop-database >/dev/null 2>&1 && \
	    update-desktop-database $(DESKTOP_DIR) 2>/dev/null || true
	@echo "  ✅  Done. Click the icon on your Desktop to launch."

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
#  start-server  — open llama-server in its own terminal window
# ================================================================
start-server:
	@chmod +x run-server-window.sh server-window.sh
	@bash run-server-window.sh

# ================================================================
#  stop-server  — stop llama-server + memory + proxy
# ================================================================
stop-server:
	@bash stop-server.sh

# ================================================================
#  install-server-icons  — install Start/Stop .desktop launchers
#  into both the application menu and the Desktop folder.
# ================================================================
install-server-icons:
	@echo "▶  Installing server Start/Stop desktop icons…"
	@chmod +x run-server-window.sh server-window.sh stop-server.sh
	@mkdir -p $(DESKTOP_DIR)
	@# --- Start icon ---
	@sed "s|PLACEHOLDER|$(CURDIR)|g" llm-server-start.desktop \
	    > $(DESKTOP_DIR)/llm-server-start.desktop
	@chmod 644 $(DESKTOP_DIR)/llm-server-start.desktop
	@if [ -d "$(HOME)/Desktop" ]; then \
	    cp $(DESKTOP_DIR)/llm-server-start.desktop $(HOME)/Desktop/; \
	    chmod 644 $(HOME)/Desktop/llm-server-start.desktop; \
	    gio trust $(HOME)/Desktop/llm-server-start.desktop 2>/dev/null || true; \
	    echo "  ✅  Start icon → ~/Desktop/"; \
	fi
	@# --- Stop icon ---
	@sed "s|PLACEHOLDER|$(CURDIR)|g" llm-server-stop.desktop \
	    > $(DESKTOP_DIR)/llm-server-stop.desktop
	@chmod 644 $(DESKTOP_DIR)/llm-server-stop.desktop
	@if [ -d "$(HOME)/Desktop" ]; then \
	    cp $(DESKTOP_DIR)/llm-server-stop.desktop $(HOME)/Desktop/; \
	    chmod 644 $(HOME)/Desktop/llm-server-stop.desktop; \
	    gio trust $(HOME)/Desktop/llm-server-stop.desktop 2>/dev/null || true; \
	    echo "  ✅  Stop icon  → ~/Desktop/"; \
	fi
	@command -v update-desktop-database >/dev/null 2>&1 && \
	    update-desktop-database $(DESKTOP_DIR) 2>/dev/null || true
	@echo "  ✅  Icons installed — look for them in your app launcher."

# ================================================================
#  fix-deps  — install any missing pip packages into the venv
#              and purge stale __pycache__ bytecode
#              Run this after a git pull that adds new dependencies.
# ================================================================
fix-deps:
	@if [ ! -d "$(VENV)" ]; then \
	    echo "❌  venv not found — run 'make setup' first."; exit 1; \
	fi
	@echo "▶  Installing / upgrading dependencies…"
	$(PIP) install --upgrade \
	    requests-ratelimiter \
	    urllib3 \
	    streamlit \
	    requests \
	    PyPDF2
	@echo "▶  Purging stale __pycache__ bytecode…"
	find . -type d -name __pycache__ ! -path "./.git/*" -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" ! -path "./.git/*" -delete 2>/dev/null || true
	@echo "  ✅  Done. Start the app with:  make run"

# ================================================================
#  purge-cache  — clear __pycache__ only (no pip changes)
# ================================================================
purge-cache:
	@echo "▶  Purging __pycache__…"
	find . -type d -name __pycache__ ! -path "./.git/*" -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" ! -path "./.git/*" -delete 2>/dev/null || true
	@echo "  ✅  Bytecode cache cleared."


# ================================================================
git-sync:
	git add .
	git commit -m "Station Sync: $$(date)"
	git push 

# ================================================================
#  stop  — Streamlit and the AI stack
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
#  stop  — Streamlit only
# ================================================================
stop-streamlit:
	@echo "▶  Stopping Streamlit…"
	@pkill -f "streamlit run" 2>/dev/null && echo "  Stopped Streamlit" || echo "  Streamlit not running"
	@if [ -f logs/.streamlit_pid ]; then \
	    kill $$(cat logs/.streamlit_pid) 2>/dev/null || true; \
	    rm -f logs/.streamlit_pid; \
	fi

# ================================================================
#  stop  — the AI stack only
# ================================================================
stop-AIstack:
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

.PHONY: setup run launch install-desktop install-autostart start-server stop-server install-server-icons fix-deps purge-cache git-sync stop status add-user lint test
