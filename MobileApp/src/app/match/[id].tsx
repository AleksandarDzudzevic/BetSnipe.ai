/**
 * Match Detail Screen for BetSnipe.ai
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
import { useLocalSearchParams, Stack } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { useQuery } from '@tanstack/react-query';

import { getMatch, getOddsTrends, addToWatchlist } from '@/services/api';
import { useAuthStore } from '@/stores';

export default function MatchDetailScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const colorScheme = useColorScheme();
  const isDark = colorScheme === 'dark';
  const { isAuthenticated } = useAuthStore();

  const matchId = parseInt(id, 10);

  // Fetch match details
  const { data: match, isLoading, refetch } = useQuery({
    queryKey: ['match', matchId],
    queryFn: () => getMatch(matchId),
    enabled: !isNaN(matchId),
  });

  // Fetch odds trends
  const { data: trends } = useQuery({
    queryKey: ['oddsTrends', matchId],
    queryFn: () => getOddsTrends(matchId, { bet_type_id: 2, hours: 24 }),
    enabled: !isNaN(matchId),
  });

  const handleAddToWatchlist = async () => {
    if (!isAuthenticated) {
      // Could show login prompt
      return;
    }
    try {
      await addToWatchlist({ match_id: matchId });
      // Show success toast
    } catch (error) {
      // Show error toast
    }
  };

  const styles = createStyles(isDark);

  if (!match) {
    return (
      <View style={styles.loadingContainer}>
        <Text style={styles.loadingText}>Loading...</Text>
      </View>
    );
  }

  // Group odds by bet type
  const oddsByBetType: Record<string, typeof match.odds> = {};
  match.odds.forEach((odd) => {
    const key = `${odd.bet_type_name}${odd.margin > 0 ? ` (${odd.margin})` : ''}`;
    if (!oddsByBetType[key]) {
      oddsByBetType[key] = [];
    }
    oddsByBetType[key].push(odd);
  });

  return (
    <>
      <Stack.Screen
        options={{
          title: `${match.team1} vs ${match.team2}`.substring(0, 30),
          headerRight: () => (
            <TouchableOpacity onPress={handleAddToWatchlist}>
              <Ionicons
                name="bookmark-outline"
                size={24}
                color={isDark ? '#ffffff' : '#1a1a2e'}
              />
            </TouchableOpacity>
          ),
        }}
      />

      <ScrollView
        style={styles.container}
        contentContainerStyle={styles.content}
        refreshControl={
          <RefreshControl refreshing={isLoading} onRefresh={refetch} />
        }
      >
        {/* Match Header */}
        <View style={styles.header}>
          <View style={styles.sportBadge}>
            <Text style={styles.sportText}>{match.sport_name}</Text>
          </View>
          <View style={styles.teamsContainer}>
            <Text style={styles.teamName}>{match.team1}</Text>
            <Text style={styles.vs}>vs</Text>
            <Text style={styles.teamName}>{match.team2}</Text>
          </View>
          <View style={styles.timeContainer}>
            <Ionicons name="time" size={16} color={isDark ? '#9ca3af' : '#6c757d'} />
            <Text style={styles.timeText}>
              {new Date(match.start_time).toLocaleDateString()} at{' '}
              {new Date(match.start_time).toLocaleTimeString([], {
                hour: '2-digit',
                minute: '2-digit',
              })}
            </Text>
          </View>
        </View>

        {/* Odds Comparison */}
        {Object.entries(oddsByBetType).map(([betType, odds]) => (
          <View key={betType} style={styles.oddsSection}>
            <Text style={styles.sectionTitle}>{betType}</Text>
            <View style={styles.oddsTable}>
              {/* Table Header */}
              <View style={styles.tableHeader}>
                <Text style={[styles.tableHeaderText, { flex: 2 }]}>Bookmaker</Text>
                <Text style={styles.tableHeaderText}>1</Text>
                <Text style={styles.tableHeaderText}>X</Text>
                <Text style={styles.tableHeaderText}>2</Text>
              </View>

              {/* Table Rows */}
              {odds.map((odd, idx) => {
                // Find best odds for highlighting
                const best1 = Math.max(...odds.map((o) => o.odd1 || 0));
                const best2 = Math.max(...odds.map((o) => o.odd2 || 0));
                const best3 = Math.max(...odds.map((o) => o.odd3 || 0));

                return (
                  <View key={idx} style={styles.tableRow}>
                    <Text style={[styles.bookmakerName, { flex: 2 }]}>
                      {odd.bookmaker_name}
                    </Text>
                    <Text
                      style={[
                        styles.oddValue,
                        odd.odd1 === best1 && styles.bestOdd,
                      ]}
                    >
                      {odd.odd1?.toFixed(2) || '-'}
                    </Text>
                    <Text
                      style={[
                        styles.oddValue,
                        odd.odd3 === best3 && styles.bestOdd,
                      ]}
                    >
                      {odd.odd3?.toFixed(2) || '-'}
                    </Text>
                    <Text
                      style={[
                        styles.oddValue,
                        odd.odd2 === best2 && styles.bestOdd,
                      ]}
                    >
                      {odd.odd2?.toFixed(2) || '-'}
                    </Text>
                  </View>
                );
              })}
            </View>
          </View>
        ))}

        {/* Odds Movement */}
        {trends && Object.keys(trends.movement).length > 0 && (
          <View style={styles.trendsSection}>
            <Text style={styles.sectionTitle}>Odds Movement (24h)</Text>
            <View style={styles.trendsCard}>
              {Object.entries(trends.movement).map(([bookmaker, movement]) => (
                <View key={bookmaker} style={styles.trendRow}>
                  <Text style={styles.trendBookmaker}>{bookmaker}</Text>
                  <View style={styles.trendValues}>
                    {movement.odd1_change !== null && (
                      <View style={styles.trendItem}>
                        <Text style={styles.trendLabel}>1</Text>
                        <Text
                          style={[
                            styles.trendChange,
                            { color: movement.odd1_change >= 0 ? '#22c55e' : '#ef4444' },
                          ]}
                        >
                          {movement.odd1_change >= 0 ? '+' : ''}
                          {movement.odd1_change.toFixed(2)}
                        </Text>
                      </View>
                    )}
                    {movement.odd2_change !== null && (
                      <View style={styles.trendItem}>
                        <Text style={styles.trendLabel}>2</Text>
                        <Text
                          style={[
                            styles.trendChange,
                            { color: movement.odd2_change >= 0 ? '#22c55e' : '#ef4444' },
                          ]}
                        >
                          {movement.odd2_change >= 0 ? '+' : ''}
                          {movement.odd2_change.toFixed(2)}
                        </Text>
                      </View>
                    )}
                  </View>
                </View>
              ))}
            </View>
          </View>
        )}

        {/* Empty State */}
        {match.odds.length === 0 && (
          <View style={styles.emptyState}>
            <Ionicons name="analytics" size={48} color={isDark ? '#6c757d' : '#adb5bd'} />
            <Text style={styles.emptyText}>No odds available yet</Text>
          </View>
        )}
      </ScrollView>
    </>
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
    loadingContainer: {
      flex: 1,
      justifyContent: 'center',
      alignItems: 'center',
      backgroundColor: isDark ? '#0f0f23' : '#f8f9fa',
    },
    loadingText: {
      fontSize: 16,
      color: isDark ? '#9ca3af' : '#6c757d',
    },
    header: {
      backgroundColor: isDark ? '#1a1a2e' : '#ffffff',
      padding: 20,
      borderRadius: 16,
      marginBottom: 16,
      alignItems: 'center',
    },
    sportBadge: {
      backgroundColor: isDark ? '#2a2a4e' : '#e9ecef',
      paddingHorizontal: 12,
      paddingVertical: 6,
      borderRadius: 8,
      marginBottom: 16,
    },
    sportText: {
      fontSize: 12,
      color: isDark ? '#9ca3af' : '#6c757d',
      textTransform: 'capitalize',
    },
    teamsContainer: {
      alignItems: 'center',
    },
    teamName: {
      fontSize: 20,
      fontWeight: '600',
      color: isDark ? '#ffffff' : '#1a1a2e',
      textAlign: 'center',
    },
    vs: {
      fontSize: 14,
      color: isDark ? '#6c757d' : '#adb5bd',
      marginVertical: 4,
    },
    timeContainer: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: 6,
      marginTop: 16,
    },
    timeText: {
      fontSize: 14,
      color: isDark ? '#9ca3af' : '#6c757d',
    },
    oddsSection: {
      marginBottom: 16,
    },
    sectionTitle: {
      fontSize: 16,
      fontWeight: '600',
      color: isDark ? '#ffffff' : '#1a1a2e',
      marginBottom: 12,
    },
    oddsTable: {
      backgroundColor: isDark ? '#1a1a2e' : '#ffffff',
      borderRadius: 12,
      overflow: 'hidden',
    },
    tableHeader: {
      flexDirection: 'row',
      backgroundColor: isDark ? '#2a2a4e' : '#f8f9fa',
      paddingVertical: 12,
      paddingHorizontal: 16,
    },
    tableHeaderText: {
      flex: 1,
      fontSize: 12,
      fontWeight: '600',
      color: isDark ? '#9ca3af' : '#6c757d',
      textAlign: 'center',
    },
    tableRow: {
      flexDirection: 'row',
      paddingVertical: 12,
      paddingHorizontal: 16,
      borderBottomWidth: 1,
      borderBottomColor: isDark ? '#2a2a4e' : '#f0f0f0',
    },
    bookmakerName: {
      fontSize: 14,
      color: isDark ? '#ffffff' : '#1a1a2e',
    },
    oddValue: {
      flex: 1,
      fontSize: 14,
      fontWeight: '500',
      color: isDark ? '#ffffff' : '#1a1a2e',
      textAlign: 'center',
    },
    bestOdd: {
      color: '#22c55e',
      fontWeight: '700',
    },
    trendsSection: {
      marginBottom: 16,
    },
    trendsCard: {
      backgroundColor: isDark ? '#1a1a2e' : '#ffffff',
      borderRadius: 12,
      padding: 16,
    },
    trendRow: {
      flexDirection: 'row',
      justifyContent: 'space-between',
      alignItems: 'center',
      paddingVertical: 8,
      borderBottomWidth: 1,
      borderBottomColor: isDark ? '#2a2a4e' : '#f0f0f0',
    },
    trendBookmaker: {
      fontSize: 14,
      color: isDark ? '#ffffff' : '#1a1a2e',
    },
    trendValues: {
      flexDirection: 'row',
      gap: 16,
    },
    trendItem: {
      alignItems: 'center',
    },
    trendLabel: {
      fontSize: 10,
      color: isDark ? '#6c757d' : '#adb5bd',
    },
    trendChange: {
      fontSize: 14,
      fontWeight: '600',
    },
    emptyState: {
      alignItems: 'center',
      paddingVertical: 48,
    },
    emptyText: {
      fontSize: 16,
      color: isDark ? '#9ca3af' : '#6c757d',
      marginTop: 12,
    },
  });
