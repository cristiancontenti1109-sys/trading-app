import { useState, useEffect, useCallback, useRef } from 'react'
import axios from 'axios'
import { createChart, CandlestickSeries, createSeriesMarkers } from 'lightweight-charts'
import './App.css'

const api = axios.create({ baseURL: 'http://localhost:8000' })
api.interceptors.request.use((c) => {
  const t = localStorage.getItem('token')
  if (t) c.headers.Authorization = `Bearer ${t}`
  return c
})

type Rec = 'BUY' | 'SELL' | 'HOLD'
interface Signal {
  symbol: string; timeframe: string; recommendation: Rec; confidence: number
  entry_zone: { low: number; high: number }; target_price: number; stop_loss: number
  reasoning: string[]; is_hot: boolean; is_hot_confluence: boolean
  indicators?: { rsi: number; macd: number; adx: number; vol_zscore: number; bb_pct_b: number }
}
interface Candle { time: number; open: number; high: number; low: number; close: number; volume: number }
interface WatchItem { symbol: string; name: string; asset_class: string }
interface Trade {
  id: string; symbol: string; direction: 'BUY' | 'SELL'
  entry_price: number; exit_price: number | null; size: number
  status: 'open' | 'closed'; notes: string | null
  pnl: number | null; pnl_pct: number | null
  opened_at: string; closed_at: string | null
}
interface TradeStats { total: number; wins: number; losses: number; win_rate: number; total_pnl: number; avg_pnl: number }
interface SignalHistItem { recommendation: Rec; confidence: number; created_at: string }
interface NewsItem { title: string; publisher: string; url: string; time: number }

const REC_COLOR: Record<Rec, string> = { BUY: '#00C896', SELL: '#FF4560', HOLD: '#F7931A' }
const ASSET_COLOR: Record<string, string> = { crypto: '#F7931A', stocks: '#58A6FF', forex: '#3FB950', commodities: '#D2A679' }
const TFS = ['15m', '1h', '4h', '1D', '1W']

function playHotAlert() {
  try {
    const AudioCtx = window.AudioContext || (window as any).webkitAudioContext
    const ctx = new AudioCtx() as AudioContext
    const play = (freq: number, t0: number, dur: number) => {
      const osc = ctx.createOscillator(); const gain = ctx.createGain()
      osc.connect(gain); gain.connect(ctx.destination)
      osc.type = 'sine'; osc.frequency.value = freq
      gain.gain.setValueAtTime(0.25, ctx.currentTime + t0)
      gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + t0 + dur)
      osc.start(ctx.currentTime + t0); osc.stop(ctx.currentTime + t0 + dur + 0.05)
    }
    play(880, 0, 0.25); play(1100, 0.3, 0.25); play(1320, 0.6, 0.35)
  } catch {}
}

const fmt = (n: number | null | undefined): string => {
  if (n == null) return '—'
  const abs = Math.abs(n)
  if (abs >= 1000) return n.toLocaleString('en-US', { maximumFractionDigits: 2 })
  if (abs >= 1) return n.toFixed(4)
  if (abs >= 0.001) return n.toFixed(6)
  return n.toFixed(8)
}

