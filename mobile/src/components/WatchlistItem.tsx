import React from 'react';
import { View, Text, TouchableOpacity, StyleSheet } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { WatchlistItem as WLItem } from '../types';

interface Props {
  item: WLItem;
  livePrice?: number;
  changePct?: number;
  onPress: () => void;
  onPin: () => void;
  onRemove: () => void;
}

const ASSET_COLORS = {
  crypto: '#F7931A',
  stocks: '#58A6FF',
  forex: '#3FB950',
  commodities: '#D2A679',
};

export default function WatchlistItemRow({ item, livePrice, changePct, onPress, onPin, onRemove }: Props) {
  const price = livePrice ?? item.last_price;
  const change = changePct ?? 0;
  const assetColor = ASSET_COLORS[item.asset_class] ?? '#8B949E';

  return (
    <TouchableOpacity style={styles.row} onPress={onPress} activeOpacity={0.7}>
      {/* Asset class dot */}
      <View style={[styles.dot, { backgroundColor: assetColor }]} />

      {/* Symbol + name */}
      <View style={styles.info}>
        <Text style={styles.symbol}>{item.symbol}</Text>
        <Text style={styles.name} numberOfLines={1}>{item.name}</Text>
      </View>

      {/* Price + change */}
      <View style={styles.priceBlock}>
        {price != null ? (
          <>
            <Text style={styles.price}>{formatPrice(price)}</Text>
            <Text style={[styles.change, { color: change >= 0 ? '#3FB950' : '#FF4560' }]}>
              {change >= 0 ? '+' : ''}{change.toFixed(2)}%
            </Text>
          </>
        ) : (
          <Text style={styles.loading}>—</Text>
        )}
      </View>

      {/* Actions */}
      <TouchableOpacity onPress={onPin} style={styles.action}>
        <Ionicons name={item.pinned ? 'bookmark' : 'bookmark-outline'} size={18} color={item.pinned ? '#F7931A' : '#484F58'} />
      </TouchableOpacity>
      <TouchableOpacity onPress={onRemove} style={styles.action}>
        <Ionicons name="trash-outline" size={18} color="#484F58" />
      </TouchableOpacity>
    </TouchableOpacity>
  );
}

function formatPrice(p: number): string {
  if (p >= 1000) return p.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  if (p >= 1) return p.toFixed(4);
  return p.toFixed(6);
}

const styles = StyleSheet.create({
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 12,
    paddingHorizontal: 16,
    borderBottomWidth: 1,
    borderBottomColor: '#21262D',
    backgroundColor: '#0D1117',
  },
  dot: { width: 8, height: 8, borderRadius: 4, marginRight: 10 },
  info: { flex: 1 },
  symbol: { color: '#E6EDF3', fontWeight: '700', fontSize: 15 },
  name: { color: '#8B949E', fontSize: 12, marginTop: 1 },
  priceBlock: { alignItems: 'flex-end', marginRight: 8 },
  price: { color: '#E6EDF3', fontWeight: '600', fontSize: 14 },
  change: { fontSize: 12, fontWeight: '600' },
  loading: { color: '#484F58', fontSize: 14 },
  action: { padding: 6 },
});
