/**
 * API Client for BetSnipe.ai
 *
 * Handles all REST API communication with the backend.
 */

import axios, { AxiosInstance, AxiosError, InternalAxiosRequestConfig } from 'axios';
import Constants from 'expo-constants';
import * as SecureStore from 'expo-secure-store';

import {
  Match,
  MatchListResponse,
  Arbitrage,
  ArbitrageStats,
  Sport,
  Bookmaker,
  UserPreferences,
  WatchlistItem,
  Device,
  OddsTrends,
} from '@/types';

// API Configuration - Auto-detect in development
const getApiUrl = (): string => {
  const configuredUrl = Constants.expoConfig?.extra?.apiUrl;

  // If a real URL is configured (not "auto"), use it
  if (configuredUrl && configuredUrl !== 'auto' && configuredUrl.startsWith('http')) {
    return configuredUrl;
  }

  // Auto-detect from Expo debugger host in development
  const debuggerHost = Constants.expoConfig?.hostUri;
  if (debuggerHost) {
    const host = debuggerHost.split(':')[0];
    console.log(`[API] Auto-detected host: ${host}`);
    return `http://${host}:8000`;
  }

  return 'http://localhost:8000';
};

const API_URL = getApiUrl();
console.log(`[API] Using URL: ${API_URL}`);
const TOKEN_KEY = 'auth_token';

// Create axios instance
const api: AxiosInstance = axios.create({
  baseURL: API_URL,
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Request interceptor - add auth token
api.interceptors.request.use(
  async (config: InternalAxiosRequestConfig) => {
    try {
      const token = await SecureStore.getItemAsync(TOKEN_KEY);
      if (token && config.headers) {
        config.headers.Authorization = `Bearer ${token}`;
      }
    } catch (error) {
      console.warn('Failed to get auth token:', error);
    }
    return config;
  },
  (error: AxiosError) => Promise.reject(error)
);

// Response interceptor - handle errors
api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    if (error.response?.status === 401) {
      // Token expired or invalid
      await SecureStore.deleteItemAsync(TOKEN_KEY);
      // Could emit an event here for the auth store to handle
    }
    return Promise.reject(error);
  }
);

// ============================================
// Auth Token Management
// ============================================

export const setAuthToken = async (token: string): Promise<void> => {
  await SecureStore.setItemAsync(TOKEN_KEY, token);
};

export const clearAuthToken = async (): Promise<void> => {
  await SecureStore.deleteItemAsync(TOKEN_KEY);
};

export const getAuthToken = async (): Promise<string | null> => {
  return SecureStore.getItemAsync(TOKEN_KEY);
};

// ============================================
// Health & Stats
// ============================================

export const getHealth = async (): Promise<{ status: string; database: boolean; scraper_running: boolean }> => {
  const response = await api.get('/health');
  return response.data;
};

export const getStats = async (): Promise<{ database: Record<string, number>; engine: Record<string, number> }> => {
  const response = await api.get('/stats');
  return response.data;
};

// ============================================
// Sports & Bookmakers
// ============================================

export const getSports = async (): Promise<Sport[]> => {
  const response = await api.get('/api/sports');
  return response.data;
};

export const getBookmakers = async (): Promise<Bookmaker[]> => {
  const response = await api.get('/api/bookmakers');
  return response.data;
};

// ============================================
// Matches & Odds
// ============================================

export const getMatches = async (params?: {
  sport_id?: number;
  hours_ahead?: number;
  page?: number;
  page_size?: number;
}): Promise<MatchListResponse> => {
  const response = await api.get('/api/matches', { params });
  return response.data;
};

export const getMatch = async (matchId: number): Promise<Match> => {
  const response = await api.get(`/api/matches/${matchId}`);
  return response.data;
};

export const getMatchOddsHistory = async (
  matchId: number,
  params?: {
    bookmaker_id?: number;
    bet_type_id?: number;
    hours?: number;
  }
): Promise<{ match_id: number; team1: string; team2: string; history: unknown[] }> => {
  const response = await api.get(`/api/matches/${matchId}/odds-history`, { params });
  return response.data;
};

export const searchMatches = async (
  query: string,
  params?: {
    sport_id?: number;
    status?: string;
    limit?: number;
  }
): Promise<{ query: string; results: Match[]; total: number }> => {
  const response = await api.get('/api/search', { params: { q: query, ...params } });
  return response.data;
};

export const getOddsTrends = async (
  matchId: number,
  params?: {
    bet_type_id?: number;
    hours?: number;
  }
): Promise<OddsTrends> => {
  const response = await api.get(`/api/odds/trends/${matchId}`, { params });
  return response.data;
};

