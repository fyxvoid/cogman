# COGMAN — Unified build
#
# Targets:
#   make build        build Rust binaries (cogman-core, cogman-planner)
#   make install      copy binaries to bin/ and optionally to /usr/local/bin
#   make deps         install Python dependencies
#   make setup-rust   install Rust toolchain via rustup
#   make run          start COGMAN AI assistant (interactive CLI)
#   make run-api      start REST API server
#   make run-gateway  start multi-channel gateway
#   make daemon       install and start systemd user service
#   make validate     validate all package manifests
#   make clean        remove build artifacts
#   make help         show this help

PROJECT := cogman
SRC_DIR := $(CURDIR)/src
BIN_DIR := $(CURDIR)/bin
CARGO   := $(shell command -v cargo 2>/dev/null || echo "$(HOME)/.cargo/bin/cargo")
PYTHON  := $(shell command -v python3 || echo python)

# ── Build Rust binaries ───────────────────────────────────────────────────

.PHONY: build
build: $(BIN_DIR)/cogman-core $(BIN_DIR)/cogman-planner

$(BIN_DIR)/cogman-core: $(SRC_DIR)/cogman-core/src/main.rs
	@echo "[cogman] building cogman-core..."
	@mkdir -p $(BIN_DIR)
	cd $(SRC_DIR) && $(CARGO) build -p cogman-core --release
	cp $(SRC_DIR)/target/release/cogman-core $(BIN_DIR)/
	@echo "[cogman] cogman-core ready: $(BIN_DIR)/cogman-core"

$(BIN_DIR)/cogman-planner: $(SRC_DIR)/cogman-planner/src/main.rs
	@echo "[cogman] building cogman-planner..."
	@mkdir -p $(BIN_DIR)
	cd $(SRC_DIR) && $(CARGO) build -p cogman-planner --release
	cp $(SRC_DIR)/target/release/cogman-planner $(BIN_DIR)/
	@echo "[cogman] cogman-planner ready: $(BIN_DIR)/cogman-planner"

# ── Install binaries ──────────────────────────────────────────────────────

.PHONY: install
install: build
	@echo "[cogman] copying binaries to /usr/local/bin (requires sudo)"
	sudo cp $(BIN_DIR)/cogman-core    /usr/local/bin/cogman-core
	sudo cp $(BIN_DIR)/cogman-planner /usr/local/bin/cogman-planner
	@echo "[cogman] installed"

# ── Python setup ──────────────────────────────────────────────────────────

.PHONY: deps
deps:
	@echo "[cogman] installing Python dependencies..."
	$(PYTHON) -m pip install -r requirements.txt

.PHONY: deps-full
deps-full:
	@echo "[cogman] installing full Python dependencies..."
	$(PYTHON) -m pip install \
		anthropic openai pyyaml rich trafilatura beautifulsoup4 \
		Pillow ruff pyttsx3 vosk sounddevice fastapi uvicorn \
		python-telegram-bot discord.py slack-bolt rapidfuzz psutil

# ── Rust setup ───────────────────────────────────────────────────────────

.PHONY: setup-rust
setup-rust:
	@if command -v cargo >/dev/null 2>&1; then \
		echo "[cogman] Rust already installed: $$(cargo --version)"; \
	else \
		echo "[cogman] Installing Rust via rustup..."; \
		curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y; \
		echo "[cogman] Rust installed. Restart shell or: source ~/.cargo/env"; \
	fi

# ── Speech model setup ────────────────────────────────────────────────────

.PHONY: setup-speech
setup-speech:
	$(PYTHON) main.py --setup

# ── Run ───────────────────────────────────────────────────────────────────

.PHONY: run
run:
	$(PYTHON) main.py

.PHONY: run-api
run-api:
	$(PYTHON) main.py --api

.PHONY: run-gateway
run-gateway:
	$(PYTHON) main.py --gateway

.PHONY: run-voice
run-voice:
	$(PYTHON) main.py --voice

.PHONY: status
status:
	$(PYTHON) main.py --status

# ── Daemon ────────────────────────────────────────────────────────────────

.PHONY: daemon
daemon:
	bash daemon/install_daemon.sh

.PHONY: daemon-remove
daemon-remove:
	bash daemon/install_daemon.sh --remove

# ── Validate all package manifests ───────────────────────────────────────

.PHONY: validate
validate:
	@echo "[cogman] validating package manifests..."
	@if [ ! -f $(BIN_DIR)/cogman-core ]; then \
		echo "  cogman-core not built — validating TOML syntax with Python"; \
		$(PYTHON) -c " \
import sys, pathlib; \
ok = True; \
[ (print('  OK  ' + str(t)) if __import__('tomllib' if sys.version_info >= (3,11) else 'tomli').loads(t.read_text()) else None) \
  for t in pathlib.Path('packages').rglob('*.toml') ]; \
"; \
	else \
		find packages -name '*.toml' -exec $(BIN_DIR)/cogman-core validate {} \; ; \
	fi

# ── Lint / check ─────────────────────────────────────────────────────────

.PHONY: lint
lint:
	@echo "[cogman] checking Python..."
	$(PYTHON) -m py_compile main.py core/*.py agents/*.py tools/*.py 2>&1 || true
	@if command -v ruff >/dev/null 2>&1; then ruff check . --select E,F --ignore E501; fi
	@echo "[cogman] checking Rust..."
	@if command -v cargo >/dev/null 2>&1; then cd $(SRC_DIR) && cargo check 2>&1; fi

# ── Clean ────────────────────────────────────────────────────────────────

.PHONY: clean
clean:
	@echo "[cogman] cleaning..."
	rm -f $(BIN_DIR)/cogman-core $(BIN_DIR)/cogman-planner
	@if [ -d $(SRC_DIR)/target ]; then cd $(SRC_DIR) && cargo clean; fi
	find . -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null || true
	find . -name '*.pyc' -delete 2>/dev/null || true
	@echo "[cogman] clean"

# ── Help ─────────────────────────────────────────────────────────────────

.PHONY: help
help:
	@echo ""
	@echo "  COGMAN — Self-learning Linux AI + Build System"
	@echo ""
	@echo "  Quick start:"
	@echo "    make setup-rust   install Rust toolchain (once)"
	@echo "    make deps         install Python dependencies"
	@echo "    make build        build cogman-core and cogman-planner"
	@echo "    make run          start the AI assistant"
	@echo ""
	@echo "  Targets:"
	@echo "    build         build Rust binaries"
	@echo "    install       copy binaries to /usr/local/bin (sudo)"
	@echo "    deps          install Python deps (requirements.txt)"
	@echo "    deps-full     install all optional Python deps"
	@echo "    setup-rust    install Rust via rustup"
	@echo "    setup-speech  download offline speech models"
	@echo "    run           interactive CLI"
	@echo "    run-api       REST API server (port 7777)"
	@echo "    run-gateway   multi-channel gateway"
	@echo "    run-voice     voice mode"
	@echo "    status        system status"
	@echo "    daemon        install systemd user service"
	@echo "    validate      validate all package manifests"
	@echo "    lint          check Python + Rust code"
	@echo "    clean         remove build artifacts"
	@echo ""
	@echo "  Package management (after make build):"
	@echo "    ./bin/cogman-planner inspect packages/base/hello/hello.toml"
	@echo "    ./bin/cogman-planner deps    packages/base/hello/hello.toml"
	@echo "    ./bin/cogman-planner build   packages/base/hello/hello.toml"
	@echo "    ./bin/cogman-core pkg list"
	@echo ""
