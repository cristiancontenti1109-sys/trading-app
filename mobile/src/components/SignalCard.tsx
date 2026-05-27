import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { Signal } from '../types';

const REC_COLORS = { BUY: '#00C896', SELL: '#FF4560', HOLD: '#F7931A' };

interface Props {
  signal: Signal;
  compact?: boolean;
}

export default function SignalCard({ signal, compact = false }: Props) {
  const recColor = REC_COLORS[signal.recommendation];
  const confidencePct = Math.round(signal.confidence * 100);

  return (
    <View style={[styles.card, compact && styles.compact]}>
      {/* Header row */}
      <View style={styles.header}>
        <View style={[styles.recBadge, { backgroundColor: recColor + '22', borderColor: recColor }]}>
          <Text style={[styles.recText, { color: recColor }]}>{signal.recommendation}</Text>
        </View>
        {(signal.is_hot_confluence || signal.is_hot) && (
          <View style={[styles.hotBadge, signal.is_hot_confluence && styles.confluenceBadge]}>
            <Text style={styles.hotText}>{signal.is_hot_confluence ? '🔥 HOT-CONFLUENCE' : '⚡ HOT'}</Text>
          </View>
        )}
        <Text style={styles.timeframe}>{signal.timeframe}</Text>
      </View>

      {/* Confidence bar */}
      <View style={styles.confidenceRow}>
        <Text style={styles.label}>Confidence</Text>
        <View style={styles.barBg}>
          <View style={[styles.barFill, { width: `${confidencePct}%`, backgroundColor: recColor }]} />
        </View>
        <Text style={[styles.confValue, { color: recColor }]}>{confidencePct}%</Text>
      </View>

      {!compact && (
        <>
          {/* Price targets */}
          <View style={styles.targets}>
            <TargetItem label="Entry" value={`${signal.entry_zone.low.toFixed(4)} – ${signal.entry_zone.high.toFixed(4)}`} />
            <TargetItem label="Target" value={signal.target_price.toFixed(4)} color={REC_COLORS.BUY} />
            <TargetItem label="Stop" value={signal.stop_loss.toFixed(4)} color={REC_COLORS.SELL} />
          </View>

          {/* Reasoning */}
          <View style={styles.reasoning}>
            {signal.reasoning.map((r, i) => (
              <View key={i} style={styles.reasonRow}>
                <Text style={styles.reasonBullet}>›</Text>
                <Text style={styles.reasonText}>{r}</Text>
              </View>
            ))}
          </View>

          {/* Indicators strip */}
          {signal.indicators && (
            <View style={styles.indicators}>
              <IndicatorChip label="RSI" value={signal.indicators.rsi.toFixed(0)} />
              <IndicatorChip label="ADX" value={signal.indicators.adx.toFixed(0)} />
              <IndicatorChip label="Vol Z" value={signal.indicators.vol_zscore.toFixed(1)} />
              <IndicatorChip label="%B" value={signal.indicators.bb_pct_b.toFixed(2)} />
            </View>
          )}
        </>
      )}

      {/* Disclaimer */}
      {!compact && (
        <Text style={styles.disclaimer}>Not financial advice. Past signals ≠ future results.</Text>
      )}
    </View>
  );
}

function TargetItem({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <View style={styles.targetItem}>
      <Text style={styles.targetLabel}>{label}</Text>
      <Text style={[styles.targetValue, color ? { color } : {}]}>{value}</Text>
    </View>
  );
}

function IndicatorChip({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.chip}>
      <Text style={styles.chipLabel}>{label}</Text>
      <Text style={styles.chipValue}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: '#161B22',
    borderRadius: 16,
    padding: 16,
    marginVertical: 8,
    borderWidth: 1,
    borderColor: '#30363D',
  },
  compact: { padding: 10, marginVertical: 4 },
  header: { flexDirection: 'row', alignItems: 'center', marginBottom: 12, gap: 8 },
  recBadge: { borderWidth: 1, borderRadius: 8, paddingHorizontal: 10, paddingVertical: 4 },
  recText: { fontWeight: '700', fontSize: 14 },
  hotBadge: { backgroundColor: '#F7931A22', borderRadius: 8, paddingHorizontal: 8, paddingVertical: 4 },
  confluenceBadge: { backgroundColor: '#FF456022' },
  hotText: { color: '#F7931A', fontSize: 11, fontWeight: '600' },
  timeframe: { color: '#8B949E', fontSize: 12, marginLeft: 'auto' },
  confidenceRow: { flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 14 },
  label: { color: '#8B949E', fontSize: 12, width: 75 },
  barBg: { flex: 1, height: 6, backgroundColor: '#21262D', borderRadius: 3, overflow: 'hidden' },
  barFill: { height: '100%', borderRadius: 3 },
  confValue: { fontWeight: '700', fontSize: 13, width: 36, textAlign: 'right' },
  targets: { flexDirection: 'row', justifyContent: 'space-between', marginBottom: 14 },
  targetItem: { flex: 1 },
  targetLabel: { color: '#8B949E', fontSize: 11, marginBottom: 2 },
  targetValue: { color: '#E6EDF3', fontSize: 12, fontWeight: '600' },
  reasoning: { marginBottom: 12 },
  reasonRow: { flexDirection: 'row', gap: 6, marginBottom: 4 },
  reasonBullet: { color: '#58A6FF', fontSize: 12 },
  reasonText: { color: '#C9D1D9', fontSize: 12, flex: 1 },
  indicators: { flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginBottom: 10 },
  chip: { backgroundColor: '#21262D', borderRadius: 6, paddingHorizontal: 8, paddingVertical: 4, flexDirection: 'row', gap: 4 },
  chipLabel: { color: '#8B949E', fontSize: 11 },
  chipValue: { color: '#E6EDF3', fontSize: 11, fontWeight: '600' },
  disclaimer: { color: '#484F58', fontSize: 10, textAlign: 'center', marginTop: 4 },
});
