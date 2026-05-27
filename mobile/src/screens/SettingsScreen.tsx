import React, { useState } from 'react';
import { View, Text, ScrollView, StyleSheet, Switch, TouchableOpacity, Alert, Modal, FlatList } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useDispatch, useSelector } from 'react-redux';
import { RootState, AppDispatch } from '../store';
import { logout } from '../store/authSlice';
import { updateSettings } from '../services/api';
import { STRATEGIES, TradingStrategy } from '../data/strategies';

export default function SettingsScreen() {
  const dispatch = useDispatch<AppDispatch>();
  const user = useSelector((s: RootState) => s.auth.user);
  const settings = user?.settings;

  const [saving, setSaving] = useState(false);
  const [strategyModalVisible, setStrategyModalVisible] = useState(false);
  const [expandedStrategy, setExpandedStrategy] = useState<string | null>(null);

  const selectedStrategyId = settings?.selected_strategy ?? null;
  const selectedStrategy = STRATEGIES.find((s) => s.id === selectedStrategyId) ?? null;

  const updateSetting = async (key: string, value: any) => {
    setSaving(true);
    try {
      await updateSettings({ [key]: value });
    } finally {
      setSaving(false);
    }
  };

  const handleLogout = () => {
    Alert.alert('Logout', 'Are you sure?', [
      { text: 'Cancel', style: 'cancel' },
      { text: 'Logout', style: 'destructive', onPress: () => dispatch(logout()) },
    ]);
  };

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      <Text style={styles.title}>Settings</Text>

      {/* Account */}
      <Section title="Account">
        <InfoRow label="Email" value={user?.email ?? '—'} />
        <InfoRow label="Plan" value={user?.subscription_tier === 'pro' ? '⭐ Pro' : 'Free'} />
        {user?.subscription_tier === 'free' && (
          <TouchableOpacity style={styles.upgradeBtn}>
            <Text style={styles.upgradeTxt}>Upgrade to Pro — Unlimited instruments & alerts</Text>
          </TouchableOpacity>
        )}
      </Section>

      {/* HOT Detection */}
      <Section title="HOT Detection">
        <SliderRow
          label="Pattern confidence threshold"
          value={`${Math.round((settings?.hot_pattern_threshold ?? 0.75) * 100)}%`}
          hint="Minimum AI confidence to trigger HOT"
        />
        <SliderRow
          label="Volume z-score threshold"
          value={`+${settings?.hot_volume_zscore ?? 3.0}σ`}
          hint="Volume spike needed to trigger HOT"
        />
      </Section>

      {/* Notifications */}
      <Section title="Notifications">
        <InfoRow label="Daily cap" value={`${settings?.daily_notification_cap ?? 20} alerts/day`} />
        <InfoRow label="Quiet hours" value={`${settings?.quiet_hours_start ?? '22:00'} – ${settings?.quiet_hours_end ?? '07:00'}`} />
        <MarketToggle label="Crypto" enabled={settings?.markets_enabled?.includes('crypto') ?? true} onToggle={(v) => {}} />
        <MarketToggle label="Stocks" enabled={settings?.markets_enabled?.includes('stocks') ?? true} onToggle={(v) => {}} />
        <MarketToggle label="Forex" enabled={settings?.markets_enabled?.includes('forex') ?? true} onToggle={(v) => {}} />
        <MarketToggle label="Commodities" enabled={settings?.markets_enabled?.includes('commodities') ?? true} onToggle={(v) => {}} />
      </Section>

      {/* Strategia di Trading */}
      <Section title="Strategia di Trading">
        <TouchableOpacity style={stStyles.strategySelector} onPress={() => setStrategyModalVisible(true)}>
          {selectedStrategy ? (
            <View style={stStyles.selectedRow}>
              <View style={stStyles.selectedIcon}>
                <Ionicons name={selectedStrategy.icona as any} size={20} color="#58A6FF" />
              </View>
              <View style={stStyles.selectedInfo}>
                <Text style={stStyles.selectedName}>{selectedStrategy.nome}</Text>
                <Text style={stStyles.selectedMeta}>{selectedStrategy.categoria} · {selectedStrategy.profilo_rischio}</Text>
              </View>
              <Ionicons name="chevron-forward" size={16} color="#484F58" />
            </View>
          ) : (
            <View style={stStyles.selectedRow}>
              <View style={[stStyles.selectedIcon, { backgroundColor: '#21262D' }]}>
                <Ionicons name="add-outline" size={20} color="#8B949E" />
              </View>
              <Text style={stStyles.placeholderTxt}>Seleziona una strategia</Text>
              <Ionicons name="chevron-forward" size={16} color="#484F58" />
            </View>
          )}
        </TouchableOpacity>
      </Section>

      <Modal visible={strategyModalVisible} animationType="slide" presentationStyle="pageSheet" onRequestClose={() => setStrategyModalVisible(false)}>
        <View style={stStyles.modal}>
          <View style={stStyles.modalHeader}>
            <Text style={stStyles.modalTitle}>Strategia di Trading</Text>
            <TouchableOpacity onPress={() => setStrategyModalVisible(false)}>
              <Ionicons name="close" size={24} color="#8B949E" />
            </TouchableOpacity>
          </View>
          <FlatList
            data={STRATEGIES}
            keyExtractor={(item) => item.id}
            contentContainerStyle={{ paddingBottom: 40 }}
            renderItem={({ item }) => {
              const isSelected = item.id === selectedStrategyId;
              const isExpanded = expandedStrategy === item.id;
              return (
                <View style={[stStyles.strategyCard, isSelected && stStyles.strategyCardSelected]}>
                  <TouchableOpacity onPress={() => setExpandedStrategy(isExpanded ? null : item.id)} activeOpacity={0.8}>
                    <View style={stStyles.strategyCardHeader}>
                      <View style={[stStyles.strategyIcon, isSelected && stStyles.strategyIconSelected]}>
                        <Ionicons name={item.icona as any} size={22} color={isSelected ? '#58A6FF' : '#8B949E'} />
                      </View>
                      <View style={stStyles.strategyCardInfo}>
                        <Text style={[stStyles.strategyName, isSelected && stStyles.strategyNameSelected]}>{item.nome}</Text>
                        <Text style={stStyles.strategyCat}>{item.categoria}</Text>
                        <View style={stStyles.tagRow}>
                          <RiskBadge risk={item.profilo_rischio} />
                          <Text style={stStyles.stile}>{item.stile}</Text>
                        </View>
                      </View>
                      <Ionicons name={isExpanded ? 'chevron-up' : 'chevron-down'} size={16} color="#484F58" />
                    </View>
                  </TouchableOpacity>

                  {isExpanded && (
                    <View style={stStyles.strategyDetail}>
                      <Text style={stStyles.filosofia}>{item.filosofia}</Text>
                      <Text style={stStyles.detailLabel}>Punti chiave</Text>
                      {item.punti_chiave.map((p, i) => (
                        <Text key={i} style={stStyles.bulletPoint}>• {p}</Text>
                      ))}
                      <Text style={stStyles.detailLabel}>Asset compatibili</Text>
                      <Text style={stStyles.detailValue}>{item.asset_compatibili.join(' · ')}</Text>
                      <Text style={stStyles.detailLabel}>Timeframe consigliati</Text>
                      <Text style={stStyles.detailValue}>{item.timeframe_consigliati.join(' · ')}</Text>
                    </View>
                  )}

                  <TouchableOpacity
                    style={[stStyles.selectBtn, isSelected && stStyles.selectBtnActive]}
                    onPress={async () => {
                      await updateSetting('selected_strategy', isSelected ? null : item.id);
                      setStrategyModalVisible(false);
                    }}
                  >
                    <Text style={[stStyles.selectBtnTxt, isSelected && stStyles.selectBtnTxtActive]}>
                      {isSelected ? '✓ Selezionata' : 'Seleziona'}
                    </Text>
                  </TouchableOpacity>
                </View>
              );
            }}
          />
        </View>
      </Modal>

      {/* Display */}
      <Section title="Display">
        <InfoRow label="Default timeframe" value={settings?.default_timeframe ?? '4h'} />
        <InfoRow label="Theme" value={settings?.theme ?? 'dark'} />
      </Section>

      {/* Legal */}
      <Section title="Legal">
        <TextRow text="This app provides analytical tools only and does not constitute financial advice. Always conduct your own due diligence before making any investment decisions. Past signal performance does not guarantee future results." />
      </Section>

      {/* Logout */}
      <TouchableOpacity style={styles.logoutBtn} onPress={handleLogout}>
        <Ionicons name="log-out-outline" size={20} color="#FF4560" />
        <Text style={styles.logoutTxt}>Logout</Text>
      </TouchableOpacity>

      <Text style={styles.version}>TradingSignals v1.0.0</Text>
    </ScrollView>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <View style={sStyles.section}>
      <Text style={sStyles.sectionTitle}>{title}</Text>
      <View style={sStyles.sectionBody}>{children}</View>
    </View>
  );
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <View style={sStyles.row}>
      <Text style={sStyles.label}>{label}</Text>
      <Text style={sStyles.value}>{value}</Text>
    </View>
  );
}

