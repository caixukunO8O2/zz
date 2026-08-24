import eslint from '@eslint/js'
import tseslint from 'typescript-eslint'

export default tseslint.config(
  eslint.configs.recommended,
  ...tseslint.configs.recommended,
  {
    ignores: ['coverage/**', 'miniprogram_npm/**'],
  },
  {
    files: ['**/*.ts'],
    languageOptions: {
      globals: {
        App: 'readonly',
        Page: 'readonly',
        Component: 'readonly',
        getApp: 'readonly',
        wx: 'readonly',
      },
    },
  },
)
