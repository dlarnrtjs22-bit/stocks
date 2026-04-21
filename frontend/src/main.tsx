import React from 'react';
import ReactDOM from 'react-dom/client';

import { App } from './app/App';
// Design Ref: Design §2 — 스타일 import 순서는 tokens → tailwind → legacy app.css
import './styles/tokens.css';
import './styles/tailwind.css';
import './styles/app.css';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
