import { getItem } from './storage';

const WS_BASE = __DEV__ ? 'ws://localhost:8000' : 'wss://api.tradingsignals.app';

type MessageHandler = (message: any) => void;

class TradingWebSocket {
  private ws: WebSocket | null = null;
  private handlers: Map<string, Set<MessageHandler>> = new Map();
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private subscribedSymbols: Set<string> = new Set();

  async connect() {
    const token = await getItem('auth_token');
    if (!token) return;

    this.ws = new WebSocket(`${WS_BASE}/ws?token=${token}`);

    this.ws.onopen = () => {
      for (const symbol of this.subscribedSymbols) {
        this.send({ action: 'subscribe', symbol });
      }
    };

    this.ws.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data);
        const handlers = this.handlers.get(message.type) || new Set();
        handlers.forEach((h) => h(message));
        const allHandlers = this.handlers.get('*') || new Set();
        allHandlers.forEach((h) => h(message));
      } catch (e) {}
    };

    this.ws.onerror = () => {};
    this.ws.onclose = () => {
      this.reconnectTimer = setTimeout(() => this.connect(), 5000);
    };
  }

  disconnect() {
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
    this.ws?.close();
    this.ws = null;
  }

  subscribe(symbol: string) {
    this.subscribedSymbols.add(symbol);
    this.send({ action: 'subscribe', symbol });
  }

  unsubscribe(symbol: string) {
    this.subscribedSymbols.delete(symbol);
    this.send({ action: 'unsubscribe', symbol });
  }

  on(type: string, handler: MessageHandler) {
    if (!this.handlers.has(type)) this.handlers.set(type, new Set());
    this.handlers.get(type)!.add(handler);
    return () => this.handlers.get(type)?.delete(handler);
  }

  private send(data: object) {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(data));
    }
  }
}

export const wsClient = new TradingWebSocket();
