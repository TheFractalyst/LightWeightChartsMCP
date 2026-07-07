# ruff: noqa: E501
"""
templates/templates.py
JavaScript/TypeScript scaffold templates for TradingView Lightweight Charts v5.0.

Each template uses ES module import syntax and the v5 addSeries() API with
SeriesType definitions (CandlestickSeries, LineSeries, AreaSeries, etc.).

Placeholders:
  {name}     - replaced with the user-provided display name
  {var_name} - replaced with camelCase version of name (first letter lowercase,
               spaces removed) for the main JavaScript variable
"""

from __future__ import annotations

BASIC_CHART = """/**
 * {name} - Basic Lightweight Charts Candlestick + Line Chart
 *
 * Creates a chart with a candlestick series and a line series,
 * sets sample data, and fits the content.
 */
import { createChart, CandlestickSeries, LineSeries } from 'lightweight-charts';

const container = document.getElementById('container');

const {var_name} = createChart(container, {
    layout: {
        background: { type: 'solid', color: '#ffffff' },
        textColor: '#333333',
    },
    grid: {
        vertLines: { color: '#eeeeee' },
        horzLines: { color: '#eeeeee' },
    },
});

const candlestickSeries = {var_name}.addSeries(CandlestickSeries, {
    upColor: '#26a69a',
    downColor: '#ef5350',
    borderVisible: false,
    wickUpColor: '#26a69a',
    wickDownColor: '#ef5350',
});

candlestickSeries.setData([
    { time: '2024-01-01', open: 100, high: 110, low: 95, close: 105 },
    { time: '2024-01-02', open: 105, high: 115, low: 100, close: 110 },
    { time: '2024-01-03', open: 110, high: 120, low: 105, close: 115 },
]);

const lineSeries = {var_name}.addSeries(LineSeries, {
    color: '#2962FF',
    lineWidth: 2,
});

lineSeries.setData([
    { time: '2024-01-01', value: 100 },
    { time: '2024-01-02', value: 108 },
    { time: '2024-01-03', value: 112 },
]);

{var_name}.timeScale().fitContent();
"""

REALTIME_UPDATES = """/**
 * {name} - Real-Time Updates Chart
 *
 * Creates a candlestick series with initial data and simulates
 * real-time updates using setInterval and series.update().
 */
import { createChart, CandlestickSeries } from 'lightweight-charts';

const container = document.getElementById('container');

const {var_name} = createChart(container, {
    layout: {
        background: { type: 'solid', color: '#ffffff' },
        textColor: '#333333',
    },
});

const candlestickSeries = {var_name}.addSeries(CandlestickSeries, {
    upColor: '#26a69a',
    downColor: '#ef5350',
    borderVisible: false,
    wickUpColor: '#26a69a',
    wickDownColor: '#ef5350',
});

candlestickSeries.setData([
    { time: '2024-01-01', open: 100, high: 110, low: 95, close: 105 },
    { time: '2024-01-02', open: 105, high: 115, low: 100, close: 110 },
    { time: '2024-01-03', open: 110, high: 120, low: 105, close: 115 },
    { time: '2024-01-04', open: 115, high: 125, low: 110, close: 120 },
    { time: '2024-01-05', open: 120, high: 130, low: 115, close: 125 },
]);

{var_name}.timeScale().fitContent();

// Simulate real-time updates with setInterval
let lastTime = '2024-01-05';
let lastClose = 125;

const intervalId = setInterval(() => {
    const date = new Date(lastTime);
    date.setDate(date.getDate() + 1);
    lastTime = date.toISOString().split('T')[0];

    const open = lastClose;
    const close = open + (Math.random() - 0.5) * 10;
    const high = Math.max(open, close) + Math.random() * 5;
    const low = Math.min(open, close) - Math.random() * 5;

    candlestickSeries.update({
        time: lastTime,
        open: open,
        high: high,
        low: low,
        close: close,
    });

    lastClose = close;
}, 1000);

// Stop updates after 60 seconds
setTimeout(() => clearInterval(intervalId), 60000);
"""

