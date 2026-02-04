/**
 * Login Screen for BetSnipe.ai
 */

import { useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TextInput,
  TouchableOpacity,
  KeyboardAvoidingView,
  Platform,
  ActivityIndicator,
  useColorScheme,
} from 'react-native';
import { router } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';

import { useAuthStore } from '@/stores';

export default function LoginScreen() {
  const colorScheme = useColorScheme();
  const isDark = colorScheme === 'dark';

  const [isLogin, setIsLogin] = useState(true);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);

  const { login, register, isLoading, error, clearError } = useAuthStore();

  const handleSubmit = async () => {
    if (!email.trim() || !password.trim()) {
      return;
    }

    if (!isLogin && password !== confirmPassword) {
      // Show error
      return;
    }

    let success: boolean;
    if (isLogin) {
      success = await login(email.trim(), password);
    } else {
      success = await register(email.trim(), password);
    }

    if (success) {
      router.back();
    }
  };

  const switchMode = () => {
    clearError();
    setIsLogin(!isLogin);
    setPassword('');
    setConfirmPassword('');
  };

  const styles = createStyles(isDark);

  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
    >
      <View style={styles.content}>
        {/* Logo/Header */}
        <View style={styles.header}>
          <View style={styles.logoContainer}>
            <Ionicons name="trending-up" size={48} color="#4361ee" />
          </View>
          <Text style={styles.title}>BetSnipe</Text>
          <Text style={styles.subtitle}>
            {isLogin ? 'Sign in to your account' : 'Create your account'}
          </Text>
        </View>

        {/* Form */}
        <View style={styles.form}>
          {/* Email Input */}
          <View style={styles.inputContainer}>
            <Ionicons name="mail" size={20} color={isDark ? '#6c757d' : '#adb5bd'} />
            <TextInput
              style={styles.input}
              placeholder="Email"
              placeholderTextColor={isDark ? '#6c757d' : '#adb5bd'}
              value={email}
              onChangeText={setEmail}
              keyboardType="email-address"
              autoCapitalize="none"
              autoComplete="email"
            />
          </View>

          {/* Password Input */}
          <View style={styles.inputContainer}>
            <Ionicons name="lock-closed" size={20} color={isDark ? '#6c757d' : '#adb5bd'} />
            <TextInput
              style={styles.input}
              placeholder="Password"
              placeholderTextColor={isDark ? '#6c757d' : '#adb5bd'}
              value={password}
              onChangeText={setPassword}
              secureTextEntry={!showPassword}
              autoCapitalize="none"
            />
            <TouchableOpacity onPress={() => setShowPassword(!showPassword)}>
              <Ionicons
                name={showPassword ? 'eye-off' : 'eye'}
                size={20}
                color={isDark ? '#6c757d' : '#adb5bd'}
              />
            </TouchableOpacity>
          </View>

          {/* Confirm Password (Register only) */}
          {!isLogin && (
            <View style={styles.inputContainer}>
              <Ionicons name="lock-closed" size={20} color={isDark ? '#6c757d' : '#adb5bd'} />
              <TextInput
                style={styles.input}
                placeholder="Confirm Password"
                placeholderTextColor={isDark ? '#6c757d' : '#adb5bd'}
                value={confirmPassword}
                onChangeText={setConfirmPassword}
                secureTextEntry={!showPassword}
                autoCapitalize="none"
              />
            </View>
          )}

          {/* Error Message */}
          {error && (
            <View style={styles.errorContainer}>
              <Ionicons name="alert-circle" size={16} color="#ef4444" />
              <Text style={styles.errorText}>{error}</Text>
            </View>
          )}

          {/* Submit Button */}
          <TouchableOpacity
            style={[styles.submitButton, isLoading && styles.submitButtonDisabled]}
            onPress={handleSubmit}
            disabled={isLoading}
          >
            {isLoading ? (
              <ActivityIndicator color="#ffffff" />
            ) : (
              <Text style={styles.submitButtonText}>
                {isLogin ? 'Sign In' : 'Create Account'}
              </Text>
            )}
          </TouchableOpacity>

          {/* Forgot Password (Login only) */}
          {isLogin && (
            <TouchableOpacity style={styles.forgotPassword}>
              <Text style={styles.forgotPasswordText}>Forgot Password?</Text>
            </TouchableOpacity>
          )}
        </View>

        {/* Switch Mode */}
        <View style={styles.switchContainer}>
          <Text style={styles.switchText}>
            {isLogin ? "Don't have an account?" : 'Already have an account?'}
          </Text>
          <TouchableOpacity onPress={switchMode}>
            <Text style={styles.switchLink}>
              {isLogin ? 'Sign Up' : 'Sign In'}
            </Text>
          </TouchableOpacity>
        </View>

        {/* Terms */}
        <Text style={styles.terms}>
          By continuing, you agree to our Terms of Service and Privacy Policy
        </Text>
      </View>
    </KeyboardAvoidingView>
  );
}

