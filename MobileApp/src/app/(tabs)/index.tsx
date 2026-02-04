/**
 * Dashboard Screen for BetSnipe.ai
 */

import { useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  RefreshControl,
  TouchableOpacity,
  useColorScheme,
} from 'react-native';
import { Link } from 'expo-router';
import { useQuery } from '@tanstack/react-query';
import { Ionicons } from '@expo/vector-icons';

import { getStats, getArbitrageStats } from '@/services/api';
import { useArbitrageStore, useAuthStore } from '@/stores';

export default function DashboardScreen() {
  const colorScheme = useColorScheme();
  const isDark = colorScheme === 'dark';
  const { isAuthenticated, user } = useAuthStore();
  const { opportunities = [], fetchOpportunities, subscribeToUpdates } = useArbitrageStore();

  // Fetch system stats
  const { data: systemStats, refetch: refetchSystem, isLoading: loadingSystem } = useQuery({
    queryKey: ['systemStats'],
    queryFn: getStats,
    refetchInterval: 30000, // Refresh every 30 seconds
  });

  // Fetch arbitrage stats
  const { data: arbStats, refetch: refetchArb, isLoading: loadingArb } = useQuery({
    queryKey: ['arbitrageStats'],
    queryFn: getArbitrageStats,
    refetchInterval: 30000,
  });

  useEffect(() => {
    fetchOpportunities();
    const unsubscribe = subscribeToUpdates();
    return unsubscribe;
  }, []);

  const onRefresh = async () => {
    await Promise.all([refetchSystem(), refetchArb(), fetchOpportunities()]);
  };

  const isLoading = loadingSystem || loadingArb;

  const styles = createStyles(isDark);

  return (
    <ScrollView
      style={styles.container}
      contentContainerStyle={styles.content}
      refreshControl={
        <RefreshControl refreshing={isLoading} onRefresh={onRefresh} />
      }
    >
      {/* Welcome Section */}
      <View style={styles.welcomeSection}>
        <Text style={styles.welcomeText}>
          {isAuthenticated ? `Welcome back${user?.email ? ', ' + user.email.split('@')[0] : ''}!` : 'Welcome to BetSnipe'}
        </Text>
        <Text style={styles.subtitle}>Real-time arbitrage detection</Text>
      </View>

      {/* Quick Stats */}
      <View style={styles.statsGrid}>
        <View style={styles.statCard}>
          <Ionicons name="flash" size={24} color="#22c55e" />
          <Text style={styles.statValue}>{arbStats?.active_count ?? 0}</Text>
          <Text style={styles.statLabel}>Active Arbs</Text>
        </View>

        <View style={styles.statCard}>
          <Ionicons name="trending-up" size={24} color="#4361ee" />
          <Text style={styles.statValue}>{arbStats?.avg_profit?.toFixed(2) ?? '0.00'}%</Text>
          <Text style={styles.statLabel}>Avg Profit</Text>
        </View>

        <View style={styles.statCard}>
          <Ionicons name="football" size={24} color="#f59e0b" />
          <Text style={styles.statValue}>{systemStats?.database?.total_matches ?? 0}</Text>
          <Text style={styles.statLabel}>Matches</Text>
        </View>

        <View style={styles.statCard}>
          <Ionicons name="analytics" size={24} color="#8b5cf6" />
          <Text style={styles.statValue}>{systemStats?.database?.bookmakers_with_odds ?? 0}</Text>
          <Text style={styles.statLabel}>Bookmakers</Text>
        </View>
      </View>

      {/* Latest Arbitrage */}
      <View style={styles.section}>
        <View style={styles.sectionHeader}>
          <Text style={styles.sectionTitle}>Latest Arbitrage</Text>
          <Link href="/arbitrage" asChild>
            <TouchableOpacity>
              <Text style={styles.seeAll}>See All</Text>
            </TouchableOpacity>
          </Link>
        </View>

        {opportunities.length === 0 ? (
          <View style={styles.emptyState}>
            <Ionicons name="search" size={48} color={isDark ? '#6c757d' : '#adb5bd'} />
            <Text style={styles.emptyText}>No arbitrage opportunities found</Text>
            <Text style={styles.emptySubtext}>Check back soon!</Text>
          </View>
        ) : (
          opportunities.slice(0, 3).map((arb) => (
            <Link key={arb.id} href={`/arbitrage/${arb.id}`} asChild>
              <TouchableOpacity style={styles.arbCard}>
                <View style={styles.arbHeader}>
                  <View style={styles.profitBadge}>
                    <Text style={styles.profitText}>{arb.profit_percentage.toFixed(2)}%</Text>
                  </View>
                  <Text style={styles.arbSport}>{arb.sport_name}</Text>
                </View>
                <Text style={styles.arbTeams}>
                  {arb.team1} vs {arb.team2}
                </Text>
                <Text style={styles.arbMeta}>
                  {arb.bet_type_name} | {arb.best_odds.length} bookmakers
                </Text>
              </TouchableOpacity>
            </Link>
          ))
        )}
      </View>

      {/* System Status */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>System Status</Text>
        <View style={styles.statusCard}>
          <View style={styles.statusRow}>
            <Text style={styles.statusLabel}>Scraper</Text>
            <View style={[styles.statusIndicator, { backgroundColor: '#22c55e' }]} />
          </View>
          <View style={styles.statusRow}>
            <Text style={styles.statusLabel}>Database</Text>
            <View style={[styles.statusIndicator, { backgroundColor: '#22c55e' }]} />
          </View>
          <View style={styles.statusRow}>
            <Text style={styles.statusLabel}>Today's Opportunities</Text>
            <Text style={styles.statusValue}>{arbStats?.total_today ?? 0}</Text>
          </View>
        </View>
      </View>

      {/* Auth Prompt (if not logged in) */}
      {!isAuthenticated && (
        <View style={styles.authPrompt}>
          <Ionicons name="notifications" size={32} color="#4361ee" />
          <Text style={styles.authTitle}>Get Instant Alerts</Text>
          <Text style={styles.authText}>
            Sign in to receive push notifications for new arbitrage opportunities
          </Text>
          <Link href="/login" asChild>
            <TouchableOpacity style={styles.authButton}>
              <Text style={styles.authButtonText}>Sign In</Text>
            </TouchableOpacity>
          </Link>
        </View>
      )}
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
    welcomeSection: {
      marginBottom: 24,
    },
    welcomeText: {
      fontSize: 28,
      fontWeight: '700',
      color: isDark ? '#ffffff' : '#1a1a2e',
    },
    subtitle: {
      fontSize: 16,
      color: isDark ? '#9ca3af' : '#6c757d',
      marginTop: 4,
    },
    statsGrid: {
      flexDirection: 'row',
      flexWrap: 'wrap',
      gap: 12,
      marginBottom: 24,
    },
    statCard: {
      flex: 1,
      minWidth: '45%',
      backgroundColor: isDark ? '#1a1a2e' : '#ffffff',
      padding: 16,
      borderRadius: 12,
      alignItems: 'center',
    },
    statValue: {
      fontSize: 24,
      fontWeight: '700',
      color: isDark ? '#ffffff' : '#1a1a2e',
      marginTop: 8,
    },
    statLabel: {
      fontSize: 12,
      color: isDark ? '#9ca3af' : '#6c757d',
      marginTop: 4,
    },
    section: {
      marginBottom: 24,
    },
    sectionHeader: {
      flexDirection: 'row',
      justifyContent: 'space-between',
      alignItems: 'center',
      marginBottom: 12,
    },
    sectionTitle: {
      fontSize: 18,
      fontWeight: '600',
      color: isDark ? '#ffffff' : '#1a1a2e',
    },
    seeAll: {
      fontSize: 14,
      color: '#4361ee',
    },
    emptyState: {
      backgroundColor: isDark ? '#1a1a2e' : '#ffffff',
      padding: 32,
      borderRadius: 12,
      alignItems: 'center',
    },
    emptyText: {
      fontSize: 16,
      fontWeight: '500',
      color: isDark ? '#ffffff' : '#1a1a2e',
      marginTop: 12,
    },
    emptySubtext: {
      fontSize: 14,
      color: isDark ? '#9ca3af' : '#6c757d',
      marginTop: 4,
    },
    arbCard: {
      backgroundColor: isDark ? '#1a1a2e' : '#ffffff',
      padding: 16,
      borderRadius: 12,
      marginBottom: 12,
    },
    arbHeader: {
      flexDirection: 'row',
      alignItems: 'center',
      marginBottom: 8,
    },
    profitBadge: {
      backgroundColor: '#22c55e',
      paddingHorizontal: 8,
      paddingVertical: 4,
      borderRadius: 6,
    },
    profitText: {
      color: '#ffffff',
      fontSize: 12,
      fontWeight: '600',
    },
    arbSport: {
      fontSize: 12,
      color: isDark ? '#9ca3af' : '#6c757d',
      marginLeft: 8,
    },
    arbTeams: {
      fontSize: 16,
      fontWeight: '500',
      color: isDark ? '#ffffff' : '#1a1a2e',
    },
    arbMeta: {
      fontSize: 12,
      color: isDark ? '#9ca3af' : '#6c757d',
      marginTop: 4,
    },
    statusCard: {
      backgroundColor: isDark ? '#1a1a2e' : '#ffffff',
      padding: 16,
      borderRadius: 12,
    },
    statusRow: {
      flexDirection: 'row',
      justifyContent: 'space-between',
      alignItems: 'center',
      paddingVertical: 8,
    },
    statusLabel: {
      fontSize: 14,
      color: isDark ? '#ffffff' : '#1a1a2e',
    },
    statusIndicator: {
      width: 12,
      height: 12,
      borderRadius: 6,
    },
    statusValue: {
      fontSize: 14,
      fontWeight: '600',
      color: isDark ? '#ffffff' : '#1a1a2e',
    },
    authPrompt: {
      backgroundColor: isDark ? '#1a1a2e' : '#ffffff',
      padding: 24,
      borderRadius: 12,
      alignItems: 'center',
      marginBottom: 24,
    },
    authTitle: {
      fontSize: 18,
      fontWeight: '600',
      color: isDark ? '#ffffff' : '#1a1a2e',
      marginTop: 12,
    },
    authText: {
      fontSize: 14,
      color: isDark ? '#9ca3af' : '#6c757d',
      textAlign: 'center',
      marginTop: 8,
      marginBottom: 16,
    },
    authButton: {
      backgroundColor: '#4361ee',
      paddingHorizontal: 32,
      paddingVertical: 12,
      borderRadius: 8,
    },
    authButtonText: {
      color: '#ffffff',
      fontSize: 16,
      fontWeight: '600',
    },
  });
