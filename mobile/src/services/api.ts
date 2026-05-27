import axios from 'axios';
import { saveItem, getItem, deleteItem } from './storage';
import { Signal, WatchlistItem, Instrument, Candle, User } from '../types';

const BASE_URL = __DEV__ ? 'http://localhost:8000' : 'https://api.tradingsignals.app';

const api = axios.create({ baseURL: BASE_URL, timeout: 15000 });

api.interceptors.request.use(async (config) => {
  const token = await getItem('auth_token');
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

// Auth
export const login = async (email: string, password: string) => {
  const form = new FormData();
  form.append('username', email);
  form.append('password', password);
  const { data } = await api.post('/auth/login', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  await saveItem('auth_token', data.access_token);
  return data;
};

export const register = async (email: string, password: string) => {
  const { data } = await api.post('/auth/register', { email, password });
  await saveItem('auth_token', data.access_token);
  return data;
};

export const getMe = async (): Promise<User> => {
  const { data } = await api.get('/auth/me');
  return data;
};

export const updateSettings = async (settings: Partial<User['settings']>) => {
  const { data } = await api.patch('/auth/settings', settings);
  return data;
};

export const updatePushToken = async (token: string) => {
  await api.patch('/auth/push-token', { token });
};

export const logout = async () => {
  await deleteItem('auth_token');
};

// Watchlist
export const getWatchlist = async (): Promise<WatchlistItem[]> => {
  const { data } = await api.get('/watchlist/');
  return data;
};

export const addToWatchlist = async (symbol: string, pinned = false) => {
  const { data } = await api.post('/watchlist/', { symbol, pinned });
  return data;
};

export const removeFromWatchlist = async (symbol: string) => {
  await api.delete(`/watchlist/${symbol}`);
};

export const togglePin = async (symbol: string) => {
  const { data } = await api.patch(`/watchlist/${symbol}/pin`);
  return data;
};

export const searchInstruments = async (q: string): Promise<Instrument[]> => {
  const { data } = await api.get('/watchlist/search', { params: { q } });
  return data;
};

// Signals
export const getSignal = async (symbol: string, timeframe = '4h'): Promise<Signal> => {
  const { data } = await api.get(`/signals/${symbol}`, { params: { timeframe } });
  return data;
};

export const getSignalHistory = async (symbol: string, timeframe = '4h', limit = 30): Promise<Signal[]> => {
  const { data } = await api.get(`/signals/${symbol}/history`, { params: { timeframe, limit } });
  return data;
};

export const getOHLCV = async (symbol: string, timeframe = '4h', limit = 200): Promise<{ candles: Candle[] }> => {
  const { data } = await api.get(`/signals/${symbol}/ohlcv`, { params: { timeframe, limit } });
  return data;
};

// Instruments
export const getInstrument = async (symbol: string): Promise<Instrument> => {
  const { data } = await api.get(`/instruments/${symbol}`);
  return data;
};