const createStyles = (isDark: boolean) =>
  StyleSheet.create({
    container: {
      flex: 1,
      backgroundColor: isDark ? '#0f0f23' : '#f8f9fa',
    },
    content: {
      flex: 1,
      padding: 24,
      justifyContent: 'center',
    },
    header: {
      alignItems: 'center',
      marginBottom: 40,
    },
    logoContainer: {
      width: 80,
      height: 80,
      borderRadius: 20,
      backgroundColor: isDark ? '#1a1a2e' : '#ffffff',
      justifyContent: 'center',
      alignItems: 'center',
      marginBottom: 16,
    },
    title: {
      fontSize: 28,
      fontWeight: '700',
      color: isDark ? '#ffffff' : '#1a1a2e',
    },
    subtitle: {
      fontSize: 16,
      color: isDark ? '#9ca3af' : '#6c757d',
      marginTop: 8,
    },
    form: {
      gap: 16,
    },
    inputContainer: {
      flexDirection: 'row',
      alignItems: 'center',
      backgroundColor: isDark ? '#1a1a2e' : '#ffffff',
      paddingHorizontal: 16,
      borderRadius: 12,
      borderWidth: 1,
      borderColor: isDark ? '#2a2a4e' : '#e9ecef',
    },
    input: {
      flex: 1,
      paddingVertical: 16,
      paddingHorizontal: 12,
      fontSize: 16,
      color: isDark ? '#ffffff' : '#1a1a2e',
    },
    errorContainer: {
      flexDirection: 'row',
      alignItems: 'center',
      backgroundColor: '#fef2f2',
      padding: 12,
      borderRadius: 8,
      gap: 8,
    },
    errorText: {
      flex: 1,
      fontSize: 14,
      color: '#ef4444',
    },
    submitButton: {
      backgroundColor: '#4361ee',
      paddingVertical: 16,
      borderRadius: 12,
      alignItems: 'center',
      marginTop: 8,
    },
    submitButtonDisabled: {
      opacity: 0.7,
    },
    submitButtonText: {
      color: '#ffffff',
      fontSize: 16,
      fontWeight: '600',
    },
    forgotPassword: {
      alignItems: 'center',
      paddingVertical: 8,
    },
    forgotPasswordText: {
      fontSize: 14,
      color: '#4361ee',
    },
    switchContainer: {
      flexDirection: 'row',
      justifyContent: 'center',
      alignItems: 'center',
      marginTop: 32,
      gap: 4,
    },
    switchText: {
      fontSize: 14,
      color: isDark ? '#9ca3af' : '#6c757d',
    },
    switchLink: {
      fontSize: 14,
      fontWeight: '600',
      color: '#4361ee',
    },
    terms: {
      fontSize: 12,
      color: isDark ? '#6c757d' : '#adb5bd',
      textAlign: 'center',
      marginTop: 24,
      lineHeight: 18,
    },
  });
