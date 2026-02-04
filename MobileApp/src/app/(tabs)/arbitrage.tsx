/**
 * Arbitrage Screen for BetSnipe.ai
 */

import { useEffect, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  TouchableOpacity,
  RefreshControl,
  useColorScheme,
} from 'react-native';
import { Link } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import Slider from '@react-native-community/slider';

import { useArbitrageStore } from '@/stores';
import { Arbitrage } from '@/types';

export default function ArbitrageScreen() {
  const colorScheme = useColorScheme();
  const isDark = colorScheme === 'dark';
  const [showFilters, setShowFilters] = useState(false);

  const {
    opportunities = [],
    stats,
    isLoading,
    minProfitFilter,
    sportFilter,
    fetchOpportunities,
    fetchStats,
    setMinProfitFilter,
    setSportFilter,
    subscribeToUpdates,
  } = useArbitrageStore();

  useEffect(() => {
    fetchOpportunities();
    fetchStats();
    const unsubscribe = subscribeToUpdates();
    return unsubscribe;
  }, []);

  const styles = createStyles(isDark);

  const renderArbitrage = ({ item }: { item: Arbitrage }) => (
    <Link href={`/arbitrage/${item.id}`} asChild>
      <TouchableOpacity style={styles.arbCard}>
        <View style={styles.arbHeader}>
          <View style={[styles.profitBadge, getProfitStyle(item.profit_percentage)]}>
            <Ionicons name="trending-up" size={14} color="#ffffff" />
            <Text style={styles.profitText}>{item.profit_percentage.toFixed(2)}%</Text>
          </View>
          <View style={styles.metaBadges}>
            <View style={styles.sportBadge}>
              <Text style={styles.sportText}>{item.sport_name}</Text>
            </View>
            <View style={styles.betTypeBadge}>
              <Text style={styles.betTypeText}>{item.bet_type_name}</Text>
            </View>
          </View>
        </View>

        <View style={styles.matchInfo}>
          <Text style={styles.teamName}>{item.team1}</Text>
          <Text style={styles.vs}>vs</Text>
          <Text style={styles.teamName}>{item.team2}</Text>
        </View>

        <View style={styles.oddsContainer}>
          {item.best_odds.map((odd, idx) => (
            <View key={idx} style={styles.oddItem}>
              <Text style={styles.oddBookmaker}>{odd.bookmaker_name}</Text>
              <Text style={styles.oddOutcome}>{odd.outcome}</Text>
              <Text style={styles.oddValue}>{odd.odd.toFixed(2)}</Text>
            </View>
          ))}
        </View>

        <View style={styles.arbFooter}>
          <Text style={styles.timeText}>
            {new Date(item.start_time).toLocaleDateString()} at{' '}
            {new Date(item.start_time).toLocaleTimeString([], {
              hour: '2-digit',
              minute: '2-digit',
            })}
          </Text>
          <Ionicons name="chevron-forward" size={20} color={isDark ? '#6c757d' : '#adb5bd'} />
        </View>
      </TouchableOpacity>
    </Link>
  );

  return (
    <View style={styles.container}>
      {/* Stats Banner */}
      <View style={styles.statsBanner}>
        <View style={styles.statItem}>
          <Text style={styles.statValue}>{stats?.active_count ?? 0}</Text>
          <Text style={styles.statLabel}>Active</Text>
        </View>
        <View style={styles.statDivider} />
        <View style={styles.statItem}>
          <Text style={styles.statValue}>{stats?.avg_profit?.toFixed(2) ?? '0.00'}%</Text>
          <Text style={styles.statLabel}>Avg Profit</Text>
        </View>
        <View style={styles.statDivider} />
        <View style={styles.statItem}>
          <Text style={styles.statValue}>{stats?.total_today ?? 0}</Text>
          <Text style={styles.statLabel}>Today</Text>
        </View>
      </View>

      {/* Filter Toggle */}
      <TouchableOpacity
        style={styles.filterToggle}
        onPress={() => setShowFilters(!showFilters)}
      >
        <Ionicons name="options" size={20} color={isDark ? '#ffffff' : '#1a1a2e'} />
        <Text style={styles.filterToggleText}>
          Min Profit: {minProfitFilter.toFixed(1)}%
        </Text>
        <Ionicons
          name={showFilters ? 'chevron-up' : 'chevron-down'}
          size={20}
          color={isDark ? '#6c757d' : '#adb5bd'}
        />
      </TouchableOpacity>

      {/* Filters Panel */}
      {showFilters && (
        <View style={styles.filtersPanel}>
          <Text style={styles.filterLabel}>Minimum Profit %</Text>
          <Slider
            style={styles.slider}
            minimumValue={0.5}
            maximumValue={10}
            step={0.5}
            value={minProfitFilter}
            onSlidingComplete={(value) => setMinProfitFilter(value)}
            minimumTrackTintColor="#4361ee"
            maximumTrackTintColor={isDark ? '#2a2a4e' : '#e9ecef'}
            thumbTintColor="#4361ee"
          />
          <Text style={styles.filterValue}>{minProfitFilter.toFixed(1)}%</Text>
        </View>
      )}

      {/* Arbitrage List */}
      <FlatList
        data={opportunities}
        keyExtractor={(item) => String(item.id)}
        renderItem={renderArbitrage}
        contentContainerStyle={styles.listContent}
        refreshControl={
          <RefreshControl refreshing={isLoading} onRefresh={fetchOpportunities} />
        }
        ListEmptyComponent={
          <View style={styles.emptyState}>
            <Ionicons name="analytics" size={64} color={isDark ? '#6c757d' : '#adb5bd'} />
            <Text style={styles.emptyTitle}>No Arbitrage Found</Text>
            <Text style={styles.emptyText}>
              Try lowering the minimum profit filter or check back later
            </Text>
          </View>
        }
      />
    </View>
  );
}

