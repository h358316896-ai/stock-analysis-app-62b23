const express = require('express')
const cors = require('cors')
const yf = require('yahoo-finance2').default

const app = express()
app.use(cors())

app.get('/quote', async (req, res) => {
  const symbol = req.query.symbol
  const market = req.query.market || 'cn'
  if (!symbol) return res.status(400).json({ error: 'missing symbol' })
  let ticker = symbol
  if (market === 'hk') ticker = `${symbol}.HK`

  try {
    const q = await yf.quote(ticker)
    if (!q) return res.status(404).json({ error: 'no data' })
    const price = q.regularMarketPrice || (q.price && q.price.regularMarketPrice)
    const prev = q.regularMarketPreviousClose || (q.price && q.price.regularMarketPreviousClose)
    const changePercent = prev ? Number(((price - prev) / prev * 100).toFixed(2)) : 0
    return res.json({ symbol, ticker, price, change_percent: changePercent })
  } catch (e) {
    return res.status(500).json({ error: String(e) })
  }
})

app.get('/history', async (req, res) => {
  const symbol = req.query.symbol
  const market = req.query.market || 'cn'
  const period = req.query.period || '60d'
  const interval = req.query.interval || '1d'
  if (!symbol) return res.status(400).json({ error: 'missing symbol' })
  let ticker = symbol
  if (market === 'hk') ticker = `${symbol}.HK`

  try {
    const opts = { period, interval }
    const hist = await yf.historical(ticker, opts)
    if (!hist || hist.length === 0) return res.status(404).json({ error: 'no data' })
    const records = hist.map(r => ({
      t: new Date(r.date).getTime(),
      o: Number(r.open.toFixed(2)),
      h: Number(r.high.toFixed(2)),
      l: Number(r.low.toFixed(2)),
      c: Number(r.close.toFixed(2)),
      v: r.volume || 0
    }))
    return res.json({ symbol, ticker, records })
  } catch (e) {
    return res.status(500).json({ error: String(e) })
  }
})

const port = process.env.PORT || 5000
app.listen(port, () => console.log(`Node proxy listening on http://localhost:${port}`))
