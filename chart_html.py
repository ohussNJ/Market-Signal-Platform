# chart_html.py  –  TradingView Lightweight Charts HTML generation for indicator tabs

import json
import pathlib
import pandas as pd
import numpy as np
from config import C, MA_PERIODS, STOCHRSI_CONFIGS
import signals as Sig
import divergence as Div

_HERE = pathlib.Path(__file__).parent
_LWC_JS = (_HERE / "lightweight-charts.min.js").read_text(encoding="utf-8")

# Data serialization
def _dt(ts: pd.Timestamp, intraday: bool = False):
    return int(ts.timestamp()) if intraday else ts.strftime("%Y-%m-%d")

def _line(df: pd.DataFrame, col: str, intraday: bool = False) -> list:
    if col not in df.columns:
        return []
    return [
        {"time": _dt(ts, intraday), "value": round(float(v), 6)}
        for ts, v in df[col].items()
        if pd.notna(v)
    ]

def _ohlcv(df: pd.DataFrame, intraday: bool = False) -> tuple:
    ohlc, vol = [], []
    for ts, row in df.iterrows():
        t = _dt(ts, intraday)
        o = row.get("Open")
        h = row.get("High")
        l = row.get("Low")
        c = row.get("Close")
        v = row.get("Volume")
        if all(pd.notna(x) for x in [o, h, l, c]):
            ohlc.append({
                "time": t,
                "open":  round(float(o), 6),
                "high":  round(float(h), 6),
                "low":   round(float(l), 6),
                "close": round(float(c), 6),
            })
        if pd.notna(v) and pd.notna(o) and pd.notna(c):
            is_up = float(c) >= float(o)
            vol.append({
                "time":  t,
                "value": float(v),
                "color": (C["vol_up"] + "40") if is_up else (C["vol_down"] + "40"),
            })
    return ohlc, vol

def _score_histogram(df: pd.DataFrame, intraday: bool = False) -> list:
    score = Sig.score_history(df, n=len(df)).reindex(df.index)
    state = Sig.signal_state_history(df, n=len(df)).reindex(df.index).fillna("NEUTRAL")
    result = []
    for ts, val in score.items():
        if pd.isna(val):
            continue
        st = state.get(ts, "NEUTRAL")
        if st == "BULL":
            color = C["bull_fg"] + "bb"
        elif st == "BEAR":
            color = C["bear_fg"] + "bb"
        else:
            color = "#6c7086"
        result.append({"time": _dt(ts, intraday), "value": round(float(val), 4), "color": color})
    return result

def _cnv_histogram(df: pd.DataFrame, intraday: bool = False) -> list:
    if "CNV_TB" not in df.columns:
        return []
    result = []
    for ts, val in df["CNV_TB"].items():
        if pd.isna(val):
            continue
        color = "#3b82f6cc" if float(val) >= 0 else "#ef4444cc"
        result.append({"time": _dt(ts, intraday), "value": round(float(val), 4), "color": color})
    return result

def _divergences(df: pd.DataFrame, indicator, intraday: bool = False,
                 min_price_pct: float = 0.3, min_ind_delta: float = 3.0) -> list:
    """
    indicator: column name string or a pre-computed pd.Series aligned to df.index.
    Returns a list of divergence dicts with serialized time values.
    """
    price = df["Close"].dropna().values.astype(float)
    if isinstance(indicator, str):
        if indicator not in df.columns:
            return []
        ind_vals = df[indicator].values.astype(float)
    else:
        ind_vals = indicator.reindex(df.index).values.astype(float)

    divs = Div.find_regular_divergences(
        price, ind_vals, left=5, right=5,
        min_price_pct=min_price_pct, min_ind_delta=min_ind_delta,
    )
    result = []
    idx = df.index
    for d in divs:
        result.append({
            "type": d["type"],
            "pt1":  _dt(idx[d["pi1"]], intraday), "p1":   round(float(d["p1"]),   6),
            "pt2":  _dt(idx[d["pi2"]], intraday), "p2":   round(float(d["p2"]),   6),
            "it1":  _dt(idx[d["ii1"]], intraday), "ind1": round(float(d["ind1"]), 6),
            "it2":  _dt(idx[d["ii2"]], intraday), "ind2": round(float(d["ind2"]), 6),
        })
    return result

