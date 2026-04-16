import React from 'react';

// 이 컴포넌트는 단순 페이지 이동 버튼만 제공한다.
interface PagerProps {
  page: number;
  totalPages: number;
  onChange: (page: number) => void;
}

export function Pager({ page, totalPages, onChange }: PagerProps) {
  if (!totalPages || totalPages <= 1) return null;

  return (
    <div className="pager">
      <button className="ghost-button" disabled={page <= 1} onClick={() => onChange(page - 1)}>
        이전
      </button>
      <span className="pager-value">
        {page} / {totalPages}
      </span>
      <button className="ghost-button" disabled={page >= totalPages} onClick={() => onChange(page + 1)}>
        다음
      </button>
    </div>
  );
}
