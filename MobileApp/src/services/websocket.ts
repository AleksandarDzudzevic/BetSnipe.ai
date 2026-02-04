/**
 * WebSocket Service for BetSnipe.ai
 *
 * Handles real-time communication with the backend.
 */

import Constants from 'expo-constants';
import { AppState, AppStateStatus } from 'react-native';

import { WebSocketMessage } from '@/types';

// WebSocket Configuration - Auto-detect in development
const getApiUrl = (): string => {
  const configuredUrl = Constants.expoConfig?.extra?.apiUrl;

  if (configuredUrl && configuredUrl !== 'auto' && configuredUrl.startsWith('http')) {
    return configuredUrl;
  }

  const debuggerHost = Constants.expoConfig?.hostUri;
  if (debuggerHost) {
    const host = debuggerHost.split(':')[0];
    return `http://${host}:8000`;
  }

  return 'http://localhost:8000';
};

const API_URL = getApiUrl();
const WS_URL = API_URL.replace('http', 'ws');
console.log(`[WebSocket] Using URL: ${WS_URL}`);

type MessageHandler = (message: WebSocketMessage) => void;
type ConnectionHandler = (isConnected: boolean) => void;

class WebSocketService {
  private socket: WebSocket | null = null;
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 5;
  private reconnectDelay = 1000;
  private messageHandlers: Set<MessageHandler> = new Set();
  private connectionHandlers: Set<ConnectionHandler> = new Set();
  private subscriptions: Set<string> = new Set();
  private pingInterval: ReturnType<typeof setInterval> | null = null;
  private appStateSubscription: ReturnType<typeof AppState.addEventListener> | null = null;

  constructor() {
    // Listen for app state changes
    this.appStateSubscription = AppState.addEventListener('change', this.handleAppStateChange);
  }

  private handleAppStateChange = (nextAppState: AppStateStatus) => {
    if (nextAppState === 'active' && !this.isConnected()) {
      // App came to foreground, reconnect if needed
      this.connect();
    } else if (nextAppState === 'background') {
      // App went to background, could optionally disconnect
      // For now, keep connection alive
    }
  };

  /**
   * Connect to the WebSocket server.
   */
  connect(endpoint: string = '/ws'): void {
    if (this.socket?.readyState === WebSocket.OPEN) {
      return;
    }

    const url = `${WS_URL}${endpoint}`;
    console.log(`[WebSocket] Connecting to ${url}`);

    try {
      this.socket = new WebSocket(url);

      this.socket.onopen = () => {
        console.log('[WebSocket] Connected');
        this.reconnectAttempts = 0;
        this.notifyConnectionChange(true);
        this.startPing();

        // Re-subscribe to channels
        this.subscriptions.forEach((channel) => {
          this.sendMessage({ action: 'subscribe', channel });
        });
      };

      this.socket.onmessage = (event) => {
        try {
          const message: WebSocketMessage = JSON.parse(event.data);
          this.notifyMessage(message);
        } catch (error) {
          console.warn('[WebSocket] Failed to parse message:', error);
        }
      };

      this.socket.onerror = (error) => {
        console.error('[WebSocket] Error:', error);
      };

      this.socket.onclose = (event) => {
        console.log(`[WebSocket] Disconnected: ${event.code} - ${event.reason}`);
        this.stopPing();
        this.notifyConnectionChange(false);
        this.handleReconnect();
      };
    } catch (error) {
      console.error('[WebSocket] Connection failed:', error);
      this.handleReconnect();
    }
  }

  /**
   * Disconnect from the WebSocket server.
   */
  disconnect(): void {
    this.reconnectAttempts = this.maxReconnectAttempts; // Prevent reconnection
    this.stopPing();

    if (this.socket) {
      this.socket.close(1000, 'Client disconnect');
      this.socket = null;
    }
  }

  /**
   * Check if connected.
   */
  isConnected(): boolean {
    return this.socket?.readyState === WebSocket.OPEN;
  }

  /**
   * Subscribe to a channel.
   */
  subscribe(channel: string): void {
    this.subscriptions.add(channel);

    if (this.isConnected()) {
      this.sendMessage({ action: 'subscribe', channel });
    }
  }

  /**
   * Unsubscribe from a channel.
   */
  unsubscribe(channel: string): void {
    this.subscriptions.delete(channel);

    if (this.isConnected()) {
      this.sendMessage({ action: 'unsubscribe', channel });
    }
  }

  /**
   * Send a message to the server.
   */
  sendMessage(message: Record<string, unknown>): void {
    if (!this.isConnected()) {
      console.warn('[WebSocket] Cannot send message - not connected');
      return;
    }

    try {
      this.socket?.send(JSON.stringify(message));
    } catch (error) {
      console.error('[WebSocket] Failed to send message:', error);
    }
  }

  /**
   * Register a message handler.
   */
  onMessage(handler: MessageHandler): () => void {
    this.messageHandlers.add(handler);
    return () => this.messageHandlers.delete(handler);
  }

  /**
   * Register a connection status handler.
   */
  onConnectionChange(handler: ConnectionHandler): () => void {
    this.connectionHandlers.add(handler);
    return () => this.connectionHandlers.delete(handler);
  }

  /**
   * Clean up resources.
   */
  destroy(): void {
    this.disconnect();
    this.messageHandlers.clear();
    this.connectionHandlers.clear();
    this.subscriptions.clear();
    this.appStateSubscription?.remove();
  }

  // Private methods

  private handleReconnect(): void {
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      console.log('[WebSocket] Max reconnection attempts reached');
      return;
    }

    const delay = this.reconnectDelay * Math.pow(2, this.reconnectAttempts);
    this.reconnectAttempts++;

    console.log(`[WebSocket] Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts})`);

    setTimeout(() => {
      if (AppState.currentState === 'active') {
        this.connect();
      }
    }, delay);
  }

  private notifyMessage(message: WebSocketMessage): void {
    this.messageHandlers.forEach((handler) => {
      try {
        handler(message);
      } catch (error) {
        console.error('[WebSocket] Message handler error:', error);
      }
    });
  }

  private notifyConnectionChange(isConnected: boolean): void {
    this.connectionHandlers.forEach((handler) => {
      try {
        handler(isConnected);
      } catch (error) {
        console.error('[WebSocket] Connection handler error:', error);
      }
    });
  }

  private startPing(): void {
    this.stopPing();
    this.pingInterval = setInterval(() => {
      if (this.isConnected()) {
        this.sendMessage({ action: 'ping' });
      }
    }, 30000);
  }

  private stopPing(): void {
    if (this.pingInterval) {
      clearInterval(this.pingInterval);
      this.pingInterval = null;
    }
  }
}

// Export singleton instance
export const websocket = new WebSocketService();

// Export class for testing
export { WebSocketService };
