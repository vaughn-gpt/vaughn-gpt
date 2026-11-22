#!/usr/bin/env python3
"""
VaughnGPT — Independent Edition
Standalone, deployable anywhere. Python standard library ONLY — no pip installs.
Uses ZERO Muse tokens. The AI model is called via YOUR OWN API key, set on the
server as environment variables (never in chat, never in the browser).

Env vars:
  LLM_API_KEY   your model provider key (optional — without it, DEMO MODE)
  LLM_BASE_URL  default https://api.openai.com/v1  (any OpenAI-compatible endpoint)
  LLM_MODEL     default gpt-4o-mini  (change to whatever your provider offers)
  PORT          default 8000

Run:  python3 server.py
"""
import json, os, re, math, statistics, urllib.request, urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from datetime import datetime, timezone

PORT = int(os.environ.get("PORT", "8000"))
LLM_API_KEY = os.environ.get("LLM_API_KEY", "").strip()
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/")
LLM_MODEL = os.environ.get("LLM_MODEL", "gpt-4o-mini").strip()

WATCHLIST = ["SPY", "QQQ", "IWM", "AAPL", "NVDA", "MSFT", "TSLA", "AMZN"]
CRYPTO = {"BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana"}
UA = {"User-Agent": "Mozilla/5.0 (VaughnGPT)"}

# ---------- HTTP helpers ----------
def fetch_json(url, headers=None, timeout=15):
    req = urllib.request.Request(url, headers={**UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))

def post_json(url, payload, headers=None, timeout=60):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST",
        headers={"Content-Type": "application/json", **UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))

# ---------- Market data (no key needed) ----------
def yahoo_history(symbol, range_="1y", interval="1d"):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range={range_}&interval={interval}"
    d = fetch_json(url)
    res = (d.get("chart", {}).get("result") or [None])[0]
    if not res:
        raise ValueError(f"No data for {symbol}")
    meta = res.get("meta", {})
    closes_raw = ((res.get("indicators", {}).get("quote") or [{}])[0].get("close") or [])
    closes = [float(c) for c in closes_raw if c is not None]
    return meta, closes

def yahoo_quote(symbol):
    meta, closes = yahoo_history(symbol, range_="5d")
    price = meta.get("regularMarketPrice") or (closes[-1] if closes else None)
    prev = closes[-2] if len(closes) > 1 else meta.get("chartPreviousClose")
    change_pct = ((price - prev) / prev * 100) if price and prev else None
    return {"symbol": symbol, "price": round(price, 2) if price else None,
            "change_pct": round(change_pct, 2) if change_pct is not None else None,
            "day_high": meta.get("regularMarketDayHigh"), "day_low": meta.get("regularMarketDayLow"),
            "volume": meta.get("regularMarketVolume"), "name": meta.get("longName") or symbol,
            "source": "Yahoo Finance"}

def crypto_quotes():
    ids = ",".join(CRYPTO.values())
    d = fetch_json(f"https://api.coingecko.com/api/v3/simple/price?ids={ids}&vs_currencies=usd&include_24hr_change=true")
    out = {}
    for sym, cid in CRYPTO.items():
        row = d.get(cid, {})
        if row.get("usd"):
            out[sym] = {"symbol": sym, "price": row["usd"],
                        "change_pct": round(row.get("usd_24h_change", 0), 2),
                        "name": cid.capitalize(), "source": "CoinGecko"}
    return out

def market_overview():
    quotes = []
    for s in WATCHLIST:
        try: quotes.append(yahoo_quote(s))
        except Exception as e: quotes.append({"symbol": s, "error": str(e)})
    try:
        btc = crypto_quotes().get("BTC")
        if btc: quotes.append(btc)
    except Exception as e:
        quotes.append({"symbol": "BTC", "error": str(e)})
    return {"as_of": datetime.now(timezone.utc).isoformat(), "quotes": quotes}

# ---------- Quant engine (pure Python) ----------
def ema(vals, period):
    if len(vals) < period: return None
    k = 2 / (period + 1); e = sum(vals[:period]) / period
    for v in vals[period:]: e = v * k + e * (1 - k)
    return e

def rsi(closes, period=14):
    if len(closes) <= period: return None
    gains, losses = [], []
    for i in range(1, len(closes)):
        d = closes[i] - closes[i-1]; gains.append(max(d, 0)); losses.append(max(-d, 0))
    ag = sum(gains[-period:]) / period; al = sum(losses[-period:]) / period
    if al == 0: return 100.0
    return round(100 - 100 / (1 + ag / al), 1)

