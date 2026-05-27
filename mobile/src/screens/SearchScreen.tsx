import React, { useState, useEffect } from 'react';
import { View, Text, TextInput, FlatList, TouchableOpacity, StyleSheet, ActivityIndicator } from 'react-native';
import { useNavigation } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import { useDispatch } from 'react-redux';

import { AppDispatch } from '../store';
import { fetchWatchlist } from '../store/watchlistSlice';
import { Instrument } from '../types';
import { searchInstruments, addToWatchlist } from '../services/api';

const ASSET_COLORS: Record<string, string> = {
  crypto: '#F7931A', stocks: '#58A6FF', forex: '#3FB950', commodities: '#D2A679',
};

export default function SearchScreen() {
  const navigation = useNavigation<any>();
  const dispatch = useDispatch<AppDispatch>();
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<Instrument[]>([]);
  const [loading, setLoading] = useState(false);
  const [added, setAdded] = useState<Set<string>>(new Set());

  useEffect(() => {
    if (!query.trim()) { setResults([]); return; }
    const timer = setTimeout(async () => {
      setLoading(true);
      const data = await searchInstruments(query);
      setResults(data);
      setLoading(false);
    }, 300);
    return () => clearTimeout(timer);
  }, [query]);

  const handleAdd = async (instrument: Instrument) => {
    try {
      await addToWatchlist(instrument.symbol);
      setAdded((prev) => new Set(prev).add(instrument.symbol));
      dispatch(fetchWatchlist());
    } catch (e: any) {
      // Already in watchlist or tier limit
    }
  };

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.goBack()} style={styles.back}>
          <Ionicons name="arrow-back" size={24} color="#E6EDF3" />
        </TouchableOpacity>
        <View style={styles.inputWrap}>
          <Ionicons name="search" size={18} color="#8B949E" style={styles.searchIcon} />
          <TextInput
            style={styles.input}
            placeholder="Search BTC, AAPL, EUR/USD..."
            placeholderTextColor="#484F58"
            value={query}
            onChangeText={setQuery}
            autoFocus
            autoCapitalize="characters"
          />
          {query ? (
            <TouchableOpacity onPress={() => setQuery('')}>
              <Ionicons name="close-circle" size={18} color="#484F58" />
            </TouchableOpacity>
          ) : null}
        </View>
      </View>

      {loading && <ActivityIndicator color="#58A6FF" style={{ marginTop: 24 }} />}

      <FlatList
        data={results}
        keyExtractor={(i) => i.symbol}
        renderItem={({ item }) => (
          <TouchableOpacity
            style={styles.resultRow}
            onPress={() => handleAdd(item)}
            activeOpacity={0.7}
          >
            <View style={[styles.assetDot, { backgroundColor: ASSET_COLORS[item.asset_class] }]} />
            <View style={styles.resultInfo}>
              <Text style={styles.resultSymbol}>{item.symbol}</Text>
              <Text style={styles.resultName}>{item.name}</Text>
            </View>
            <View style={[styles.classBadge, { borderColor: ASSET_COLORS[item.asset_class] + '60' }]}>
              <Text style={[styles.classTxt, { color: ASSET_COLORS[item.asset_class] }]}>{item.asset_class}</Text>
            </View>
            {added.has(item.symbol) ? (
              <Ionicons name="checkmark-circle" size={22} color="#3FB950" />
            ) : (
              <Ionicons name="add-circle-outline" size={22} color="#58A6FF" />
            )}
          </TouchableOpacity>
        )}
        ListEmptyComponent={
          query && !loading ? (
            <Text style={styles.empty}>No results for "{query}"</Text>
          ) : !query ? (
            <View style={styles.hints}>
              {['BTC', 'AAPL', 'EURUSD', 'XAUUSD', 'TSLA', 'NVDA'].map((s) => (
                <TouchableOpacity key={s} onPress={() => setQuery(s)} style={styles.hint}>
                  <Text style={styles.hintText}>{s}</Text>
                </TouchableOpacity>
              ))}
            </View>
          ) : null
        }
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#0D1117' },
  header: { flexDirection: 'row', alignItems: 'center', padding: 16, paddingTop: 52, gap: 12, borderBottomWidth: 1, borderBottomColor: '#21262D' },
  back: { padding: 4 },
  inputWrap: { flex: 1, flexDirection: 'row', alignItems: 'center', backgroundColor: '#161B22', borderRadius: 12, paddingHorizontal: 12, height: 44, borderWidth: 1, borderColor: '#30363D' },
  searchIcon: { marginRight: 8 },
  input: { flex: 1, color: '#E6EDF3', fontSize: 15 },
  resultRow: { flexDirection: 'row', alignItems: 'center', padding: 14, paddingHorizontal: 16, borderBottomWidth: 1, borderBottomColor: '#161B22' },
  assetDot: { width: 8, height: 8, borderRadius: 4, marginRight: 12 },
  resultInfo: { flex: 1 },
  resultSymbol: { color: '#E6EDF3', fontWeight: '700', fontSize: 15 },
  resultName: { color: '#8B949E', fontSize: 12 },
  classBadge: { borderWidth: 1, borderRadius: 6, paddingHorizontal: 7, paddingVertical: 2, marginRight: 10 },
  classTxt: { fontSize: 11, fontWeight: '600' },
  empty: { color: '#484F58', textAlign: 'center', marginTop: 48, fontSize: 14 },
  hints: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, padding: 16 },
  hint: { backgroundColor: '#161B22', borderRadius: 8, paddingHorizontal: 14, paddingVertical: 8, borderWidth: 1, borderColor: '#30363D' },
  hintText: { color: '#8B949E', fontWeight: '600' },
});
