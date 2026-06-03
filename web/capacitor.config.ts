import type { CapacitorConfig } from '@capacitor/cli';

const config: CapacitorConfig = {
  appId: 'com.tradingapp.mobile',
  appName: 'Trading App',
  webDir: 'dist',
  android: {
    allowMixedContent: true,
  },
  server: {
    // Updated to Tailscale URL after setup
    androidScheme: 'https',
  },
};

export default config;