# JS fragments
def _col_js() -> str:
    return (
        "const COL={"
        + f"bullFg:'{C['bull_fg']}',"
        + f"bearFg:'{C['bear_fg']}',"
        + f"ema50:'{C['ema50']}',"
        + f"ema100:'{C['ema100']}',"
        + f"ema200:'{C['ema200']}',"
        + f"bullSma:'{C['bull_sma']}',"
        + f"bullEma:'{C['bull_ema']}',"
        + f"kc:'{C['kc']}',"
        + f"nw:'{C['nw']}',"
        + f"rsi:'{C['rsi']}',"
        + f"rsiMa:'{C['obv_ma']}',"
        + f"kLine:'{C['k_line']}',"
        + f"dLine:'{C['d_line']}',"
        + f"obv:'{C['obv']}',"
        + f"obvMa:'{C['obv_ma']}',"
        + f"volMa:'{C['vol_ma']}',"
        + "divBull:'#16a34a',"
        + "divBear:'#dc2626',"
        + "};"
    )

_SHARED_JS = r"""
const {createChart, CrosshairMode, LineStyle, PriceScaleMode} = LightweightCharts;

function makeChart(el, label) {
    return createChart(el, {
        autoSize: true,
        layout: { background: { color: '#181825' }, textColor: '#cdd6f4' },
        grid: { vertLines: { color: '#313244' }, horzLines: { color: '#313244' } },
        crosshair: {
            mode: CrosshairMode.Normal,
            vertLine: { color: '#6c7086', width: 1, style: LineStyle.Dashed, labelBackgroundColor: '#313244' },
            horzLine: { color: '#6c7086', width: 1, style: LineStyle.Dashed, labelBackgroundColor: '#313244' },
        },
        timeScale: { borderColor: '#45475a', timeVisible: true, secondsVisible: false },
        rightPriceScale: { borderColor: '#45475a', minimumWidth: 80 },
        watermark: label ? { visible: true, text: label, color: '#4a4a6a', fontSize: 11, horzAlign: 'left', vertAlign: 'top' } : { visible: false },
    });
}

function syncCharts(charts) {
    charts.forEach((src, si) => {
        src.timeScale().subscribeVisibleLogicalRangeChange(range => {
            if (!range) return;
            charts.forEach((dst, di) => { if (di !== si) dst.timeScale().setVisibleLogicalRange(range); });
        });
    });
}

const panes = document.querySelectorAll('.pane');
const charts = [];
"""

_PRICE_PANE_BASE_JS = r"""
const pChart = makeChart(panes[0], TITLE);
charts.push(pChart);

const candles = pChart.addCandlestickSeries({
    upColor: COL.bullFg, downColor: COL.bearFg,
    borderUpColor: COL.bullFg, borderDownColor: COL.bearFg,
    wickUpColor: COL.bullFg + '80', wickDownColor: COL.bearFg + '80',
});
candles.setData(DATA.ohlc);

const volS = pChart.addHistogramSeries({
    priceScaleId: 'vol', priceFormat: { type: 'volume' },
    lastValueVisible: false, priceLineVisible: false,
});
pChart.priceScale('vol').applyOptions({ scaleMargins: { top: 0.85, bottom: 0 }, visible: false });
volS.setData(DATA.vol);
if (DATA.vol_ma && DATA.vol_ma.length) {
    const volMaS = pChart.addLineSeries({
        priceScaleId: 'vol', color: COL.volMa, lineWidth: 1,
        lastValueVisible: false, priceLineVisible: false,
    });
    volMaS.setData(DATA.vol_ma);
}
"""