const getProfitStyle = (profit: number) => {
  if (profit >= 3) return { backgroundColor: '#22c55e' };
  if (profit >= 2) return { backgroundColor: '#4361ee' };
  return { backgroundColor: '#f59e0b' };
};

const createStyles = (isDark: boolean) =>
  StyleSheet.create({
    container: {
      flex: 1,
      backgroundColor: isDark ? '#0f0f23' : '#f8f9fa',
    },
    statsBanner: {
      flexDirection: 'row',
      backgroundColor: isDark ? '#1a1a2e' : '#ffffff',
      padding: 16,
      marginHorizontal: 16,
      marginTop: 16,
      borderRadius: 12,
    },
    statItem: {
      flex: 1,
      alignItems: 'center',
    },
    statValue: {
      fontSize: 20,
      fontWeight: '700',
      color: isDark ? '#ffffff' : '#1a1a2e',
    },
    statLabel: {
      fontSize: 12,
      color: isDark ? '#9ca3af' : '#6c757d',
      marginTop: 4,
    },
    statDivider: {
      width: 1,
      backgroundColor: isDark ? '#2a2a4e' : '#e9ecef',
    },
    filterToggle: {
      flexDirection: 'row',
      alignItems: 'center',
      backgroundColor: isDark ? '#1a1a2e' : '#ffffff',
      padding: 12,
      marginHorizontal: 16,
      marginTop: 12,
      borderRadius: 10,
      gap: 8,
    },
    filterToggleText: {
      flex: 1,
      fontSize: 14,
      color: isDark ? '#ffffff' : '#1a1a2e',
    },
    filtersPanel: {
      backgroundColor: isDark ? '#1a1a2e' : '#ffffff',
      padding: 16,
      marginHorizontal: 16,
      marginTop: 8,
      borderRadius: 10,
    },
    filterLabel: {
      fontSize: 14,
      color: isDark ? '#9ca3af' : '#6c757d',
    },
    slider: {
      width: '100%',
      height: 40,
    },
    filterValue: {
      fontSize: 16,
      fontWeight: '600',
      color: isDark ? '#ffffff' : '#1a1a2e',
      textAlign: 'center',
    },
    listContent: {
      padding: 16,
    },
    arbCard: {
      backgroundColor: isDark ? '#1a1a2e' : '#ffffff',
      padding: 16,
      borderRadius: 12,
      marginBottom: 12,
    },
    arbHeader: {
      flexDirection: 'row',
      justifyContent: 'space-between',
      alignItems: 'center',
      marginBottom: 12,
    },
    profitBadge: {
      flexDirection: 'row',
      alignItems: 'center',
      paddingHorizontal: 10,
      paddingVertical: 6,
      borderRadius: 8,
      gap: 4,
    },
    profitText: {
      color: '#ffffff',
      fontSize: 14,
      fontWeight: '700',
    },
    metaBadges: {
      flexDirection: 'row',
      gap: 8,
    },
    sportBadge: {
      backgroundColor: isDark ? '#2a2a4e' : '#e9ecef',
      paddingHorizontal: 8,
      paddingVertical: 4,
      borderRadius: 6,
    },
    sportText: {
      fontSize: 12,
      color: isDark ? '#9ca3af' : '#6c757d',
    },
    betTypeBadge: {
      backgroundColor: isDark ? '#2a2a4e' : '#e9ecef',
      paddingHorizontal: 8,
      paddingVertical: 4,
      borderRadius: 6,
    },
    betTypeText: {
      fontSize: 12,
      color: isDark ? '#9ca3af' : '#6c757d',
    },
    matchInfo: {
      marginBottom: 12,
    },
    teamName: {
      fontSize: 16,
      fontWeight: '500',
      color: isDark ? '#ffffff' : '#1a1a2e',
    },
    vs: {
      fontSize: 12,
      color: isDark ? '#6c757d' : '#adb5bd',
      marginVertical: 2,
    },
    oddsContainer: {
      flexDirection: 'row',
      gap: 8,
      marginBottom: 12,
    },
    oddItem: {
      flex: 1,
      backgroundColor: isDark ? '#2a2a4e' : '#f8f9fa',
      padding: 10,
      borderRadius: 8,
      alignItems: 'center',
    },
    oddBookmaker: {
      fontSize: 11,
      color: isDark ? '#9ca3af' : '#6c757d',
    },
    oddOutcome: {
      fontSize: 12,
      fontWeight: '500',
      color: isDark ? '#ffffff' : '#1a1a2e',
      marginVertical: 2,
    },
    oddValue: {
      fontSize: 16,
      fontWeight: '700',
      color: '#4361ee',
    },
    arbFooter: {
      flexDirection: 'row',
      justifyContent: 'space-between',
      alignItems: 'center',
      paddingTop: 12,
      borderTopWidth: 1,
      borderTopColor: isDark ? '#2a2a4e' : '#e9ecef',
    },
    timeText: {
      fontSize: 12,
      color: isDark ? '#9ca3af' : '#6c757d',
    },
    emptyState: {
      alignItems: 'center',
      paddingVertical: 64,
    },
    emptyTitle: {
      fontSize: 18,
      fontWeight: '600',
      color: isDark ? '#ffffff' : '#1a1a2e',
      marginTop: 16,
    },
    emptyText: {
      fontSize: 14,
      color: isDark ? '#9ca3af' : '#6c757d',
      textAlign: 'center',
      marginTop: 8,
      paddingHorizontal: 32,
    },
  });
