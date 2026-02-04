/**
 * Matches Screen for BetSnipe.ai
 */

import { useEffect, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  TouchableOpacity,
  TextInput,
  RefreshControl,
  useColorScheme,
} from 'react-native';
import { Link } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';

import { useOddsStore } from '@/stores';
import { Match } from '@/types';

const SPORTS = [
  { id: null, name: 'All', icon: 'grid' },
  { id: 1, name: 'Football', icon: 'football' },
  { id: 2, name: 'Basketball', icon: 'basketball' },
  { id: 3, name: 'Tennis', icon: 'tennisball' },
  { id: 4, name: 'Hockey', icon: 'snow' },
  { id: 5, name: 'Table Tennis', icon: 'ellipse' },
];

export default function MatchesScreen() {
  const colorScheme = useColorScheme();
  const isDark = colorScheme === 'dark';
  const [searchText, setSearchText] = useState('');

  const {
    matches,
    searchResults,
    isLoading,
    currentSportId,
    fetchMatches,
    search,
    setSportFilter,
    clearSearch,
    subscribeToUpdates,
  } = useOddsStore();

  useEffect(() => {
    fetchMatches();
    const unsubscribe = subscribeToUpdates();
    return unsubscribe;
  }, []);

  const handleSearch = (text: string) => {
    setSearchText(text);
    if (text.trim()) {
      search(text, currentSportId ?? undefined);
    } else {
      clearSearch();
    }
  };

  const handleSportFilter = (sportId: number | null) => {
    setSportFilter(sportId);
    if (searchText.trim()) {
      search(searchText, sportId ?? undefined);
    }
  };

  const displayMatches = searchText.trim() ? searchResults : matches;

  const styles = createStyles(isDark);

  const renderMatch = ({ item }: { item: Match }) => (
    <Link href={`/match/${item.id}`} asChild>
      <TouchableOpacity style={styles.matchCard}>
        <View style={styles.matchHeader}>
          <View style={styles.sportBadge}>
            <Text style={styles.sportText}>{item.sport_name}</Text>
          </View>
          <Text style={styles.matchTime}>
            {new Date(item.start_time).toLocaleTimeString([], {
              hour: '2-digit',
              minute: '2-digit',
            })}
          </Text>
        </View>

        <View style={styles.teamsContainer}>
          <Text style={styles.teamName}>{item.team1}</Text>
          <Text style={styles.vs}>vs</Text>
          <Text style={styles.teamName}>{item.team2}</Text>
        </View>

        {item.odds.length > 0 && (
          <View style={styles.oddsPreview}>
            <Text style={styles.oddsLabel}>{item.odds.length} bookmakers</Text>
            <View style={styles.oddsBadges}>
              {item.odds.slice(0, 3).map((odd, idx) => (
                <View key={idx} style={styles.oddBadge}>
                  <Text style={styles.oddValue}>
                    {odd.odd1?.toFixed(2) ?? '-'}
                  </Text>
                </View>
              ))}
            </View>
          </View>
        )}
      </TouchableOpacity>
    </Link>
  );

  return (
    <View style={styles.container}>
      {/* Search Bar */}
      <View style={styles.searchContainer}>
        <Ionicons name="search" size={20} color={isDark ? '#9ca3af' : '#6c757d'} />
        <TextInput
          style={styles.searchInput}
          placeholder="Search teams..."
          placeholderTextColor={isDark ? '#6c757d' : '#adb5bd'}
          value={searchText}
          onChangeText={handleSearch}
        />
        {searchText.length > 0 && (
          <TouchableOpacity onPress={() => handleSearch('')}>
            <Ionicons name="close-circle" size={20} color={isDark ? '#9ca3af' : '#6c757d'} />
          </TouchableOpacity>
        )}
      </View>

      {/* Sport Filters */}
      <View style={styles.filterContainer}>
        <FlatList
          horizontal
          showsHorizontalScrollIndicator={false}
          data={SPORTS}
          keyExtractor={(item) => String(item.id)}
          renderItem={({ item }) => (
            <TouchableOpacity
              style={[
                styles.filterChip,
                currentSportId === item.id && styles.filterChipActive,
              ]}
              onPress={() => handleSportFilter(item.id)}
            >
              <Ionicons
                name={item.icon as any}
                size={16}
                color={currentSportId === item.id ? '#ffffff' : isDark ? '#9ca3af' : '#6c757d'}
              />
              <Text
                style={[
                  styles.filterText,
                  currentSportId === item.id && styles.filterTextActive,
                ]}
              >
                {item.name}
              </Text>
            </TouchableOpacity>
          )}
        />
      </View>

      {/* Matches List */}
      <FlatList
        data={displayMatches}
        keyExtractor={(item) => String(item.id)}
        renderItem={renderMatch}
        contentContainerStyle={styles.listContent}
        refreshControl={
          <RefreshControl
            refreshing={isLoading}
            onRefresh={() => fetchMatches(currentSportId ?? undefined)}
          />
        }
        ListEmptyComponent={
          <View style={styles.emptyState}>
            <Ionicons name="calendar" size={48} color={isDark ? '#6c757d' : '#adb5bd'} />
            <Text style={styles.emptyText}>
              {searchText ? 'No matches found' : 'No upcoming matches'}
            </Text>
          </View>
        }
      />
    </View>
  );
}