_MA_OVERLAYS_JS = r"""
const EMA_COLS = [COL.ema50, COL.ema100, COL.ema200];
const _lgItems = [];
[50, 100, 200].forEach((p, i) => {
    const ek = 'ema' + p, sk = 'sma' + p;
    if (DATA[ek] && DATA[ek].length) {
        const s = pChart.addLineSeries({ color: EMA_COLS[i], lineWidth: 1, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false });
        s.setData(DATA[ek]);
        _lgItems.push({ label: 'EMA'+p, color: EMA_COLS[i], series: s, data: DATA[ek] });
    }
    if (DATA[sk] && DATA[sk].length) {
        const s = pChart.addLineSeries({ color: EMA_COLS[i], lineWidth: 1, lineStyle: LineStyle.Dashed, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false });
        s.setData(DATA[sk]);
        _lgItems.push({ label: 'SMA'+p, color: EMA_COLS[i], series: s, data: DATA[sk] });
    }
});
if (DATA.bull_sma && DATA.bull_sma.length) {
    const s = pChart.addLineSeries({ color: COL.bullSma, lineWidth: 1, lineStyle: LineStyle.Dotted, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false });
    s.setData(DATA.bull_sma);
    _lgItems.push({ label: '20wSMA', color: COL.bullSma, series: s, data: DATA.bull_sma });
}
if (DATA.bull_ema && DATA.bull_ema.length) {
    const s = pChart.addLineSeries({ color: COL.bullEma, lineWidth: 1, lineStyle: LineStyle.Dotted, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false });
    s.setData(DATA.bull_ema);
    _lgItems.push({ label: '21wEMA', color: COL.bullEma, series: s, data: DATA.bull_ema });
}
{
    const _el = document.createElement('div');
    _el.style.cssText = 'position:absolute;top:8px;left:8px;z-index:10;font:11px Consolas,monospace;line-height:1.8;pointer-events:none;background:rgba(24,24,37,0.7);padding:4px 8px;border-radius:4px;';
    panes[0].appendChild(_el);
    const _fv = v => (v == null || isNaN(v)) ? null : v >= 1000 ? (v/1000).toFixed(2)+'k' : v >= 1 ? v.toFixed(2) : v.toFixed(4);
    const _render = param => {
        _el.innerHTML = _lgItems.map(({label, color, series, data}) => {
            let v = data.length ? data[data.length-1].value : null;
            if (param && param.time && series) {
                const d = param.seriesData && param.seriesData.get(series);
                if (d && d.value != null) v = d.value;
            }
            const f = _fv(v);
            return f ? `<span style="color:${color}">${label}&nbsp;<b>${f}</b></span>` : '';
        }).filter(Boolean).join('<span style="color:#555">&nbsp;·&nbsp;</span>');
    };
    _render(null);
    pChart.subscribeCrosshairMove(_render);
}
"""

_KC_NW_OVERLAYS_JS = r"""
const _lgItems = [];
if (DATA.kc_upper && DATA.kc_upper.length) {
    const kcU = pChart.addLineSeries({ color: COL.kc, lineWidth: 1, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false });
    kcU.setData(DATA.kc_upper);
    const kcL = pChart.addLineSeries({ color: COL.kc, lineWidth: 1, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false });
    kcL.setData(DATA.kc_lower);
    const basis = pChart.addLineSeries({ color: COL.kc + '70', lineWidth: 1, lineStyle: LineStyle.Dashed, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false });
    basis.setData(DATA.kc_basis);
    _lgItems.push({ label: 'KC Upper', color: COL.kc, series: kcU, data: DATA.kc_upper });
    _lgItems.push({ label: 'KC Lower', color: COL.kc, series: kcL, data: DATA.kc_lower });
    _lgItems.push({ label: 'KC Mid',   color: COL.kc, series: basis, data: DATA.kc_basis });
}
if (DATA.nw_upper && DATA.nw_upper.length) {
    const nwU = pChart.addLineSeries({ color: COL.nw, lineWidth: 1, lineStyle: LineStyle.Dotted, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false });
    nwU.setData(DATA.nw_upper);
    const nwL = pChart.addLineSeries({ color: COL.bearFg, lineWidth: 1, lineStyle: LineStyle.Dotted, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false });
    nwL.setData(DATA.nw_lower);
    _lgItems.push({ label: 'NW Upper', color: COL.nw,    series: nwU, data: DATA.nw_upper });
    _lgItems.push({ label: 'NW Lower', color: COL.bearFg, series: nwL, data: DATA.nw_lower });
}
if (DATA.price_17 !== null) {
    candles.createPriceLine({ price: DATA.price_17, color: COL.ema50, lineWidth: 1, lineStyle: LineStyle.Dashed, axisLabelVisible: false, title: '17-bar' });
    _lgItems.push({ label: '17-bar', color: COL.ema50, series: null, data: [], staticVal: DATA.price_17 });
}
if (DATA.price_42 !== null) {
    candles.createPriceLine({ price: DATA.price_42, color: COL.ema100, lineWidth: 1, lineStyle: LineStyle.Dashed, axisLabelVisible: false, title: '42-bar' });
    _lgItems.push({ label: '42-bar', color: COL.ema100, series: null, data: [], staticVal: DATA.price_42 });
}
{
    const _el = document.createElement('div');
    _el.style.cssText = 'position:absolute;top:8px;left:8px;z-index:10;font:11px Consolas,monospace;line-height:1.8;pointer-events:none;background:rgba(24,24,37,0.7);padding:4px 8px;border-radius:4px;';
    panes[0].appendChild(_el);
    const _fv = v => (v == null || isNaN(v)) ? null : v >= 1000 ? (v/1000).toFixed(2)+'k' : v >= 1 ? v.toFixed(2) : v.toFixed(4);
    const _render = param => {
        _el.innerHTML = _lgItems.map(({label, color, series, data, staticVal}) => {
            let v = staticVal != null ? staticVal : (data.length ? data[data.length-1].value : null);
            if (param && param.time && series) {
                const d = param.seriesData && param.seriesData.get(series);
                if (d && d.value != null) v = d.value;
            }
            const f = _fv(v);
            return f ? `<span style="color:${color}">${label}&nbsp;<b>${f}</b></span>` : '';
        }).filter(Boolean).join('<span style="color:#555">&nbsp;·&nbsp;</span>');
    };
    _render(null);
    pChart.subscribeCrosshairMove(_render);
}
"""

