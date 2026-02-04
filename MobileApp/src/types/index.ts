/**
 * BetSnipe.ai Mobile App Types
 */

// ============================================
// API Response Types
// ============================================

export interface Sport {
  id: number;
  name: string;
  name_sr: string;
}

export interface Bookmaker {
  id: number;
  name: string;
  display_name: string;
  enabled: boolean;
}

export interface Odds {
  bookmaker_id: number;
  bookmaker_name: string;
  bet_type_id: number;
  bet_type_name: string;
  margin: number;
  odd1: number | null;
  odd2: number | null;
  odd3: number | null;
  updated_at: string;
}

export interface Match {
  id: number;
  team1: string;
  team2: string;
  sport_id: number;
  sport_name: string;
  start_time: string;
  status: 'upcoming' | 'live' | 'finished' | 'cancelled';
  odds: Odds[];
}

export interface MatchListResponse {
  matches: Match[];
  total: number;
  page: number;
  page_size: number;
}

export interface ArbitrageOdd {
  bookmaker_id: number;
  bookmaker_name: string;
  outcome: string;
  odd: number;
}

export interface Arbitrage {
  id: number;
  match_id: number;
  team1: string;
  team2: string;
  start_time: string;
  sport_name: string;
  bet_type_name: string;
  margin: number;
  profit_percentage: number;
  best_odds: ArbitrageOdd[];
  stakes: number[];
  is_active: boolean;
  detected_at: string;
}

export interface ArbitrageStats {
  active_count: number;
  total_today: number;
  avg_profit: number;
  max_profit: number;
  by_sport: Record<string, number>;
}

// ============================================
// User Types
// ============================================

export interface User {
  id: string;
  email: string | null;
  created_at: string | null;
}

export interface NotificationSettings {
  arbitrage_alerts: boolean;
  watchlist_odds_change: boolean;
  match_start_reminder: boolean;
  daily_summary: boolean;
  quiet_hours_start: string | null;
  quiet_hours_end: string | null;
}

export interface DisplaySettings {
  default_sport: number;
  odds_format: 'decimal' | 'american' | 'fractional';
  theme: 'light' | 'dark' | 'system';
}

export interface UserPreferences {
  min_profit_percentage: number;
  sports: number[];
  bookmakers: number[];
  notification_settings: NotificationSettings;
  display_settings: DisplaySettings;
  created_at: string;
  updated_at: string;
}

export interface WatchlistItem {
  id: number;
  match_id: number;
  notify_on_odds_change: boolean;
  odds_change_threshold: number;
  notes: string | null;
  created_at: string;
  team1: string;
  team2: string;
  start_time: string;
  match_status: string;
  sport_name: string;
  sport_id: number;
  league_name: string | null;
}

export interface Device {
  id: number;
  expo_push_token: string;
  platform: 'ios' | 'android';
  device_id: string | null;
  device_name: string | null;
  is_active: boolean;
  last_used_at: string;
  created_at: string;
}

// ============================================
// WebSocket Types
// ============================================

export type WebSocketMessageType =
  | 'odds_update'
  | 'arbitrage'
  | 'match_update'
  | 'connected'
  | 'error';

export interface WebSocketMessage {
  type: WebSocketMessageType;
  data: unknown;
  timestamp?: string;
}

export interface OddsUpdateMessage {
  type: 'odds_update';
  data: {
    match_id: number;
    bookmaker_id: number;
    odds: Partial<Odds>;
  };
}

export interface ArbitrageMessage {
  type: 'arbitrage';
  data: Arbitrage;
}

// ============================================
// Chart Types
// ============================================

export interface OddsTrendEntry {
  odd1: number | null;
  odd2: number | null;
  odd3: number | null;
  timestamp: string;
}

export interface BookmakerTrend {
  odd1_change: number | null;
  odd2_change: number | null;
  odd3_change: number | null;
  data_points: number;
}

export interface OddsTrends {
  match_id: number;
  bet_type_id: number;
  hours: number;
  history: Record<string, OddsTrendEntry[]>;
  movement: Record<string, BookmakerTrend>;
}

// ============================================
// Navigation Types
// ============================================

export type RootStackParamList = {
  '(tabs)': undefined;
  'match/[id]': { id: string };
  'arbitrage/[id]': { id: string };
  'settings': undefined;
  'login': undefined;
  'register': undefined;
};

// ============================================
// Store Types
// ============================================

export interface AuthState {
  user: User | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  checkAuth: () => Promise<void>;
}

export interface OddsState {
  matches: Match[];
  selectedMatch: Match | null;
  isLoading: boolean;
  error: string | null;
  fetchMatches: (sportId?: number) => Promise<void>;
  fetchMatch: (id: number) => Promise<void>;
  updateOdds: (matchId: number, odds: Partial<Odds>) => void;
}

export interface ArbitrageState {
  opportunities: Arbitrage[];
  stats: ArbitrageStats | null;
  isLoading: boolean;
  error: string | null;
  fetchOpportunities: (minProfit?: number, sportId?: number) => Promise<void>;
  fetchStats: () => Promise<void>;
}

export interface WebSocketState {
  isConnected: boolean;
  lastMessage: WebSocketMessage | null;
  connect: () => void;
  disconnect: () => void;
  subscribe: (channel: string) => void;
  unsubscribe: (channel: string) => void;
}
