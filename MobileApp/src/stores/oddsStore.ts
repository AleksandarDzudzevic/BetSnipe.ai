/**
 * Odds Store for BetSnipe.ai
 *
 * Manages matches and odds state using Zustand.
 */

import { create } from 'zustand';
import { getMatches, getMatch, searchMatches } from '@/services/api';
import { websocket } from '@/services/websocket';
import { Match, Odds, WebSocketMessage } from '@/types';

interface OddsState {
  matches: Match[];
  selectedMatch: Match | null;
  isLoading: boolean;
  error: string | null;
  currentSportId: number | null;
  searchQuery: string;
  searchResults: Match[];

  // Actions
  fetchMatches: (sportId?: number, page?: number) => Promise<void>;
  fetchMatch: (id: number) => Promise<void>;
  search: (query: string, sportId?: number) => Promise<void>;
  updateOdds: (matchId: number, bookmarkerId: number, odds: Partial<Odds>) => void;
  setSportFilter: (sportId: number | null) => void;
  clearSearch: () => void;
  subscribeToUpdates: () => () => void;
}

export const useOddsStore = create<OddsState>((set, get) => ({
  matches: [],
  selectedMatch: null,
  isLoading: false,
  error: null,
  currentSportId: null,
  searchQuery: '',
  searchResults: [],

  fetchMatches: async (sportId?: number, page = 1) => {
    set({ isLoading: true, error: null });

    try {
      const response = await getMatches({
        sport_id: sportId,
        hours_ahead: 24,
        page,
        page_size: 50,
      });

      set({
        matches: response.matches,
        currentSportId: sportId ?? null,
        isLoading: false,
      });
    } catch (error) {
      console.error('[OddsStore] Fetch matches error:', error);
      set({
        isLoading: false,
        error: 'Failed to load matches',
      });
    }
  },

  fetchMatch: async (id: number) => {
    set({ isLoading: true, error: null });

    try {
      const match = await getMatch(id);
      set({
        selectedMatch: match,
        isLoading: false,
      });
    } catch (error) {
      console.error('[OddsStore] Fetch match error:', error);
      set({
        isLoading: false,
        error: 'Failed to load match details',
      });
    }
  },

  search: async (query: string, sportId?: number) => {
    if (!query.trim()) {
      set({ searchResults: [], searchQuery: '' });
      return;
    }

    set({ isLoading: true, searchQuery: query });

    try {
      const response = await searchMatches(query, {
        sport_id: sportId,
        limit: 20,
      });

      set({
        searchResults: response.results,
        isLoading: false,
      });
    } catch (error) {
      console.error('[OddsStore] Search error:', error);
      set({
        isLoading: false,
        error: 'Search failed',
      });
    }
  },

  updateOdds: (matchId: number, bookmakerId: number, newOdds: Partial<Odds>) => {
    const { matches, selectedMatch } = get();

    // Update in matches list
    const updatedMatches = matches.map((match) => {
      if (match.id !== matchId) return match;

      const updatedOdds = match.odds.map((odd) => {
        if (odd.bookmaker_id !== bookmakerId) return odd;
        return { ...odd, ...newOdds };
      });

      return { ...match, odds: updatedOdds };
    });

    set({ matches: updatedMatches });

    // Update selected match if it's the same
    if (selectedMatch?.id === matchId) {
      const updatedSelectedOdds = selectedMatch.odds.map((odd) => {
        if (odd.bookmaker_id !== bookmakerId) return odd;
        return { ...odd, ...newOdds };
      });

      set({
        selectedMatch: { ...selectedMatch, odds: updatedSelectedOdds },
      });
    }
  },

  setSportFilter: (sportId: number | null) => {
    set({ currentSportId: sportId });
    get().fetchMatches(sportId ?? undefined);
  },

  clearSearch: () => {
    set({ searchQuery: '', searchResults: [] });
  },

  subscribeToUpdates: () => {
    // Connect to WebSocket
    websocket.connect();

    // Subscribe to odds updates
    websocket.subscribe('odds');

    // Handle incoming messages
    const unsubscribe = websocket.onMessage((message: WebSocketMessage) => {
      if (message.type === 'odds_update') {
        const data = message.data as {
          match_id: number;
          bookmaker_id: number;
          odds: Partial<Odds>;
        };
        get().updateOdds(data.match_id, data.bookmaker_id, data.odds);
      }
    });

    // Return cleanup function
    return () => {
      unsubscribe();
      websocket.unsubscribe('odds');
    };
  },
}));