_SCORE_IND_JS = r"""
const iChart0 = makeChart(panes[1], 'Score');
iChart0.priceScale('right').applyOptions({ ticksVisible: false });
charts.push(iChart0);
if (DATA.score && DATA.score.length) {
    const scoreSeries = iChart0.addHistogramSeries({ base: 0, priceFormat: { type: 'price', precision: 0, minMove: 1 }, priceLineVisible: false, lastValueVisible: true });
    scoreSeries.setData(DATA.score);
    [70, 30, 0, -30, -70].forEach(v => {
        scoreSeries.createPriceLine({ price: v, color: '#3a3a5a', lineWidth: 1, lineStyle: LineStyle.Dotted, axisLabelVisible: true });
    });
}
"""

_RSI_IND_JS = r"""
const iChart0 = makeChart(panes[1], 'RSI');
charts.push(iChart0);
if (DATA.rsi && DATA.rsi.length) {
    const rsiS = iChart0.addLineSeries({ color: COL.rsi, lineWidth: 1, priceLineVisible: false, lastValueVisible: true });
    rsiS.setData(DATA.rsi);
    rsiS.createPriceLine({ price: 70, color: COL.bearFg + '99', lineWidth: 1, lineStyle: LineStyle.Dashed, axisLabelVisible: true });
    rsiS.createPriceLine({ price: 50, color: '#444', lineWidth: 1, lineStyle: LineStyle.Dotted, axisLabelVisible: false });
    rsiS.createPriceLine({ price: 30, color: COL.bullFg + '99', lineWidth: 1, lineStyle: LineStyle.Dashed, axisLabelVisible: true });
}
if (DATA.rsi_ma && DATA.rsi_ma.length) {
    const rsiMa = iChart0.addLineSeries({ color: COL.rsiMa, lineWidth: 1, lineStyle: LineStyle.Dashed, priceLineVisible: false, lastValueVisible: false });
    rsiMa.setData(DATA.rsi_ma);
}
"""

_STOCH_IND_JS = r"""
[[panes[1], DATA.slow_k, DATA.slow_d, 'Slow StochRSI'],
 [panes[2], DATA.fast_k, DATA.fast_d, 'Fast StochRSI']
].forEach(([pane, kd, dd, lbl]) => {
    const ch = makeChart(pane, lbl);
    charts.push(ch);
    if (kd && kd.length) {
        const kS = ch.addLineSeries({ color: COL.kLine, lineWidth: 1, priceLineVisible: false, lastValueVisible: true });
        kS.setData(kd);
        kS.createPriceLine({ price: 80, color: COL.bearFg + '99', lineWidth: 1, lineStyle: LineStyle.Dashed, axisLabelVisible: true });
        kS.createPriceLine({ price: 20, color: COL.bullFg + '99', lineWidth: 1, lineStyle: LineStyle.Dashed, axisLabelVisible: true });
    }
    if (dd && dd.length) {
        const dS = ch.addLineSeries({ color: COL.dLine, lineWidth: 1, lineStyle: LineStyle.Dashed, priceLineVisible: false, lastValueVisible: false });
        dS.setData(dd);
    }
});
"""

