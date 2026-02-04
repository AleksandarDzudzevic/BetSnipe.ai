/**
 * Push Notifications Service for BetSnipe.ai
 *
 * Handles Expo push notification registration and handling.
 */

import * as Notifications from 'expo-notifications';
import * as Device from 'expo-device';
import { Platform } from 'react-native';
import Constants from 'expo-constants';

import { registerDevice } from './api';

// Configure notification behavior
Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowAlert: true,
    shouldPlaySound: true,
    shouldSetBadge: true,
  }),
});

type NotificationHandler = (notification: Notifications.Notification) => void;
type ResponseHandler = (response: Notifications.NotificationResponse) => void;

class NotificationService {
  private expoPushToken: string | null = null;
  private notificationListener: Notifications.Subscription | null = null;
  private responseListener: Notifications.Subscription | null = null;
  private notificationHandlers: Set<NotificationHandler> = new Set();
  private responseHandlers: Set<ResponseHandler> = new Set();

  /**
   * Initialize push notifications.
   */
  async initialize(): Promise<string | null> {
    if (!Device.isDevice) {
      console.warn('[Notifications] Must use physical device for push notifications');
      return null;
    }

    // Request permissions
    const { status: existingStatus } = await Notifications.getPermissionsAsync();
    let finalStatus = existingStatus;

    if (existingStatus !== 'granted') {
      const { status } = await Notifications.requestPermissionsAsync();
      finalStatus = status;
    }

    if (finalStatus !== 'granted') {
      console.warn('[Notifications] Permission not granted');
      return null;
    }

    // Get push token
    try {
      const projectId = Constants.expoConfig?.extra?.eas?.projectId;
      const tokenData = await Notifications.getExpoPushTokenAsync({
        projectId,
      });
      this.expoPushToken = tokenData.data;
      console.log('[Notifications] Push token:', this.expoPushToken);
    } catch (error) {
      console.error('[Notifications] Failed to get push token:', error);
      return null;
    }

    // Configure Android channel
    if (Platform.OS === 'android') {
      await this.setupAndroidChannels();
    }

    // Set up listeners
    this.setupListeners();

    return this.expoPushToken;
  }

  /**
   * Register device with the backend.
   */
  async registerWithBackend(): Promise<boolean> {
    if (!this.expoPushToken) {
      console.warn('[Notifications] No push token available');
      return false;
    }

    try {
      await registerDevice({
        expo_push_token: this.expoPushToken,
        platform: Platform.OS as 'ios' | 'android',
        device_id: Constants.deviceId ?? undefined,
        device_name: Device.deviceName ?? undefined,
      });
      console.log('[Notifications] Device registered with backend');
      return true;
    } catch (error) {
      console.error('[Notifications] Failed to register device:', error);
      return false;
    }
  }

  /**
   * Get the current push token.
   */
  getPushToken(): string | null {
    return this.expoPushToken;
  }

  /**
   * Register a handler for received notifications.
   */
  onNotificationReceived(handler: NotificationHandler): () => void {
    this.notificationHandlers.add(handler);
    return () => this.notificationHandlers.delete(handler);
  }

  /**
   * Register a handler for notification responses (taps).
   */
  onNotificationResponse(handler: ResponseHandler): () => void {
    this.responseHandlers.add(handler);
    return () => this.responseHandlers.delete(handler);
  }

  /**
   * Schedule a local notification.
   */
  async scheduleLocalNotification(
    title: string,
    body: string,
    data?: Record<string, unknown>,
    trigger?: Notifications.NotificationTriggerInput
  ): Promise<string> {
    return Notifications.scheduleNotificationAsync({
      content: {
        title,
        body,
        data: data ?? {},
        sound: true,
      },
      trigger: trigger ?? null, // null = immediate
    });
  }

  /**
   * Cancel a scheduled notification.
   */
  async cancelNotification(notificationId: string): Promise<void> {
    await Notifications.cancelScheduledNotificationAsync(notificationId);
  }

  /**
   * Cancel all scheduled notifications.
   */
  async cancelAllNotifications(): Promise<void> {
    await Notifications.cancelAllScheduledNotificationsAsync();
  }

  /**
   * Set badge count (iOS only).
   */
  async setBadgeCount(count: number): Promise<void> {
    await Notifications.setBadgeCountAsync(count);
  }

  /**
   * Get badge count.
   */
  async getBadgeCount(): Promise<number> {
    return Notifications.getBadgeCountAsync();
  }

  /**
   * Dismiss all notifications.
   */
  async dismissAllNotifications(): Promise<void> {
    await Notifications.dismissAllNotificationsAsync();
  }

  /**
   * Clean up resources.
   */
  destroy(): void {
    this.notificationListener?.remove();
    this.responseListener?.remove();
    this.notificationHandlers.clear();
    this.responseHandlers.clear();
  }

  // Private methods

  private async setupAndroidChannels(): Promise<void> {
    // Main channel
    await Notifications.setNotificationChannelAsync('default', {
      name: 'Default',
      importance: Notifications.AndroidImportance.HIGH,
      vibrationPattern: [0, 250, 250, 250],
      lightColor: '#4361ee',
    });

    // Arbitrage alerts (high priority)
    await Notifications.setNotificationChannelAsync('arbitrage', {
      name: 'Arbitrage Alerts',
      description: 'Alerts for new arbitrage opportunities',
      importance: Notifications.AndroidImportance.MAX,
      vibrationPattern: [0, 500, 250, 500],
      lightColor: '#22c55e',
      sound: 'default',
    });

    // Watchlist updates
    await Notifications.setNotificationChannelAsync('watchlist', {
      name: 'Watchlist Updates',
      description: 'Odds changes for watched matches',
      importance: Notifications.AndroidImportance.DEFAULT,
      lightColor: '#3b82f6',
    });

    // Match reminders
    await Notifications.setNotificationChannelAsync('reminder', {
      name: 'Match Reminders',
      description: 'Reminders before matches start',
      importance: Notifications.AndroidImportance.DEFAULT,
      lightColor: '#f59e0b',
    });
  }

  private setupListeners(): void {
    // Listen for notifications received while app is foregrounded
    this.notificationListener = Notifications.addNotificationReceivedListener((notification) => {
      console.log('[Notifications] Received:', notification);
      this.notificationHandlers.forEach((handler) => {
        try {
          handler(notification);
        } catch (error) {
          console.error('[Notifications] Handler error:', error);
        }
      });
    });

    // Listen for notification responses (user taps)
    this.responseListener = Notifications.addNotificationResponseReceivedListener((response) => {
      console.log('[Notifications] Response:', response);
      this.responseHandlers.forEach((handler) => {
        try {
          handler(response);
        } catch (error) {
          console.error('[Notifications] Response handler error:', error);
        }
      });
    });
  }
}

// Export singleton instance
export const notifications = new NotificationService();

// Export class for testing
export { NotificationService };
