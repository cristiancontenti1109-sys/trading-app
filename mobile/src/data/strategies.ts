export interface TradingStrategy {
  id: string;
  nome: string;
  categoria: string;
  icona: string;
  filosofia: string;
  punti_chiave: string[];
  asset_compatibili: string[];
  timeframe_consigliati: string[];
  profilo_rischio: string;
  stile: string;
  tag: string[];
}

export const STRATEGIES: TradingStrategy[] = [
  {
    id: 'jpmorgan_institutional',
    nome: 'JPMorgan – Approccio Istituzionale',
    categoria: 'Macro / Istituzionale',
    icona: 'business-outline',
    filosofia:
      'Strategia ispirata all\'approccio delle grandi banche d\'investimento come JPMorgan. Si basa sull\'analisi macroeconomica globale, sui flussi di capitale istituzionali, sulle politiche delle banche centrali e sul posizionamento dei grandi player.',
    punti_chiave: [
      'Analisi top-down: dal contesto macro al singolo asset',
      'Focus sui flussi di liquidità e sulle decisioni delle banche centrali',
      'Attenzione al posizionamento istituzionale (COT, dark pools, volumi)',
      'Diversificazione tra classi di attivo e gestione del rischio strutturata',
      'Orizzonte temporale medio-lungo, bassa frequenza operativa',
    ],
    asset_compatibili: ['Forex', 'Azioni', 'Indici', 'Materie prime', 'Crypto'],
    timeframe_consigliati: ['Daily', 'Weekly', 'Monthly'],
    profilo_rischio: 'Medio',
    stile: 'Trend following macro',
    tag: ['macro', 'istituzionale', 'long-term', 'fondamentale'],
  },
  {
    id: 'warren_buffett_value',
    nome: 'Warren Buffett – Value Investing',
    categoria: 'Investimento di valore',
    icona: 'diamond-outline',
    filosofia:
      'Strategia ispirata alla filosofia di Warren Buffett e della scuola di Benjamin Graham. Consiste nell\'acquistare asset di qualità a un prezzo inferiore al loro valore intrinseco, mantenendoli per molto tempo.',
    punti_chiave: [
      'Selezione di aziende solide, con vantaggio competitivo durevole (\'moat\')',
      'Acquisto solo quando il prezzo offre un margine di sicurezza sul valore intrinseco',
      'Orizzonte di investimento molto lungo (anni o decenni)',
      'Bassa rotazione di portafoglio, alta convinzione sulle posizioni',
      'Disinteresse per analisi tecnica e timing di breve periodo',
    ],
    asset_compatibili: ['Azioni', 'ETF', 'Indici', 'Crypto (solo blue-chip selezionate)'],
    timeframe_consigliati: ['Weekly', 'Monthly', 'Yearly'],
    profilo_rischio: 'Basso-Medio',
    stile: 'Buy & Hold / Value',
    tag: ['value', 'long-term', 'fondamentale', 'qualità'],
  },
  {
    id: 'fibonacci_retracements',
    nome: 'Fibonacci – Ritracciamenti ed Estensioni',
    categoria: 'Analisi tecnica',
    icona: 'analytics-outline',
    filosofia:
      'Strategia basata sulla sequenza di Fibonacci applicata ai mercati finanziari. Le correzioni e le estensioni di un trend tendono a rispettare proporzioni naturali ricorrenti (23,6% – 38,2% – 61,8% – 161,8%), interpretate come zone di possibile reazione del prezzo.',
    punti_chiave: [
      'Identificazione del trend dominante e dei suoi swing principali',
      'Uso dei livelli di ritracciamento per individuare aree di interesse',
      'Uso delle estensioni per stimare possibili obiettivi di prezzo',
      'Combinazione con altri strumenti (supporti/resistenze, candlestick, volumi)',
      'Strategia adattabile a qualsiasi mercato e timeframe',
    ],
    asset_compatibili: ['Forex', 'Azioni', 'Crypto', 'Indici', 'Materie prime'],
    timeframe_consigliati: ['M15', 'H1', 'H4', 'Daily'],
    profilo_rischio: 'Medio',
    stile: 'Swing / Pullback trading',
    tag: ['tecnico', 'ritracciamenti', 'armonico', 'multi-asset'],
  },
  {
    id: 'elliott_waves',
    nome: 'Onde di Elliott',
    categoria: 'Analisi tecnica avanzata',
    icona: 'pulse-outline',
    filosofia:
      'Teoria sviluppata da Ralph Nelson Elliott: i mercati si muovono per cicli ricorrenti guidati dalla psicologia collettiva. Ogni ciclo è composto da cinque onde impulsive e tre onde correttive. L\'obiettivo è riconoscere la fase del ciclo per anticiparne i probabili sviluppi.',
    punti_chiave: [
      'Struttura base: 5 onde impulsive + 3 onde correttive (pattern 5-3)',
      'Le onde sono frattali: si ripetono su qualsiasi timeframe',
      'Forte integrazione con i livelli di Fibonacci per misurare le onde',
      'Richiede interpretazione soggettiva ed esperienza',
      'Utile per identificare l\'inizio e la fine dei grandi trend',
    ],
    asset_compatibili: ['Forex', 'Azioni', 'Crypto', 'Indici', 'Materie prime'],
    timeframe_consigliati: ['H4', 'Daily', 'Weekly'],
    profilo_rischio: 'Medio-Alto',
    stile: 'Trend following / Contrarian sui finali di ciclo',
    tag: ['tecnico', 'cicli', 'psicologia di mercato', 'frattale'],
  },
  {
    id: 'smart_money_concepts',
    nome: 'Smart Money Concepts (SMC)',
    categoria: 'Price action istituzionale',
    icona: 'locate-outline',
    filosofia:
      'Strategia di price action che replica il comportamento del "denaro intelligente" (banche, hedge fund, market maker). Il mercato è mosso dalla liquidità: gli istituzionali accumulano e distribuiscono posizioni colpendo gli stop loss del retail.',
    punti_chiave: [
      'Identificazione di zone di liquidità (equal highs/lows, swing points)',
      'Riconoscimento di Break of Structure (BOS) e Change of Character (CHoCH)',
      'Operatività su Order Block, Fair Value Gap e zone di mitigazione',
      'Focus su manipolazione e induzione del prezzo prima dei grandi movimenti',
      'Approccio multi-timeframe: bias dai grafici alti, esecuzione sui bassi',
    ],
    asset_compatibili: ['Forex', 'Indici', 'Crypto', 'Azioni', 'Materie prime'],
    timeframe_consigliati: ['M5', 'M15', 'H1', 'H4'],
    profilo_rischio: 'Medio-Alto',
    stile: 'Intraday / Swing istituzionale',
    tag: ['price action', 'liquidità', 'istituzionale', 'order block'],
  },
];
