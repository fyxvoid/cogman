#!/bin/bash
# Install Ollama + pull a lightweight local LLM for cogman Tier 3.

set -e

echo "=== cogman: Tier 3 Local LLM Setup ==="
echo ""

# Install Ollama
if ! command -v ollama &>/dev/null; then
    echo "[1/3] Installing Ollama..."
    curl -fsSL https://ollama.ai/install.sh | sh
else
    echo "[1/3] Ollama already installed: $(ollama --version)"
fi

# Start Ollama service
echo "[2/3] Starting Ollama service..."
systemctl --user enable --now ollama 2>/dev/null || ollama serve &>/dev/null &
sleep 2

# Pull a model
MODEL="${COGMAN_OLLAMA_MODEL:-mistral}"
echo "[3/3] Pulling model: $MODEL"
echo "      (phi3=2GB | mistral=4GB | llama3=4.7GB | codellama=4GB)"
ollama pull "$MODEL"

echo ""
echo "=== Done! ==="
echo "cogman Tier 3 (local LLM) is ready."
echo "Model: $MODEL"
echo ""
echo "Test: ollama run $MODEL 'hello'"
echo "cogman auto-detects Ollama at http://localhost:11434"
