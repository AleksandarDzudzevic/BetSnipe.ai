/**
 * Arbitrage Store for BetSnipe.ai
 *
 * Manages arbitrage opportunities state using Zustand.
 */

import { create } from 'zustand';
import {
  getArbitrageOpportunities,
  getArbitrageById,
  getArbitrageStats,
  recordArbitrageAction,
} from '@/services/api';
import { websocket } from '@/services/websocket';
import { Arbitrage, ArbitrageStats, WebSocketMessage } from '@/types';

interface ArbitrageState {
  opportunities: Arbitrage[];
  selectedArbitrage: Arbitrage | null;
  stats: ArbitrageStats | null;
  isLoading: boolean;
  error: string | null;
  minProfitFilter: number;
  sportFilter: number | null;

  // Actions
  fetchOpportunities: (minProfit?: number, sportId?: number) => Promise<void>;
  fetchArbitrage: (id: number) => Promise<void>;
  fetchStats: () => Promise<void>;
  recordAction: (
    id: number,
    action: 'viewed' | 'saved' | 'executed' | 'dismissed',
    notes?: string
  ) => Promise<void>;
  addOpportunity: (arb: Arbitrage) => void;
  setMinProfitFilter: (minProfit: number) => void;
  setSportFilter: (sportId: number | null) => void;
  subscribeToUpdates: () => () => void;
}

export const useArbitrageStore = create<ArbitrageState>((set, get) => ({
  opportunities: [],
  selectedArbitrage: null,
  stats: null,
  isLoading: false,
  error: null,
  minProfitFilter: 1.0,
  sportFilter: null,

  fetchOpportunities: async (minProfit?: number, sportId?: number) => {
    set({ isLoading: true, error: null });

    const profit = minProfit ?? get().minProfitFilter;
    const sport = sportId ?? get().sportFilter;

    try {
      const opportunities = await getArbitrageOpportunities({
        min_profit: profit,
        sport_id: sport ?? undefined,
        limit: 50,
      });

      set({
        opportunities,
        isLoading: false,
      });
    } catch (error) {
      console.error('[ArbitrageStore] Fetch opportunities error:', error);
      set({
        isLoading: false,
        error: 'Failed to load arbitrage opportunities',
      });
    }
  },

  fetchArbitrage: async (id: number) => {
    set({ isLoading: true, error: null });

    try {
      const arb = await getArbitrageById(id);
      set({
        selectedArbitrage: arb,
        isLoading: false,
      });

      // Record view action
      get().recordAction(id, 'viewed');
    } catch (error) {
      console.error('[ArbitrageStore] Fetch arbitrage error:', error);
      set({
        isLoading: false,
        error: 'Failed to load arbitrage details',
      });
    }
  },

  fetchStats: async () => {
    try {
      const stats = await getArbitrageStats();
      set({ stats });
    } catch (error) {
      console.error('[ArbitrageStore] Fetch stats error:', error);
    }
  },

  recordAction: async (id, action, notes) => {
    try {
      await recordArbitrageAction(id, action, notes);
    } catch (error) {
      console.error('[ArbitrageStore] Record action error:', error);
    }
  },

  addOpportunity: (arb: Arbitrage) => {
    const { opportunities, minProfitFilter, sportFilter } = get();

    // Check if it passes filters
    if (arb.profit_percentage < minProfitFilter) return;
    if (sportFilter && arb.sport_name !== String(sportFilter)) return;

    // Check if already exists
    const exists = opportunities.some((o) => o.id === arb.id);
    if (exists) return;

    // Add to beginning of list
    set({
      opportunities: [arb, ...opportunities],
    });
  },

  setMinProfitFilter: (minProfit: number) => {
    set({ minProfitFilter: minProfit });
    get().fetchOpportunities(minProfit);
  },

  setSportFilter: (sportId: number | null) => {
    set({ sportFilter: sportId });
    get().fetchOpportunities(undefined, sportId ?? undefined);
  },

  subscribeToUpdates: () => {
    // Connect to WebSocket
    websocket.connect('/ws/arbitrage');

    // Handle incoming arbitrage messages
    const unsubscribe = websocket.onMessage((message: WebSocketMessage) => {
      if (message.type === 'arbitrage') {
        const arb = message.data as Arbitrage;
        get().addOpportunity(arb);
      }
    });

    // Return cleanup function
    return () => {
      unsubscribe();
    };
  },
}));
