import React from 'react';
import { TradeHistoryView } from '../components/trade-history/TradeHistoryView';
import type { TradeHistoryResponse } from '../types/api';

interface TradeHistoryPageProps {
  loading: boolean;
  data?: TradeHistoryResponse | null;
}

export function TradeHistoryPage({ loading, data }: TradeHistoryPageProps) {
  return <TradeHistoryView loading={loading} data={data} />;
}
