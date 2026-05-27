import { createSlice, createAsyncThunk, PayloadAction } from '@reduxjs/toolkit';
import { Signal, Timeframe } from '../types';
import * as api from '../services/api';

interface SignalState {
  signals: Record<string, Signal>;  // key: symbol+timeframe
  loading: Record<string, boolean>;
  error: Record<string, string>;
}

const initialState: SignalState = { signals: {}, loading: {}, error: {} };

export const fetchSignal = createAsyncThunk(
  'signals/fetch',
  ({ symbol, timeframe }: { symbol: string; timeframe: Timeframe }) =>
    api.getSignal(symbol, timeframe).then((s) => ({ key: `${symbol}_${timeframe}`, signal: s })),
);

const signalSlice = createSlice({
  name: 'signals',
  initialState,
  reducers: {
    updateSignal: (state, action: PayloadAction<{ symbol: string; signal: Signal }>) => {
      const key = `${action.payload.symbol}_${action.payload.signal.timeframe}`;
      state.signals[key] = action.payload.signal;
    },
  },
  extraReducers: (builder) => {
    builder
      .addCase(fetchSignal.pending, (state, action) => {
        const key = `${action.meta.arg.symbol}_${action.meta.arg.timeframe}`;
        state.loading[key] = true;
        delete state.error[key];
      })
      .addCase(fetchSignal.fulfilled, (state, action) => {
        state.loading[action.payload.key] = false;
        state.signals[action.payload.key] = action.payload.signal;
      })
      .addCase(fetchSignal.rejected, (state, action) => {
        const key = `${action.meta.arg.symbol}_${action.meta.arg.timeframe}`;
        state.loading[key] = false;
        state.error[key] = action.error.message || 'Failed to fetch signal';
      });
  },
});

export const { updateSignal } = signalSlice.actions;
export default signalSlice.reducer;
