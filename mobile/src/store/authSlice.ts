import { createSlice, createAsyncThunk } from '@reduxjs/toolkit';
import { User } from '../types';
import * as api from '../services/api';

interface AuthState {
  user: User | null;
  loading: boolean;
  error: string | null;
}

const initialState: AuthState = { user: null, loading: false, error: null };

export const fetchMe = createAsyncThunk('auth/me', api.getMe);
export const loginUser = createAsyncThunk('auth/login', ({ email, password }: { email: string; password: string }) =>
  api.login(email, password),
);
export const registerUser = createAsyncThunk('auth/register', ({ email, password }: { email: string; password: string }) =>
  api.register(email, password),
);

const authSlice = createSlice({
  name: 'auth',
  initialState,
  reducers: {
    logout: (state) => {
      state.user = null;
      api.logout();
    },
  },
  extraReducers: (builder) => {
    builder
      .addCase(fetchMe.fulfilled, (state, action) => { state.user = action.payload; })
      .addCase(loginUser.fulfilled, (state) => { state.loading = false; })
      .addCase(loginUser.pending, (state) => { state.loading = true; state.error = null; })
      .addCase(loginUser.rejected, (state, action) => { state.loading = false; state.error = action.error.message || 'Login failed'; });
  },
});

export const { logout } = authSlice.actions;
export default authSlice.reducer;
