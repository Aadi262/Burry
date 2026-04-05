#!/bin/bash
# ================================================================
#  setup.sh — Mac Butler Setup Script
#  Installs dependencies, pulls Ollama model, and runs a test.
# ================================================================

set -e  # Exit on any error

echo "========================================"
echo "  🎩  Mac Butler — Setup"
echo "========================================"
echo ""

# ------------------------------------------------------------------
# 1. Create virtual environment and install Python dependencies
# ------------------------------------------------------------------
echo "[1/4] Setting up Python virtual environment..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo "  ✅ Virtual environment created."
else
    echo "  ✅ Virtual environment already exists."
fi
source venv/bin/activate
echo "  Installing Python dependencies..."
pip install -r requirements.txt
echo "  ✅ Dependencies installed."
echo ""

# ------------------------------------------------------------------
# 2. Check if Ollama is installed
# ------------------------------------------------------------------
echo "[2/4] Checking for Ollama..."
if command -v ollama &> /dev/null; then
    echo "  ✅ Ollama is installed: $(ollama --version 2>/dev/null || echo 'version unknown')"
else
    echo "  ❌ Ollama is NOT installed."
    echo ""
    echo "  Install it with:"
    echo "    brew install ollama"
    echo ""
    echo "  Or download from: https://ollama.com/download"
    echo ""
    echo "  After installing, run 'ollama serve' in a separate terminal,"
    echo "  then re-run this setup script."
    exit 1
fi
echo ""

# ------------------------------------------------------------------
# 3. Pull the LLM model
# ------------------------------------------------------------------
echo "[3/6] Pulling orchestrator model (qwen2.5-coder:14b)..."
ollama pull qwen2.5-coder:14b
echo "  ✅ Orchestrator model pulled."
echo ""

# ------------------------------------------------------------------
# 4. Pull specialist agent models (optional — Butler falls back gracefully)
# ------------------------------------------------------------------
echo "[4/6] Pulling specialist models for multi-agent system..."
echo "  (These are optional — Butler falls back to qwen if not available)"
echo ""

ollama pull deepseek-r1:7b && echo "  ✅ deepseek-r1:7b (news/search)" || echo "  ⚠️ deepseek-r1:7b skipped"
ollama pull qwen2.5-coder:7b && echo "  ✅ qwen2.5-coder:7b (VPS agent)" || echo "  ⚠️ qwen2.5-coder:7b skipped"
ollama pull phi4-mini && echo "  ✅ phi4-mini (memory agent)" || echo "  ⚠️ phi4-mini skipped"

echo ""
echo "  Specialist models ready."
echo ""

# ------------------------------------------------------------------
# 5. Check optional MCP prerequisites
# ------------------------------------------------------------------
echo "[5/6] Checking optional MCP prerequisites..."
if command -v npx &> /dev/null; then
    echo "  ✅ npx is available for Brave/GitHub MCP servers."
else
    echo "  ⚠️ npx not found. Install Node.js if you want Brave/GitHub MCP support."
fi
echo ""

# ------------------------------------------------------------------
# 6. Create example TODO.md if it doesn't exist
# ------------------------------------------------------------------
TODO_FILE="$HOME/Developer/TODO.md"
if [ ! -f "$TODO_FILE" ]; then
    echo "[6/6] Creating example TODO.md at $TODO_FILE..."
    mkdir -p "$HOME/Developer"
    cat > "$TODO_FILE" << 'EOF'
# TODO

## Priority
- [ ] Review pull requests
- [ ] Deploy staging environment
- [ ] Write unit tests for auth module

## This Week
- [ ] Finish API documentation
- [ ] Fix login page bug
- [ ] Set up CI/CD pipeline
- [ ] Code review for team

## Backlog
- [ ] Refactor database queries
- [ ] Add dark mode support
- [ ] Performance optimization
EOF
    echo "  ✅ Created example TODO.md"
else
    echo "[6/6] ~/Developer/TODO.md already exists — skipping."
fi
echo ""

# ------------------------------------------------------------------
# 7. Run a quick test
# ------------------------------------------------------------------
echo "========================================"
echo "  Running quick test..."
echo "========================================"
echo ""
python scripts/system_check.py
echo ""
echo "Starting local search backend..."
bash scripts/start_searxng.sh
echo ""
echo "========================================"
echo "  🎩  Setup complete!"
echo "========================================"
echo ""
echo "Activate the project environment:"
echo "  source venv/bin/activate"
echo ""
echo "To start Butler with clap trigger:"
echo "  python trigger.py --clap"
echo ""
echo "To start both keyboard and clap:"
echo "  python trigger.py --both"