def macd(closes):
    if len(closes) < 35: return None
    # full EMA series for MACD line + signal
    def ema_series(vals, p):
        k = 2/(p+1); out=[vals[0]]
        for v in vals[1:]: out.append(v*k + out[-1]*(1-k))
        return out
    e12, e26 = ema_series(closes,12), ema_series(closes,26)
    line = [a-b for a,b in zip(e12,e26)]
    sig = ema_series(line,9)
    return {"macd": round(line[-1],3), "signal": round(sig[-1],3), "histogram": round(line[-1]-sig[-1],3)}

def quant(symbol):
    symbol = symbol.upper()
    if symbol in CRYPTO:
        meta, closes = yahoo_history(f"{symbol}-USD")
        name = CRYPTO[symbol].capitalize()
    else:
        meta, closes = yahoo_history(symbol)
        name = meta.get("longName") or symbol
    if len(closes) < 30: raise ValueError("Not enough history")
    price = closes[-1]
    def ret(days):
        if len(closes) <= days: return None
        return round((price/closes[-days-1]-1)*100, 2)
    daily = [(closes[i]/closes[i-1]-1) for i in range(1,len(closes))]
    vol = round(statistics.pstdev(daily)*math.sqrt(252)*100,1) if len(daily)>2 else None
    mean_d = statistics.mean(daily)
    sharpe = round((mean_d/statistics.pstdev(daily))*math.sqrt(252),2) if statistics.pstdev(daily)>0 else None
    peak, mdd = closes[0], 0.0
    for c in closes:
        peak = max(peak,c); mdd = min(mdd, c/peak-1)
    sma50 = round(sum(closes[-50:])/50,2) if len(closes)>=50 else None
    sma200 = round(sum(closes[-200:])/200,2) if len(closes)>=200 else None
    beta = None
    if symbol not in CRYPTO and symbol != "SPY":
        try:
            _, spy = yahoo_history("SPY")
            n = min(len(closes), len(spy))
            a = [(closes[-n+i]/closes[-n+i-1]-1) for i in range(1,n)]
            b = [(spy[-n+i]/spy[-n+i-1]-1) for i in range(1,n)]
            if statistics.pvariance(b)>0:
                beta = round(statistics.covariance(a,b)/statistics.variance(b),2)
        except Exception: pass
    return {"symbol": symbol, "name": name, "price": round(price,2),
        "as_of": datetime.now(timezone.utc).isoformat(), "source": "Yahoo Finance (1y daily)",
        "returns_pct": {"1M": ret(21), "3M": ret(63), "6M": ret(126), "1Y": ret(len(closes)-1)},
        "annualized_volatility_pct": vol, "rsi_14": rsi(closes),
        "sma_50": sma50, "sma_200": sma200, "vs_sma50": ("above" if sma50 and price>sma50 else "below") if sma50 else None,
        "vs_sma200": ("above" if sma200 and price>sma200 else "below") if sma200 else None,
        "macd": macd(closes), "max_drawdown_pct": round(mdd*100,1),
        "sharpe_rf0": sharpe, "beta_vs_spy": beta,
        "week52_high": round(max(closes),2), "week52_low": round(min(closes),2)}

def format_quant(q):
    r, m = q["returns_pct"], q["macd"] or {}
    lines = [f"**{q['symbol']} — {q['name']}**  ${q['price']}  _(live, {q['source']}, {q['as_of'][:19]}Z)_",
      f"- Returns: 1M {r['1M']}% · 3M {r['3M']}% · 6M {r['6M']}% · 1Y {r['1Y']}%%",
      f"- Volatility (annualized): {q['annualized_volatility_pct']}% · Sharpe (rf=0): {q['sharpe_rf0']} · Beta vs SPY: {q['beta_vs_spy']}",
      f"- RSI(14): {q['rsi_14']} · MACD {m.get('macd')} / signal {m.get('signal')} / hist {m.get('histogram')}",
      f"- Trend: SMA50 ${q['sma_50']} (price {q['vs_sma50']}) · SMA200 ${q['sma_200']} (price {q['vs_sma200']})",
      f"- Max drawdown (1Y): {q['max_drawdown_pct']}% · 52-week range ${q['week52_low']} – ${q['week52_high']}",
      "_Quant read: " + ("overbought momentum — careful chasing. " if (q['rsi_14'] or 50)>=70 else "oversold — watch for a base. " if (q['rsi_14'] or 50)<=30 else "momentum is neutral. ") +
       ("Uptrend intact above the 200-day. " if q['vs_sma200']=="above" else "Below the 200-day — long-term trend is not confirmed. ") +
       "Numbers only, not financial advice; sizing and the final call are yours._"]
    return "\n".join(lines)

