export interface Portfolio {
  total: number;
  available: number;
  margin: number;
  unrealisedPnl: number;
}

export interface Position {
  symbol: string;
  side: "LONG" | "SHORT";
  quantity: number;
  entryPrice: number;
  markPrice: number;
  pnl: number;
  pnlPct: number;
  margin: number;
  leverage: number;
  liquidationPrice: number;
}

export interface Transaction {
  symbol: string;
  side: "BUY" | "SELL";
  quantity: number;
  price: number;
  fee: number;
  tds: number;
  gst: number;
}
