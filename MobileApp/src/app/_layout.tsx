/**
 * Root Layout for BetSnipe.ai
 */

import { useEffect } from 'react';
import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useColorScheme } from 'react-native';
import * as SplashScreen from 'expo-splash-screen';

import { useAuthStore } from '@/stores';

// Keep splash screen visible while loading
SplashScreen.preventAutoHideAsync();

// Create a client
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 1000 * 60, // 1 minute
      retry: 2,
    },
  },
});

export default function RootLayout() {
  const colorScheme = useColorScheme();
  const { initialize, isLoading } = useAuthStore();

  useEffect(() => {
    const init = async () => {
      await initialize();
      await SplashScreen.hideAsync();
    };
    init();
  }, []);

  if (isLoading) {
    return null; // Splash screen is still visible
  }

  return (
    <QueryClientProvider client={queryClient}>
      <StatusBar style={colorScheme === 'dark' ? 'light' : 'dark'} />
      <Stack
        screenOptions={{
          headerStyle: {
            backgroundColor: colorScheme === 'dark' ? '#1a1a2e' : '#ffffff',
          },
          headerTintColor: colorScheme === 'dark' ? '#ffffff' : '#1a1a2e',
          headerTitleStyle: {
            fontWeight: '600',
          },
        }}
      >
        <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
        <Stack.Screen
          name="match/[id]"
          options={{
            title: 'Match Details',
            presentation: 'card',
          }}
        />
        <Stack.Screen
          name="arbitrage/[id]"
          options={{
            title: 'Arbitrage Details',
            presentation: 'card',
          }}
        />
        <Stack.Screen
          name="login"
          options={{
            title: 'Login',
            presentation: 'modal',
          }}
        />
        <Stack.Screen
          name="settings"
          options={{
            title: 'Settings',
            presentation: 'card',
          }}
        />
      </Stack>
    </QueryClientProvider>
  );
}
