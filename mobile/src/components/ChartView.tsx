import React, { useMemo } from 'react';
import { View, StyleSheet, ActivityIndicator } from 'react-native';
import { WebView } from 'react-native-webview';
import { Candle } from '../types';

interface Props {
  candles: Candle[];
  loading?: boolean;
  signal?: { target_price?: number; stop_loss?: number; entry_zone?: { low: number; high: number } };
}

export default function ChartView({ candles, loading, signal }: Props) {
  const html = useMemo(() => buildChartHTML(candles, signal), [candles, signal]);

  if (loading) {
    return (
      <View style={[styles.container, styles.center]}>
        <ActivityIndicator color="#58A6FF" size="large" />
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <WebView
        source={{ html }}
        style={styles.webview}
        scrollEnabled={false}
        javaScriptEnabled
        originWhitelist={['*']}
      />
    </View>
  );
}

function buildChartHTML(candles: Candle[], signal?: Props['signal']): string {
  const candleData = JSON.stringify(candles.map((c) => ({
    time: c.time,
    open: c.open,
    high: c.high,
    low: c.low,
    close: c.close,
  })));

  const lines: string[] = [];
  if (signal?.target_price) {
    lines.push(`{ price: ${signal.target_price}, color: '#00C896', lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title: 'Target' }`);
  }
  if (signal?.stop_loss) {
    lines.push(`{ price: ${signal.stop_loss}, color: '#FF4560', lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title: 'Stop' }`);
  }

  return `<!DOCTYPE html>
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<script src="https://unpkg.com/lightweight-charts/dist/lightweight-charts.standalone.production.js"></script>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { background: #0D1117; overflow: hidden; }
  #chart { width: 100vw; height: 100vh; }
</style>
</head>
<body>
<div id="chart"></div>
<script>
  const chart = LightweightCharts.createChart(document.getElementById('chart'), {
    width: window.innerWidth,
    height: window.innerHeight,
    layout: { background: { color: '#0D1117' }, textColor: '#8B949E' },
    grid: { vertLines: { color: '#21262D' }, horzLines: { color: '#21262D' } },
    crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
    rightPriceScale: { borderColor: '#30363D' },
    timeScale: { borderColor: '#30363D', timeVisible: true },
  });

  const series = chart.addCandlestickSeries({
    upColor: '#00C896', downColor: '#FF4560',
    borderUpColor: '#00C896', borderDownColor: '#FF4560',
    wickUpColor: '#00C896', wickDownColor: '#FF4560',
  });

  series.setData(${candleData});
  ${lines.map((l) => `series.createPriceLine(${l});`).join('\n  ')}

  chart.timeScale().fitContent();
  window.addEventListener('resize', () => chart.applyOptions({ width: window.innerWidth, height: window.innerHeight }));
</script>
</body>
</html>`;
}

const styles = StyleSheet.create({
  container: { height: 280, backgroundColor: '#0D1117', borderRadius: 12, overflow: 'hidden' },
  center: { justifyContent: 'center', alignItems: 'center' },
  webview: { backgroundColor: '#0D1117' },
});
