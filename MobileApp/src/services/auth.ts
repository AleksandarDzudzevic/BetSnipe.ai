/**
 * Auth Service for BetSnipe.ai
 *
 * Handles Supabase authentication.
 */

import { createClient, SupabaseClient, User, Session } from '@supabase/supabase-js';
import Constants from 'expo-constants';
import * as SecureStore from 'expo-secure-store';

import { setAuthToken, clearAuthToken } from './api';

// Supabase Configuration
const SUPABASE_URL = Constants.expoConfig?.extra?.supabaseUrl || '';
const SUPABASE_ANON_KEY = Constants.expoConfig?.extra?.supabaseAnonKey || '';

// Custom storage adapter for Supabase using SecureStore
const ExpoSecureStoreAdapter = {
  getItem: async (key: string): Promise<string | null> => {
    try {
      return await SecureStore.getItemAsync(key);
    } catch (error) {
      console.warn('SecureStore getItem error:', error);
      return null;
    }
  },
  setItem: async (key: string, value: string): Promise<void> => {
    try {
      await SecureStore.setItemAsync(key, value);
    } catch (error) {
      console.warn('SecureStore setItem error:', error);
    }
  },
  removeItem: async (key: string): Promise<void> => {
    try {
      await SecureStore.deleteItemAsync(key);
    } catch (error) {
      console.warn('SecureStore removeItem error:', error);
    }
  },
};

// Create Supabase client
const supabase: SupabaseClient = createClient(SUPABASE_URL, SUPABASE_ANON_KEY, {
  auth: {
    storage: ExpoSecureStoreAdapter,
    autoRefreshToken: true,
    persistSession: true,
    detectSessionInUrl: false,
  },
});

export interface AuthResult {
  user: User | null;
  session: Session | null;
  error: Error | null;
}

class AuthService {
  private currentUser: User | null = null;
  private currentSession: Session | null = null;

  constructor() {
    // Listen for auth state changes
    supabase.auth.onAuthStateChange(async (event, session) => {
      console.log(`[Auth] State changed: ${event}`);
      this.currentSession = session;
      this.currentUser = session?.user ?? null;

      // Update API token
      if (session?.access_token) {
        await setAuthToken(session.access_token);
      } else {
        await clearAuthToken();
      }
    });
  }

  /**
   * Get the current session.
   */
  async getSession(): Promise<Session | null> {
    const { data, error } = await supabase.auth.getSession();
    if (error) {
      console.error('[Auth] Get session error:', error);
      return null;
    }
    this.currentSession = data.session;
    this.currentUser = data.session?.user ?? null;
    return data.session;
  }

  /**
   * Get the current user.
   */
  async getUser(): Promise<User | null> {
    const session = await this.getSession();
    return session?.user ?? null;
  }

  /**
   * Check if user is authenticated.
   */
  async isAuthenticated(): Promise<boolean> {
    const session = await this.getSession();
    return session !== null;
  }

  /**
   * Sign up with email and password.
   */
  async signUp(email: string, password: string): Promise<AuthResult> {
    try {
      const { data, error } = await supabase.auth.signUp({
        email,
        password,
      });

      if (error) {
        return { user: null, session: null, error };
      }

      return {
        user: data.user,
        session: data.session,
        error: null,
      };
    } catch (error) {
      return { user: null, session: null, error: error as Error };
    }
  }

  /**
   * Sign in with email and password.
   */
  async signIn(email: string, password: string): Promise<AuthResult> {
    try {
      const { data, error } = await supabase.auth.signInWithPassword({
        email,
        password,
      });

      if (error) {
        return { user: null, session: null, error };
      }

      return {
        user: data.user,
        session: data.session,
        error: null,
      };
    } catch (error) {
      return { user: null, session: null, error: error as Error };
    }
  }

  /**
   * Sign out.
   */
  async signOut(): Promise<void> {
    await supabase.auth.signOut();
    await clearAuthToken();
    this.currentUser = null;
    this.currentSession = null;
  }

  /**
   * Reset password.
   */
  async resetPassword(email: string): Promise<{ error: Error | null }> {
    const { error } = await supabase.auth.resetPasswordForEmail(email, {
      redirectTo: 'betsnipe://reset-password',
    });

    return { error: error as Error | null };
  }

  /**
   * Update password.
   */
  async updatePassword(newPassword: string): Promise<{ error: Error | null }> {
    const { error } = await supabase.auth.updateUser({
      password: newPassword,
    });

    return { error: error as Error | null };
  }

  /**
   * Update user email.
   */
  async updateEmail(newEmail: string): Promise<{ error: Error | null }> {
    const { error } = await supabase.auth.updateUser({
      email: newEmail,
    });

    return { error: error as Error | null };
  }

  /**
   * Get the current access token.
   */
  getAccessToken(): string | null {
    return this.currentSession?.access_token ?? null;
  }

  /**
   * Refresh the session.
   */
  async refreshSession(): Promise<Session | null> {
    const { data, error } = await supabase.auth.refreshSession();
    if (error) {
      console.error('[Auth] Refresh session error:', error);
      return null;
    }
    this.currentSession = data.session;
    return data.session;
  }
}

// Export singleton instance
export const auth = new AuthService();

// Export Supabase client for direct access if needed
export { supabase };

// Export class for testing
export { AuthService };
