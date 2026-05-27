import React, { useEffect } from 'react';
import { StatusBar } from 'expo-status-bar';
import { NavigationContainer, DarkTheme } from '@react-navigation/native';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { createStackNavigator } from '@react-navigation/stack';
import { Provider, useDispatch, useSelector } from 'react-redux';
import { Ionicons } from '@expo/vector-icons';
import Toast from 'react-native-toast-message';

import { store, RootState, AppDispatch } from './src/store';
import { fetchMe } from './src/store/authSlice';
import { wsClient } from './src/services/websocket';
import { registerForPushNotifications } from './src/services/notifications';

import AuthScreen from './src/screens/AuthScreen';
import WatchlistScreen from './src/screens/WatchlistScreen';
import InstrumentScreen from './src/screens/InstrumentScreen';
import SearchScreen from './src/screens/SearchScreen';
import SettingsScreen from './src/screens/SettingsScreen';

const Tab = createBottomTabNavigator();
const Stack = createStackNavigator();

function WatchlistStack() {
  return (
    <Stack.Navigator screenOptions={{ headerShown: false }}>
      <Stack.Screen name="Watchlist" component={WatchlistScreen} />
      <Stack.Screen name="Instrument" component={InstrumentScreen} />
      <Stack.Screen name="Search" component={SearchScreen} />
    </Stack.Navigator>
  );
}

function AppTabs() {
  return (
    <Tab.Navigator
      screenOptions={({ route }) => ({
        headerShown: false,
        tabBarStyle: { backgroundColor: '#161B22', borderTopColor: '#21262D', borderTopWidth: 1 },
        tabBarActiveTintColor: '#58A6FF',
        tabBarInactiveTintColor: '#484F58',
        tabBarIcon: ({ color, size }) => {
          const icons: Record<string, keyof typeof Ionicons.glyphMap> = {
            'WatchlistTab': 'list',
            'SettingsTab': 'settings-outline',
          };
          return <Ionicons name={icons[route.name] ?? 'apps'} size={size} color={color} />;
        },
      })}
    >
      <Tab.Screen name="WatchlistTab" component={WatchlistStack} options={{ tabBarLabel: 'Watchlist' }} />
      <Tab.Screen name="SettingsTab" component={SettingsScreen} options={{ tabBarLabel: 'Settings' }} />
    </Tab.Navigator>
  );
}

function Root() {
  const dispatch = useDispatch<AppDispatch>();
  const user = useSelector((s: RootState) => s.auth.user);

  useEffect(() => {
    dispatch(fetchMe()).then((result) => {
      if (result.meta.requestStatus === 'fulfilled') {
        wsClient.connect();
        registerForPushNotifications();
      }
    });
  }, [dispatch]);

  const navTheme = {
    ...DarkTheme,
    colors: { ...DarkTheme.colors, background: '#0D1117', card: '#161B22', border: '#21262D' },
  };

  return (
    <NavigationContainer theme={navTheme}>
      <StatusBar style="light" />
      {user ? <AppTabs /> : <AuthScreen />}
      <Toast />
    </NavigationContainer>
  );
}

export default function App() {
  return (
    <Provider store={store}>
      <Root />
    </Provider>
  );
}
