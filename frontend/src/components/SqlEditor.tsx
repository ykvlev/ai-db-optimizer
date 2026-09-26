import Editor, { DiffEditor, loader } from '@monaco-editor/react'
import * as monaco from 'monaco-editor'
import editorWorker from 'monaco-editor/editor/editor.worker?worker'

// Monaco загружается из бандла, а не с CDN — интерфейс работает без доступа к внешним сетям.
self.MonacoEnvironment = { getWorker: () => new editorWorker() }
loader.config({ monaco })

// Чёрная тема в швейцарском стиле: без подсветки фона строк, акцент — красный курсор
monaco.editor.defineTheme('swiss', {
  base: 'vs-dark', inherit: true,
  rules: [
    { token: 'keyword', foreground: 'ffffff', fontStyle: 'bold' },
    { token: 'string', foreground: 'b5b5b5' },
    { token: 'string.sql', foreground: 'b5b5b5' },
    { token: 'predefined', foreground: 'e6e6e6' },
    { token: 'predefined.sql', foreground: 'e6e6e6' },
    { token: 'identifier', foreground: 'e6e6e6' },
    { token: 'identifier.quote', foreground: 'e6e6e6' },
    { token: 'type', foreground: 'e6e6e6' },
    { token: 'delimiter', foreground: '8f8f8f' },
    { token: 'number', foreground: 'ff6b61' },
    { token: 'comment', foreground: '6b6b6b', fontStyle: 'italic' },
    { token: 'operator', foreground: 'd0d0d0' },
  ],
  colors: {
    'editor.background': '#000000', 'editor.foreground': '#e6e6e6', 'editorLineNumber.foreground': '#4a4a4a',
    'editorLineNumber.activeForeground': '#ff3b30', 'editorCursor.foreground': '#ff3b30',
    'editor.lineHighlightBackground': '#0d0d0d', 'editor.lineHighlightBorder': '#00000000',
    'editor.selectionBackground': '#3a1512', 'editorGutter.background': '#000000',
    'diffEditor.insertedTextBackground': '#1f5a3a66', 'diffEditor.removedTextBackground': '#6e1f1a66',
  },
})

const options: monaco.editor.IStandaloneEditorConstructionOptions = {
  minimap: { enabled: false },
  fontSize: 13,
  fontFamily: 'JetBrains Mono, Cascadia Code, Consolas, monospace',
  scrollBeyondLastLine: false,
  wordWrap: 'on',
  lineNumbersMinChars: 3,
  padding: { top: 8 },
  automaticLayout: true,
  tabSize: 2,
  bracketPairColorization: { enabled: false },
  renderLineHighlight: 'gutter',
}

export function SqlEditor({ value, onChange, height = 260, readOnly = false }: { value: string; onChange?: (v: string) => void; height?: number | string; readOnly?: boolean }) {
  return (
    <div className="overflow-hidden border border-line">
      <Editor height={height} language="sql" theme="swiss" value={value}
        onChange={v => onChange?.(v ?? '')} options={{ ...options, readOnly }} />
    </div>
  )
}

export function SqlDiff({ original, modified, height = 280 }: { original: string; modified: string; height?: number }) {
  return (
    <div className="overflow-hidden border border-line">
      <DiffEditor height={height} language="sql" theme="swiss" original={original} modified={modified}
        keepCurrentOriginalModel keepCurrentModifiedModel
        options={{ ...options, readOnly: true, renderSideBySide: true, originalEditable: false }} />
    </div>
  )
}