function timeAgo(unix: number): string {
  if (!unix) return ''
  const diff = Math.floor((Date.now() / 1000) - unix)
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`
  return `${Math.floor(diff / 86400)}d ago`
}

function snapToCandle(sigTime: number, times: number[]): number {
  if (!times.length) return sigTime
  return times.reduce((best, t) => Math.abs(t - sigTime) < Math.abs(best - sigTime) ? t : best)
}

function buildNarrative(signal: Signal, symbol: string): string[] {
  const { recommendation: rec, confidence, indicators: ind, reasoning, entry_zone, target_price, stop_loss, timeframe } = signal
  const pct = Math.round(confidence * 100)
  const bias = rec === 'BUY' ? 'bullish' : rec === 'SELL' ? 'bearish' : 'neutral'
  const strength = pct > 75 ? 'strong' : pct > 60 ? 'moderate' : 'developing'
  const paras: string[] = []

  paras.push(
    `The ${timeframe} analysis of ${symbol} shows a ${strength} ${bias} setup with ${pct}% model confidence. ` +
    (rec === 'BUY'
      ? `Price structure supports a long entry in the zone ${fmt(entry_zone.low)}–${fmt(entry_zone.high)}, targeting ${fmt(target_price)} with risk defined at ${fmt(stop_loss)}.`
      : rec === 'SELL'
      ? `Price structure favours a short entry in the zone ${fmt(entry_zone.low)}–${fmt(entry_zone.high)}, targeting ${fmt(target_price)} with stop at ${fmt(stop_loss)}.`
      : `No clear directional edge is present — the model recommends staying flat until a cleaner setup appears.`)
  )

  if (ind) {
    const parts: string[] = []
    if (ind.rsi >= 80) parts.push(`RSI at ${ind.rsi.toFixed(0)} is overbought — upside momentum is stretched and a pullback is possible`)
    else if (ind.rsi >= 60) parts.push(`RSI at ${ind.rsi.toFixed(0)} sits in the bullish zone, confirming that buyers remain in control`)
    else if (ind.rsi <= 20) parts.push(`RSI at ${ind.rsi.toFixed(0)} is deeply oversold, suggesting a potential mean-reversion bounce`)
    else if (ind.rsi <= 40) parts.push(`RSI at ${ind.rsi.toFixed(0)} reflects sustained selling pressure`)
    else parts.push(`RSI at ${ind.rsi.toFixed(0)} is neutral — no momentum extreme`)

    if (ind.adx >= 30) parts.push(`ADX at ${ind.adx.toFixed(0)} confirms a strong, well-established trend`)
    else if (ind.adx >= 20) parts.push(`ADX at ${ind.adx.toFixed(0)} shows the trend is gaining traction but still developing`)
    else parts.push(`ADX at ${ind.adx.toFixed(0)} indicates a weak or ranging market — breakout not yet confirmed`)

    if (ind.bb_pct_b > 0.85) parts.push(`price is pressing against the upper Bollinger Band (%B ${ind.bb_pct_b.toFixed(2)}), signalling overextension`)
    else if (ind.bb_pct_b < 0.15) parts.push(`price is hugging the lower Bollinger Band (%B ${ind.bb_pct_b.toFixed(2)}), a historically oversold zone`)

    if (ind.vol_zscore > 2) parts.push(`volume is surging ${ind.vol_zscore.toFixed(1)}σ above its 20-period average, giving the move strong institutional conviction`)
    else if (ind.vol_zscore > 1) parts.push(`volume is moderately elevated (${ind.vol_zscore.toFixed(1)}σ), providing some confidence in the direction`)
    else parts.push(`volume is below average — this move lacks broad participation and could fade`)

    if (parts.length) paras.push(parts.join('. ') + '.')
  }

  if (reasoning.length) {
    paras.push(`Key technical confluences: ${reasoning.join('; ')}.`)
  }

  return paras
}

export default function App() {
  const [token, setToken] = useState(localStorage.getItem('token'))
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [authMode, setAuthMode] = useState<'login' | 'register'>('login')
  const [authError, setAuthError] = useState('')

  const [watchlist, setWatchlist] = useState<WatchItem[]>([])
  const [livePrices, setLivePrices] = useState<Record<string, number>>({})
  const [selected, setSelected] = useState<string | null>(null)
  const [tf, setTf] = useState('4h')
  const [signal, setSignal] = useState<Signal | null>(null)
  const [candles, setCandles] = useState<Candle[]>([])
  const [signalHistory, setSignalHistory] = useState<SignalHistItem[]>([])
  const [news, setNews] = useState<NewsItem[]>([])
  const [loading, setLoading] = useState(false)
  const [search, setSearch] = useState('')
  const [searchResults, setSearchResults] = useState<WatchItem[]>([])
  const [sideTab, setSideTab] = useState<'watchlist' | 'search'>('watchlist')

  const [mainView, setMainView] = useState<'signals' | 'journal'>('signals')
  const [trades, setTrades] = useState<Trade[]>([])
  const [tradeStats, setTradeStats] = useState<TradeStats | null>(null)
  const [journalSub, setJournalSub] = useState<'open' | 'closed' | 'new'>('open')
  const [newTrade, setNewTrade] = useState({ symbol: '', direction: 'BUY', entry_price: '', size: '1', notes: '' })
  const [closeForm, setCloseForm] = useState<{ id: string; exit_price: string } | null>(null)

  const chartRef = useRef<HTMLDivElement>(null)
  const chartInstance = useRef<ReturnType<typeof createChart> | null>(null)

  // ---- loaders ----
  const loadWatchlist = useCallback(async () => {
    try { setWatchlist((await api.get('/watchlist/')).data) } catch {}
  }, [])

  const loadTrades = useCallback(async () => {
    try {
      const [t, s] = await Promise.all([api.get('/trades/'), api.get('/trades/stats')])
      setTrades(t.data); setTradeStats(s.data)
    } catch {}
  }, [])

  useEffect(() => { if (token) { loadWatchlist(); loadTrades() } }, [token, loadWatchlist, loadTrades])

  // ---- live price polling ----
  useEffect(() => {
    if (!token || watchlist.length === 0) return
    const poll = async () => {
      const updates: Record<string, number> = {}
      await Promise.allSettled(watchlist.map(async (item) => {
        try {
          const { data } = await api.get(`/instruments/${item.symbol}/price`)
          updates[item.symbol] = data.price
        } catch {}
      }))
      if (Object.keys(updates).length) setLivePrices(prev => ({ ...prev, ...updates }))
    }
    poll()
    const id = setInterval(poll, 30000)
    return () => clearInterval(id)
  }, [token, watchlist])

  // ---- search ----
  useEffect(() => {
    if (!search.trim()) { setSearchResults([]); return }
    const id = setTimeout(async () => {
      try { setSearchResults((await api.get('/watchlist/search', { params: { q: search } })).data) } catch {}
    }, 300)
    return () => clearTimeout(id)
  }, [search])

  // ---- signal + OHLCV + history + news ----
  useEffect(() => {
    if (!selected || !token) return
    setLoading(true); setSignal(null); setCandles([]); setSignalHistory([]); setNews([])
    Promise.all([
      api.get(`/signals/${selected}`, { params: { timeframe: tf } }),
      api.get(`/signals/${selected}/ohlcv`, { params: { timeframe: tf, limit: 150 } }),
      api.get(`/signals/${selected}/history`, { params: { timeframe: tf, limit: 50 } }).catch(() => ({ data: [] })),
      api.get(`/signals/${selected}/news`).catch(() => ({ data: { news: [] } })),
    ]).then(([s, o, h, n]) => {
      setSignal(s.data)
      setCandles(o.data.candles)
      setSignalHistory(h.data)
      setNews(n.data.news ?? [])
      if (s.data.is_hot) playHotAlert()
    }).catch(() => {}).finally(() => setLoading(false))
  }, [selected, tf, token])

  // ---- candlestick chart + markers ----
  useEffect(() => {
    if (!chartRef.current || candles.length === 0) return

    if (chartInstance.current) { chartInstance.current.remove(); chartInstance.current = null }

    const chart = createChart(chartRef.current, {
      width: chartRef.current.clientWidth,
      height: 300,
      layout: { background: { color: '#161B22' }, textColor: '#8B949E' },
      grid: { vertLines: { color: '#21262D' }, horzLines: { color: '#21262D' } },
      timeScale: { borderColor: '#30363D', timeVisible: true },
      rightPriceScale: { borderColor: '#30363D' },
    })

    const series = chart.addSeries(CandlestickSeries, {
      upColor: '#00C896', downColor: '#FF4560',
      borderVisible: false,
      wickUpColor: '#00C896', wickDownColor: '#FF4560',
    })

    series.setData(candles.map(c => ({
      time: c.time as any, open: c.open, high: c.high, low: c.low, close: c.close,
    })))

    // Build buy/sell markers from signal history
    const candleTimes = candles.map(c => c.time)
    const seen = new Set<number>()
    const markers: any[] = []

    // Collect history markers (oldest first so they render in order)
    const sorted = [...signalHistory].reverse()
    for (const h of sorted) {
      if (h.recommendation === 'HOLD') continue
      const sigTime = Math.floor(new Date(h.created_at).getTime() / 1000)
      const snapped = snapToCandle(sigTime, candleTimes)
      // Deduplicate: keep latest if two signals snap to same candle
      seen.has(snapped) ? null : seen.add(snapped)
      markers.push({
        time: snapped as any,
        position: h.recommendation === 'BUY' ? 'belowBar' : 'aboveBar',
        color: h.recommendation === 'BUY' ? '#00C896' : '#FF4560',
        shape: h.recommendation === 'BUY' ? 'arrowUp' : 'arrowDown',
        text: `${h.recommendation} ${Math.round(h.confidence * 100)}%`,
        size: 1,
      })
    }

    // Deduplicate by snapped time (keep last per time)
    const dedupedMap = new Map<number, any>()
    for (const m of markers) dedupedMap.set(m.time, m)
    createSeriesMarkers(series, [...dedupedMap.values()].sort((a, b) => a.time - b.time))

    chart.timeScale().fitContent()
    chartInstance.current = chart

    const ro = new ResizeObserver(() => {
      if (chartRef.current && chartInstance.current)
        chartInstance.current.applyOptions({ width: chartRef.current.clientWidth })
    })
    ro.observe(chartRef.current)

    return () => {
      ro.disconnect()
      if (chartInstance.current) { chartInstance.current.remove(); chartInstance.current = null }
    }
  }, [candles, signalHistory])

  // ---- auth ----
  const handleAuth = async () => {
    setAuthError('')
    try {
      if (authMode === 'login') {
        const form = new FormData()
        form.append('username', email); form.append('password', password)
        const { data } = await api.post('/auth/login', form)
        localStorage.setItem('token', data.access_token); setToken(data.access_token)
      } else {
        const { data } = await api.post('/auth/register', { email, password })
        localStorage.setItem('token', data.access_token); setToken(data.access_token)
      }
    } catch (e: any) { setAuthError(e.response?.data?.detail || 'Authentication failed') }
  }

  // ---- trade actions ----
  const createTrade = async () => {
    if (!newTrade.symbol || !newTrade.entry_price) return
    try {
      await api.post('/trades/', {
        symbol: newTrade.symbol.toUpperCase(),
        direction: newTrade.direction,
        entry_price: parseFloat(newTrade.entry_price),
        size: parseFloat(newTrade.size) || 1,
        notes: newTrade.notes || null,
      })
      setNewTrade({ symbol: '', direction: 'BUY', entry_price: '', size: '1', notes: '' })
      setJournalSub('open'); loadTrades()
    } catch {}
  }

  const closeTrade = async (id: string, exitPrice: string) => {
    const val = parseFloat(exitPrice); if (isNaN(val)) return
    try { await api.patch(`/trades/${id}/close`, { exit_price: val }); setCloseForm(null); loadTrades() } catch {}
  }

  const deleteTrade = async (id: string) => {
    try { await api.delete(`/trades/${id}`); loadTrades() } catch {}
  }

  // ---- login page ----
  if (!token) return (
    <div className="auth-page">
      <div className="auth-box">
        <div style={{ fontSize: 56, marginBottom: 8 }}>📈</div>
        <h1 style={{ margin: '0 0 4px', color: '#E6EDF3' }}>TradingSignals</h1>
        <p style={{ color: '#8B949E', marginBottom: 32 }}>AI-powered signals for every market</p>
        <input className="input" placeholder="Email" value={email} onChange={e => setEmail(e.target.value)} onKeyDown={e => e.key === 'Enter' && handleAuth()} />
        <input className="input" placeholder="Password" type="password" value={password} onChange={e => setPassword(e.target.value)} onKeyDown={e => e.key === 'Enter' && handleAuth()} />
        {authError && <div className="error-msg">{authError}</div>}
        <button className="btn-primary" onClick={handleAuth}>{authMode === 'login' ? 'Sign In' : 'Create Account'}</button>
        <button className="btn-link" onClick={() => setAuthMode(authMode === 'login' ? 'register' : 'login')}>
          {authMode === 'login' ? "Don't have an account? Sign up" : 'Already have an account? Sign in'}
        </button>
        <p style={{ color: '#484F58', fontSize: 11, marginTop: 24 }}>Not financial advice. For informational purposes only.</p>
      </div>
    </div>
  )

  const openTrades = trades.filter(t => t.status === 'open')
  const closedTrades = trades.filter(t => t.status === 'closed')

  return (
    <div className="layout">
      {/* ---- sidebar ---- */}
      <aside className="sidebar">
        <div className="sidebar-header">
          <span style={{ fontWeight: 700, color: '#E6EDF3' }}>📈 TradingSignals</span>
          <button className="btn-link" style={{ fontSize: 12 }} onClick={() => { localStorage.removeItem('token'); setToken(null) }}>Logout</button>
        </div>
        <div className="tab-row">
          <button className={`tab ${sideTab === 'watchlist' ? 'active' : ''}`} onClick={() => setSideTab('watchlist')}>Watchlist</button>
          <button className={`tab ${sideTab === 'search' ? 'active' : ''}`} onClick={() => setSideTab('search')}>+ Add</button>
        </div>

        {sideTab === 'search' ? (
          <div style={{ padding: '8px 12px' }}>
            <input className="input" style={{ marginBottom: 8 }} placeholder="BTC, AAPL, EUR..." value={search} onChange={e => setSearch(e.target.value)} autoFocus />
            {searchResults.map(r => (
              <div key={r.symbol} className="list-row" style={{ cursor: 'pointer' }} onClick={async () => {
                try { await api.post('/watchlist/', { symbol: r.symbol }); loadWatchlist(); setSideTab('watchlist') } catch {}
              }}>
                <span className="dot" style={{ background: ASSET_COLOR[r.asset_class] }} />
                <div style={{ flex: 1 }}><div className="sym">{r.symbol}</div><div className="label-sm">{r.name}</div></div>
                <span style={{ color: '#58A6FF', fontSize: 18 }}>+</span>
              </div>
            ))}
          </div>
        ) : (
          <div>
            {watchlist.length === 0 && <div className="empty-hint">Use + Add to build your watchlist</div>}
            {watchlist.map(item => (
              <div key={item.symbol} className={`list-row ${selected === item.symbol && mainView === 'signals' ? 'selected' : ''}`}
                onClick={() => { setSelected(item.symbol); setMainView('signals') }}>
                <span className="dot" style={{ background: ASSET_COLOR[item.asset_class] }} />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 4 }}>
                    <div className="sym">{item.symbol}</div>
                    {livePrices[item.symbol] != null && <div className="live-price">{fmt(livePrices[item.symbol])}</div>}
                  </div>
                  <div className="label-sm" style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{item.name}</div>
                </div>
                <button className="btn-remove" onClick={async e => { e.stopPropagation(); await api.delete(`/watchlist/${item.symbol}`); loadWatchlist() }}>×</button>
              </div>
            ))}
          </div>
        )}
      </aside>

      {/* ---- main ---- */}
      <main className="main">
        <div className="main-tabs">
          <button className={`main-tab ${mainView === 'signals' ? 'active' : ''}`} onClick={() => setMainView('signals')}>📊 Signals</button>
          <button className={`main-tab ${mainView === 'journal' ? 'active' : ''}`} onClick={() => { setMainView('journal'); loadTrades() }}>
            📓 Journal {openTrades.length > 0 && <span className="badge-count">{openTrades.length}</span>}
          </button>
        </div>

        {/* ===== SIGNALS ===== */}
        {mainView === 'signals' && (
          !selected ? (
            <div className="empty-state">
              <div style={{ fontSize: 64 }}>📊</div>
              <h2>Select an instrument</h2>
              <p>Pick something from your watchlist to see the AI signal</p>
            </div>
          ) : loading ? (
            <div className="empty-state"><div className="spinner" /><p style={{ color: '#8B949E', marginTop: 16 }}>Loading signal...</p></div>
          ) : (
            <div className="detail">
              <div className="detail-header">
                <div>
                  <h2 style={{ margin: 0, color: '#E6EDF3', display: 'flex', alignItems: 'baseline', gap: 12 }}>
                    {selected}
                    {livePrices[selected] != null && <span style={{ fontSize: 18, color: '#58A6FF', fontWeight: 400 }}>{fmt(livePrices[selected])}</span>}
                  </h2>
                  <span style={{ color: '#8B949E', fontSize: 14 }}>{watchlist.find(w => w.symbol === selected)?.name}</span>
                </div>
                <div className="tf-row">
                  {TFS.map(t => <button key={t} className={`tf ${tf === t ? 'active' : ''}`} onClick={() => setTf(t)}>{t}</button>)}
                </div>
              </div>

              {/* Chart */}
              <div className="chart-box">
                {candles.length === 0
                  ? <div style={{ height: 300, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#484F58' }}>No chart data</div>
                  : <div ref={chartRef} style={{ width: '100%' }} />
                }
                {signalHistory.length > 0 && (
                  <div className="chart-legend">
                    <span className="legend-item"><span className="legend-dot" style={{ background: '#00C896' }} /> BUY signal</span>
                    <span className="legend-item"><span className="legend-dot" style={{ background: '#FF4560' }} /> SELL signal</span>
                  </div>
                )}
              </div>

              {/* Signal card */}
              {signal && (
                <div className="signal-card">
                  <div className="signal-top">
                    <span className="rec-badge" style={{ color: REC_COLOR[signal.recommendation], border: `1px solid ${REC_COLOR[signal.recommendation]}60`, background: REC_COLOR[signal.recommendation] + '18' }}>
                      {signal.recommendation}
                    </span>
                    {signal.is_hot_confluence && <span className="badge-hot" style={{ background: '#FF456018', color: '#FF4560' }}>🔥 HOT-CONFLUENCE</span>}
                    {signal.is_hot && !signal.is_hot_confluence && <span className="badge-hot" style={{ background: '#F7931A18', color: '#F7931A' }}>⚡ HOT</span>}
                    <span style={{ marginLeft: 'auto', color: '#8B949E', fontSize: 13 }}>{signal.timeframe}</span>
                  </div>

                  <div className="conf-row">
                    <span style={{ color: '#8B949E', fontSize: 13, width: 90 }}>Confidence</span>
                    <div className="conf-bg"><div className="conf-fill" style={{ width: `${Math.round(signal.confidence * 100)}%`, background: REC_COLOR[signal.recommendation] }} /></div>
                    <span style={{ color: REC_COLOR[signal.recommendation], fontWeight: 700, fontSize: 14, width: 42, textAlign: 'right' }}>{Math.round(signal.confidence * 100)}%</span>
                  </div>

                  <div className="targets">
                    {([
                      ['Entry zone', `${signal.entry_zone.low.toFixed(4)} – ${signal.entry_zone.high.toFixed(4)}`, ''],
                      ['Target', signal.target_price.toFixed(4), '#00C896'],
                      ['Stop loss', signal.stop_loss.toFixed(4), '#FF4560'],
                    ] as [string, string, string][]).map(([label, val, col]) => (
                      <div key={label} className="target-item">
                        <div style={{ color: '#8B949E', fontSize: 12, marginBottom: 2 }}>{label}</div>
                        <div style={{ color: col || '#E6EDF3', fontWeight: 600, fontSize: 13 }}>{val}</div>
                      </div>
                    ))}
                  </div>

                  {signal.indicators && (
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 16 }}>
                      {([['RSI', signal.indicators.rsi?.toFixed(1)], ['ADX', signal.indicators.adx?.toFixed(1)], ['Vol Z', signal.indicators.vol_zscore?.toFixed(2)], ['%B', signal.indicators.bb_pct_b?.toFixed(2)]] as [string, string][]).map(([l, v]) => (
                        <div key={l} style={{ background: '#21262D', borderRadius: 6, padding: '4px 10px', display: 'flex', gap: 6, alignItems: 'center' }}>
                          <span style={{ color: '#8B949E', fontSize: 11 }}>{l}</span>
                          <span style={{ color: '#E6EDF3', fontSize: 11, fontWeight: 600 }}>{v}</span>
                        </div>
                      ))}
                    </div>
                  )}

                  <button className="btn-log-trade"
                    style={{ borderColor: REC_COLOR[signal.recommendation] + '60', color: REC_COLOR[signal.recommendation], background: REC_COLOR[signal.recommendation] + '18' }}
                    onClick={() => {
                      setNewTrade(p => ({ ...p, symbol: signal.symbol, direction: signal.recommendation === 'SELL' ? 'SELL' : 'BUY', entry_price: signal.entry_zone.low.toFixed(6) }))
                      setMainView('journal'); setJournalSub('new')
                    }}>
                    Log this trade in Journal
                  </button>
                </div>
              )}

              {/* ===== AI ANALYSIS + NEWS ===== */}
              {signal && (
                <div className="analysis-section">
                  <h3 className="analysis-title">AI Analysis</h3>

                  {/* Narrative paragraphs */}
                  <div className="narrative">
                    {buildNarrative(signal, selected).map((p, i) => (
                      <p key={i} className="narrative-para">{p}</p>
                    ))}
                  </div>

                  {/* Signal history timeline */}
                  {signalHistory.length > 0 && (
                    <div style={{ marginTop: 20 }}>
                      <div className="section-label">Signal History ({signal.timeframe})</div>
                      <div className="history-row">
                        {[...signalHistory].reverse().map((h, i) => (
                          <div key={i} className="history-pill" style={{
                            background: REC_COLOR[h.recommendation] + '18',
                            borderColor: REC_COLOR[h.recommendation] + '50',
                            color: REC_COLOR[h.recommendation],
                          }}>
                            <span style={{ fontWeight: 700 }}>{h.recommendation}</span>
                            <span style={{ opacity: 0.7, fontSize: 11 }}>{Math.round(h.confidence * 100)}%</span>
                            <span style={{ opacity: 0.5, fontSize: 10 }}>{timeAgo(Math.floor(new Date(h.created_at).getTime() / 1000))}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* News */}
                  {news.length > 0 && (
                    <div style={{ marginTop: 20 }}>
                      <div className="section-label">Market News</div>
                      <div className="news-grid">
                        {news.map((item, i) => (
                          <a key={i} className="news-card" href={item.url} target="_blank" rel="noopener noreferrer">
                            <div className="news-title">{item.title}</div>
                            <div className="news-meta">
                              <span className="news-publisher">{item.publisher}</span>
                              {item.time > 0 && <span className="news-time">{timeAgo(item.time)}</span>}
                            </div>
                          </a>
                        ))}
                      </div>
                    </div>
                  )}

                  <p style={{ color: '#484F58', fontSize: 11, textAlign: 'center', marginTop: 20 }}>⚠️ Not financial advice. Always do your own research before trading.</p>
                </div>
              )}
            </div>
          )
        )}

        {/* ===== JOURNAL ===== */}
        {mainView === 'journal' && (
          <div className="detail">
            <div className="detail-header">
              <h2 style={{ margin: 0, color: '#E6EDF3' }}>Trade Journal</h2>
            </div>

            {tradeStats && tradeStats.total > 0 && (
              <div className="stats-row">
                {([['Total', String(tradeStats.total)], ['Win Rate', `${tradeStats.win_rate}%`], ['Total P&L', fmt(tradeStats.total_pnl)], ['Avg P&L', fmt(tradeStats.avg_pnl)], ['Wins', String(tradeStats.wins)], ['Losses', String(tradeStats.losses)]] as [string, string][]).map(([l, v]) => (
                  <div key={l} className="stat-card">
                    <div style={{ color: '#8B949E', fontSize: 11, marginBottom: 4 }}>{l}</div>
                    <div style={{ color: (l === 'Total P&L' || l === 'Avg P&L') ? (v.startsWith('-') ? '#FF4560' : '#00C896') : l === 'Win Rate' ? '#00C896' : '#E6EDF3', fontWeight: 700, fontSize: 16 }}>{v}</div>
                  </div>
                ))}
              </div>
            )}

            <div className="tab-row" style={{ marginBottom: 16 }}>
              <button className={`tab ${journalSub === 'open' ? 'active' : ''}`} onClick={() => setJournalSub('open')}>Open ({openTrades.length})</button>
              <button className={`tab ${journalSub === 'closed' ? 'active' : ''}`} onClick={() => setJournalSub('closed')}>Closed ({closedTrades.length})</button>
              <button className={`tab ${journalSub === 'new' ? 'active' : ''}`} onClick={() => setJournalSub('new')}>+ New Trade</button>
            </div>

            {journalSub === 'new' && (
              <div className="trade-form">
                <h3 style={{ color: '#E6EDF3', fontSize: 16, marginBottom: 16 }}>Log New Trade</h3>
                <div className="form-row">
                  <div className="form-field"><label>Symbol</label><input className="input" placeholder="BTCUSD" value={newTrade.symbol} onChange={e => setNewTrade(p => ({ ...p, symbol: e.target.value.toUpperCase() }))} /></div>
                  <div className="form-field"><label>Direction</label><select className="input" value={newTrade.direction} onChange={e => setNewTrade(p => ({ ...p, direction: e.target.value }))}><option value="BUY">BUY (Long)</option><option value="SELL">SELL (Short)</option></select></div>
                </div>
                <div className="form-row">
                  <div className="form-field"><label>Entry Price</label><input className="input" placeholder="0.00" type="number" step="any" value={newTrade.entry_price} onChange={e => setNewTrade(p => ({ ...p, entry_price: e.target.value }))} /></div>
                  <div className="form-field"><label>Size</label><input className="input" placeholder="1.0" type="number" step="any" value={newTrade.size} onChange={e => setNewTrade(p => ({ ...p, size: e.target.value }))} /></div>
                </div>
                <div className="form-field"><label>Notes (optional)</label><input className="input" placeholder="Signal reason, strategy..." value={newTrade.notes} onChange={e => setNewTrade(p => ({ ...p, notes: e.target.value }))} /></div>
                <button className="btn-primary" style={{ marginTop: 12 }} disabled={!newTrade.symbol || !newTrade.entry_price} onClick={createTrade}>Log Trade</button>
              </div>
            )}

            {journalSub === 'open' && (
              openTrades.length === 0
                ? <div className="empty-hint" style={{ padding: '40px 0' }}>No open trades. Use "+ New Trade" to log one.</div>
                : openTrades.map(t => (
                  <div key={t.id} className="trade-row">
                    <div className="trade-row-left">
                      <span className="dir-badge" style={{ color: t.direction === 'BUY' ? '#00C896' : '#FF4560', borderColor: t.direction === 'BUY' ? '#00C89660' : '#FF456060', background: (t.direction === 'BUY' ? '#00C896' : '#FF4560') + '18' }}>{t.direction}</span>
                      <div>
                        <div style={{ color: '#E6EDF3', fontWeight: 700, fontSize: 14 }}>{t.symbol}</div>
                        <div style={{ color: '#8B949E', fontSize: 12 }}>Entry: {fmt(t.entry_price)} · Size: {t.size} · {new Date(t.opened_at).toLocaleDateString()}</div>
                        {t.notes && <div style={{ color: '#6E7681', fontSize: 11, marginTop: 2 }}>{t.notes}</div>}
                      </div>
                    </div>
                    <div className="trade-row-right">
                      {closeForm?.id === t.id ? (
                        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                          <input className="input" style={{ width: 110, padding: '6px 10px', fontSize: 13 }} placeholder="Exit price" type="number" step="any" value={closeForm.exit_price} onChange={e => setCloseForm(p => p ? { ...p, exit_price: e.target.value } : null)} autoFocus onKeyDown={e => e.key === 'Enter' && closeTrade(t.id, closeForm.exit_price)} />
                          <button className="btn-confirm" onClick={() => closeTrade(t.id, closeForm.exit_price)}>OK</button>
                          <button className="btn-link" style={{ fontSize: 12 }} onClick={() => setCloseForm(null)}>Cancel</button>
                        </div>
                      ) : (
                        <div style={{ display: 'flex', gap: 8 }}>
                          <button className="btn-close-trade" onClick={() => setCloseForm({ id: t.id, exit_price: '' })}>Close trade</button>
                          <button className="btn-remove" onClick={() => deleteTrade(t.id)}>×</button>
                        </div>
                      )}
                    </div>
                  </div>
                ))
            )}

            {journalSub === 'closed' && (
              closedTrades.length === 0
                ? <div className="empty-hint" style={{ padding: '40px 0' }}>No closed trades yet.</div>
                : closedTrades.map(t => (
                  <div key={t.id} className="trade-row">
                    <div className="trade-row-left">
                      <span className="dir-badge" style={{ color: t.direction === 'BUY' ? '#00C896' : '#FF4560', borderColor: t.direction === 'BUY' ? '#00C89660' : '#FF456060', background: (t.direction === 'BUY' ? '#00C896' : '#FF4560') + '18' }}>{t.direction}</span>
                      <div>
                        <div style={{ color: '#E6EDF3', fontWeight: 700, fontSize: 14 }}>{t.symbol}</div>
                        <div style={{ color: '#8B949E', fontSize: 12 }}>{fmt(t.entry_price)} → {fmt(t.exit_price)} · Size: {t.size}</div>
                        <div style={{ color: '#6E7681', fontSize: 11, marginTop: 2 }}>{new Date(t.opened_at).toLocaleDateString()} → {t.closed_at ? new Date(t.closed_at).toLocaleDateString() : '—'}</div>
                        {t.notes && <div style={{ color: '#6E7681', fontSize: 11, marginTop: 2 }}>{t.notes}</div>}
                      </div>
                    </div>
                    <div className="trade-row-right" style={{ flexDirection: 'column', alignItems: 'flex-end', gap: 4 }}>
                      <div style={{ color: (t.pnl ?? 0) >= 0 ? '#00C896' : '#FF4560', fontWeight: 700, fontSize: 16 }}>{(t.pnl ?? 0) >= 0 ? '+' : ''}{fmt(t.pnl)}</div>
                      {t.pnl_pct != null && <div style={{ color: t.pnl_pct >= 0 ? '#00C896' : '#FF4560', fontSize: 12 }}>{t.pnl_pct >= 0 ? '+' : ''}{t.pnl_pct.toFixed(2)}%</div>}
                      <button className="btn-remove" onClick={() => deleteTrade(t.id)}>×</button>
                    </div>
                  </div>
                ))
            )}
          </div>
        )}
      </main>
    </div>
  )
}