export const getBestOdds = async (params?: {
  sport_id?: number;
  bet_type_id?: number;
  limit?: number;
}): Promise<{ best_odds: unknown[] }> => {
  const response = await api.get('/api/odds/best', { params });
  return response.data;
};

// ============================================
// Arbitrage
// ============================================

export const getArbitrageOpportunities = async (params?: {
  min_profit?: number;
  sport_id?: number;
  limit?: number;
}): Promise<Arbitrage[]> => {
  const response = await api.get('/api/arbitrage', { params });
  // API returns { opportunities: [...], total: N }
  return response.data.opportunities || [];
};

export const getArbitrageById = async (id: number): Promise<Arbitrage> => {
  const response = await api.get(`/api/arbitrage/${id}`);
  return response.data;
};

export const getArbitrageStats = async (): Promise<ArbitrageStats> => {
  const response = await api.get('/api/arbitrage/stats');
  return response.data;
};

export const calculateArbitrage = async (odds: {
  odd1: number;
  odd2: number;
  odd3?: number;
  stake?: number;
}): Promise<{
  is_arbitrage: boolean;
  profit_percentage: number;
  stakes: number[];
}> => {
  const response = await api.post('/api/arbitrage/calculate', odds);
  return response.data;
};

// ============================================
// User Profile & Auth
// ============================================

export const getCurrentUser = async (): Promise<{
  id: string;
  email: string | null;
  preferences: UserPreferences | null;
  device_count: number;
  watchlist_count: number;
}> => {
  const response = await api.get('/api/auth/me');
  return response.data;
};

export const registerDevice = async (device: {
  expo_push_token: string;
  platform: 'ios' | 'android';
  device_id?: string;
  device_name?: string;
}): Promise<Device> => {
  const response = await api.post('/api/auth/register-device', device);
  return response.data;
};

export const getDevices = async (): Promise<Device[]> => {
  const response = await api.get('/api/auth/devices');
  return response.data;
};

export const unregisterDevice = async (deviceId: number): Promise<void> => {
  await api.delete(`/api/auth/devices/${deviceId}`);
};

export const testDeviceNotification = async (deviceId: number): Promise<void> => {
  await api.post(`/api/auth/devices/${deviceId}/test`);
};

// ============================================
// User Preferences
// ============================================

export const getPreferences = async (): Promise<UserPreferences> => {
  const response = await api.get('/api/user/preferences');
  return response.data;
};

export const updatePreferences = async (preferences: Partial<UserPreferences>): Promise<UserPreferences> => {
  const response = await api.put('/api/user/preferences', preferences);
  return response.data;
};

// ============================================
// Watchlist
// ============================================

export const getWatchlist = async (params?: {
  sport_id?: number;
  status?: string;
}): Promise<WatchlistItem[]> => {
  const response = await api.get('/api/user/watchlist', { params });
  return response.data;
};

export const addToWatchlist = async (item: {
  match_id: number;
  notify_on_odds_change?: boolean;
  odds_change_threshold?: number;
  notes?: string;
}): Promise<WatchlistItem> => {
  const response = await api.post('/api/user/watchlist', item);
  return response.data;
};

export const removeFromWatchlist = async (matchId: number): Promise<void> => {
  await api.delete(`/api/user/watchlist/${matchId}`);
};

export const updateWatchlistItem = async (
  matchId: number,
  item: {
    notify_on_odds_change?: boolean;
    odds_change_threshold?: number;
    notes?: string;
  }
): Promise<WatchlistItem> => {
  const response = await api.put(`/api/user/watchlist/${matchId}`, item);
  return response.data;
};

// ============================================
// Arbitrage History
// ============================================

export const getArbitrageHistory = async (params?: {
  action?: string;
  limit?: number;
  offset?: number;
}): Promise<unknown[]> => {
  const response = await api.get('/api/user/arbitrage-history', { params });
  return response.data;
};

export const recordArbitrageAction = async (
  arbitrageId: number,
  action: 'viewed' | 'saved' | 'executed' | 'dismissed',
  notes?: string
): Promise<unknown> => {
  const response = await api.post('/api/user/arbitrage-history', null, {
    params: { arbitrage_id: arbitrageId, action, notes },
  });
  return response.data;
};

export const getArbitrageHistoryStats = async (): Promise<{
  by_action: Record<string, number>;
  total: number;
  avg_profit_viewed: number;
  last_7_days: number;
}> => {
  const response = await api.get('/api/user/arbitrage-history/stats');
  return response.data;
};

export default api;