const createStyles = (isDark: boolean) =>
  StyleSheet.create({
    container: {
      flex: 1,
      backgroundColor: isDark ? '#0f0f23' : '#f8f9fa',
    },
    searchContainer: {
      flexDirection: 'row',
      alignItems: 'center',
      backgroundColor: isDark ? '#1a1a2e' : '#ffffff',
      margin: 16,
      marginBottom: 8,
      paddingHorizontal: 12,
      borderRadius: 10,
    },
    searchInput: {
      flex: 1,
      paddingVertical: 12,
      paddingHorizontal: 8,
      fontSize: 16,
      color: isDark ? '#ffffff' : '#1a1a2e',
    },
    filterContainer: {
      paddingHorizontal: 16,
      paddingBottom: 8,
    },
    filterChip: {
      flexDirection: 'row',
      alignItems: 'center',
      backgroundColor: isDark ? '#1a1a2e' : '#ffffff',
      paddingHorizontal: 12,
      paddingVertical: 8,
      borderRadius: 20,
      marginRight: 8,
      gap: 6,
    },
    filterChipActive: {
      backgroundColor: '#4361ee',
    },
    filterText: {
      fontSize: 14,
      color: isDark ? '#9ca3af' : '#6c757d',
    },
    filterTextActive: {
      color: '#ffffff',
    },
    listContent: {
      padding: 16,
      paddingTop: 8,
    },
    matchCard: {
      backgroundColor: isDark ? '#1a1a2e' : '#ffffff',
      padding: 16,
      borderRadius: 12,
      marginBottom: 12,
    },
    matchHeader: {
      flexDirection: 'row',
      justifyContent: 'space-between',
      alignItems: 'center',
      marginBottom: 12,
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
      textTransform: 'capitalize',
    },
    matchTime: {
      fontSize: 14,
      fontWeight: '600',
      color: isDark ? '#ffffff' : '#1a1a2e',
    },
    teamsContainer: {
      gap: 4,
    },
    teamName: {
      fontSize: 16,
      fontWeight: '500',
      color: isDark ? '#ffffff' : '#1a1a2e',
    },
    vs: {
      fontSize: 12,
      color: isDark ? '#6c757d' : '#adb5bd',
    },
    oddsPreview: {
      flexDirection: 'row',
      justifyContent: 'space-between',
      alignItems: 'center',
      marginTop: 12,
      paddingTop: 12,
      borderTopWidth: 1,
      borderTopColor: isDark ? '#2a2a4e' : '#e9ecef',
    },
    oddsLabel: {
      fontSize: 12,
      color: isDark ? '#9ca3af' : '#6c757d',
    },
    oddsBadges: {
      flexDirection: 'row',
      gap: 8,
    },
    oddBadge: {
      backgroundColor: isDark ? '#2a2a4e' : '#e9ecef',
      paddingHorizontal: 8,
      paddingVertical: 4,
      borderRadius: 4,
    },
    oddValue: {
      fontSize: 12,
      fontWeight: '600',
      color: isDark ? '#ffffff' : '#1a1a2e',
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
