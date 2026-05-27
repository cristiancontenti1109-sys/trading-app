import React, { useEffect, useState, useCallback } from 'react';
import { View, Text, ScrollView, StyleSheet, TouchableOpacity, ActivityIndicator } from 'react-native';
import { useRoute, useNavigation } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import { useDispatch, useSelector } from 'react-redux';

import { RootState, AppDispatch } from '../store';
import { fetchSignal } from '../store/signalSlice';
import { Timeframe, Candle } from '../types';
import SignalCard from '../components/SignalCard';
import ChartView from '../components/ChartView';
import { getOHLCV } from '../services/api';
import { wsClient } from '../services/websocket';
import { updatePrice } from '../store/watchlistSlice';

const TIMEFRAMES: Timeframe[] = ['15m', '1h', '4h', '1D', '1W'];

export default function InstrumentScreen() {
  const route = useRoute<any>();
  const navigation = useNavigation<any>();
  const dispatch = useDispatch<AppDispatch>();
  const { symbol } = route.params as { symbol: string };

  const [timeframe, setTimeframe] = useState<Timeframe>('4h');
  const [candles, setCandles] = useState<Candle[]>([]);
  const [candlesLoading, setCandlesLoading] = useState(false);
  const [livePrice, setLivePrice] = useState<number | null>(null);

  const signalKey = `${symbol}_${timeframe}`;
  const signal = useSelector((s: RootState) => s.signals.signals[signalKey]);
  const signalLoading = useSelector((s: RootState) => s.signals.loading[signalKey]);

  const loadCandles = useCallback(async () => {
    setCandlesLoading(true);
    const data = await getOHLCV(symbol, timeframe, 200);
    setCandles(data.candles);
    setCandlesLoading(false);
  }, [symbol, timeframe]);

  useEffect(() => {
    dispatch(fetchSignal({ symbol, timeframe }));
    loadCandles();
  }, [symbol, timeframe, dispatch, loadCandles]);

  useEffect(() => {
    wsClient.subscribe(symbol);
    const unsub = wsClient.on('price_update', (msg) => {
      if (msg.symbol === symbol) setLivePrice(msg.price);
    });
    return () => {
      unsub();
      wsClient.unsubscribe(symbol);
    };
  }, [symbol]);

  const priceDisplay = livePrice ?? (candles.length > 0 ? candles[candles.length - 1]?.close : null);

  return (
    <View style={styles.container}>
      {/* Nav header */}
      <View style={styles.navBar}>
        <TouchableOpacity onPress={() => navigation.goBack()} style={styles.backBtn}>
          <Ionicons name="arrow-back" size={24} color="#E6EDF3" />
        </TouchableOpacity>
        <View>
          <Text style={styles.navSymbol}>{symbol}</Text>
          {priceDisplay != null && (
            <Text style={styles.navPrice}>{formatPrice(priceDisplay)}</Text>
          )}
        </View>
      </View>

      <ScrollView showsVerticalScrollIndicator={false}>
        {/* Chart */}
        <View style={styles.chartWrap}>
          <ChartView candles={candles} loading={candlesLoading} signal={signal} />
        </View>

        {/* Timeframe selector */}
        <View style={styles.tfRow}>
          {TIMEFRAMES.map((tf) => (
            <TouchableOpacity
              key={tf}
              onPress={() => setTimeframe(tf)}
              style={[styles.tfBtn, timeframe === tf && styles.tfActive]}
            >
              <Text style={[styles.tfText, timeframe === tf && styles.tfActiveText]}>{tf}</Text>
            </TouchableOpacity>
          ))}
        </View>

        {/* Signal */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>AI Signal</Text>
          {signalLoading ? (
            <View style={styles.center}>
              <ActivityIndicator color="#58A6FF" />
            </View>
          ) : signal ? (
            <SignalCard signal={signal} />
          ) : (
            <Text style={styles.noData}>No signal available</Text>
          )}
        </View>

        {/* Disclaimer */}
        <Text style={styles.disclaimer}>
          This app provides analytical tools only. Not financial advice. Always do your own research before trading.
        </Text>
      </ScrollView>
    </View>
  );
}

function formatPrice(p: number): string {
  if (p >= 1000) return '$' + p.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  if (p >= 1) return '$' + p.toFixed(4);
  return '$' + p.toFixed(6);
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#0D1117' },
  navBar: { flexDirection: 'row', alignItems: 'center', gap: 12, padding: 16, paddingTop: 52, borderBottomWidth: 1, borderBottomColor: '#21262D' },
  backBtn: { padding: 4 },
  navSymbol: { color: '#E6EDF3', fontWeight: '700', fontSize: 18 },
  navPrice: { color: '#8B949E', fontSize: 14 },
  chartWrap: { margin: 16 },
  tfRow: { flexDirection: 'row', justifyContent: 'center', gap: 6, marginHorizontal: 16, marginBottom: 8 },
  tfBtn: { paddingHorizontal: 12, paddingVertical: 6, borderRadius: 8, backgroundColor: '#161B22' },
  tfActive: { backgroundColor: '#58A6FF22', borderWidth: 1, borderColor: '#58A6FF' },
  tfText: { color: '#8B949E', fontSize: 13, fontWeight: '600' },
  tfActiveText: { color: '#58A6FF' },
  section: { paddingHorizontal: 16, marginBottom: 8 },
  sectionTitle: { color: '#E6EDF3', fontWeight: '700', fontSize: 16, marginBottom: 8 },
  center: { padding: 24, alignItems: 'center' },
  noData: { color: '#484F58', textAlign: 'center', padding: 24 },
  disclaimer: { color: '#484F58', fontSize: 11, textAlign: 'center', padding: 16, paddingBottom: 32 },
});
