PREFIX ?= $(HOME)/.local
VENV := $(PREFIX)/share/echoflow/venv
BIN := $(PREFIX)/bin/echoflow

.PHONY: install uninstall model train bench-baseline bench

install:
	@echo "Creating venv with system site-packages..."
	python3 -m venv --system-site-packages $(VENV)
	$(VENV)/bin/pip install --upgrade pip
	$(VENV)/bin/pip install .
	@mkdir -p $(PREFIX)/bin
	ln -sf $(VENV)/bin/echoflow $(BIN)
	@echo ""
	@echo "Installing systemd user service..."
	mkdir -p $(HOME)/.config/systemd/user
	cp contrib/echoflow.service $(HOME)/.config/systemd/user/
	sed -i 's|ExecStart=.*|ExecStart=$(BIN) daemon|' \
		$(HOME)/.config/systemd/user/echoflow.service
	systemctl --user daemon-reload
	@echo ""
	@echo "Installed! Next steps:"
	@echo "  1. cp config.example.toml ~/.config/echoflow/config.toml"
	@echo "  2. systemctl --user enable --now echoflow"

model:
	ollama create echoflow-refiner -f contrib/Modelfile

train:
	.venv/bin/python3 benchmarks/refiner/train.py

bench-baseline:
	.venv/bin/python3 benchmarks/refiner/run.py --profile master --save master

bench:
	.venv/bin/python3 benchmarks/refiner/run.py --compare master

uninstall:
	systemctl --user disable --now echoflow 2>/dev/null || true
	rm -f $(HOME)/.config/systemd/user/echoflow.service
	systemctl --user daemon-reload
	rm -f $(BIN)
	rm -rf $(PREFIX)/share/echoflow
	@echo "Uninstalled."
