VENV = venv
PIP = $(VENV)/bin/pip
STREAMLIT = $(VENV)/bin/streamlit

setup:
	sudo apt update && sudo apt install -y python3-venv git intel-gpu-tools
	python3 -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install streamlit requests bandit psutil py-cpuinfo black pylint pytest
	mkdir -p workspace/logs workspace/.archive

run:
	@if [ ! -d "$(VENV)" ]; then make setup; fi
	$(STREAMLIT) run app.py

git-sync:
	git add .
	git commit -m "Station Sync: $$(date)"
	git push origin main
