import 'bootstrap/dist/css/bootstrap.min.css';
import 'bootstrap/dist/js/bootstrap.bundle.min.js';
import 'bootstrap-icons/font/bootstrap-icons.css';
import './index.css';
import './career-os.css';

import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App.jsx'
import { DesktopBoot } from './components/DesktopBoot.jsx'
import { I18nProvider } from './i18n/I18nContext.jsx'
import { installExternalNavigation } from './platform/navigation.js'

installExternalNavigation();

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <I18nProvider>
      <DesktopBoot>
        <App />
      </DesktopBoot>
    </I18nProvider>
  </StrictMode>,
)
