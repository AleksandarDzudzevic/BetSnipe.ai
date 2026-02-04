/**
 * Auth Store for BetSnipe.ai
 *
 * Manages authentication state using Zustand.
 */

import { create } from 'zustand';
import { auth } from '@/services/auth';
import { notifications } from '@/services/notifications';
import { User } from '@/types';

interface AuthState {
  user: User | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  error: string | null;

  // Actions
  initialize: () => Promise<void>;
  login: (email: string, password: string) => Promise<boolean>;
  register: (email: string, password: string) => Promise<boolean>;
  logout: () => Promise<void>;
  clearError: () => void;
}

export const useAuthStore = create<AuthState>((set, get) => ({
  user: null,
  isLoading: true,
  isAuthenticated: false,
  error: null,

  initialize: async () => {
    set({ isLoading: true, error: null });

    try {
      const session = await auth.getSession();

      if (session?.user) {
        set({
          user: {
            id: session.user.id,
            email: session.user.email ?? null,
            created_at: session.user.created_at,
          },
          isAuthenticated: true,
          isLoading: false,
        });

        // Initialize push notifications after auth
        const token = await notifications.initialize();
        if (token) {
          await notifications.registerWithBackend();
        }
      } else {
        set({
          user: null,
          isAuthenticated: false,
          isLoading: false,
        });
      }
    } catch (error) {
      console.error('[AuthStore] Initialize error:', error);
      set({
        user: null,
        isAuthenticated: false,
        isLoading: false,
        error: 'Failed to initialize authentication',
      });
    }
  },

  login: async (email: string, password: string) => {
    set({ isLoading: true, error: null });

    try {
      const result = await auth.signIn(email, password);

      if (result.error) {
        set({
          isLoading: false,
          error: result.error.message,
        });
        return false;
      }

      if (result.user) {
        set({
          user: {
            id: result.user.id,
            email: result.user.email ?? null,
            created_at: result.user.created_at,
          },
          isAuthenticated: true,
          isLoading: false,
        });

        // Register device for push notifications
        const token = await notifications.initialize();
        if (token) {
          await notifications.registerWithBackend();
        }

        return true;
      }

      set({ isLoading: false });
      return false;
    } catch (error) {
      console.error('[AuthStore] Login error:', error);
      set({
        isLoading: false,
        error: 'Login failed. Please try again.',
      });
      return false;
    }
  },

  register: async (email: string, password: string) => {
    set({ isLoading: true, error: null });

    try {
      const result = await auth.signUp(email, password);

      if (result.error) {
        set({
          isLoading: false,
          error: result.error.message,
        });
        return false;
      }

      // If email confirmation is required, user won't be authenticated yet
      if (result.session && result.user) {
        set({
          user: {
            id: result.user.id,
            email: result.user.email ?? null,
            created_at: result.user.created_at,
          },
          isAuthenticated: true,
          isLoading: false,
        });
        return true;
      }

      set({ isLoading: false });
      return true; // Registration successful, but may need email confirmation
    } catch (error) {
      console.error('[AuthStore] Register error:', error);
      set({
        isLoading: false,
        error: 'Registration failed. Please try again.',
      });
      return false;
    }
  },

  logout: async () => {
    set({ isLoading: true });

    try {
      await auth.signOut();
      set({
        user: null,
        isAuthenticated: false,
        isLoading: false,
        error: null,
      });
    } catch (error) {
      console.error('[AuthStore] Logout error:', error);
      set({
        user: null,
        isAuthenticated: false,
        isLoading: false,
      });
    }
  },

  clearError: () => {
    set({ error: null });
  },
}));