# ---------- Chat ----------
TICKER_RE = re.compile(r"\b(SPY|QQQ|IWM|AAPL|NVDA|MSFT|TSLA|AMZN|BTC|ETH|SOL|AMD|PLTR|HOOD|MSTR|COIN)\b")
SYSTEM = ("You are VaughnGPT, a general-purpose AI assistant owned by De'Erique. You can help with anything: "
  "writing, code, math, planning, business, and markets. For market questions, think quantitatively: use the "
  "live data provided in context, show the numbers, state risk plainly, and never promise returns or give a "
  "guaranteed buy/sell call — decisions stay with the user.")

def handle_chat(messages):
    user_text = " ".join(m.get("content","") for m in messages if m.get("role")=="user")
    tickers = list(dict.fromkeys(TICKER_RE.findall(user_text.upper())))
    quants, errors = [], []
    for t in tickers[:3]:
        try: quants.append(quant(t))
        except Exception as e: errors.append(f"{t}: {e}")
    if not LLM_API_KEY:
        if quants:
            body = "\n\n".join(format_quant(q) for q in quants)
            return {"mode": "demo", "reply": body + "\n\n— *Demo mode: this answer was computed live from market data by VaughnGPT's own quant engine. Add your model API key on the server (LLM_API_KEY) to unlock full general AI chat.*"}
        return {"mode": "demo", "reply": "**Demo mode is on.** I can already do live market & quant work — try *\"Analyze NVDA quantitatively\"* or *\"Compare SPY and QQQ\"* (name a ticker). For general do-anything AI chat, the owner needs to set `LLM_API_KEY` on the server (see Settings / README). No key ever goes in this chat."}
    context = ""
    if quants:
        context = "\n\nLIVE QUANT DATA (computed just now, use these exact numbers):\n" + json.dumps(quants, indent=1)
    payload = {"model": LLM_MODEL, "messages": [{"role":"system","content": SYSTEM+context}] + messages}
    try:
        d = post_json(f"{LLM_BASE_URL}/chat/completions", payload, headers={"Authorization": f"Bearer {LLM_API_KEY}"})
        reply = d["choices"][0]["message"]["content"]
        return {"mode": "live", "model": LLM_MODEL, "reply": reply, "quant_used": [q["symbol"] for q in quants]}
    except Exception as e:
        return {"mode": "error", "reply": f"Model call failed: {e}. Check LLM_API_KEY / LLM_BASE_URL / LLM_MODEL on the server."}

# ---------- Server ----------
HERE = os.path.dirname(os.path.abspath(__file__))
class H(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json"):
        data = body.encode() if isinstance(body,str) else json.dumps(body).encode()
        self.send_response(code); self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)
    def do_GET(self):
        try:
            if self.path in ("/", "/index.html"):
                with open(os.path.join(HERE,"index.html"), encoding="utf-8") as f: self._send(200, f.read(), "text/html; charset=utf-8")
            elif self.path == "/api/health":
                self._send(200, {"ok": True, "mode": "live" if LLM_API_KEY else "demo", "model": LLM_MODEL, "base_url": LLM_BASE_URL})
            elif self.path == "/api/market":
                self._send(200, market_overview())
            elif self.path.startswith("/api/quant/"):
                self._send(200, quant(self.path.split("/")[-1]))
            else: self._send(404, {"error":"not found"})
        except Exception as e: self._send(500, {"error": str(e)})
    def do_POST(self):
        try:
            if self.path == "/api/chat":
                length = int(self.headers.get("Content-Length",0))
                body = json.loads(self.rfile.read(length) or b"{}")
                self._send(200, handle_chat(body.get("messages",[])))
            else: self._send(404, {"error":"not found"})
        except Exception as e: self._send(500, {"error": str(e)})
    def log_message(self, *a): pass

if __name__ == "__main__":
    print(f"VaughnGPT Independent on http://localhost:{PORT}  mode={'LIVE ('+LLM_MODEL+')' if LLM_API_KEY else 'DEMO (no LLM_API_KEY)'}")
    ThreadingHTTPServer(("0.0.0.0", PORT), H).serve_forever()