_OBV_IND_JS = r"""
const iChart0 = makeChart(panes[1], 'OBV');
charts.push(iChart0);
if (DATA.obv && DATA.obv.length) {
    const obvS = iChart0.addLineSeries({ color: COL.obv, lineWidth: 1, priceFormat: { type: 'volume' }, priceLineVisible: false, lastValueVisible: true });
    obvS.setData(DATA.obv);
}
if (DATA.obv_ma && DATA.obv_ma.length) {
    const obvMa = iChart0.addLineSeries({ color: COL.obvMa, lineWidth: 1, lineStyle: LineStyle.Dashed, priceLineVisible: false, lastValueVisible: false });
    obvMa.setData(DATA.obv_ma);
}
"""

_CNV_IND_JS = r"""
const iChart0 = makeChart(panes[1], 'CNV');
charts.push(iChart0);
if (DATA.cnv_tb && DATA.cnv_tb.length) {
    const cnvS = iChart0.addHistogramSeries({ base: 0, priceFormat: { type: 'volume' }, priceLineVisible: false, lastValueVisible: true });
    cnvS.setData(DATA.cnv_tb);
    cnvS.createPriceLine({ price: 0, color: '#555', lineWidth: 1, lineStyle: LineStyle.Solid, axisLabelVisible: false });
}
"""

_DIV_JS = r"""
if (DATA.divergences && DATA.divergences.length) {
    DATA.divergences.forEach(div => {
        const col = div.type === 'bullish' ? COL.divBull : COL.divBear;
        const opts = {
            color: col, lineWidth: 1, lineStyle: LineStyle.Dashed,
            lastValueVisible: false, priceLineVisible: false,
            crosshairMarkerVisible: false,
        };
        const pLine = pChart.addLineSeries(opts);
        pLine.setData([{time: div.pt1, value: div.p1}, {time: div.pt2, value: div.p2}]);
        const iLine = iChart0.addLineSeries(opts);
        iLine.setData([{time: div.it1, value: div.ind1}, {time: div.it2, value: div.ind2}]);
    });
}
"""

_IND_JS = {
    "score":   _SCORE_IND_JS + _DIV_JS,
    "rsi":     _RSI_IND_JS   + _DIV_JS,
    "stoch":   _STOCH_IND_JS,
    "obv":     _OBV_IND_JS   + _DIV_JS,
    "keltner": _CNV_IND_JS,
}

_PANE_DIVS = {
    "score":   '<div class="pane" style="flex:3"></div><div class="pane" style="flex:1"></div>',
    "rsi":     '<div class="pane" style="flex:3"></div><div class="pane" style="flex:1"></div>',
    "obv":     '<div class="pane" style="flex:3"></div><div class="pane" style="flex:1"></div>',
    "keltner": '<div class="pane" style="flex:3"></div><div class="pane" style="flex:1"></div>',
    "stoch":   '<div class="pane" style="flex:3"></div><div class="pane" style="flex:1.2"></div><div class="pane" style="flex:1.2"></div>',
}