MULTIPLE_SERIES = """/**
 * {name} - Multiple Series Types Chart
 *
 * Creates Area, Bar, Baseline, and Histogram series on a single chart
 * to demonstrate different series types and their data formats.
 */
import { createChart, AreaSeries, BarSeries, BaselineSeries, HistogramSeries } from 'lightweight-charts';

const container = document.getElementById('container');

const {var_name} = createChart(container, {
    layout: {
        background: { type: 'solid', color: '#ffffff' },
        textColor: '#333333',
    },
});

// Area series - data format: { time, value }
const areaSeries = {var_name}.addSeries(AreaSeries, {
    lineColor: '#2962FF',
    topColor: '#2962FF',
    bottomColor: 'rgba(41, 98, 255, 0.28)',
    lineWidth: 2,
});

areaSeries.setData([
    { time: '2024-01-01', value: 100 },
    { time: '2024-01-02', value: 108 },
    { time: '2024-01-03', value: 112 },
    { time: '2024-01-04', value: 115 },
    { time: '2024-01-05', value: 120 },
]);

// Bar series - data format: { time, open, high, low, close }
const barSeries = {var_name}.addSeries(BarSeries, {
    upColor: '#26a69a',
    downColor: '#ef5350',
});

barSeries.setData([
    { time: '2024-01-01', open: 100, high: 110, low: 95, close: 105 },
    { time: '2024-01-02', open: 105, high: 115, low: 100, close: 110 },
    { time: '2024-01-03', open: 110, high: 120, low: 105, close: 115 },
    { time: '2024-01-04', open: 115, high: 125, low: 110, close: 120 },
    { time: '2024-01-05', open: 120, high: 130, low: 115, close: 125 },
]);

// Baseline series - data format: { time, value }
const baselineSeries = {var_name}.addSeries(BaselineSeries, {
    baseValue: { type: 'price', price: 110 },
    topLineColor: '#26a69a',
    topFillColor1: 'rgba(38, 166, 154, 0.28)',
    topFillColor2: 'rgba(38, 166, 154, 0.05)',
    bottomLineColor: '#ef5350',
    bottomFillColor1: 'rgba(239, 83, 80, 0.05)',
    bottomFillColor2: 'rgba(239, 83, 80, 0.28)',
});

baselineSeries.setData([
    { time: '2024-01-01', value: 100 },
    { time: '2024-01-02', value: 108 },
    { time: '2024-01-03', value: 112 },
    { time: '2024-01-04', value: 115 },
    { time: '2024-01-05', value: 120 },
]);

// Histogram series - data format: { time, value, color }
const histogramSeries = {var_name}.addSeries(HistogramSeries, {
    priceFormat: { type: 'volume' },
    priceScaleId: '',
});

histogramSeries.setData([
    { time: '2024-01-01', value: 1000, color: '#26a69a' },
    { time: '2024-01-02', value: 1500, color: '#ef5350' },
    { time: '2024-01-03', value: 1200, color: '#26a69a' },
    { time: '2024-01-04', value: 1800, color: '#ef5350' },
    { time: '2024-01-05', value: 2000, color: '#26a69a' },
]);

{var_name}.timeScale().fitContent();
"""

CUSTOM_STYLING = """/**
 * {name} - Custom Styling Chart
 *
 * Demonstrates appearance customization: dark theme colors, grid styles,
 * crosshair options, text watermark, and layout configuration.
 */
import { createChart, CandlestickSeries, LineStyle, createTextWatermark } from 'lightweight-charts';

const container = document.getElementById('container');

const {var_name} = createChart(container, {
    layout: {
        background: { type: 'solid', color: '#1e222d' },
        textColor: '#d1d4dc',
        fontSize: 12,
        fontFamily: 'monospace',
    },
    grid: {
        vertLines: { color: 'rgba(42, 46, 57, 0.5)', style: LineStyle.Dotted },
        horzLines: { color: 'rgba(42, 46, 57, 0.5)', style: LineStyle.Dotted },
    },
    crosshair: {
        mode: 1,
        vertLine: {
            color: '#758696',
            width: 1,
            style: LineStyle.Dashed,
            labelBackgroundColor: '#758696',
        },
        horzLine: {
            color: '#758696',
            width: 1,
            style: LineStyle.Dashed,
            labelBackgroundColor: '#758696',
        },
    },
    rightPriceScale: {
        borderColor: 'rgba(42, 46, 57, 0.5)',
    },
    timeScale: {
        borderColor: 'rgba(42, 46, 57, 0.5)',
        timeVisible: true,
        secondsVisible: false,
    },
});

// Add a text watermark to the first pane (v5 API)
const firstPane = {var_name}.panes()[0];
createTextWatermark(firstPane, {
    horzAlign: 'center',
    vertAlign: 'center',
    lines: [
        {
            text: '{name}',
            color: 'rgba(255, 255, 255, 0.1)',
            fontSize: 48,
            fontStyle: 'bold',
        },
    ],
});

const candlestickSeries = {var_name}.addSeries(CandlestickSeries, {
    upColor: '#26a69a',
    downColor: '#ef5350',
    borderVisible: false,
    wickUpColor: '#26a69a',
    wickDownColor: '#ef5350',
});

candlestickSeries.setData([
    { time: '2024-01-01', open: 100, high: 110, low: 95, close: 105 },
    { time: '2024-01-02', open: 105, high: 115, low: 100, close: 110 },
    { time: '2024-01-03', open: 110, high: 120, low: 105, close: 115 },
    { time: '2024-01-04', open: 115, high: 125, low: 110, close: 120 },
    { time: '2024-01-05', open: 120, high: 130, low: 115, close: 125 },
]);

{var_name}.timeScale().fitContent();
"""

