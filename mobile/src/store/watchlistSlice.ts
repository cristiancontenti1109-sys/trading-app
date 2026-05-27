import { createSlice, createAsyncThunk, PayloadAction } from '@reduxjs/toolkit';
import { WatchlistItem } from '../types';
import * as api from '../services/api';

interface WatchlistState {
  items: WatchlistItem[];
  loading: boolean;
  prices: Record<string, { price: number; change_pct: number }>;
}

const initialState: WatchlistState = { items: [], loading: false, prices: {} };

export const fetchWatchlist = createAsyncThunk('watchlist/fetch', api.getWatchlist);
export const addSymbol = createAsyncThunk('watchlist/add', (symbol: string) => api.addToWatchlist(symbol));
export const removeSymbol = createAsyncThunk('watchlist/remove', (symbol: string) => {
  api.removeFromWatchlist(symbol);
  return symbol;
});

const watchlistSlice = createSlice({
  name: 'watchlist',
  initialState,
  reducers: {
    updatePrice: (state, action: PayloadAction<{ symbol: string; price: number; change_pct: number }>) => {
      state.prices[action.payload.symbol] = {
        price: action.payload.price,
        change_pct: action.payload.change_pct,
      };
    },
  },
  extraReducers: (builder) => {
    builder
      .addCase(fetchWatchlist.pending, (state) => { state.loading = true; })
      .addCase(fetchWatchlist.fulfilled, (state, action) => {
        state.loading = false;
        state.items = action.payload;
      })
      .addCase(addSymbol.fulfilled, (state, action) => {
        // Refetch will update the list
      })
      .addCase(removeSymbol.fulfilled, (state, action) => {
        state.items = state.items.filter((i) => i.symbol !== action.payload);
      });
  },
});

export const { updatePrice } = watchlistSlice.actions;
export default watchlistSlice.reducer;