_HTML_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
html, body { width: 100%; height: 100%; background: #181825; overflow: hidden; }
#root { display: flex; flex-direction: column; width: 100%; height: 100%; }
.pane { position: relative; min-height: 0; overflow: hidden; }
.pane + .pane { border-top: 1px solid #313244; }
</style>
</head>
<body>
<div id="root">
__PANE_DIVS__
</div>
<script>__LWC_JS__</script>
<script>
(function() {
__INIT_JS__
// Anchor every indicator chart to the full OHLC time extent so all charts share
// the same logical-index space; without this, series with warmup NaN stripped
// have fewer bars and the same logical index maps to a different date.
const _ohlcTimes = DATA.ohlc.map(b => ({ time: b.time, value: 0 }));
for (let i = 1; i < charts.length; i++) {
    const _a = charts[i].addLineSeries({ visible: false, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false });
    _a.setData(_ohlcTimes);
}
syncCharts(charts);
function syncScaleWidths() {
    let maxW = 0;
    charts.forEach(c => { const w = c.priceScale('right').width(); if (w > maxW) maxW = w; });
    if (maxW > 0) charts.forEach(c => c.applyOptions({ rightPriceScale: { minimumWidth: maxW } }));
}
if (DATA.ohlc.length > __DEFAULT_BARS__) {
    const from = DATA.ohlc[DATA.ohlc.length - __DEFAULT_BARS__].time;
    const to   = DATA.ohlc[DATA.ohlc.length - 1].time;
    const applyRange = () => { charts.forEach(c => c.timeScale().setVisibleRange({ from, to })); requestAnimationFrame(() => requestAnimationFrame(syncScaleWidths)); };
    if (panes[0].clientWidth > 0) {
        applyRange();
    } else {
        const obs = new ResizeObserver(() => {
            if (panes[0].clientWidth > 0) { obs.disconnect(); requestAnimationFrame(() => requestAnimationFrame(applyRange)); }
        });
        obs.observe(panes[0]);
    }
} else {
    requestAnimationFrame(() => requestAnimationFrame(syncScaleWidths));
}
})();
</script>
</body>
</html>"""

# Public API
def make_chart_html(
    ticker: str,
    df: pd.DataFrame,
    interval: str,
    chart_type: str,
) -> str:
    intraday = interval == "3h"

    price_17 = price_42 = None
    if chart_type == "keltner":
        c = df["Close"].dropna()
        if len(c) >= 17:
            price_17 = float(c.iloc[-17])
        if len(c) >= 42:
            price_42 = float(c.iloc[-42])

    ohlc, vol = _ohlcv(df, intraday)

    data: dict = {
        "ohlc": ohlc, "vol": vol,
        "vol_ma": _line(df, "VOL_MA", intraday),
        "price_17": price_17, "price_42": price_42,
    }

    if chart_type != "keltner":
        for p in MA_PERIODS:
            data[f"ema{p}"] = _line(df, f"EMA_{p}", intraday)
            data[f"sma{p}"] = _line(df, f"SMA_{p}", intraday)
        data["bull_sma"] = _line(df, "BULL_SMA", intraday)
        data["bull_ema"] = _line(df, "BULL_EMA", intraday)
    else:
        data["kc_upper"] = _line(df, "KC_UPPER", intraday)
        data["kc_lower"] = _line(df, "KC_LOWER", intraday)
        data["kc_basis"] = _line(df, "KC_BASIS", intraday)
        data["nw_upper"] = _line(df, "NW_UPPER", intraday)
        data["nw_lower"] = _line(df, "NW_LOWER", intraday)
        data["cnv_tb"]   = _cnv_histogram(df, intraday)

    if chart_type == "score":
        score_series = Sig.score_history(df, n=len(df)).reindex(df.index)
        data["score"]       = _score_histogram(df, intraday)
        data["divergences"] = _divergences(df, score_series, intraday, min_price_pct=0.3, min_ind_delta=3.0)
    elif chart_type == "rsi":
        data["rsi"]         = _line(df, "RSI", intraday)
        data["rsi_ma"]      = _line(df, "RSI_MA", intraday)
        data["divergences"] = _divergences(df, "RSI", intraday, min_price_pct=0.3, min_ind_delta=2.0)
    elif chart_type == "stoch":
        data["slow_k"] = _line(df, f"SRSI_{STOCHRSI_CONFIGS[0]['label']}_K", intraday)
        data["slow_d"] = _line(df, f"SRSI_{STOCHRSI_CONFIGS[0]['label']}_D", intraday)
        data["fast_k"] = _line(df, f"SRSI_{STOCHRSI_CONFIGS[1]['label']}_K", intraday)
        data["fast_d"] = _line(df, f"SRSI_{STOCHRSI_CONFIGS[1]['label']}_D", intraday)
    elif chart_type == "obv":
        data["obv"]         = _line(df, "OBV", intraday)
        data["obv_ma"]      = _line(df, "OBV_MA", intraday)
        obv = df["OBV"].dropna()
        obv_min_delta = max((obv.max() - obv.min()) * 0.01, 1.0) if not obv.empty else 1.0
        data["divergences"] = _divergences(df, "OBV", intraday, min_price_pct=0.3, min_ind_delta=obv_min_delta)

    price_overlay = _KC_NW_OVERLAYS_JS if chart_type == "keltner" else _MA_OVERLAYS_JS
    title = f"{ticker} · {interval.upper()}"

    default_bars = {"3h": 120, "1d": 252, "3d": 104, "1wk": 104}.get(interval, 252)

    init_js = "\n".join([
        "const DATA = " + json.dumps(data, separators=(",", ":")) + ";",
        _col_js(),
        "const TITLE = " + json.dumps(title) + ";",
        _SHARED_JS,
        _PRICE_PANE_BASE_JS,
        price_overlay,
        _IND_JS[chart_type],
    ])

    return (
        _HTML_TEMPLATE
        .replace("__PANE_DIVS__", _PANE_DIVS[chart_type])
        .replace("__LWC_JS__", _LWC_JS)
        .replace("__INIT_JS__", init_js)
        .replace("__DEFAULT_BARS__", str(default_bars))
    )
