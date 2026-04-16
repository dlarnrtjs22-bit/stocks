import React from 'react';
import type { DashboardResponse } from '../types/api';
import { DashboardView } from '../components/dashboard/DashboardView';

interface DashboardPageProps {
  loading: boolean;
  data?: DashboardResponse | null;
  onRefresh: () => void;
  onRefreshAccount: () => void;
  dashboardRefreshing: boolean;
  accountRefreshing: boolean;
}

export function DashboardPage({ loading, data, onRefresh, onRefreshAccount, dashboardRefreshing, accountRefreshing }: DashboardPageProps) {
  return (
    <DashboardView
      loading={loading}
      data={data}
      onRefresh={onRefresh}
      onRefreshAccount={onRefreshAccount}
      dashboardRefreshing={dashboardRefreshing}
      accountRefreshing={accountRefreshing}
    />
  );
}
