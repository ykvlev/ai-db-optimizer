import Editor, { DiffEditor, loader } from '@monaco-editor/react'
import * as monaco from 'monaco-editor'
import editorWorker from 'monaco-editor/editor/editor.worker?worker'

// Monaco загружается из бандла, а не с CDN — интерфейс работает без доступа к внешним сетям.
self.MonacoEnvironment = { getWorker: () => new editorWorker() }
loader.config({ monaco })

// Светлая тема «бумага»: монохромная подсветка, строки — Terminal Green, как в дизайн-системе
monaco.editor.defineTheme('paper', {
  base: 'vs', inherit: true,
  rules: [
    { token: '', foreground: '171717' },
    { token: 'keyword', foreground: '171717', fontStyle: 'bold' },
    { token: 'string', foreground: '297a3a' },
    { token: 'string.sql', foreground: '297a3a' },
    { token: 'number', foreground: '4d4d4d' },
    { token: 'comment', foreground: 'a8a8a8', fontStyle: 'italic' },
    { token: 'operator', foreground: '666666' },
    { token: 'delimiter', foreground: '8f8f8f' },
    { token: 'predefined', foreground: '171717' },
    { token: 'predefined.sql', foreground: '171717' },
    { token: 'identifier', foreground: '171717' },
    { token: 'identifier.quote', foreground: '171717' },
    { token: 'type', foreground: '171717' },
  ],
  colors: {
    'editor.background': '#ffffff', 'editor.foreground': '#171717', 'editorLineNumber.foreground': '#c9c9c9',
    'editorLineNumber.activeForeground': '#171717', 'editorCursor.foreground': '#171717',
    'editor.lineHighlightBackground': '#fafafa', 'editor.lineHighlightBorder': '#00000000',
    'editor.selectionBackground': '#ebebeb', 'editorGutter.background': '#ffffff',
    'editorOverviewRuler.border': '#00000000', 'scrollbarSlider.background': '#c9c9c966',
    'diffEditor.insertedTextBackground': '#297a3a22', 'diffEditor.removedTextBackground': '#17171714',
  },
})

const options: monaco.editor.IStandaloneEditorConstructionOptions = {
  minimap: { enabled: false },
  fontSize: 13,
  fontFamily: '"Geist Mono Variable", Consolas, monospace',
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
    <div className="card overflow-hidden">
      <Editor height={height} language="sql" theme="paper" value={value}
        onChange={v => onChange?.(v ?? '')} options={{ ...options, readOnly }} />
    </div>
  )
}

export function SqlDiff({ original, modified, height = 280 }: { original: string; modified: string; height?: number }) {
  return (
    <div className="card overflow-hidden">
      <DiffEditor height={height} language="sql" theme="paper" original={original} modified={modified}
        keepCurrentOriginalModel keepCurrentModifiedModel
        options={{ ...options, readOnly: true, renderSideBySide: true, originalEditable: false }} />
    </div>
  )
}
