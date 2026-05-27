import { configureStore } from '@reduxjs/toolkit';
import watchlistReducer from './watchlistSlice';
import signalReducer from './signalSlice';
import authReducer from './authSlice';

export const store = configureStore({
  reducer: {
    watchlist: watchlistReducer,
    signals: signalReducer,
    auth: authReducer,
  },
});

export type RootState = ReturnType<typeof store.getState>;
export type AppDispatch = typeof store.dispatch;
