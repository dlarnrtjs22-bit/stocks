import React from 'react';

// 이 컴포넌트는 미리보기와 로그 창에 공통으로 쓰는 간단한 모달이다.
interface ModalProps {
  open: boolean;
  title: string;
  onClose: () => void;
  children: React.ReactNode;
}

export function Modal({ open, title, onClose, children }: ModalProps) {
  if (!open) return null;

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal-panel" onClick={(event) => event.stopPropagation()}>
        <div className="modal-head">
          <h3>{title}</h3>
          <button className="ghost-button" onClick={onClose}>
            닫기
          </button>
        </div>
        <div className="modal-body">{children}</div>
      </div>
    </div>
  );
}
