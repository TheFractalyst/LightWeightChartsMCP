.PHONY: serve test index index-full check help

serve:           ## Start MCP server (stdio transport)
	.venv/bin/python server.py

serve-sse:       ## Start MCP server (SSE transport on port 8080)
	TRANSPORT=sse PORT=8080 .venv/bin/python server.py

test:            ## Run production test suite
	@.venv/bin/python -c "
import asyncio
from tools.lookup import lwc_lookup
from tools.search import lwc_search
from tools.context import lwc_browse
from tools.validation import lwc_validate, lwc_repair
from tools.codegen import lwc_scaffold
from core.hot_cache import build_hot_cache, cache_lookup
async def t():
    await build_hot_cache()
    p = f = 0
    for name in ['createChart','IChartApi','ISeriesApi','CandlestickSeries','setData']:
        r = await lwc_lookup(name=name)
        p += 1 if len(r) > 50 else 0; f += 0 if len(r) > 50 else 1
    r = await lwc_search(query='candlestick series', n_results=3); p += 1
    r = await lwc_browse(namespace='interfaces'); p += 1
    r = await lwc_validate(code='import { createChart } from \"lightweight-charts\";\nconst chart = createChart(document.getElementById(\"c\"));'); p += 1
    r = await lwc_repair(code='chart.addCandlestickSeries()', context='deprecated'); p += 1
    r = await lwc_scaffold(kind='basic_chart', name='Test'); p += 1
    print(f'{p}/{p+f} tests passed')
    return f == 0
asyncio.run(t())
"

index:           ## Re-index ChromaDB from existing data (skip scraping)
	.venv/bin/python pipeline/merge_and_index.py --reset

index-full:      ## Full re-scrape + re-index
	.venv/bin/python pipeline/scrape_lwc.py
	.venv/bin/python pipeline/merge_and_index.py --reset

check:           ## Verify server: 6 tools + 1 resource
	@.venv/bin/python -c "from server import mcp; import asyncio; t=asyncio.run(mcp.list_tools()); r=asyncio.run(mcp.list_resources()); print(f'{len(t)} tools, {len(r)} resource(s)')"

health:          ## Check health endpoint (requires SSE server running)
	curl -s http://127.0.0.1:8080/health | python -m json.tool

help:            ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*##' Makefile | awk 'BEGIN{FS=":.*##"}{printf "  %-14s %s\n",$$1,$$2}'