function SliderRow({ label, value, hint }: { label: string; value: string; hint: string }) {
  return (
    <View style={sStyles.sliderRow}>
      <View style={sStyles.sliderTop}>
        <Text style={sStyles.label}>{label}</Text>
        <Text style={sStyles.value}>{value}</Text>
      </View>
      <Text style={sStyles.hint}>{hint}</Text>
    </View>
  );
}

function MarketToggle({ label, enabled, onToggle }: { label: string; enabled: boolean; onToggle: (v: boolean) => void }) {
  return (
    <View style={sStyles.row}>
      <Text style={sStyles.label}>{label}</Text>
      <Switch value={enabled} onValueChange={onToggle} trackColor={{ false: '#30363D', true: '#58A6FF' }} thumbColor="#fff" />
    </View>
  );
}

function TextRow({ text }: { text: string }) {
  return <Text style={sStyles.legalText}>{text}</Text>;
}

const RISK_COLORS: Record<string, string> = {
  'Basso': '#3FB950',
  'Basso-Medio': '#3FB950',
  'Medio': '#D29922',
  'Medio-Alto': '#F85149',
  'Alto': '#F85149',
};

function RiskBadge({ risk }: { risk: string }) {
  const color = RISK_COLORS[risk] ?? '#8B949E';
  return (
    <View style={[stStyles.riskBadge, { borderColor: color + '60', backgroundColor: color + '18' }]}>
      <Text style={[stStyles.riskTxt, { color }]}>{risk}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#0D1117' },
  content: { paddingBottom: 48 },
  title: { color: '#E6EDF3', fontSize: 24, fontWeight: '700', padding: 16, paddingTop: 52 },
  upgradeBtn: { margin: 12, backgroundColor: '#F7931A', borderRadius: 12, padding: 14, alignItems: 'center' },
  upgradeTxt: { color: '#fff', fontWeight: '700', fontSize: 14 },
  logoutBtn: { flexDirection: 'row', alignItems: 'center', gap: 8, margin: 16, padding: 14, backgroundColor: '#FF456012', borderRadius: 12, borderWidth: 1, borderColor: '#FF456040', justifyContent: 'center' },
  logoutTxt: { color: '#FF4560', fontWeight: '700', fontSize: 15 },
  version: { color: '#484F58', textAlign: 'center', fontSize: 12, marginTop: 8 },
});