PRICE_LINES = """/**
 * {name} - Price Lines and Markers Chart
 *
 * Demonstrates price lines (createPriceLine) and series markers
 * (createSeriesMarkers) on a candlestick chart. Uses v5 markers API.
 */
import { createChart, CandlestickSeries, LineStyle, createSeriesMarkers } from 'lightweight-charts';

const container = document.getElementById('container');

const {var_name} = createChart(container, {
    layout: {
        background: { type: 'solid', color: '#ffffff' },
        textColor: '#333333',
    },
});

const candlestickSeries = {var_name}.addSeries(CandlestickSeries, {
    upColor: '#26a69a',
    downColor: '#ef5350',
    borderVisible: false,
    wickUpColor: '#26a69a',
    wickDownColor: '#ef5350',
});

candlestickSeries.setData([
    { time: '2024-01-01', open: 100, high: 110, low: 95, close: 105 },
    { time: '2024-01-02', open: 105, high: 115, low: 100, close: 110 },
    { time: '2024-01-03', open: 110, high: 120, low: 105, close: 115 },
    { time: '2024-01-04', open: 115, high: 125, low: 110, close: 120 },
    { time: '2024-01-05', open: 120, high: 130, low: 115, close: 125 },
]);

// Create price lines for support and resistance levels
const supportLine = candlestickSeries.createPriceLine({
    price: 95,
    color: '#ef5350',
    lineWidth: 1,
    lineStyle: LineStyle.Dashed,
    axisLabelVisible: true,
    title: 'Support',
});

const resistanceLine = candlestickSeries.createPriceLine({
    price: 130,
    color: '#26a69a',
    lineWidth: 1,
    lineStyle: LineStyle.Dashed,
    axisLabelVisible: true,
    title: 'Resistance',
});

// Create series markers (v5 API: use createSeriesMarkers, not series.setMarkers)
const seriesMarkers = createSeriesMarkers(candlestickSeries, [
    {
        time: '2024-01-02',
        position: 'belowBar',
        color: '#26a69a',
        shape: 'arrowUp',
        text: 'Buy',
    },
    {
        time: '2024-01-04',
        position: 'aboveBar',
        color: '#ef5350',
        shape: 'arrowDown',
        text: 'Sell',
    },
]);

{var_name}.timeScale().fitContent();
"""

