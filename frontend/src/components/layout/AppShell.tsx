import React from 'react';
import type { ViewKey } from '../../types/api';
import { clsx } from '../../app/formatters';

// 이 컴포넌트는 전체 앱 레이아웃과 좌측 메뉴를 담당한다.
interface AppShellProps {
  view: ViewKey;
  onChangeView: (view: ViewKey) => void;
  children: React.ReactNode;
}

const menuItems: Array<{ key: ViewKey; title: string; desc: string }> = [
  { key: 'dashboard', title: 'Dashboard', desc: '시장 요약과 추천' },
  { key: 'closing', title: '종가배팅', desc: 'Closing Bet V2' },
  { key: 'performance', title: '누적 성과', desc: 'Performance' },
  { key: 'data_status', title: 'Data Status', desc: '배치 상태와 로그' },
];

export function AppShell({ view, onChangeView, children }: AppShellProps) {
  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-badge">M</div>
          <div>
            <div className="brand-title">MarketFlow</div>
            <div className="brand-sub">Rebuild</div>
          </div>
        </div>
        <div className="menu-section-title">KR MARKET</div>
        <nav className="menu-list">
          {menuItems.map((item) => (
            <button
              key={item.key}
              className={clsx('menu-item', view === item.key && 'active')}
              onClick={() => onChangeView(item.key)}
            >
              <span className="menu-item-title">{item.title}</span>
              <span className="menu-item-desc">{item.desc}</span>
            </button>
          ))}
        </nav>
      </aside>
      <main className="content">{children}</main>
    </div>
  );
}
