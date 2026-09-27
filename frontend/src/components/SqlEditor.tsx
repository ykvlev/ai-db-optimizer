import Editor, { DiffEditor, loader } from '@monaco-editor/react'
import * as monaco from 'monaco-editor'
import editorWorker from 'monaco-editor/editor/editor.worker?worker'
import { useEffect, useRef } from 'react'
import type { TableInfo } from '../api'

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

// Автодополнение по схеме подключённой базы: таблицы, столбцы, а после «алиас.» — столбцы этой таблицы.
// Провайдер один на все редакторы; схему задаёт тот, кто последним вызвал setCompletionSchema.
let completionTables: TableInfo[] = []
export function setCompletionSchema(tables: TableInfo[]) { completionTables = tables }

// ключевые слова SQL Monaco подсказывает сам; провайдер регистрируется один раз (и при горячей перезагрузке модуля)
const w = window as unknown as { __aidboCompletion?: monaco.IDisposable }
w.__aidboCompletion?.dispose()
w.__aidboCompletion = monaco.languages.registerCompletionItemProvider('sql', {
  triggerCharacters: ['.'],
  provideCompletionItems(model, position) {
    const word = model.getWordUntilPosition(position)
    const range = { startLineNumber: position.lineNumber, endLineNumber: position.lineNumber, startColumn: word.startColumn, endColumn: word.endColumn }
    const K = monaco.languages.CompletionItemKind
    const before = model.getLineContent(position.lineNumber).slice(0, word.startColumn - 1)
    const dot = before.match(/([\w.]+)\.$/)
    const byName = (n: string) => completionTables.find(t => t.name.toLowerCase() === n.toLowerCase() || t.name.split('.').pop()!.toLowerCase() === n.toLowerCase())
    if (dot) {
      // алиас → таблица: «FROM orders o», «JOIN users AS u»
      const text = model.getValue()
      const alias = dot[1]
      let table = byName(alias)
      for (const m of text.matchAll(/\b(?:from|join)\s+([\w.]+)(?:\s+(?:as\s+)?(\w+))?/gi)) {
        if (m[2] && m[2].toLowerCase() === alias.toLowerCase()) table = byName(m[1])
      }
      return { suggestions: (table?.columns ?? []).map(c => ({ label: c.name, kind: K.Field, detail: c.type, insertText: c.name, range })) }
    }
    return {
      suggestions: [
        ...completionTables.map(t => ({ label: t.name, kind: K.Struct, detail: `таблица · ${t.row_count ?? '?'} строк`, insertText: t.name, range })),
        ...completionTables.flatMap(t => t.columns.map(c => ({ label: c.name, kind: K.Field, detail: `${t.name} · ${c.type}`, insertText: c.name, range, sortText: 'z' + c.name }))),
      ],
    }
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

export function SqlEditor({ value, onChange, height = 260, readOnly = false, onRun }: {
  value: string; onChange?: (v: string) => void; height?: number | string; readOnly?: boolean
  onRun?: () => void  // Ctrl+Enter
}) {
  const runRef = useRef(onRun)
  useEffect(() => { runRef.current = onRun }, [onRun])
  return (
    <div className="card overflow-hidden">
      <Editor height={height} language="sql" theme="paper" value={value}
        onChange={v => onChange?.(v ?? '')} options={{ ...options, readOnly }}
        onMount={ed => {
          // addAction привязан к этому редактору (addCommand срабатывал бы в последнем созданном редакторе на странице)
          if (onRun) ed.addAction({ id: 'run-query', label: 'Выполнить запрос', keybindings: [monaco.KeyMod.CtrlCmd | monaco.KeyCode.Enter], run: () => runRef.current?.() })
        }} />
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