REACT_INTEGRATION = """/**
 * {name} - React Integration Component
 *
 * React component that creates a Lightweight Chart on mount and
 * cleans up on unmount using useRef and useEffect. Includes
 * responsive resize handling.
 */
import React, { useRef, useEffect } from 'react';
import { createChart, CandlestickSeries } from 'lightweight-charts';

export function {var_name}({ data = [] }) {
    const containerRef = useRef(null);
    const chartRef = useRef(null);

    useEffect(() => {
        if (!containerRef.current) return;

        const chart = createChart(containerRef.current, {
            layout: {
                background: { type: 'solid', color: '#ffffff' },
                textColor: '#333333',
            },
            width: containerRef.current.clientWidth,
            height: 400,
        });

        const candlestickSeries = chart.addSeries(CandlestickSeries, {
            upColor: '#26a69a',
            downColor: '#ef5350',
            borderVisible: false,
            wickUpColor: '#26a69a',
            wickDownColor: '#ef5350',
        });

        candlestickSeries.setData(data.length > 0 ? data : [
            { time: '2024-01-01', open: 100, high: 110, low: 95, close: 105 },
            { time: '2024-01-02', open: 105, high: 115, low: 100, close: 110 },
            { time: '2024-01-03', open: 110, high: 120, low: 105, close: 115 },
        ]);

        chart.timeScale().fitContent();
        chartRef.current = chart;

        // Responsive resize handling
        const handleResize = () => {
            if (containerRef.current) {
                chart.applyOptions({ width: containerRef.current.clientWidth });
            }
        };
        window.addEventListener('resize', handleResize);

        // Cleanup on unmount
        return () => {
            window.removeEventListener('resize', handleResize);
            chart.remove();
            chartRef.current = null;
        };
    }, [data]);

    return <div ref={containerRef} style={{ width: '100%', height: '400px' }} />;
}
"""

TWO_PRICE_SCALES = """/**
 * {name} - Two Price Scales Chart
 *
 * Creates two series on different price scales (left and right)
 * to compare values with different ranges on the same time scale.
 */
import { createChart, LineSeries, HistogramSeries } from 'lightweight-charts';

const container = document.getElementById('container');

const {var_name} = createChart(container, {
    layout: {
        background: { type: 'solid', color: '#ffffff' },
        textColor: '#333333',
    },
    leftPriceScale: {
        visible: true,
        borderColor: 'rgba(0, 0, 0, 0.2)',
    },
    rightPriceScale: {
        visible: true,
        borderColor: 'rgba(0, 0, 0, 0.2)',
    },
});

// Line series on the left price scale (e.g., price data)
const priceSeries = {var_name}.addSeries(LineSeries, {
    color: '#2962FF',
    lineWidth: 2,
    priceScaleId: 'left',
});

priceSeries.setData([
    { time: '2024-01-01', value: 100 },
    { time: '2024-01-02', value: 108 },
    { time: '2024-01-03', value: 112 },
    { time: '2024-01-04', value: 115 },
    { time: '2024-01-05', value: 120 },
]);

// Histogram series on the right price scale (e.g., volume data)
const volumeSeries = {var_name}.addSeries(HistogramSeries, {
    priceFormat: { type: 'volume' },
    priceScaleId: 'right',
});

volumeSeries.setData([
    { time: '2024-01-01', value: 1000, color: '#26a69a' },
    { time: '2024-01-02', value: 1500, color: '#ef5350' },
    { time: '2024-01-03', value: 1200, color: '#26a69a' },
    { time: '2024-01-04', value: 1800, color: '#ef5350' },
    { time: '2024-01-05', value: 2000, color: '#26a69a' },
]);

{var_name}.timeScale().fitContent();
"""

_TEMPLATES = {
    "basic_chart": BASIC_CHART,
    "realtime_updates": REALTIME_UPDATES,
    "multiple_series": MULTIPLE_SERIES,
    "custom_styling": CUSTOM_STYLING,
    "price_lines": PRICE_LINES,
    "react_integration": REACT_INTEGRATION,
    "two_price_scales": TWO_PRICE_SCALES,
}


def _to_camel_case(name: str) -> str:
    """Convert a display name to a camelCase JavaScript variable name.

    Removes spaces and lowercases the first letter.
    """
    var_name = name.replace(" ", "")
    if not var_name:
        return "chart"
    return var_name[0].lower() + var_name[1:]


def get_template(kind: str, name: str) -> str:
    """Look up a template by kind and substitute placeholders.

    Args:
        kind: Template key (e.g., 'basic_chart', 'realtime_updates').
        name: Display name for the generated chart/script.

    Returns:
        Template string with {name} and {var_name} placeholders replaced.

    Raises:
        ValueError: If kind is not a known template key.
    """
    if kind not in _TEMPLATES:
        available = ", ".join(sorted(_TEMPLATES.keys()))
        raise ValueError(f"Unknown template kind: '{kind}'. Available: {available}")

    template = _TEMPLATES[kind]
    var_name = _to_camel_case(name)

    template = template.replace("{name}", name)
    template = template.replace("{var_name}", var_name)

    return template
