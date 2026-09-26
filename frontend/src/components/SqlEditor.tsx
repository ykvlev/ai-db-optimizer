import Editor, { DiffEditor, loader } from '@monaco-editor/react'
import * as monaco from 'monaco-editor'
import editorWorker from 'monaco-editor/editor/editor.worker?worker'

// Monaco загружается из бандла, а не с CDN — интерфейс работает без доступа к внешним сетям.
self.MonacoEnvironment = { getWorker: () => new editorWorker() }
loader.config({ monaco })

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
}

export function SqlEditor({ value, onChange, height = 260, readOnly = false }: { value: string; onChange?: (v: string) => void; height?: number | string; readOnly?: boolean }) {
  return (
    <div className="overflow-hidden rounded-md border border-line">
      <Editor height={height} language="sql" theme="vs-dark" value={value}
        onChange={v => onChange?.(v ?? '')} options={{ ...options, readOnly }} />
    </div>
  )
}

export function SqlDiff({ original, modified, height = 280 }: { original: string; modified: string; height?: number }) {
  return (
    <div className="overflow-hidden rounded-md border border-line">
      <DiffEditor height={height} language="sql" theme="vs-dark" original={original} modified={modified}
        keepCurrentOriginalModel keepCurrentModifiedModel
        options={{ ...options, readOnly: true, renderSideBySide: true, originalEditable: false }} />
    </div>
  )
}
