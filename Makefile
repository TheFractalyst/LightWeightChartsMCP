.PHONY: serve serve-sse test lint install check help index index-full

serve:           ## Start MCP server (stdio transport)
	.venv/bin/python server.py

serve-sse:       ## Start MCP server (SSE transport on port 8080)
	.venv/bin/python server.py --transport sse --port 8080

test:            ## Run full test suite
	.venv/bin/python -m pytest tests/ -q

lint:            ## Lint source packages (ruff)
	.venv/bin/ruff check core/ formatters/ templates/ tools/ server.py --fix

install:         ## Setup venv + install all dependencies
	python3 -m venv .venv && .venv/bin/pip install -e ".[dev,pipeline]"

check:           ## Verify server: 6 tools + 1 resource
	@.venv/bin/python -c "from server import mcp; import asyncio; t=asyncio.run(mcp.list_tools()); r=asyncio.run(mcp.list_resources()); print(f'{len(t)} tools, {len(r)} resource(s)')"

index:           ## Re-index ChromaDB from existing data (skip scraping)
	.venv/bin/python pipeline/merge_and_index.py --reset

index-full:      ## Full re-scrape + re-index
	.venv/bin/python pipeline/scrape_lwc.py
	.venv/bin/python pipeline/merge_and_index.py --reset

help:            ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*##' Makefile | awk 'BEGIN{FS=":.*##"}{printf "  %-14s %s\n",$$1,$$2}'