const sStyles = StyleSheet.create({
  section: { marginHorizontal: 16, marginBottom: 16 },
  sectionTitle: { color: '#8B949E', fontSize: 12, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 0.8, marginBottom: 8, marginLeft: 4 },
  sectionBody: { backgroundColor: '#161B22', borderRadius: 12, overflow: 'hidden', borderWidth: 1, borderColor: '#30363D' },
  row: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingHorizontal: 16, paddingVertical: 14, borderBottomWidth: 1, borderBottomColor: '#21262D' },
  label: { color: '#C9D1D9', fontSize: 14 },
  value: { color: '#8B949E', fontSize: 14 },
  sliderRow: { paddingHorizontal: 16, paddingVertical: 12, borderBottomWidth: 1, borderBottomColor: '#21262D' },
  sliderTop: { flexDirection: 'row', justifyContent: 'space-between', marginBottom: 4 },
  hint: { color: '#484F58', fontSize: 11 },
  legalText: { color: '#8B949E', fontSize: 12, lineHeight: 18, padding: 16 },
});

const stStyles = StyleSheet.create({
  strategySelector: { paddingHorizontal: 16, paddingVertical: 14 },
  selectedRow: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  selectedIcon: { width: 40, height: 40, borderRadius: 10, backgroundColor: '#58A6FF18', alignItems: 'center', justifyContent: 'center', borderWidth: 1, borderColor: '#58A6FF40' },
  selectedInfo: { flex: 1 },
  selectedName: { color: '#E6EDF3', fontSize: 14, fontWeight: '600' },
  selectedMeta: { color: '#8B949E', fontSize: 12, marginTop: 2 },
  placeholderTxt: { flex: 1, color: '#8B949E', fontSize: 14 },
  modal: { flex: 1, backgroundColor: '#0D1117' },
  modalHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', padding: 20, paddingTop: 24, borderBottomWidth: 1, borderBottomColor: '#21262D' },
  modalTitle: { color: '#E6EDF3', fontSize: 18, fontWeight: '700' },
  strategyCard: { marginHorizontal: 16, marginTop: 12, backgroundColor: '#161B22', borderRadius: 14, borderWidth: 1, borderColor: '#30363D', overflow: 'hidden' },
  strategyCardSelected: { borderColor: '#58A6FF60', backgroundColor: '#58A6FF08' },
  strategyCardHeader: { flexDirection: 'row', alignItems: 'flex-start', padding: 14, gap: 12 },
  strategyIcon: { width: 44, height: 44, borderRadius: 11, backgroundColor: '#21262D', alignItems: 'center', justifyContent: 'center', borderWidth: 1, borderColor: '#30363D' },
  strategyIconSelected: { backgroundColor: '#58A6FF18', borderColor: '#58A6FF40' },
  strategyCardInfo: { flex: 1 },
  strategyName: { color: '#C9D1D9', fontSize: 14, fontWeight: '600', lineHeight: 20 },
  strategyNameSelected: { color: '#58A6FF' },
  strategyCat: { color: '#8B949E', fontSize: 12, marginTop: 2, marginBottom: 6 },
  tagRow: { flexDirection: 'row', alignItems: 'center', gap: 8, flexWrap: 'wrap' },
  riskBadge: { paddingHorizontal: 8, paddingVertical: 2, borderRadius: 6, borderWidth: 1 },
  riskTxt: { fontSize: 11, fontWeight: '600' },
  stile: { color: '#484F58', fontSize: 11 },
  strategyDetail: { paddingHorizontal: 14, paddingBottom: 14, borderTopWidth: 1, borderTopColor: '#21262D', paddingTop: 12 },
  filosofia: { color: '#8B949E', fontSize: 13, lineHeight: 19, marginBottom: 12 },
  detailLabel: { color: '#58A6FF', fontSize: 11, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 0.6, marginTop: 10, marginBottom: 4 },
  detailValue: { color: '#8B949E', fontSize: 13 },
  bulletPoint: { color: '#8B949E', fontSize: 13, lineHeight: 20, paddingLeft: 4 },
  selectBtn: { margin: 12, marginTop: 8, paddingVertical: 10, borderRadius: 10, backgroundColor: '#21262D', alignItems: 'center', borderWidth: 1, borderColor: '#30363D' },
  selectBtnActive: { backgroundColor: '#58A6FF18', borderColor: '#58A6FF60' },
  selectBtnTxt: { color: '#8B949E', fontSize: 14, fontWeight: '600' },
  selectBtnTxtActive: { color: '#58A6FF' },
});
