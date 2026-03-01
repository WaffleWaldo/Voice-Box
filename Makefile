PREFIX ?= $(HOME)/.local
VENV := $(PREFIX)/share/voicebox/venv
BIN := $(PREFIX)/bin/voicebox

.PHONY: install uninstall model train bench-baseline bench

install:
	@echo "Creating venv with system site-packages..."
	python3 -m venv --system-site-packages $(VENV)
	$(VENV)/bin/pip install --upgrade pip
	$(VENV)/bin/pip install .
	@mkdir -p $(PREFIX)/bin
	ln -sf $(VENV)/bin/voicebox $(BIN)
	@echo ""
	@echo "Installing systemd user service..."
	mkdir -p $(HOME)/.config/systemd/user
	cp contrib/voicebox.service $(HOME)/.config/systemd/user/
	sed -i 's|ExecStart=.*|ExecStart=$(BIN) daemon|' \
		$(HOME)/.config/systemd/user/voicebox.service
	systemctl --user daemon-reload
	@echo ""
	@echo "Installed! Next steps:"
	@echo "  1. cp config.example.toml ~/.config/voicebox/config.toml"
	@echo "  2. systemctl --user enable --now voicebox"

model:
	ollama create voicebox-refiner -f contrib/Modelfile

train:
	.venv/bin/python3 benchmarks/refiner/train.py

bench-baseline:
	.venv/bin/python3 benchmarks/refiner/run.py --profile master --save master

bench:
	.venv/bin/python3 benchmarks/refiner/run.py --compare master

uninstall:
	systemctl --user disable --now voicebox 2>/dev/null || true
	rm -f $(HOME)/.config/systemd/user/voicebox.service
	systemctl --user daemon-reload
	rm -f $(BIN)
	rm -rf $(PREFIX)/share/voicebox
	@echo "Uninstalled."
