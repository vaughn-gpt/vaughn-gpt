# VaughnGPT — Independent Edition

De'Erique's own GPT-style website. Runs **completely outside Muse** and uses
**zero Muse tokens**. The AI brain is whatever model provider *you* plug in,
billed to *your* account. Live market data and the quant engine need no key at all.

## What it does
- ChatGPT-style chat that can help with anything (once your model key is set)
- **Live market tape**: SPY, QQQ, IWM, AAPL, NVDA, MSFT, TSLA, AMZN + BTC
  (Yahoo Finance for stocks, CoinGecko for crypto — both free, no key)
- **Quant panel / quant engine** (pure Python, from ~1y of real daily prices):
  returns 1M/3M/6M/1Y, annualized volatility, RSI(14), SMA50/SMA200, MACD,
  max drawdown, Sharpe (rf=0), beta vs SPY
- Chat is market-aware: name a ticker and VaughnGPT fetches its live quant
  numbers first and gives them to the model, so answers use real figures
- **Demo mode** (no key): market/quant questions are answered directly from
  live data; general chat explains that a key is needed

## The ONLY accounts/keys you need to go fully live
1. **A hosting account** — e.g. Render (free tier works). This is where the site lives.
2. **A model provider API key** — e.g. OpenAI. Any OpenAI-compatible provider
   works (OpenAI, Together, Groq, Meta Model API gateways that expose an
   OpenAI-compatible endpoint, or a local Ollama with no key/billing).
   Your key is set as a server environment variable — **never** paste it in
   chat, in the web page, or in this repo.

Environment variables (see `.env.example`):
| Var | Required | Default |
|---|---|---|
| `LLM_API_KEY` | For full AI chat | *(demo mode if unset)* |
| `LLM_BASE_URL` | No | `https://api.openai.com/v1` |
| `LLM_MODEL` | No | `gpt-4o-mini` (change to your provider's model) |
| `PORT` | No | `8000` (hosts usually set this automatically) |

## (a) Run locally
```bash
cd vaughn-gpt-independent
python3 server.py                      # demo mode, no key needed
# or with your key:
LLM_API_KEY=your-key LLM_MODEL=your-model python3 server.py
```
Open http://localhost:8000 — no installs, Python 3 standard library only.

## (b) Deploy to Render (free)
1. Create a free account at render.com and a GitHub account if you don't have one.
2. Push this folder to a new **private** GitHub repo (do NOT commit any real key).
3. In Render: **New → Web Service → connect the repo**. Render reads
   `render.yaml` / the `Dockerfile` automatically. Plan: **Free**.
4. In the service's **Environment** tab, set `LLM_API_KEY` to your provider key
   (and `LLM_MODEL` / `LLM_BASE_URL` if your provider differs from OpenAI).
5. Click **Create Web Service**. Render builds the Docker image and gives you a
   public `https://vaughngpt-….onrender.com` URL. Done — usage is billed by
   your model provider, not Muse.

## (c) Deploy with Docker anywhere (VPS, Fly.io, a home server…)
```bash
docker build -t vaughngpt .
docker run -p 8000:8000 -e LLM_API_KEY=your-key -e LLM_MODEL=your-model vaughngpt
```
Open http://localhost:8000 (or your server's address).

## API
- `GET /api/market` — live watchlist quotes
- `GET /api/quant/NVDA` — full quant breakdown for any ticker (BTC/ETH/SOL too)
- `POST /api/chat` — body `{"messages":[{"role":"user","content":"…"}]}`
- `GET /api/health` — mode (demo/live), model, base URL

## Honest limits
- Free Render services sleep when idle; the first visit after sleep is slow.
- Yahoo/CoinGecko free endpoints can rate-limit; numbers are educational,
  not financial advice. Trading decisions and sizing stay with you.
