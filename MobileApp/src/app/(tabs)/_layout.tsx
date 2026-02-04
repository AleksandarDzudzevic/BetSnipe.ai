/**
 * Tab Layout for BetSnipe.ai
 */

import { Tabs } from 'expo-router';
import { useColorScheme } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

type IconName = React.ComponentProps<typeof Ionicons>['name'];

export default function TabLayout() {
  const colorScheme = useColorScheme();
  const isDark = colorScheme === 'dark';

  const colors = {
    background: isDark ? '#1a1a2e' : '#ffffff',
    card: isDark ? '#16213e' : '#f8f9fa',
    text: isDark ? '#ffffff' : '#1a1a2e',
    primary: '#4361ee',
    inactive: isDark ? '#6c757d' : '#adb5bd',
  };

  return (
    <Tabs
      screenOptions={{
        headerStyle: {
          backgroundColor: colors.background,
        },
        headerTintColor: colors.text,
        tabBarStyle: {
          backgroundColor: colors.card,
          borderTopColor: isDark ? '#2a2a4e' : '#e9ecef',
        },
        tabBarActiveTintColor: colors.primary,
        tabBarInactiveTintColor: colors.inactive,
      }}
    >
      <Tabs.Screen
        name="index"
        options={{
          title: 'Dashboard',
          tabBarIcon: ({ color, size }: { color: string; size: number }) => (
            <Ionicons name="home" size={size} color={color} />
          ),
        }}
      />
      <Tabs.Screen
        name="matches"
        options={{
          title: 'Matches',
          tabBarIcon: ({ color, size }: { color: string; size: number }) => (
            <Ionicons name="football" size={size} color={color} />
          ),
        }}
      />
      <Tabs.Screen
        name="arbitrage"
        options={{
          title: 'Arbitrage',
          tabBarIcon: ({ color, size }: { color: string; size: number }) => (
            <Ionicons name="trending-up" size={size} color={color} />
          ),
        }}
      />
      <Tabs.Screen
        name="profile"
        options={{
          title: 'Profile',
          tabBarIcon: ({ color, size }: { color: string; size: number }) => (
            <Ionicons name="person" size={size} color={color} />
          ),
        }}
      />
    </Tabs>
  );
}
