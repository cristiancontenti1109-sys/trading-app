export type AssetClass = 'crypto' | 'stocks' | 'forex' | 'commodities';
export type Recommendation = 'BUY' | 'SELL' | 'HOLD';
export type Timeframe = '1m' | '5m' | '15m' | '1h' | '4h' | '1D' | '1W';

export interface Instrument {
  symbol: string;
  name: string;
  asset_class: AssetClass;
  exchange?: string;
  last_price?: number;
  last_updated?: string;
}

export interface WatchlistItem extends Instrument {
  id: string;
  pinned: boolean;
  added_at: string;
  change_pct?: number;
}

export interface Signal {
  id?: string;
  symbol: string;
  timeframe: Timeframe;
  timestamp: string;
  recommendation: Recommendation;
  confidence: number;
  entry_zone: { low: number; high: number };
  target_price: number;
  stop_loss: number;
  expected_time_to_target: string;
  expected_time_to_target_range: { min: string; max: string };
  reasoning: string[];
  is_hot: boolean;
  is_hot_confluence: boolean;
  indicators?: {
    rsi: number;
    macd: number;
    macd_signal: number;
    adx: number;
    atr: number;
    bb_pct_b: number;
    vol_zscore: number;
    ema20: number;
    ema50: number;
    ema200: number;
  };
}

export interface Candle {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface User {
  id: string;
  email: string;
  subscription_tier: 'free' | 'pro';
  settings: UserSettings;
}

export interface UserSettings {
  hot_pattern_threshold: number;
  hot_volume_zscore: number;
  atr_multiplier: number;
  quiet_hours_start: string;
  quiet_hours_end: string;
  daily_notification_cap: number;
  markets_enabled: AssetClass[];
  timeframes_enabled: Timeframe[];
  default_timeframe: Timeframe;
  theme: 'dark' | 'light' | 'system';
  selected_strategy?: string;
}
