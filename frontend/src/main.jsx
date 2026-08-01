import './shell-icons.css';
import './shell.css';

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
