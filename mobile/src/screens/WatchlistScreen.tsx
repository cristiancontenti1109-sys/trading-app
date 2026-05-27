import React, { useEffect, useCallback } from 'react';
import { View, FlatList, Text, TouchableOpacity, StyleSheet, RefreshControl, Alert } from 'react-native';
import { useNavigation } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import { useDispatch, useSelector } from 'react-redux';

import { RootState, AppDispatch } from '../store';
import { fetchWatchlist, removeSymbol, updatePrice } from '../store/watchlistSlice';
import WatchlistItemRow from '../components/WatchlistItem';
import { wsClient } from '../services/websocket';
import { togglePin } from '../services/api';

export default function WatchlistScreen() {
  const dispatch = useDispatch<AppDispatch>();
  const navigation = useNavigation<any>();
  const { items, loading, prices } = useSelector((s: RootState) => s.watchlist);

  const load = useCallback(() => {
    dispatch(fetchWatchlist());
  }, [dispatch]);

  useEffect(() => {
    load();
  }, [load]);

  // Subscribe to price updates via WebSocket
  useEffect(() => {
    const unsub = wsClient.on('price_update', (msg) => {
      dispatch(updatePrice({ symbol: msg.symbol, price: msg.price, change_pct: msg.change_pct }));
    });
    items.forEach((item) => wsClient.subscribe(item.symbol));
    return () => {
      unsub();
      items.forEach((item) => wsClient.unsubscribe(item.symbol));
    };
  }, [items, dispatch]);

  const handleRemove = (symbol: string) => {
    Alert.alert('Remove', `Remove ${symbol} from watchlist?`, [
      { text: 'Cancel', style: 'cancel' },
      { text: 'Remove', style: 'destructive', onPress: () => dispatch(removeSymbol(symbol)) },
    ]);
  };

  const handlePin = async (symbol: string) => {
    await togglePin(symbol);
    load();
  };

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.title}>Watchlist</Text>
        <TouchableOpacity onPress={() => navigation.navigate('Search')} style={styles.addBtn}>
          <Ionicons name="add-circle" size={28} color="#58A6FF" />
        </TouchableOpacity>
      </View>

      {items.length === 0 && !loading ? (
        <View style={styles.empty}>
          <Ionicons name="telescope-outline" size={64} color="#30363D" />
          <Text style={styles.emptyTitle}>Your watchlist is empty</Text>
          <Text style={styles.emptyText}>Tap + to add instruments across crypto, stocks, forex & commodities</Text>
          <TouchableOpacity style={styles.emptyBtn} onPress={() => navigation.navigate('Search')}>
            <Text style={styles.emptyBtnText}>Add Instrument</Text>
          </TouchableOpacity>
        </View>
      ) : (
        <FlatList
          data={items}
          keyExtractor={(i) => i.symbol}
          refreshControl={<RefreshControl refreshing={loading} onRefresh={load} tintColor="#58A6FF" />}
          renderItem={({ item }) => (
            <WatchlistItemRow
              item={item}
              livePrice={prices[item.symbol]?.price}
              changePct={prices[item.symbol]?.change_pct}
              onPress={() => navigation.navigate('Instrument', { symbol: item.symbol })}
              onPin={() => handlePin(item.symbol)}
              onRemove={() => handleRemove(item.symbol)}
            />
          )}
        />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#0D1117' },
  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', padding: 16, paddingTop: 52, borderBottomWidth: 1, borderBottomColor: '#21262D' },
  title: { color: '#E6EDF3', fontSize: 24, fontWeight: '700' },
  addBtn: { padding: 4 },
  empty: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: 32 },
  emptyTitle: { color: '#E6EDF3', fontSize: 20, fontWeight: '700', marginTop: 16, marginBottom: 8 },
  emptyText: { color: '#8B949E', fontSize: 14, textAlign: 'center', lineHeight: 20 },
  emptyBtn: { marginTop: 24, backgroundColor: '#58A6FF', borderRadius: 12, paddingHorizontal: 24, paddingVertical: 12 },
  emptyBtnText: { color: '#fff', fontWeight: '700', fontSize: 15 },
});
