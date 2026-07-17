import 'bootstrap/dist/css/bootstrap.min.css';
import 'bootstrap/dist/js/bootstrap.bundle.min.js';
import 'bootstrap-icons/font/bootstrap-icons.css';
import './index.css';
import './career-os.css';

import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App.jsx'
import { DesktopBoot } from './components/DesktopBoot.jsx'
import { installExternalNavigation } from './platform/navigation.js'

installExternalNavigation();

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <DesktopBoot>
      <App />
    </DesktopBoot>
  </StrictMode>,
)
