import React from 'react';
import type { DashboardResponse } from '../types/api';
import { DashboardView } from '../components/dashboard/DashboardView';

interface DashboardPageProps {
  loading: boolean;
  data?: DashboardResponse | null;
  onRefresh: () => void;
  dashboardRefreshing: boolean;
}

export function DashboardPage({
  loading,
  data,
  onRefresh,
  dashboardRefreshing,
}: DashboardPageProps) {
  return (
    <DashboardView
      loading={loading}
      data={data}
      onRefresh={onRefresh}
      dashboardRefreshing={dashboardRefreshing}
    />
  );
}
