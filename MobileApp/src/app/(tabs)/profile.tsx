/**
 * Profile Screen for BetSnipe.ai
 */

import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  Switch,
  useColorScheme,
  Alert,
} from 'react-native';
import { Link, router } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { useQuery } from '@tanstack/react-query';

import { useAuthStore } from '@/stores';
import { getCurrentUser, getPreferences } from '@/services/api';

export default function ProfileScreen() {
  const colorScheme = useColorScheme();
  const isDark = colorScheme === 'dark';
  const { isAuthenticated, user, logout } = useAuthStore();

  // Fetch user profile if authenticated
  const { data: profile } = useQuery({
    queryKey: ['userProfile'],
    queryFn: getCurrentUser,
    enabled: isAuthenticated,
  });

  // Fetch preferences if authenticated
  const { data: preferences } = useQuery({
    queryKey: ['userPreferences'],
    queryFn: getPreferences,
    enabled: isAuthenticated,
  });

  const handleLogout = () => {
    Alert.alert(
      'Sign Out',
      'Are you sure you want to sign out?',
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Sign Out',
          style: 'destructive',
          onPress: async () => {
            await logout();
          },
        },
      ]
    );
  };

  const styles = createStyles(isDark);

  if (!isAuthenticated) {
    return (
      <View style={styles.container}>
        <View style={styles.authPrompt}>
          <Ionicons name="person-circle" size={80} color={isDark ? '#6c757d' : '#adb5bd'} />
          <Text style={styles.authTitle}>Sign In to BetSnipe</Text>
          <Text style={styles.authText}>
            Create an account to save your preferences, get personalized alerts, and track your arbitrage history.
          </Text>
          <Link href="/login" asChild>
            <TouchableOpacity style={styles.authButton}>
              <Text style={styles.authButtonText}>Sign In</Text>
            </TouchableOpacity>
          </Link>
        </View>
      </View>
    );
  }

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      {/* Profile Header */}
      <View style={styles.profileHeader}>
        <View style={styles.avatar}>
          <Text style={styles.avatarText}>
            {user?.email?.[0].toUpperCase() || 'U'}
          </Text>
        </View>
        <Text style={styles.email}>{user?.email}</Text>
        <View style={styles.statsRow}>
          <View style={styles.statItem}>
            <Text style={styles.statValue}>{profile?.watchlist_count ?? 0}</Text>
            <Text style={styles.statLabel}>Watching</Text>
          </View>
          <View style={styles.statItem}>
            <Text style={styles.statValue}>{profile?.device_count ?? 0}</Text>
            <Text style={styles.statLabel}>Devices</Text>
          </View>
        </View>
      </View>

      {/* Notification Settings */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>Notifications</Text>
        <View style={styles.card}>
          <View style={styles.settingRow}>
            <View style={styles.settingInfo}>
              <Ionicons name="flash" size={20} color="#22c55e" />
              <Text style={styles.settingLabel}>Arbitrage Alerts</Text>
            </View>
            <Switch
              value={preferences?.notification_settings?.arbitrage_alerts ?? true}
              onValueChange={() => router.push('/settings')}
              trackColor={{ false: isDark ? '#2a2a4e' : '#e9ecef', true: '#4361ee' }}
            />
          </View>
          <View style={styles.settingRow}>
            <View style={styles.settingInfo}>
              <Ionicons name="eye" size={20} color="#4361ee" />
              <Text style={styles.settingLabel}>Watchlist Updates</Text>
            </View>
            <Switch
              value={preferences?.notification_settings?.watchlist_odds_change ?? true}
              onValueChange={() => router.push('/settings')}
              trackColor={{ false: isDark ? '#2a2a4e' : '#e9ecef', true: '#4361ee' }}
            />
          </View>
          <View style={styles.settingRow}>
            <View style={styles.settingInfo}>
              <Ionicons name="alarm" size={20} color="#f59e0b" />
              <Text style={styles.settingLabel}>Match Reminders</Text>
            </View>
            <Switch
              value={preferences?.notification_settings?.match_start_reminder ?? false}
              onValueChange={() => router.push('/settings')}
              trackColor={{ false: isDark ? '#2a2a4e' : '#e9ecef', true: '#4361ee' }}
            />
          </View>
        </View>
      </View>

      {/* Quick Settings */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>Settings</Text>
        <View style={styles.card}>
          <Link href="/settings" asChild>
            <TouchableOpacity style={styles.menuItem}>
              <View style={styles.menuItemLeft}>
                <Ionicons name="settings" size={20} color={isDark ? '#ffffff' : '#1a1a2e'} />
                <Text style={styles.menuItemText}>Preferences</Text>
              </View>
              <Ionicons name="chevron-forward" size={20} color={isDark ? '#6c757d' : '#adb5bd'} />
            </TouchableOpacity>
          </Link>
          <TouchableOpacity style={styles.menuItem}>
            <View style={styles.menuItemLeft}>
              <Ionicons name="phone-portrait" size={20} color={isDark ? '#ffffff' : '#1a1a2e'} />
              <Text style={styles.menuItemText}>Manage Devices</Text>
            </View>
            <Ionicons name="chevron-forward" size={20} color={isDark ? '#6c757d' : '#adb5bd'} />
          </TouchableOpacity>
          <TouchableOpacity style={styles.menuItem}>
            <View style={styles.menuItemLeft}>
              <Ionicons name="time" size={20} color={isDark ? '#ffffff' : '#1a1a2e'} />
              <Text style={styles.menuItemText}>Arbitrage History</Text>
            </View>
            <Ionicons name="chevron-forward" size={20} color={isDark ? '#6c757d' : '#adb5bd'} />
          </TouchableOpacity>
        </View>
      </View>

      {/* Info */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>About</Text>
        <View style={styles.card}>
          <TouchableOpacity style={styles.menuItem}>
            <View style={styles.menuItemLeft}>
              <Ionicons name="help-circle" size={20} color={isDark ? '#ffffff' : '#1a1a2e'} />
              <Text style={styles.menuItemText}>Help & Support</Text>
            </View>
            <Ionicons name="chevron-forward" size={20} color={isDark ? '#6c757d' : '#adb5bd'} />
          </TouchableOpacity>
          <TouchableOpacity style={styles.menuItem}>
            <View style={styles.menuItemLeft}>
              <Ionicons name="document-text" size={20} color={isDark ? '#ffffff' : '#1a1a2e'} />
              <Text style={styles.menuItemText}>Privacy Policy</Text>
            </View>
            <Ionicons name="chevron-forward" size={20} color={isDark ? '#6c757d' : '#adb5bd'} />
          </TouchableOpacity>
          <View style={styles.menuItem}>
            <View style={styles.menuItemLeft}>
              <Ionicons name="information-circle" size={20} color={isDark ? '#ffffff' : '#1a1a2e'} />
              <Text style={styles.menuItemText}>Version</Text>
            </View>
            <Text style={styles.versionText}>1.0.0</Text>
          </View>
        </View>
      </View>

      {/* Sign Out */}
      <TouchableOpacity style={styles.logoutButton} onPress={handleLogout}>
        <Ionicons name="log-out" size={20} color="#ef4444" />
        <Text style={styles.logoutText}>Sign Out</Text>
      </TouchableOpacity>
    </ScrollView>
  );
}

const createStyles = (isDark: boolean) =>
  StyleSheet.create({
    container: {
      flex: 1,
      backgroundColor: isDark ? '#0f0f23' : '#f8f9fa',
    },
    content: {
      padding: 16,
    },
    authPrompt: {
      flex: 1,
      justifyContent: 'center',
      alignItems: 'center',
      padding: 32,
    },
    authTitle: {
      fontSize: 24,
      fontWeight: '700',
      color: isDark ? '#ffffff' : '#1a1a2e',
      marginTop: 24,
    },
    authText: {
      fontSize: 16,
      color: isDark ? '#9ca3af' : '#6c757d',
      textAlign: 'center',
      marginTop: 12,
      lineHeight: 24,
    },
    authButton: {
      backgroundColor: '#4361ee',
      paddingHorizontal: 48,
      paddingVertical: 14,
      borderRadius: 10,
      marginTop: 32,
    },
    authButtonText: {
      color: '#ffffff',
      fontSize: 16,
      fontWeight: '600',
    },
    profileHeader: {
      backgroundColor: isDark ? '#1a1a2e' : '#ffffff',
      padding: 24,
      borderRadius: 16,
      alignItems: 'center',
      marginBottom: 24,
    },
    avatar: {
      width: 80,
      height: 80,
      borderRadius: 40,
      backgroundColor: '#4361ee',
      justifyContent: 'center',
      alignItems: 'center',
    },
    avatarText: {
      color: '#ffffff',
      fontSize: 32,
      fontWeight: '700',
    },
    email: {
      fontSize: 16,
      color: isDark ? '#ffffff' : '#1a1a2e',
      marginTop: 12,
    },
    statsRow: {
      flexDirection: 'row',
      marginTop: 20,
      gap: 48,
    },
    statItem: {
      alignItems: 'center',
    },
    statValue: {
      fontSize: 24,
      fontWeight: '700',
      color: isDark ? '#ffffff' : '#1a1a2e',
    },
    statLabel: {
      fontSize: 12,
      color: isDark ? '#9ca3af' : '#6c757d',
      marginTop: 4,
    },
    section: {
      marginBottom: 24,
    },
    sectionTitle: {
      fontSize: 14,
      fontWeight: '600',
      color: isDark ? '#9ca3af' : '#6c757d',
      marginBottom: 12,
      paddingHorizontal: 4,
    },
    card: {
      backgroundColor: isDark ? '#1a1a2e' : '#ffffff',
      borderRadius: 12,
      overflow: 'hidden',
    },
    settingRow: {
      flexDirection: 'row',
      justifyContent: 'space-between',
      alignItems: 'center',
      padding: 16,
      borderBottomWidth: 1,
      borderBottomColor: isDark ? '#2a2a4e' : '#f0f0f0',
    },
    settingInfo: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: 12,
    },
    settingLabel: {
      fontSize: 16,
      color: isDark ? '#ffffff' : '#1a1a2e',
    },
    menuItem: {
      flexDirection: 'row',
      justifyContent: 'space-between',
      alignItems: 'center',
      padding: 16,
      borderBottomWidth: 1,
      borderBottomColor: isDark ? '#2a2a4e' : '#f0f0f0',
    },
    menuItemLeft: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: 12,
    },
    menuItemText: {
      fontSize: 16,
      color: isDark ? '#ffffff' : '#1a1a2e',
    },
    versionText: {
      fontSize: 14,
      color: isDark ? '#6c757d' : '#adb5bd',
    },
    logoutButton: {
      flexDirection: 'row',
      justifyContent: 'center',
      alignItems: 'center',
      backgroundColor: isDark ? '#1a1a2e' : '#ffffff',
      padding: 16,
      borderRadius: 12,
      gap: 8,
      marginBottom: 32,
    },
    logoutText: {
      fontSize: 16,
      fontWeight: '600',
      color: '#ef4444',
    },
  });
