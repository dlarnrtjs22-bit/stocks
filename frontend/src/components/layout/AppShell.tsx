import React from 'react';
import clsx from 'clsx';
import {
  LayoutDashboard,
  Receipt,
  Target,
  LineChart,
  Database,
  Shield,
  type LucideIcon,
} from 'lucide-react';
import type { ViewKey } from '../../types/api';

// Design Ref: Design §4.1 — 사이드바 + 메인 셸.

interface AppShellProps {
  view: ViewKey;
  onChangeView: (view: ViewKey) => void;
  children: React.ReactNode;
}

interface MenuItem {
  key: ViewKey;
  title: string;
  desc: string;
  icon: LucideIcon;
}

function todayIso(): string {
  const d = new Date();
  const yyyy = d.getFullYear();
  const mm = String(d.getMonth() + 1).padStart(2, '0');
  const dd = String(d.getDate()).padStart(2, '0');
  return `${yyyy}-${mm}-${dd}`;
}

const menuItems: MenuItem[] = [
  { key: 'dashboard', title: 'Dashboard', desc: '시장 요약', icon: LayoutDashboard },
  { key: 'control', title: '자동매매 제어', desc: 'Auto Trade Control', icon: Shield },
  { key: 'trade_history', title: '매매내역', desc: '계좌와 체결', icon: Receipt },
  { key: 'closing', title: '종가배팅', desc: 'Closing Bet', icon: Target },
  { key: 'performance', title: '누적 성과', desc: 'Performance', icon: LineChart },
  { key: 'data_status', title: 'Data Status', desc: '배치와 로그', icon: Database },
];

export function AppShell({ view, onChangeView, children }: AppShellProps) {
  return (
    <div className="grid grid-cols-[220px_1fr] min-h-screen bg-base">
      <aside className="border-r border-border-subtle bg-surface flex flex-col">
        <div className="flex items-center gap-2.5 px-3 h-14 border-b border-border-subtle shrink-0">
          <div className="w-8 h-8 rounded-md bg-gradient-to-br from-brand to-brand-hover grid place-items-center text-white font-bold text-sm">
            M
          </div>
          <div className="min-w-0">
            <div className="text-md font-semibold text-text-primary leading-none">MarketFlow</div>
            <div className="text-xs text-text-muted mt-1">v0.2</div>
          </div>
        </div>

        <div className="px-3 py-3 text-[10px] tracking-[0.14em] text-text-muted uppercase">
          KR MARKET
        </div>

        <nav className="flex flex-col gap-0.5 px-2 flex-1">
          {menuItems.map((item) => {
            const active = view === item.key;
            const Icon = item.icon;
            return (
              <button
                key={item.key}
                onClick={() => onChangeView(item.key)}
                className={clsx(
                  'group relative flex items-center gap-2.5 px-2.5 py-2 rounded-md text-left transition-colors',
                  active
                    ? 'bg-elevated text-text-primary'
                    : 'text-text-secondary hover:bg-row-hover hover:text-text-primary',
                )}
              >
                {active ? (
                  <span className="absolute left-0 top-1.5 bottom-1.5 w-0.5 rounded-r-sm bg-brand" />
                ) : null}
                <Icon
                  size={16}
                  className={clsx(
                    'shrink-0',
                    active ? 'text-brand' : 'text-text-muted group-hover:text-text-secondary',
                  )}
                />
                <div className="min-w-0 flex-1">
                  <div className="text-sm font-medium leading-tight">{item.title}</div>
                  <div className="text-[11px] text-text-muted leading-tight mt-0.5">
                    {item.desc}
                  </div>
                </div>
              </button>
            );
          })}
        </nav>

        <div className="px-3 py-3 border-t border-border-subtle shrink-0">
          <div className="text-[10px] tracking-[0.14em] text-text-muted uppercase mb-1">
            Session
          </div>
          <div className="num text-xs text-text-secondary">{todayIso()}</div>
        </div>
      </aside>

      <main className="min-w-0 p-4 overflow-x-hidden">{children}</main>
    </div>
  );
}
