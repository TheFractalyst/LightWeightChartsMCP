#!/usr/bin/env bash
# ==================================================================
# run.sh - TradingView Lightweight Charts MCP Server full pipeline
#
# 2-stage pipeline: scrape docs -> merge+index
#
# Usage:
#   chmod +x run.sh
#   ./run.sh [--rescrape] [--reset-db] [--skip-scrape]
# ==================================================================

set -euo pipefail

RESCRAPE=false
RESET_DB=false
SKIP_SCRAPE=false

for arg in "$@"; do
    case "$arg" in
        --rescrape)     RESCRAPE=true ;;
        --reset-db)     RESET_DB=true ;;
        --skip-scrape)  SKIP_SCRAPE=true ;;
        --help|-h)
            echo "Usage: ./run.sh [--rescrape] [--reset-db] [--skip-scrape]"
            exit 0
            ;;
    esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

VENV_DIR="$SCRIPT_DIR/.venv"
if [ ! -d "$VENV_DIR" ]; then
    python3 -m venv "$VENV_DIR"
fi
PYTHON="$VENV_DIR/bin/python"
PIP="$VENV_DIR/bin/pip"
"$PIP" install --quiet --upgrade pip
"$PIP" install --quiet -e ".[pipeline,dev]"

if [ "$SKIP_SCRAPE" = false ]; then
    echo "=== Scraping Lightweight Charts ==="
    "$PYTHON" "$SCRIPT_DIR/pipeline/scrape_lwc.py"
fi

MERGE_ARGS=""
if [ "$RESET_DB" = true ]; then
    MERGE_ARGS="--reset"
fi
"$PYTHON" "$SCRIPT_DIR/pipeline/merge_and_index.py" $MERGE_ARGS

DB_DIR="$SCRIPT_DIR/lwc_db"
DB_COUNT=$("$PYTHON" -c "import chromadb; c=chromadb.PersistentClient(path='$DB_DIR'); print(c.get_collection('lwc_reference').count())" 2>/dev/null || echo 0)
echo "Database entries: $DB_COUNT"
echo "Server: $PYTHON $SCRIPT_DIR/server.py"
