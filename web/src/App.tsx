import { useState, useEffect, useCallback, useRef } from 'react'
import axios from 'axios'
import { createChart, CandlestickSeries, createSeriesMarkers } from 'lightweight-charts'
import './App.css'

const API_BASE = import.meta.env.VITE_API_URL
  || (import.meta.env.DEV ? 'http://localhost:8001' : window.location.origin)
const api = axios.create({ baseURL: API_BASE })
api.interceptors.request.use((c) => {
  const t = localStorage.getItem('token')
  if (t) c.headers.Authorization = `Bearer ${t}`
  return c
})
api.interceptors.response.use(
  (r) => r,
  (e) => {
    if (e?.response?.status === 401) {
      localStorage.removeItem('token')
      window.location.reload()
    }
    return Promise.reject(e)
  }
)

type Rec = 'BUY' | 'SELL' | 'HOLD'
interface Signal {
  symbol: string; timeframe: string; recommendation: Rec; confidence: number
  entry_zone: { low: number; high: number }; target_price: number; stop_loss: number
  tp1?: number; tp2?: number; tp3?: number
  reasoning: string[]; is_hot: boolean; is_hot_confluence: boolean
  indicators?: { rsi: number; macd: number; adx: number; vol_zscore: number; bb_pct_b: number; bull_gates?: number; bear_gates?: number }
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

interface LabParams {
  fast_ema: number; slow_ema: number; rsi_period: number
  rsi_oversold: number; rsi_overbought: number
  require_macd: boolean; require_volume: boolean; atr_multiplier: number
}
interface ChatMsg { role: 'user' | 'ai'; text: string; time: number }

type StrategyKey = 'fibonacci' | 'smart_money' | 'elliott_wave' | 'warren_buffett' | 'jpmorgan'
  | 'macd_crossover' | 'rsi_divergence' | 'bb_squeeze' | 'support_resistance'
  | 'ema_crossover' | 'ichimoku' | 'stochastic' | 'vwap'

interface StrategyResult {
  strategy: StrategyKey; recommendation: Rec; confidence: number
  entry_zone: { low: number; high: number }; target_price: number; stop_loss: number
  tp1?: number; tp2?: number; tp3?: number
  reasoning: string[]
  fib_levels?: Record<string, number>; closest_level?: string; trend?: string
  zones?: { type: string; high: number; low: number; label: string }[]
  structure?: string
  wave_label?: string; pivots?: { type: string; price: number }[]
  scores?: { quality: number; value: number; total: number }; key_levels?: Record<string, number>
  factors?: Record<string, number>; composite_score?: number
}

const REC_COLOR: Record<Rec, string> = { BUY: '#10B981', SELL: '#EF4444', HOLD: '#F59E0B' }
const ASSET_COLOR: Record<string, string> = { crypto: '#F7931A', stocks: '#3B82F6', forex: '#10B981', commodities: '#D2A679' }
const TFS = ['15m', '1h', '4h', '1D', '1W']

const STRATEGIES: { key: StrategyKey; label: string; desc: string; category: string }[] = [
  { key: 'fibonacci',          label: 'Fibonacci',           desc: 'Retracements & extensions from swing pivots',      category: 'Price Action' },
  { key: 'smart_money',        label: 'Smart Money (SMC)',    desc: 'Order blocks, FVGs, liquidity sweeps',             category: 'Price Action' },
  { key: 'elliott_wave',       label: 'Elliott Wave',         desc: 'Impulse & corrective wave count',                  category: 'Price Action' },
  { key: 'support_resistance', label: 'Support / Resistance', desc: 'Key price cluster levels from swing highs/lows',   category: 'Price Action' },
  { key: 'ema_crossover',      label: 'EMA Crossover',        desc: 'Golden Cross / Death Cross & ribbon',              category: 'Trend' },
  { key: 'ichimoku',           label: 'Ichimoku Cloud',       desc: 'Full Ichimoku: cloud, Tenkan/Kijun, Chikou',       category: 'Trend' },
  { key: 'vwap',               label: 'VWAP',                 desc: 'Volume-weighted price deviation & EMA confluence', category: 'Trend' },
  { key: 'macd_crossover',     label: 'MACD Crossover',       desc: 'Crossover, histogram momentum & divergence',       category: 'Momentum' },
  { key: 'rsi_divergence',     label: 'RSI Divergence',       desc: 'Regular bullish/bearish divergence detection',     category: 'Momentum' },
  { key: 'stochastic',         label: 'Stochastic',           desc: '%K/%D crossover in oversold/overbought zones',     category: 'Momentum' },
  { key: 'bb_squeeze',         label: 'BB Squeeze',           desc: 'Bollinger Band squeeze & breakout detection',      category: 'Volatility' },
  { key: 'warren_buffett',     label: 'Warren Buffett',       desc: 'Quality + value long-term filter',                 category: 'Institutional' },
  { key: 'jpmorgan',           label: 'JPMorgan Quant',       desc: 'Multi-factor momentum & mean-reversion',           category: 'Institutional' },
]

const FIB_COLORS: Record<string, string> = {
  '23.6%': '#8B949E', '38.2%': '#F7931A', '50.0%': '#FFCC00',
  '61.8%': '#10B981', '78.6%': '#3B82F6', '100.0%': '#EF4444',
}

function fillTPs<T extends { recommendation: Rec; target_price: number; stop_loss: number; tp1?: number; tp2?: number; tp3?: number }>(sig: T): T {
  if (sig.tp1 != null || sig.recommendation === 'HOLD') return sig
  const { recommendation: rec, target_price: tp2val, stop_loss } = sig
  const stopDist = rec === 'BUY' ? (tp2val - stop_loss) / 4.0 : (stop_loss - tp2val) / 4.0
  const close = rec === 'BUY' ? stop_loss + stopDist : stop_loss - stopDist
  const dir = rec === 'BUY' ? 1 : -1
  return { ...sig, tp1: close + dir * 1.5 * stopDist, tp2: tp2val, tp3: close + dir * 4.5 * stopDist }
}

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
    if (ind.rsi >= 80) parts.push(`RSI at ${ind.rsi.toFixed(0)} is overbought`)
    else if (ind.rsi >= 60) parts.push(`RSI at ${ind.rsi.toFixed(0)} sits in the bullish zone`)
    else if (ind.rsi <= 20) parts.push(`RSI at ${ind.rsi.toFixed(0)} is deeply oversold`)
    else if (ind.rsi <= 40) parts.push(`RSI at ${ind.rsi.toFixed(0)} reflects sustained selling pressure`)
    else parts.push(`RSI at ${ind.rsi.toFixed(0)} is neutral`)
    if (ind.adx >= 30) parts.push(`ADX at ${ind.adx.toFixed(0)} confirms a strong trend`)
    else if (ind.adx >= 20) parts.push(`ADX at ${ind.adx.toFixed(0)} shows trend gaining traction`)
    else parts.push(`ADX at ${ind.adx.toFixed(0)} indicates a ranging market`)
    if (ind.vol_zscore > 2) parts.push(`volume surging ${ind.vol_zscore.toFixed(1)}σ above average`)
    else if (ind.vol_zscore < 0.5) parts.push(`volume below average — move lacks broad participation`)
    if (parts.length) paras.push(parts.join('. ') + '.')
  }
  if (reasoning.length) paras.push(`Key confluences: ${reasoning.join('; ')}.`)
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
  const [activeStrategy, setActiveStrategy] = useState<StrategyKey | null>(null)
  const [strategyResult, setStrategyResult] = useState<StrategyResult | null>(null)
  const [strategyLoading, setStrategyLoading] = useState(false)
  const [loading, setLoading] = useState(false)
  const [search, setSearch] = useState('')
  const [searchResults, setSearchResults] = useState<WatchItem[]>([])
  const [addError, setAddError] = useState('')
  const [lastPriceUpdate, setLastPriceUpdate] = useState<number | null>(null)
  const [sideTab, setSideTab] = useState<'watchlist' | 'search'>('watchlist')
  const [mainView, setMainView] = useState<'signals' | 'journal' | 'chat' | 'lab' | 'trendrr'>('signals')
  const [trades, setTrades] = useState<Trade[]>([])
  const [tradeStats, setTradeStats] = useState<TradeStats | null>(null)
  const [journalSub, setJournalSub] = useState<'open' | 'closed' | 'new'>('open')
  const [newTrade, setNewTrade] = useState({ symbol: '', direction: 'BUY', entry_price: '', size: '1', notes: '' })
  const [closeForm, setCloseForm] = useState<{ id: string; exit_price: string } | null>(null)

  const [chatMessages, setChatMessages] = useState<ChatMsg[]>([])
  const [chatInput, setChatInput] = useState('')
  const [chatLoading, setChatLoading] = useState(false)
  const [labParams, setLabParams] = useState<LabParams>({
    fast_ema: 9, slow_ema: 21, rsi_period: 14,
    rsi_oversold: 30, rsi_overbought: 70,
    require_macd: true, require_volume: false, atr_multiplier: 1.5,
  })
  const [labResult, setLabResult] = useState<StrategyResult | null>(null)
  const [labLoading, setLabLoading] = useState(false)
  const [labDescription, setLabDescription] = useState('')
  const [labAnalysis, setLabAnalysis] = useState<{ explanation: string; rationale: string } | null>(null)
  const [labAnalysisLoading, setLabAnalysisLoading] = useState(false)

  // ── Trend RR state ──────────────────────────────────────────────────────────
  interface TrendRRTrade {
    symbol: string; order_id: string; entry_price: number; stop_loss: number
    take_profit: number; qty: number; atr: number; entered_at: string
    exit_notified: boolean; current_price: number | null
    unrealized_pnl: number | null; unrealized_pnl_pct: number | null
  }
  interface TrendRRStatus {
    strategy: string; active_trades: number
    market_open: boolean; current_time_et: string; trades_opened_today: number
    config: {
      risk_pct: number; atr_sl_multiplier: number; rr_ratio: number
      ema_period: number; rsi_period: number; rsi_trigger: number
      scan_universe: string[]; timeframe: string
    }
    trades: TrendRRTrade[]
  }
  interface StrategyScanPick {
    symbol: string; recommendation: Rec; confidence: number
    entry_zone: { low: number; high: number }; target_price: number; stop_loss: number
    tp1?: number; tp2?: number; tp3?: number; reasoning: string[]
  }

  const [trendRR, setTrendRR] = useState<TrendRRStatus | null>(null)
  const [trendRRLoading, setTrendRRLoading] = useState(false)
  const [currentUserEmail, setCurrentUserEmail] = useState('')
  const [trendRRScanning, setTrendRRScanning] = useState(false)
  const [trendRRStrategy, setTrendRRStrategy] = useState<StrategyKey>('ema_crossover')
  const [trendRRTf, setTrendRRTf] = useState('1D')
  const [scanPicks, setScanPicks] = useState<StrategyScanPick[] | null>(null)

  const loadTrendRR = useCallback(async () => {
    setTrendRRLoading(true)
    try { setTrendRR((await api.get('/trend-rr/status')).data) } catch {}
    setTrendRRLoading(false)
  }, [])

  const [scanError, setScanError] = useState<string | null>(null)

  const triggerTrendRRScan = async () => {
    setTrendRRScanning(true)
    setScanPicks(null)
    setScanError(null)
    try {
      const res = await api.post(`/trend-rr/strategy-scan?strategy=${trendRRStrategy}&timeframe=${trendRRTf}`)
      setScanPicks(res.data.picks)
    } catch (e: any) {
      setScanError(e?.response?.data?.detail || 'Scan failed — check that the backend is running')
    }
    await loadTrendRR()
    setTrendRRScanning(false)
  }

  const closeTrendRRTrade = async (symbol: string) => {
    try { await api.post(`/trend-rr/close/${symbol}`); await loadTrendRR() } catch {}
  }

  useEffect(() => { if (mainView === 'trendrr') loadTrendRR() }, [mainView, loadTrendRR])

  const chartRef = useRef<HTMLDivElement>(null)
  const chartInstance = useRef<ReturnType<typeof createChart> | null>(null)
  const chatEndRef = useRef<HTMLDivElement>(null)
  const [signalAge, setSignalAge] = useState<number | null>(null)
  const [refreshing, setRefreshing] = useState(false)
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const signalLoadTrigger = useRef(0)

  const loadWatchlist = useCallback(async () => {
    try {
      const res = await api.get('/watchlist/')
      setWatchlist(res.data)
    } catch (e) { console.error('WATCHLIST ERROR:', e) }
    try {
      const me = await api.get('/auth/me')
      setCurrentUserEmail(me.data.email || '')
    } catch {}
  }, [])

  const loadTrades = useCallback(async () => {
    try {
      const [t, s] = await Promise.all([api.get('/trades/'), api.get('/trades/stats')])
      setTrades(t.data); setTradeStats(s.data)
    } catch {}
  }, [])

  useEffect(() => { if (token) { loadWatchlist(); loadTrades() } }, [token, loadWatchlist, loadTrades])

  const pollPrices = useCallback(async (symbols: string[]) => {
    if (!symbols.length) return
    try {
      const { data } = await api.get('/instruments/prices', { params: { symbols: symbols.join(',') } })
      if (data && typeof data === 'object') {
        setLivePrices(prev => ({ ...prev, ...data }))
        setLastPriceUpdate(Date.now())
      }
    } catch {}
  }, [])

  useEffect(() => {
    if (!token || watchlist.length === 0) return
    const symbols = watchlist.map(w => w.symbol)
    pollPrices(symbols)
    const id = setInterval(() => pollPrices(symbols), 15000)
    return () => clearInterval(id)
  }, [token, watchlist, pollPrices])

  useEffect(() => {
    if (!search.trim()) { setSearchResults([]); setAddError(''); return }
    const id = setTimeout(async () => {
      try { setSearchResults((await api.get('/watchlist/search', { params: { q: search } })).data) } catch {}
    }, 300)
    return () => clearTimeout(id)
  }, [search])

  const loadSignalData = useCallback((sym: string, timeframe: string, isRefresh = false) => {
    if (isRefresh) setRefreshing(true); else setLoading(true)
    if (!isRefresh) { setSignal(null); setCandles([]); setSignalHistory([]); setNews([]) }
    Promise.all([
      api.get(`/signals/${sym}`, { params: { timeframe } }),
      api.get(`/signals/${sym}/ohlcv`, { params: { timeframe, limit: 150 } }),
      api.get(`/signals/${sym}/history`, { params: { timeframe, limit: 50 } }).catch(() => ({ data: [] })),
      api.get(`/signals/${sym}/news`).catch(() => ({ data: { news: [] } })),
    ]).then(([s, o, h, n]) => {
      setSignal(fillTPs(s.data)); setCandles(o.data.candles)
      setSignalHistory(h.data); setNews(n.data.news ?? [])
      setSignalAge(Date.now())
      if (s.data.is_hot) playHotAlert()
    }).catch(() => {}).finally(() => { setLoading(false); setRefreshing(false) })
  }, [])

  useEffect(() => {
    if (!selected || !token) return
    loadSignalData(selected, tf)
  }, [selected, tf, token, loadSignalData])

  // Auto-refresh signal + chart every 5 minutes
  useEffect(() => {
    if (!selected || !token) return
    const id = setInterval(() => {
      loadSignalData(selected, tf, true)
    }, 5 * 60 * 1000)
    return () => clearInterval(id)
  }, [selected, tf, token, loadSignalData])

  useEffect(() => {
    if (!activeStrategy || !selected || !token) { setStrategyResult(null); return }
    setStrategyLoading(true); setStrategyResult(null)
    api.get(`/signals/${selected}/strategy`, { params: { strategy: activeStrategy, timeframe: tf } })
      .then(r => setStrategyResult(fillTPs(r.data)))
      .catch(() => {})
      .finally(() => setStrategyLoading(false))
  }, [activeStrategy, selected, tf, token])

  useEffect(() => { setActiveStrategy(null); setStrategyResult(null) }, [selected])

  // Unified display: strategy result takes priority over general signal
  const displayData = activeStrategy && strategyResult ? strategyResult : signal ? fillTPs(signal) : null
  const currentStrategyInfo = STRATEGIES.find(s => s.key === activeStrategy)

  useEffect(() => {
    if (!chartRef.current || candles.length === 0) return
    if (chartInstance.current) { chartInstance.current.remove(); chartInstance.current = null }

    const chart = createChart(chartRef.current, {
      width: chartRef.current.clientWidth, height: 400,
      layout: { background: { color: '#080C14' }, textColor: '#94A3B8' },
      grid: { vertLines: { color: '#111827' }, horzLines: { color: '#111827' } },
      timeScale: { borderColor: '#1E2D45', timeVisible: true },
      rightPriceScale: { borderColor: '#1E2D45' },
    })

    const series = chart.addSeries(CandlestickSeries, {
      upColor: '#10B981', downColor: '#EF4444', borderVisible: false,
      wickUpColor: '#10B981', wickDownColor: '#EF4444',
    })

    series.setData(candles.map(c => ({ time: c.time as any, open: c.open, high: c.high, low: c.low, close: c.close })))

    const candleTimes = candles.map(c => c.time)
    const dedupedMap = new Map<number, any>()
    for (const h of [...signalHistory].reverse()) {
      if (h.recommendation === 'HOLD') continue
      const snapped = snapToCandle(Math.floor(new Date(h.created_at).getTime() / 1000), candleTimes)
      dedupedMap.set(snapped, {
        time: snapped as any,
        position: h.recommendation === 'BUY' ? 'belowBar' : 'aboveBar',
        color: h.recommendation === 'BUY' ? '#10B981' : '#EF4444',
        shape: h.recommendation === 'BUY' ? 'arrowUp' : 'arrowDown',
        text: `${h.recommendation} ${Math.round(h.confidence * 100)}%`, size: 2,
      })
    }
    createSeriesMarkers(series, [...dedupedMap.values()].sort((a, b) => a.time - b.time))
    chart.timeScale().fitContent()
    chartInstance.current = chart

    // Fibonacci overlays
    if (activeStrategy === 'fibonacci' && strategyResult?.fib_levels) {
      for (const [label, price] of Object.entries(strategyResult.fib_levels)) {
        const short = label.replace('.0%', '%')
        series.createPriceLine({ price, color: FIB_COLORS[short] ?? '#8B949E', lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title: `Fib ${short}` })
      }
    }

    // SL + TP1 only — TP2/TP3 are far from current price and force the chart to zoom out
    const src = activeStrategy && strategyResult ? strategyResult : signal
    if (src && src.recommendation !== 'HOLD') {
      series.createPriceLine({ price: src.stop_loss, color: '#EF4444', lineWidth: 2, lineStyle: 1, axisLabelVisible: true, title: 'SL' })
      const tp1 = src.tp1
      if (tp1 != null) series.createPriceLine({ price: tp1, color: '#10B981', lineWidth: 2, lineStyle: 1, axisLabelVisible: true, title: 'TP1 · 1.5R' })
    }

    const ro = new ResizeObserver(() => {
      if (chartRef.current && chartInstance.current) chartInstance.current.applyOptions({ width: chartRef.current.clientWidth })
    })
    ro.observe(chartRef.current)
    return () => { ro.disconnect(); if (chartInstance.current) { chartInstance.current.remove(); chartInstance.current = null } }
  }, [candles, signal, signalHistory, activeStrategy, strategyResult])

  const handleAuth = async () => {
    setAuthError('')
    try {
      if (authMode === 'login') {
        const form = new FormData(); form.append('username', email); form.append('password', password)
        const { data } = await api.post('/auth/login', form)
        localStorage.setItem('token', data.access_token); setToken(data.access_token)
      } else {
        const { data } = await api.post('/auth/register', { email, password })
        localStorage.setItem('token', data.access_token); setToken(data.access_token)
      }
    } catch (e: any) { setAuthError(e.response?.data?.detail || 'Authentication failed') }
  }

  const createTrade = async () => {
    if (!newTrade.symbol || !newTrade.entry_price) return
    try {
      await api.post('/trades/', { symbol: newTrade.symbol.toUpperCase(), direction: newTrade.direction, entry_price: parseFloat(newTrade.entry_price), size: parseFloat(newTrade.size) || 1, notes: newTrade.notes || null })
      setNewTrade({ symbol: '', direction: 'BUY', entry_price: '', size: '1', notes: '' }); setJournalSub('open'); loadTrades()
    } catch {}
  }

  const closeTrade = async (id: string, exitPrice: string) => {
    const val = parseFloat(exitPrice); if (isNaN(val)) return
    try { await api.patch(`/trades/${id}/close`, { exit_price: val }); setCloseForm(null); loadTrades() } catch {}
  }

  const deleteTrade = async (id: string) => {
    try { await api.delete(`/trades/${id}`); loadTrades() } catch {}
  }

  const sendChat = async (override?: string) => {
    const msg = override ?? chatInput.trim()
    if (!msg || chatLoading) return
    setChatInput('')
    setChatMessages(prev => [...prev, { role: 'user', text: msg, time: Date.now() }])
    setChatLoading(true)
    try {
      const { data } = await api.post('/chat/', {
        message: msg, symbol: selected, timeframe: tf, signal: signal, news,
      })
      setChatMessages(prev => [...prev, { role: 'ai', text: data.reply, time: Date.now() }])
    } catch {
      setChatMessages(prev => [...prev, { role: 'ai', text: 'Connection error — please try again.', time: Date.now() }])
    } finally {
      setChatLoading(false)
    }
  }

  const runLab = async () => {
    if (!selected) return
    setLabLoading(true); setLabResult(null)
    try {
      const { data } = await api.post(`/signals/${selected}/custom?timeframe=${tf}`, labParams)
      setLabResult(fillTPs(data))
    } catch {} finally { setLabLoading(false) }
  }

  const analyzeLabStrategy = async () => {
    if (!labDescription.trim()) return
    setLabAnalysisLoading(true); setLabAnalysis(null)
    try {
      const { data } = await api.post('/chat/strategy', { description: labDescription, symbol: selected })
      // Apply suggested params to sliders
      if (data.params) setLabParams(data.params)
      setLabAnalysis({ explanation: data.explanation || '', rationale: data.rationale || '' })
    } catch {
      setLabAnalysis({ explanation: 'Could not analyze strategy. Please try again.', rationale: '' })
    } finally { setLabAnalysisLoading(false) }
  }

  useEffect(() => { chatEndRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [chatMessages])

  if (!token) return (
    <div className="auth-page">
      <div className="auth-box">
        <div className="auth-logo">TS</div>
        <h1>TradingSignals</h1>
        <p className="auth-sub">AI-powered signals for every market</p>
        <input className="input" placeholder="Email" value={email} onChange={e => setEmail(e.target.value)} onKeyDown={e => e.key === 'Enter' && handleAuth()} />
        <input className="input" placeholder="Password" type="password" value={password} onChange={e => setPassword(e.target.value)} onKeyDown={e => e.key === 'Enter' && handleAuth()} />
        {authError && <div className="error-msg">{authError}</div>}
        <button className="btn-primary" onClick={handleAuth}>{authMode === 'login' ? 'Sign In' : 'Create Account'}</button>
        <button className="btn-link" onClick={() => setAuthMode(authMode === 'login' ? 'register' : 'login')}>
          {authMode === 'login' ? "Don't have an account? Sign up" : 'Already have an account? Sign in'}
        </button>
        <p className="auth-disclaimer">Not financial advice. For informational purposes only.</p>
      </div>
    </div>
  )

  const openTrades = trades.filter(t => t.status === 'open')
  const closedTrades = trades.filter(t => t.status === 'closed')

  return (
    <div className="layout">
      <aside className="sidebar">
        <div className="sidebar-header">
          <div className="sidebar-brand"><span className="brand-mark">TS</span> TradingSignals</div>
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 2 }}>
            {currentUserEmail && <div style={{ fontSize: 9, color: 'var(--text3)', maxWidth: 120, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{currentUserEmail}</div>}
            <button className="btn-link" style={{ fontSize: 12 }} onClick={() => { localStorage.removeItem('token'); setToken(null); setCurrentUserEmail('') }}>Logout</button>
          </div>
        </div>
        <div className="tab-row">
          <button className={`tab ${sideTab === 'watchlist' ? 'active' : ''}`} onClick={() => { setSideTab('watchlist'); loadWatchlist() }}>Watchlist</button>
          <button className={`tab ${sideTab === 'search' ? 'active' : ''}`} onClick={() => setSideTab('search')}>+ Add</button>
        </div>
        {sideTab === 'watchlist' && lastPriceUpdate && (
          <div className="price-update-hint">Prices updated {timeAgo(Math.floor(lastPriceUpdate / 1000))}</div>
        )}
        {sideTab === 'search' ? (
          <div style={{ padding: '8px 12px' }}>
            <input className="input" style={{ marginBottom: 8 }} placeholder="BTC, AAPL, EUR..." value={search} onChange={e => setSearch(e.target.value)} autoFocus />
            {addError && <div className="add-error">{addError}</div>}
            {searchResults.map(r => {
              const alreadyAdded = watchlist.some(w => w.symbol === r.symbol)
              return (
                <div key={r.symbol} className="list-row" onClick={async () => {
                  if (alreadyAdded) { setSearch(''); setSideTab('watchlist'); return }
                  try {
                    await api.post('/watchlist/', { symbol: r.symbol })
                    setAddError('')
                    setSearch('')
                    await loadWatchlist()
                    setSideTab('watchlist')
                  } catch (e: any) {
                    const msg = e.response?.data?.detail || 'Could not add instrument'
                    if (msg === 'Already in watchlist') {
                      await loadWatchlist()
                      setSearch('')
                      setSideTab('watchlist')
                    } else {
                      setAddError(msg)
                      setTimeout(() => setAddError(''), 4000)
                    }
                  }
                }}>
                  <span className="dot" style={{ background: ASSET_COLOR[r.asset_class] }} />
                  <div style={{ flex: 1 }}><div className="sym">{r.symbol}</div><div className="label-sm">{r.name}</div></div>
                  <span className="add-btn" style={alreadyAdded ? { color: 'var(--green)', fontSize: 16 } : {}}>
                    {alreadyAdded ? '✓' : '+'}
                  </span>
                </div>
              )
            })}
          </div>
        ) : (
          <div>
            {watchlist.length === 0 && <div className="empty-hint">Use + Add to build your watchlist</div>}
            {watchlist.map(item => (
              <div key={item.symbol} className={`list-row ${selected === item.symbol && mainView === 'signals' ? 'selected' : ''}`}
                onClick={() => { setSelected(item.symbol); setMainView('signals') }}>
                <span className="dot" style={{ background: ASSET_COLOR[item.asset_class] }} />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div className="sym-row">
                    <span className="sym">{item.symbol}</span>
                    {livePrices[item.symbol] != null && <span className="live-price">{fmt(livePrices[item.symbol])}</span>}
                  </div>
                  <div className="label-sm">{item.name}</div>
                </div>
                <button className="btn-remove" onClick={async e => { e.stopPropagation(); await api.delete(`/watchlist/${item.symbol}`); loadWatchlist() }}>×</button>
              </div>
            ))}
          </div>
        )}
      </aside>

      <main className="main">
        <div className="main-tabs">
          <button className={`main-tab ${mainView === 'signals' ? 'active' : ''}`} onClick={() => setMainView('signals')}>Signals</button>
          <button className={`main-tab ${mainView === 'lab' ? 'active' : ''}`} onClick={() => setMainView('lab')}>Strategy Lab</button>
          <button className={`main-tab ${mainView === 'chat' ? 'active' : ''}`} onClick={() => setMainView('chat')}>AI Chat</button>
          <button className={`main-tab ${mainView === 'journal' ? 'active' : ''}`} onClick={() => { setMainView('journal'); loadTrades() }}>
            Journal {openTrades.length > 0 && <span className="badge-count">{openTrades.length}</span>}
          </button>
          <button className={`main-tab ${mainView === 'trendrr' ? 'active' : ''}`} onClick={() => setMainView('trendrr')}>
            Trend RR
          </button>
        </div>

        {mainView === 'signals' && (
          !selected ? (
            <div className="empty-state">
              <div className="empty-icon" />
              <h2>Select an instrument</h2>
              <p>Pick an asset from your watchlist to view the AI signal</p>
            </div>
          ) : loading ? (
            <div className="empty-state"><div className="spinner" /><p style={{ color: '#94A3B8', marginTop: 16 }}>Loading signal...</p></div>
          ) : (
            <div className="detail">
              {/* Header */}
              <div className="detail-header">
                <div className="detail-title-block">
                  <div className="detail-title-row">
                    <span className="detail-symbol">{selected}</span>
                    {livePrices[selected] != null && <span className="detail-price">{fmt(livePrices[selected])}</span>}
                    {signal?.is_hot_confluence && <span className="badge-hot confluence">HOT CONFLUENCE</span>}
                    {signal?.is_hot && !signal.is_hot_confluence && <span className="badge-hot">HOT</span>}
                  </div>
                  <div className="detail-name">{watchlist.find(w => w.symbol === selected)?.name}</div>
                </div>
                <div className="detail-controls">
                  <div className="tf-row">
                    {TFS.map(t => <button key={t} className={`tf ${tf === t ? 'active' : ''}`} onClick={() => setTf(t)}>{t}</button>)}
                    <button
                      className={`tf refresh-btn ${refreshing ? 'spinning' : ''}`}
                      title="Refresh signal & chart"
                      onClick={() => selected && loadSignalData(selected, tf, true)}
                      disabled={refreshing}
                    >↻</button>
                  </div>
                  {signalAge && (
                    <div className="last-updated">Updated {timeAgo(Math.floor(signalAge / 1000))}</div>
                  )}
                  <div className="strategy-select-wrap">
                    <select className="strategy-select" value={activeStrategy ?? ''} onChange={e => setActiveStrategy(e.target.value ? e.target.value as StrategyKey : null)}>
                      <option value="">AI Signal</option>
                      {(['Price Action', 'Trend', 'Momentum', 'Volatility', 'Institutional'] as const).map(cat => {
                        const items = STRATEGIES.filter(s => s.category === cat)
                        return items.length ? (
                          <optgroup key={cat} label={cat}>
                            {items.map(s => <option key={s.key} value={s.key}>{s.label}</option>)}
                          </optgroup>
                        ) : null
                      })}
                    </select>
                    <span className="strategy-select-arrow">▾</span>
                  </div>
                </div>
              </div>

              {/* Chart */}
              <div className="chart-box">
                {candles.length === 0
                  ? <div className="chart-empty">No chart data available</div>
                  : <div ref={chartRef} style={{ width: '100%' }} />
                }
                <div className="chart-legend">
                  <span className="legend-item"><span className="legend-dot" style={{ background: '#10B981' }} />Buy</span>
                  <span className="legend-item"><span className="legend-dot" style={{ background: '#EF4444' }} />Sell</span>
                  <span className="legend-item"><span className="legend-line red" />SL</span>
                  <span className="legend-item"><span className="legend-line green" />TP1</span>
                </div>
              </div>

              {/* Unified signal panel */}
              {strategyLoading ? (
                <div className="signal-card">
                  <div className="loading-row">
                    <div className="spinner" style={{ width: 18, height: 18, borderWidth: 2 }} />
                    <span>Analysing with {currentStrategyInfo?.label}…</span>
                  </div>
                </div>
              ) : displayData ? (
                <div className={`signal-card rec-${displayData.recommendation.toLowerCase()}`}>
                  {/* Source tag */}
                  <div className="signal-source-row">
                    <span className="signal-source-tag">
                      {currentStrategyInfo ? currentStrategyInfo.label : 'AI Signal'}
                    </span>
                    {currentStrategyInfo && <span className="signal-source-desc">{currentStrategyInfo.desc}</span>}
                    <span className="signal-tf-tag">{tf}</span>
                  </div>

                  {/* Rec + confidence */}
                  <div className="signal-top">
                    <span className="rec-badge" style={{ color: REC_COLOR[displayData.recommendation], borderColor: REC_COLOR[displayData.recommendation] + '50', background: REC_COLOR[displayData.recommendation] + '15' }}>
                      {displayData.recommendation}
                    </span>
                    <div className="conf-row">
                      <div className="conf-bg">
                        <div className="conf-fill" style={{ width: `${Math.round(displayData.confidence * 100)}%`, background: REC_COLOR[displayData.recommendation] }} />
                      </div>
                      <span className="conf-pct" style={{ color: REC_COLOR[displayData.recommendation] }}>{Math.round(displayData.confidence * 100)}%</span>
                    </div>
                  </div>

                  {/* Targets grid */}
                  <div className="targets-grid">
                    <div className="target-cell">
                      <div className="target-label">Entry zone</div>
                      <div className="target-value">{displayData.entry_zone.low.toFixed(4)} – {displayData.entry_zone.high.toFixed(4)}</div>
                    </div>
                    <div className="target-cell">
                      <div className="target-label">Stop loss</div>
                      <div className="target-value sell">{fmt(displayData.stop_loss)}</div>
                    </div>
                  </div>

                  {/* TP ladder */}
                  {displayData.recommendation !== 'HOLD' && (
                    <div className="tp-ladder">
                      {([
                        ['TP1', displayData.tp1, '1.5 R'],
                        ['TP2', displayData.tp2 ?? displayData.target_price, '3.0 R'],
                        ['TP3', displayData.tp3, '4.5 R'],
                      ] as [string, number | undefined, string][]).map(([lbl, price, rr]) =>
                        price != null ? (
                          <div key={lbl} className="tp-row">
                            <span className="tp-rr">{rr}</span>
                            <span className="tp-lbl">{lbl}</span>
                            <span className="tp-price">{fmt(price)}</span>
                          </div>
                        ) : null
                      )}
                    </div>
                  )}

                  {/* Indicators + Gate meter (general signal only) */}
                  {!activeStrategy && signal?.indicators && (
                    <>
                      <div className="ind-strip">
                        {([['RSI', signal.indicators.rsi?.toFixed(1)], ['ADX', signal.indicators.adx?.toFixed(1)], ['Vol Z', signal.indicators.vol_zscore?.toFixed(2)], ['%B', signal.indicators.bb_pct_b?.toFixed(2)]] as [string, string][]).map(([l, v]) => (
                          <div key={l} className="ind-chip"><span className="ind-label">{l}</span><span className="ind-val">{v}</span></div>
                        ))}
                      </div>
                      {signal.indicators.bull_gates != null && (
                        <div className="gate-meter">
                          <span className="gate-label">Confluence gates</span>
                          <div className="gate-dots">
                            {Array.from({ length: 7 }, (_, i) => {
                              const bg = signal.recommendation === 'BUY'
                                ? i < (signal.indicators!.bull_gates ?? 0) ? 'var(--green)' : 'var(--surface3)'
                                : signal.recommendation === 'SELL'
                                ? i < (signal.indicators!.bear_gates ?? 0) ? 'var(--red)' : 'var(--surface3)'
                                : 'var(--surface3)'
                              return <span key={i} className="gate-dot" style={{ background: bg }} />
                            })}
                          </div>
                          <span className="gate-count" style={{ color: signal.recommendation === 'BUY' ? 'var(--green)' : signal.recommendation === 'SELL' ? 'var(--red)' : 'var(--text3)' }}>
                            {signal.recommendation === 'BUY' ? signal.indicators.bull_gates : signal.recommendation === 'SELL' ? signal.indicators.bear_gates : 0}/7
                          </span>
                        </div>
                      )}
                    </>
                  )}

                  {/* Reasoning */}
                  <div className="reasons">
                    {displayData.reasoning.map((r, i) => (
                      <div key={i} className="reason-row"><span className="reason-arrow">›</span><span className="reason-text">{r}</span></div>
                    ))}
                  </div>

                  {/* Strategy extras */}
                  {activeStrategy === 'fibonacci' && strategyResult?.fib_levels && (
                    <div className="strat-extra">
                      <div className="section-label">Fibonacci Levels</div>
                      <div className="fib-levels">
                        {Object.entries(strategyResult.fib_levels).map(([label, price]) => {
                          const short = label.replace('.0%', '%')
                          const isClosest = label === strategyResult.closest_level
                          return (
                            <div key={label} className={`fib-row${isClosest ? ' active' : ''}`}>
                              <span className="fib-dot" style={{ background: FIB_COLORS[short] ?? '#8B949E' }} />
                              <span className="fib-pct">{short}</span>
                              <span className="fib-price">{fmt(price)}</span>
                              {isClosest && <span className="fib-current">current</span>}
                            </div>
                          )
                        })}
                      </div>
                    </div>
                  )}

                  {activeStrategy === 'smart_money' && strategyResult && (
                    <div className="strat-extra">
                      <div className="smc-struct-row">
                        <span className="section-label">Structure</span>
                        <span className={`smc-struct ${strategyResult.structure?.startsWith('Bull') ? 'bull' : strategyResult.structure?.startsWith('Bear') ? 'bear' : ''}`}>{strategyResult.structure}</span>
                      </div>
                      {strategyResult.zones && strategyResult.zones.length > 0 && (
                        <div className="smc-zones">
                          {strategyResult.zones.map((z, i) => (
                            <div key={i} className="smc-zone">
                              <span className={`smc-zone-tag ${z.type.includes('bull') ? 'bull' : 'bear'}`}>{z.label}</span>
                              <span className="smc-zone-range">{fmt(z.low)} – {fmt(z.high)}</span>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  )}

                  {activeStrategy === 'elliott_wave' && strategyResult && (
                    <div className="strat-extra">
                      <div className="smc-struct-row">
                        <span className="section-label">Wave position</span>
                        <span className="ew-label">{strategyResult.wave_label}</span>
                      </div>
                      {strategyResult.pivots && (
                        <div className="ew-pivots">
                          {strategyResult.pivots.map((p, i) => (
                            <div key={i} className={`ew-pivot ${p.type === 'H' ? 'high' : 'low'}`}>
                              <div className="ew-pivot-type">{p.type === 'H' ? 'HIGH' : 'LOW'}</div>
                              <div className="ew-pivot-price">{fmt(p.price)}</div>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  )}

                  {activeStrategy === 'warren_buffett' && strategyResult?.scores && (
                    <div className="strat-extra">
                      <div className="section-label">Scorecard</div>
                      <div className="buffett-scores">
                        {([['Quality', strategyResult.scores.quality, 4], ['Value', strategyResult.scores.value, 5], ['Total', strategyResult.scores.total, 9]] as [string, number, number][]).map(([l, v, max]) => (
                          <div key={l} className="buffett-item">
                            <div className="buffett-label">{l}</div>
                            <div className={`buffett-val ${v >= max * 0.6 ? 'good' : v >= max * 0.3 ? 'mid' : 'bad'}`}>{v}/{max}</div>
                          </div>
                        ))}
                      </div>
                      {strategyResult.key_levels && (
                        <div className="key-levels">
                          {Object.entries(strategyResult.key_levels).map(([k, v]) => (
                            <div key={k} className="key-level"><span className="key-level-label">{k.replace(/_/g, ' ')}</span><span className="key-level-val">{fmt(v)}</span></div>
                          ))}
                        </div>
                      )}
                    </div>
                  )}

                  {activeStrategy === 'jpmorgan' && strategyResult?.factors && (
                    <div className="strat-extra">
                      <div className="section-label">Quantitative Factors</div>
                      <div className="jpm-factors">
                        {Object.entries(strategyResult.factors).map(([k, v]) => (
                          <div key={k} className="jpm-factor">
                            <div className="jpm-factor-label">{k.replace(/_/g, ' ')}</div>
                            <div className={`jpm-factor-val ${v > 0 ? 'pos' : v < 0 ? 'neg' : ''}`}>{v > 0 ? '+' : ''}{typeof v === 'number' ? v.toFixed(3) : v}</div>
                          </div>
                        ))}
                      </div>
                      {strategyResult.composite_score != null && (
                        <div className="jpm-composite">Composite: <span className={(strategyResult.composite_score) > 0 ? 'pos' : 'neg'}>{strategyResult.composite_score > 0 ? '+' : ''}{strategyResult.composite_score.toFixed(3)}</span></div>
                      )}
                    </div>
                  )}

                  <button className="btn-log-trade" onClick={() => {
                    setNewTrade(p => ({ ...p, symbol: selected, direction: displayData.recommendation === 'SELL' ? 'SELL' : 'BUY', entry_price: displayData.entry_zone.low.toFixed(6) }))
                    setMainView('journal'); setJournalSub('new')
                  }}>Log in Journal</button>
                </div>
              ) : null}

              {/* AI analysis + news — only in AI mode */}
              {!activeStrategy && signal && (
                <div className="analysis-section">
                  <h3 className="analysis-title">AI Analysis</h3>
                  <div className="narrative">
                    {buildNarrative(signal, selected).map((p, i) => <p key={i} className="narrative-para">{p}</p>)}
                  </div>
                  {signalHistory.length > 0 && (
                    <div style={{ marginTop: 20 }}>
                      <div className="section-label">Signal History ({signal.timeframe})</div>
                      <div className="history-row">
                        {[...signalHistory].reverse().map((h, i) => (
                          <div key={i} className="history-pill" style={{ background: REC_COLOR[h.recommendation] + '15', borderColor: REC_COLOR[h.recommendation] + '40', color: REC_COLOR[h.recommendation] }}>
                            <span style={{ fontWeight: 700 }}>{h.recommendation}</span>
                            <span style={{ opacity: 0.7, fontSize: 11 }}>{Math.round(h.confidence * 100)}%</span>
                            <span style={{ opacity: 0.5, fontSize: 10 }}>{timeAgo(Math.floor(new Date(h.created_at).getTime() / 1000))}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
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
                  <p className="disclaimer">Not financial advice. Always do your own research before trading.</p>
                </div>
              )}
            </div>
          )
        )}

        {/* ── Strategy Lab ─────────────────────────────────── */}
        {mainView === 'lab' && (
          <div className="detail">
            <div className="detail-header">
              <div className="detail-title-block">
                <div className="detail-symbol">Strategy Lab</div>
                <div className="detail-name">Build and test your own trading strategy</div>
              </div>
              <div className="detail-controls">
                <div className="tf-row">
                  {TFS.map(t => <button key={t} className={`tf ${tf === t ? 'active' : ''}`} onClick={() => setTf(t)}>{t}</button>)}
                </div>
              </div>
            </div>

            {/* AI Strategy Description */}
            <div className="lab-describe">
              <div className="lab-describe-header">
                <div className="lab-describe-icon">AI</div>
                <div>
                  <div className="lab-describe-title">Describe your strategy</div>
                  <div className="lab-describe-sub">Write how you trade in plain English — AI will configure the optimal parameters for you</div>
                </div>
              </div>
              <textarea
                className="lab-describe-input"
                placeholder={'Examples:\n• "I use swing trading with EMA crossovers, buying when momentum is strong but not overbought"\n• "Conservative trend-following strategy that requires multiple confirmations before entering"\n• "Momentum scalping on short timeframes with tight stops and high frequency"'}
                value={labDescription}
                onChange={e => setLabDescription(e.target.value)}
                rows={4}
              />
              <div className="lab-describe-footer">
                <button
                  className="btn-analyze"
                  disabled={!labDescription.trim() || labAnalysisLoading}
                  onClick={analyzeLabStrategy}
                >
                  {labAnalysisLoading ? (
                    <><span className="spinner" style={{ width: 14, height: 14, borderWidth: 2, marginRight: 8 }} />Analyzing…</>
                  ) : 'Analyze with AI'}
                </button>
                {labAnalysis && (
                  <span className="lab-describe-applied">Parameters applied to sliders below</span>
                )}
              </div>
              {labAnalysis && (
                <div className="lab-analysis-result">
                  <div className="lab-analysis-section">
                    <div className="lab-analysis-label">Strategy interpretation</div>
                    <div className="lab-analysis-text">{labAnalysis.explanation}</div>
                  </div>
                  {labAnalysis.rationale && (
                    <div className="lab-analysis-section">
                      <div className="lab-analysis-label">Why these parameters</div>
                      <div className="lab-analysis-text">{labAnalysis.rationale}</div>
                    </div>
                  )}
                </div>
              )}
            </div>

            <div className="lab-layout">
              {/* Parameters panel */}
              <div className="lab-params">
                <div className="lab-section-title">Parameters</div>

                <div className="lab-group">
                  <div className="lab-group-title">Moving Averages</div>
                  <div className="lab-row">
                    <label>Fast EMA</label>
                    <div className="lab-input-row">
                      <input type="range" min={3} max={50} value={labParams.fast_ema} onChange={e => setLabParams(p => ({ ...p, fast_ema: +e.target.value }))} className="lab-slider" />
                      <span className="lab-val">{labParams.fast_ema}</span>
                    </div>
                  </div>
                  <div className="lab-row">
                    <label>Slow EMA</label>
                    <div className="lab-input-row">
                      <input type="range" min={10} max={200} value={labParams.slow_ema} onChange={e => setLabParams(p => ({ ...p, slow_ema: +e.target.value }))} className="lab-slider" />
                      <span className="lab-val">{labParams.slow_ema}</span>
                    </div>
                  </div>
                </div>

                <div className="lab-group">
                  <div className="lab-group-title">RSI</div>
                  <div className="lab-row">
                    <label>Period</label>
                    <div className="lab-input-row">
                      <input type="range" min={5} max={30} value={labParams.rsi_period} onChange={e => setLabParams(p => ({ ...p, rsi_period: +e.target.value }))} className="lab-slider" />
                      <span className="lab-val">{labParams.rsi_period}</span>
                    </div>
                  </div>
                  <div className="lab-row">
                    <label>Oversold</label>
                    <div className="lab-input-row">
                      <input type="range" min={10} max={45} value={labParams.rsi_oversold} onChange={e => setLabParams(p => ({ ...p, rsi_oversold: +e.target.value }))} className="lab-slider" />
                      <span className="lab-val">{labParams.rsi_oversold}</span>
                    </div>
                  </div>
                  <div className="lab-row">
                    <label>Overbought</label>
                    <div className="lab-input-row">
                      <input type="range" min={55} max={90} value={labParams.rsi_overbought} onChange={e => setLabParams(p => ({ ...p, rsi_overbought: +e.target.value }))} className="lab-slider" />
                      <span className="lab-val">{labParams.rsi_overbought}</span>
                    </div>
                  </div>
                </div>

                <div className="lab-group">
                  <div className="lab-group-title">Risk</div>
                  <div className="lab-row">
                    <label>ATR Stop Mult.</label>
                    <div className="lab-input-row">
                      <input type="range" min={0.5} max={4} step={0.25} value={labParams.atr_multiplier} onChange={e => setLabParams(p => ({ ...p, atr_multiplier: +e.target.value }))} className="lab-slider" />
                      <span className="lab-val">{labParams.atr_multiplier}×</span>
                    </div>
                  </div>
                </div>

                <div className="lab-group">
                  <div className="lab-group-title">Filters</div>
                  <div className="lab-toggle-row">
                    <label>Require MACD confirmation</label>
                    <button className={`lab-toggle ${labParams.require_macd ? 'on' : ''}`} onClick={() => setLabParams(p => ({ ...p, require_macd: !p.require_macd }))}>
                      {labParams.require_macd ? 'ON' : 'OFF'}
                    </button>
                  </div>
                  <div className="lab-toggle-row">
                    <label>Require volume spike</label>
                    <button className={`lab-toggle ${labParams.require_volume ? 'on' : ''}`} onClick={() => setLabParams(p => ({ ...p, require_volume: !p.require_volume }))}>
                      {labParams.require_volume ? 'ON' : 'OFF'}
                    </button>
                  </div>
                </div>

                <button
                  className="btn-primary"
                  style={{ marginTop: 8 }}
                  disabled={!selected || labLoading}
                  onClick={runLab}
                >
                  {labLoading ? 'Analysing…' : selected ? `Run on ${selected}` : 'Select an instrument first'}
                </button>
                {!selected && <div style={{ color: 'var(--text3)', fontSize: 12, marginTop: 8, textAlign: 'center' }}>Select an asset from your watchlist to run the strategy</div>}
              </div>

              {/* Result panel */}
              <div className="lab-result">
                {labLoading ? (
                  <div className="lab-empty"><div className="spinner" /><span>Running strategy…</span></div>
                ) : labResult ? (
                  <>
                    <div className="lab-section-title">Result — {selected} · {tf}</div>
                    <div className={`signal-card rec-${labResult.recommendation.toLowerCase()}`} style={{ marginTop: 10 }}>
                      <div className="signal-source-row">
                        <span className="signal-source-tag">Custom Strategy</span>
                        <span className="signal-source-desc">EMA {labParams.fast_ema}/{labParams.slow_ema} · RSI {labParams.rsi_period}{labParams.require_macd ? ' · MACD' : ''}{labParams.require_volume ? ' · Vol' : ''}</span>
                        <span className="signal-tf-tag">{tf}</span>
                      </div>
                      <div className="signal-top">
                        <span className="rec-badge" style={{ color: REC_COLOR[labResult.recommendation], borderColor: REC_COLOR[labResult.recommendation] + '50', background: REC_COLOR[labResult.recommendation] + '15' }}>
                          {labResult.recommendation}
                        </span>
                        <div className="conf-row">
                          <div className="conf-bg"><div className="conf-fill" style={{ width: `${Math.round(labResult.confidence * 100)}%`, background: REC_COLOR[labResult.recommendation] }} /></div>
                          <span className="conf-pct" style={{ color: REC_COLOR[labResult.recommendation] }}>{Math.round(labResult.confidence * 100)}%</span>
                        </div>
                      </div>
                      <div className="targets-grid">
                        <div className="target-cell"><div className="target-label">Entry zone</div><div className="target-value">{labResult.entry_zone.low.toFixed(4)} – {labResult.entry_zone.high.toFixed(4)}</div></div>
                        <div className="target-cell"><div className="target-label">Stop loss</div><div className="target-value sell">{fmt(labResult.stop_loss)}</div></div>
                      </div>
                      {labResult.recommendation !== 'HOLD' && (
                        <div className="tp-ladder">
                          {([['TP1', labResult.tp1, '1.5 R'], ['TP2', labResult.tp2 ?? labResult.target_price, '3.0 R'], ['TP3', labResult.tp3, '4.5 R']] as [string, number | undefined, string][]).map(([lbl, price, rr]) =>
                            price != null ? (
                              <div key={lbl} className="tp-row">
                                <span className="tp-rr">{rr}</span>
                                <span className="tp-lbl">{lbl}</span>
                                <span className="tp-price">{fmt(price)}</span>
                              </div>
                            ) : null
                          )}
                        </div>
                      )}
                      <div className="reasons">
                        {labResult.reasoning.map((r, i) => (
                          <div key={i} className="reason-row"><span className="reason-arrow">›</span><span className="reason-text">{r}</span></div>
                        ))}
                      </div>
                      <button className="btn-log-trade" onClick={() => {
                        setNewTrade(p => ({ ...p, symbol: selected!, direction: labResult!.recommendation === 'SELL' ? 'SELL' : 'BUY', entry_price: labResult!.entry_zone.low.toFixed(6) }))
                        setMainView('journal'); setJournalSub('new')
                      }}>Log in Journal</button>
                    </div>
                  </>
                ) : (
                  <div className="lab-empty">
                    <div className="lab-empty-icon" />
                    <span>Configure parameters and click Run</span>
                    <span style={{ color: 'var(--text3)', fontSize: 11, marginTop: 4 }}>Results will appear here</span>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* ── AI Chat ──────────────────────────────────────── */}
        {mainView === 'chat' && (
          <div className="chat-view">
            <div className="chat-header">
              <div>
                <div className="chat-title">AI Trading Assistant</div>
                <div className="chat-sub">{selected ? `Context: ${selected} · ${tf}` : 'Select an instrument for context-aware analysis'}</div>
              </div>
              {chatMessages.length > 0 && (
                <button className="btn-link" style={{ fontSize: 12 }} onClick={() => setChatMessages([])}>Clear chat</button>
              )}
            </div>

            <div className="chat-messages">
              {chatMessages.length === 0 && (
                <div className="chat-welcome">
                  <div className="chat-welcome-icon">TS</div>
                  <div className="chat-welcome-title">Ask me anything about the markets</div>
                  <div className="chat-welcome-sub">I can analyse technical setups, explain indicators, discuss risk management, and more.{selected ? ` Currently viewing ${selected}.` : ''}</div>
                </div>
              )}
              {chatMessages.map((m, i) => (
                <div key={i} className={`chat-bubble-wrap ${m.role}`}>
                  {m.role === 'ai' && <div className="chat-avatar">TS</div>}
                  <div className={`chat-bubble ${m.role}`}>
                    {m.text.split('\n').map((line, j) => (
                      <span key={j}>
                        {line.split(/(\*\*[^*]+\*\*)/).map((part, k) =>
                          part.startsWith('**') && part.endsWith('**')
                            ? <strong key={k}>{part.slice(2, -2)}</strong>
                            : part
                        )}
                        {j < m.text.split('\n').length - 1 && <br />}
                      </span>
                    ))}
                  </div>
                </div>
              ))}
              {chatLoading && (
                <div className="chat-bubble-wrap ai">
                  <div className="chat-avatar">TS</div>
                  <div className="chat-bubble ai chat-typing">
                    <span /><span /><span />
                  </div>
                </div>
              )}
              <div ref={chatEndRef} />
            </div>

            <div className="chat-input-area">
              <div className="chat-chips">
                {[
                  selected ? `Should I buy ${selected}?` : 'Should I buy?',
                  'Explain the signal',
                  'What are the key levels?',
                  'How should I manage risk?',
                  'What does the volume say?',
                  'Latest news impact',
                ].map(chip => (
                  <button key={chip} className="chat-chip" onClick={() => sendChat(chip)}>{chip}</button>
                ))}
              </div>
              <div className="chat-input-row">
                <input
                  className="input chat-input"
                  placeholder="Ask about technicals, strategy, risk management…"
                  value={chatInput}
                  onChange={e => setChatInput(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && !e.shiftKey && sendChat()}
                  disabled={chatLoading}
                />
                <button className="chat-send" onClick={() => sendChat()} disabled={!chatInput.trim() || chatLoading}>
                  {chatLoading ? '…' : '↑'}
                </button>
              </div>
            </div>
          </div>
        )}

        {mainView === 'journal' && (
          <div className="detail">
            <div className="detail-header">
              <span className="detail-symbol">Trade Journal</span>
            </div>
            {tradeStats && tradeStats.total > 0 && (
              <div className="stats-row">
                {([['Total', String(tradeStats.total)], ['Win Rate', `${tradeStats.win_rate}%`], ['Total P&L', fmt(tradeStats.total_pnl)], ['Avg P&L', fmt(tradeStats.avg_pnl)], ['Wins', String(tradeStats.wins)], ['Losses', String(tradeStats.losses)]] as [string, string][]).map(([l, v]) => (
                  <div key={l} className="stat-card">
                    <div style={{ color: '#94A3B8', fontSize: 11, marginBottom: 4 }}>{l}</div>
                    <div style={{ color: (l === 'Total P&L' || l === 'Avg P&L') ? (v.startsWith('-') ? '#EF4444' : '#10B981') : l === 'Win Rate' ? '#10B981' : '#E2E8F0', fontWeight: 700, fontSize: 16 }}>{v}</div>
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
                <h3 style={{ color: '#E2E8F0', fontSize: 16, marginBottom: 16 }}>Log New Trade</h3>
                <div className="form-row">
                  <div className="form-field"><label>Symbol</label><input className="input" placeholder="BTCUSD" value={newTrade.symbol} onChange={e => setNewTrade(p => ({ ...p, symbol: e.target.value.toUpperCase() }))} /></div>
                  <div className="form-field"><label>Direction</label><select className="input" value={newTrade.direction} onChange={e => setNewTrade(p => ({ ...p, direction: e.target.value }))}><option value="BUY">BUY (Long)</option><option value="SELL">SELL (Short)</option></select></div>
                </div>
                <div className="form-row">
                  <div className="form-field"><label>Entry Price</label><input className="input" placeholder="0.00" type="number" step="any" value={newTrade.entry_price} onChange={e => setNewTrade(p => ({ ...p, entry_price: e.target.value }))} /></div>
                  <div className="form-field"><label>Size</label><input className="input" placeholder="1.0" type="number" step="any" value={newTrade.size} onChange={e => setNewTrade(p => ({ ...p, size: e.target.value }))} /></div>
                </div>
                <div className="form-field"><label>Notes (optional)</label><input className="input" placeholder="Signal reason, strategy…" value={newTrade.notes} onChange={e => setNewTrade(p => ({ ...p, notes: e.target.value }))} /></div>
                <button className="btn-primary" style={{ marginTop: 12 }} disabled={!newTrade.symbol || !newTrade.entry_price} onClick={createTrade}>Log Trade</button>
              </div>
            )}
            {journalSub === 'open' && (
              openTrades.length === 0
                ? <div className="empty-hint" style={{ padding: '40px 0' }}>No open trades. Use "+ New Trade" to log one.</div>
                : openTrades.map(t => (
                  <div key={t.id} className="trade-row">
                    <div className="trade-row-left">
                      <span className="dir-badge" style={{ color: t.direction === 'BUY' ? '#10B981' : '#EF4444', borderColor: (t.direction === 'BUY' ? '#10B981' : '#EF4444') + '50', background: (t.direction === 'BUY' ? '#10B981' : '#EF4444') + '15' }}>{t.direction}</span>
                      <div>
                        <div style={{ color: '#E2E8F0', fontWeight: 700, fontSize: 14 }}>{t.symbol}</div>
                        <div style={{ color: '#94A3B8', fontSize: 12 }}>Entry: {fmt(t.entry_price)} · Size: {t.size} · {new Date(t.opened_at).toLocaleDateString()}</div>
                        {t.notes && <div style={{ color: '#4A5568', fontSize: 11, marginTop: 2 }}>{t.notes}</div>}
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
                      <span className="dir-badge" style={{ color: t.direction === 'BUY' ? '#10B981' : '#EF4444', borderColor: (t.direction === 'BUY' ? '#10B981' : '#EF4444') + '50', background: (t.direction === 'BUY' ? '#10B981' : '#EF4444') + '15' }}>{t.direction}</span>
                      <div>
                        <div style={{ color: '#E2E8F0', fontWeight: 700, fontSize: 14 }}>{t.symbol}</div>
                        <div style={{ color: '#94A3B8', fontSize: 12 }}>{fmt(t.entry_price)} → {fmt(t.exit_price)} · Size: {t.size}</div>
                        <div style={{ color: '#4A5568', fontSize: 11, marginTop: 2 }}>{new Date(t.opened_at).toLocaleDateString()} → {t.closed_at ? new Date(t.closed_at).toLocaleDateString() : '—'}</div>
                        {t.notes && <div style={{ color: '#4A5568', fontSize: 11, marginTop: 2 }}>{t.notes}</div>}
                      </div>
                    </div>
                    <div className="trade-row-right" style={{ flexDirection: 'column', alignItems: 'flex-end', gap: 4 }}>
                      <div style={{ color: (t.pnl ?? 0) >= 0 ? '#10B981' : '#EF4444', fontWeight: 700, fontSize: 16 }}>{(t.pnl ?? 0) >= 0 ? '+' : ''}{fmt(t.pnl)}</div>
                      {t.pnl_pct != null && <div style={{ color: t.pnl_pct >= 0 ? '#10B981' : '#EF4444', fontSize: 12 }}>{t.pnl_pct >= 0 ? '+' : ''}{t.pnl_pct.toFixed(2)}%</div>}
                      <button className="btn-remove" onClick={() => deleteTrade(t.id)}>×</button>
                    </div>
                  </div>
                ))
            )}
          </div>
        )}

        {/* ── Trend RR Strategy ──────────────────────────────── */}
        {mainView === 'trendrr' && (
          <div className="chat-view" style={{ padding: '24px 28px', overflowY: 'auto' }}>

            {/* Header */}
            <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 24, flexWrap: 'wrap', gap: 12 }}>
              <div>
                <div style={{ color: '#E2E8F0', fontWeight: 700, fontSize: 20 }}>Semi-Auto 1:2 RR Trend Strategy</div>
                <div style={{ color: '#64748B', fontSize: 13, marginTop: 4 }}>
                  EMA-50 trend filter · RSI-14 pullback entry · 1% risk sizing · Manual exit approval
                </div>
              </div>
              <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
                {/* Strategy selector */}
                <div className="strategy-select-wrap">
                  <select className="strategy-select" value={trendRRStrategy} onChange={e => setTrendRRStrategy(e.target.value as StrategyKey)}>
                    {(['Price Action', 'Trend', 'Momentum', 'Volatility', 'Institutional'] as const).map(cat => {
                      const items = STRATEGIES.filter(s => s.category === cat)
                      return items.length ? (
                        <optgroup key={cat} label={cat}>
                          {items.map(s => <option key={s.key} value={s.key}>{s.label}</option>)}
                        </optgroup>
                      ) : null
                    })}
                  </select>
                  <span className="strategy-select-arrow">▾</span>
                </div>
                {/* Timeframe selector */}
                <div style={{ display: 'flex', gap: 4 }}>
                  {TFS.map(t => (
                    <button key={t} onClick={() => setTrendRRTf(t)}
                      style={{ padding: '5px 10px', fontSize: 12, borderRadius: 6, border: '1px solid', cursor: 'pointer', fontWeight: trendRRTf === t ? 700 : 400, background: trendRRTf === t ? '#3B82F6' : '#1E293B', borderColor: trendRRTf === t ? '#3B82F6' : '#334155', color: trendRRTf === t ? '#fff' : '#94A3B8' }}>
                      {t}
                    </button>
                  ))}
                </div>
                <button className="btn-primary" style={{ fontSize: 13, padding: '8px 18px' }}
                  disabled={trendRRScanning}
                  onClick={triggerTrendRRScan}>
                  {trendRRScanning ? <><span className="spinner" style={{ width: 13, height: 13, borderWidth: 2, marginRight: 8 }} />Scanning…</> : '▶ Run Scan'}
                </button>
                <button className="btn-link" style={{ fontSize: 13 }} onClick={loadTrendRR}>↻ Refresh</button>
              </div>
            </div>

            {trendRRLoading && <div style={{ color: '#64748B', fontSize: 14 }}>Loading…</div>}

            {trendRR && (
              <>
                {/* Market status bar */}
                <div style={{ display: 'flex', gap: 16, alignItems: 'center', marginBottom: 20, padding: '10px 16px', background: '#0F172A', border: '1px solid #1E293B', borderRadius: 10, fontSize: 13 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <span style={{ width: 8, height: 8, borderRadius: '50%', background: trendRR.market_open ? '#10B981' : '#EF4444', display: 'inline-block', boxShadow: trendRR.market_open ? '0 0 6px #10B981' : 'none' }} />
                    <span style={{ color: trendRR.market_open ? '#10B981' : '#EF4444', fontWeight: 600 }}>{trendRR.market_open ? 'Market Open' : 'Market Closed'}</span>
                  </div>
                  <span style={{ color: '#475569' }}>{trendRR.current_time_et}</span>
                  <span style={{ color: '#334155' }}>|</span>
                  <span style={{ color: '#64748B' }}>Trades opened today: <span style={{ color: '#E2E8F0', fontWeight: 600 }}>{trendRR.trades_opened_today}</span></span>
                  <span style={{ color: '#334155' }}>|</span>
                  <span style={{ color: '#64748B' }}>Auto-scan: <span style={{ color: '#94A3B8' }}>every 30 min · Mon–Fri 09:35–15:30 ET</span></span>
                </div>

                {/* Config strip */}
                <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 24 }}>
                  {[
                    ['Risk', `${trendRR.config.risk_pct}%`],
                    ['EMA', trendRR.config.ema_period],
                    ['RSI trigger', `>${trendRR.config.rsi_trigger}`],
                    ['ATR mult', `×${trendRR.config.atr_sl_multiplier}`],
                    ['RR', `1:${trendRR.config.rr_ratio}`],
                    ['TF', trendRR.config.timeframe],
                    ['Universe', `${trendRR.config.scan_universe.length} symbols`],
                  ].map(([label, val]) => (
                    <div key={label as string} style={{ background: '#1E293B', border: '1px solid #2D3748', borderRadius: 8, padding: '6px 12px', fontSize: 12 }}>
                      <span style={{ color: '#64748B' }}>{label} </span>
                      <span style={{ color: '#E2E8F0', fontWeight: 600 }}>{val}</span>
                    </div>
                  ))}
                </div>

                {/* How it works banner */}
                <div style={{ background: '#0F172A', border: '1px solid #1D4ED880', borderRadius: 10, padding: '14px 18px', marginBottom: 24, fontSize: 12, color: '#94A3B8', lineHeight: 1.7 }}>
                  <span style={{ color: '#3B82F6', fontWeight: 600 }}>How it works: </span>
                  Every 15 min the scanner checks {trendRR.config.scan_universe.length} symbols on the {trendRR.config.timeframe} chart. When
                  price is above EMA-{trendRR.config.ema_period} <strong>and</strong> RSI crosses above {trendRR.config.rsi_trigger} from below, it automatically places a market
                  order sized to risk exactly {trendRR.config.risk_pct}% of equity. Stop loss = {trendRR.config.atr_sl_multiplier}×ATR below entry,
                  take profit = {trendRR.config.rr_ratio * trendRR.config.atr_sl_multiplier}×ATR above entry (1:{trendRR.config.rr_ratio} RR).
                  When price reaches either level a <strong>push notification</strong> is sent — you review and manually close.
                </div>

                {/* Strategy Scan Results */}
                {(trendRRScanning || scanPicks || scanError) && (
                  <div style={{ marginBottom: 32 }}>
                    <div style={{ color: '#94A3B8', fontSize: 13, fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase', marginBottom: 12 }}>
                      Top 10 Setups
                      {scanPicks && <span style={{ color: '#64748B', fontWeight: 400, fontSize: 12, textTransform: 'none', marginLeft: 8 }}>
                        — {STRATEGIES.find(s => s.key === trendRRStrategy)?.label} · {trendRRTf} · ranked by confidence
                      </span>}
                    </div>

                    {trendRRScanning && (
                      <div style={{ background: '#1E293B', border: '1px solid #2D3748', borderRadius: 10, padding: '28px 20px', textAlign: 'center', color: '#64748B', fontSize: 14 }}>
                        <span className="spinner" style={{ width: 16, height: 16, borderWidth: 2, display: 'inline-block', marginRight: 10, verticalAlign: 'middle' }} />
                        Scanning {trendRR?.config.scan_universe.length ?? '—'} symbols with {STRATEGIES.find(s => s.key === trendRRStrategy)?.label}…
                      </div>
                    )}

                    {!trendRRScanning && scanError && (
                      <div style={{ background: '#EF444415', border: '1px solid #EF444440', borderRadius: 10, padding: '16px 20px', color: '#EF4444', fontSize: 13 }}>
                        {scanError}
                      </div>
                    )}

                    {!trendRRScanning && scanPicks && scanPicks.length === 0 && (
                      <div style={{ background: '#1E293B', border: '1px solid #2D3748', borderRadius: 10, padding: '28px 20px', textAlign: 'center', color: '#4A5568', fontSize: 14 }}>
                        No actionable setups found — try a different strategy or timeframe
                      </div>
                    )}

                    {!trendRRScanning && scanPicks && scanPicks.length > 0 && (
                      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                        {scanPicks.map((p, i) => {
                          const rec = p.recommendation
                          const recColor = REC_COLOR[rec]
                          const pct = Math.round(p.confidence * 100)
                          const pick = fillTPs(p)
                          return (
                            <div key={p.symbol} style={{ background: '#1E293B', border: `1px solid ${i === 0 ? recColor + '50' : '#2D3748'}`, borderRadius: 10, padding: '14px 18px', display: 'flex', alignItems: 'center', gap: 16, flexWrap: 'wrap' }}>
                              {/* Rank */}
                              <div style={{ width: 28, height: 28, borderRadius: '50%', border: `2px solid ${i === 0 ? '#F59E0B' : i === 1 ? '#94A3B8' : i === 2 ? '#CD7F32' : '#2D3748'}`, display: 'flex', alignItems: 'center', justifyContent: 'center', color: i === 0 ? '#F59E0B' : i === 1 ? '#94A3B8' : i === 2 ? '#CD7F32' : '#64748B', fontSize: 12, fontWeight: 700, flexShrink: 0 }}>
                                {i + 1}
                              </div>

                              {/* Symbol + signal */}
                              <div style={{ minWidth: 80 }}>
                                <div style={{ color: '#E2E8F0', fontWeight: 700, fontSize: 15 }}>{p.symbol}</div>
                                <div style={{ color: recColor, fontSize: 11, fontWeight: 600 }}>{rec}</div>
                              </div>

                              {/* Confidence bar */}
                              <div style={{ minWidth: 70 }}>
                                <div style={{ color: recColor, fontWeight: 700, fontSize: 16 }}>{pct}%</div>
                                <div style={{ height: 4, background: '#0F172A', borderRadius: 2, marginTop: 4, width: 60 }}>
                                  <div style={{ height: '100%', width: `${pct}%`, background: recColor, borderRadius: 2 }} />
                                </div>
                              </div>

                              {/* Entry zone */}
                              <div style={{ minWidth: 90 }}>
                                <div style={{ color: '#E2E8F0', fontSize: 12 }}>${fmt(p.entry_zone.low)} – ${fmt(p.entry_zone.high)}</div>
                                <div style={{ color: '#475569', fontSize: 10 }}>Entry Zone</div>
                              </div>

                              {/* SL / TP */}
                              <div style={{ flex: 1, display: 'flex', gap: 12, justifyContent: 'flex-end', flexWrap: 'wrap' }}>
                                <div style={{ textAlign: 'right' }}>
                                  <div style={{ color: '#EF4444', fontSize: 12, fontWeight: 600 }}>${fmt(p.stop_loss)}</div>
                                  <div style={{ color: '#475569', fontSize: 10 }}>Stop Loss</div>
                                </div>
                                <div style={{ textAlign: 'right' }}>
                                  <div style={{ color: '#10B981', fontSize: 12, fontWeight: 600 }}>${fmt(pick.tp1)}</div>
                                  <div style={{ color: '#475569', fontSize: 10 }}>TP1</div>
                                </div>
                                <div style={{ textAlign: 'right' }}>
                                  <div style={{ color: '#10B981', fontSize: 12, fontWeight: 600 }}>${fmt(pick.tp2)}</div>
                                  <div style={{ color: '#475569', fontSize: 10 }}>TP2</div>
                                </div>
                              </div>

                              {/* Top reasoning */}
                              {p.reasoning?.[0] && (
                                <div style={{ width: '100%', color: '#64748B', fontSize: 11, marginTop: 4, borderTop: '1px solid #1E293B', paddingTop: 8 }}>
                                  {p.reasoning[0]}
                                </div>
                              )}
                            </div>
                          )
                        })}
                      </div>
                    )}
                  </div>
                )}

              </>
            )}
          </div>
        )}

      </main>
    </div>
  )
}
