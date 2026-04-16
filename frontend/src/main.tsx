import React from 'react';
import ReactDOM from 'react-dom/client';

import { App } from './app/App';
import './styles/app.css';

// 이 파일은 React 앱의 실제 시작점이다.
ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
