import React, { useState } from 'react';
import { View, Text, TextInput, TouchableOpacity, StyleSheet, KeyboardAvoidingView, Platform, Alert } from 'react-native';
import { useDispatch, useSelector } from 'react-redux';
import { AppDispatch, RootState } from '../store';
import { loginUser, registerUser, fetchMe } from '../store/authSlice';

export default function AuthScreen() {
  const dispatch = useDispatch<AppDispatch>();
  const loading = useSelector((s: RootState) => s.auth.loading);
  const [mode, setMode] = useState<'login' | 'register'>('login');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');

  const handleSubmit = async () => {
    if (!email || !password) {
      Alert.alert('Error', 'Please fill in all fields');
      return;
    }
    const action = mode === 'login' ? loginUser : registerUser;
    const result = await dispatch(action({ email, password }));
    if (result.meta.requestStatus === 'fulfilled') {
      dispatch(fetchMe());
    } else {
      Alert.alert('Error', (result as any).error?.message ?? 'Authentication failed');
    }
  };

  return (
    <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : 'height'} style={styles.container}>
      <View style={styles.inner}>
        <Text style={styles.logo}>📈</Text>
        <Text style={styles.title}>TradingSignals</Text>
        <Text style={styles.subtitle}>AI-powered signals for every market</Text>

        <View style={styles.form}>
          <TextInput
            style={styles.input}
            placeholder="Email"
            placeholderTextColor="#484F58"
            value={email}
            onChangeText={setEmail}
            autoCapitalize="none"
            keyboardType="email-address"
          />
          <TextInput
            style={styles.input}
            placeholder="Password"
            placeholderTextColor="#484F58"
            value={password}
            onChangeText={setPassword}
            secureTextEntry
          />
          <TouchableOpacity style={styles.btn} onPress={handleSubmit} disabled={loading}>
            <Text style={styles.btnText}>{loading ? 'Loading...' : mode === 'login' ? 'Sign In' : 'Create Account'}</Text>
          </TouchableOpacity>
        </View>

        <TouchableOpacity onPress={() => setMode(mode === 'login' ? 'register' : 'login')}>
          <Text style={styles.switchTxt}>
            {mode === 'login' ? "Don't have an account? Sign up" : 'Already have an account? Sign in'}
          </Text>
        </TouchableOpacity>

        <Text style={styles.disclaimer}>Not financial advice. For informational purposes only.</Text>
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#0D1117' },
  inner: { flex: 1, justifyContent: 'center', alignItems: 'center', padding: 32 },
  logo: { fontSize: 64, marginBottom: 12 },
  title: { color: '#E6EDF3', fontSize: 32, fontWeight: '800', marginBottom: 6 },
  subtitle: { color: '#8B949E', fontSize: 15, marginBottom: 40, textAlign: 'center' },
  form: { width: '100%', gap: 12, marginBottom: 20 },
  input: { backgroundColor: '#161B22', borderWidth: 1, borderColor: '#30363D', borderRadius: 12, paddingHorizontal: 16, paddingVertical: 14, color: '#E6EDF3', fontSize: 15 },
  btn: { backgroundColor: '#58A6FF', borderRadius: 12, paddingVertical: 14, alignItems: 'center' },
  btnText: { color: '#fff', fontWeight: '700', fontSize: 16 },
  switchTxt: { color: '#58A6FF', fontSize: 14, marginBottom: 32 },
  disclaimer: { color: '#484F58', fontSize: 11, textAlign: 'center' },
});
