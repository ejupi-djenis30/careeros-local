import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import { defineConfig, globalIgnores } from 'eslint/config'

const visibleCopyAttributes = new Set(['alt', 'aria-label', 'confirmText', 'label', 'message', 'placeholder', 'title'])
const visibleCopyAllowlist = new Set([
  'Arial',
  'ATS',
  'C',
  'Career Vault',
  'CareerOS',
  'CareerOS Local',
  'CH, EU',
  'CHF',
  'Georgia',
  'GitHub',
  'h',
  'Helvetica',
  'KB',
  'km',
  'km)',
  'LinkedIn',
  'LLM_DEBUG',
  'v',
  '· SHA-256',
])

function isUntranslatedCopy(value) {
  const normalized = value.replace(/\s+/g, ' ').trim()
  if (!/[A-Za-zÀ-ÿ]/.test(normalized) || visibleCopyAllowlist.has(normalized)) return false
  if (/^(?:https?:\/\/|[A-Z]{2,5}:?\s*\{)/.test(normalized)) return false
  if (/^\d+(?:[.,]\d+)?\s*(?:h|KB|km|pt)$/.test(normalized)) return false
  return true
}

const noHardcodedUiCopy = {
  meta: {
    type: 'problem',
    docs: { description: 'Require user-visible copy to use the translation catalogue' },
    schema: [],
    messages: { untranslated: 'Move user-visible copy “{{copy}}” to the translation catalogue.' },
  },
  create(context) {
    const report = (node, value) => {
      if (typeof value === 'string' && isUntranslatedCopy(value)) {
        context.report({ node, messageId: 'untranslated', data: { copy: value.replace(/\s+/g, ' ').trim() } })
      }
    }
    const reportDirectFallback = (node) => {
      if (node?.type === 'Literal') report(node, node.value)
      if (node?.type === 'TemplateLiteral' && node.expressions.length === 0) report(node, node.quasis[0].value.cooked)
      if (node?.type === 'LogicalExpression') reportDirectFallback(node.right)
    }
    return {
      JSXText(node) {
        report(node, node.value)
      },
      JSXAttribute(node) {
        if (!visibleCopyAttributes.has(node.name.name) || node.value?.type !== 'Literal') return
        report(node.value, node.value.value)
      },
      CallExpression(node) {
        if (node.callee?.type !== 'Identifier' || !['setError', 'showToast'].includes(node.callee.name)) return
        reportDirectFallback(node.arguments[0])
      },
    }
  },
}

export default defineConfig([
  globalIgnores(['dist', 'coverage', 'src-tauri/target', 'src-tauri/binaries']),
  {
    files: ['**/*.{js,jsx}'],
    extends: [
      js.configs.recommended,
      reactHooks.configs.flat.recommended,
      reactRefresh.configs.vite,
    ],
    languageOptions: {
      ecmaVersion: 2020,
      globals: globals.browser,
      parserOptions: {
        ecmaVersion: 'latest',
        ecmaFeatures: { jsx: true },
        sourceType: 'module',
      },
    },
    rules: {
      'no-unused-vars': ['error', { varsIgnorePattern: '^[A-Z_]' }],
    },
  },
  {
    files: ['src/**/*.{js,jsx}'],
    ignores: ['src/**/*.test.*', 'src/test/**', 'src/i18n/messages.js'],
    plugins: { local: { rules: { 'no-hardcoded-ui-copy': noHardcodedUiCopy } } },
    rules: { 'local/no-hardcoded-ui-copy': 'error' },
  },
])
