# Обновляет поля (оглавление) через Microsoft Word, сохраняет .docx, экспортирует PDF и пишет число страниц в stats.json
param([string]$Docx = "$PSScriptRoot\Отчет_о_НИР.docx")
$ErrorActionPreference = 'Stop'
$word = New-Object -ComObject Word.Application
$word.Visible = $false
$word.DisplayAlerts = 0
try {
    $doc = $word.Documents.Open($Docx, $false, $false)
    foreach ($toc in $doc.TablesOfContents) { $toc.Update() }
    $doc.Fields.Update() | Out-Null
    $doc.Repaginate()
    $pages = $doc.ComputeStatistics(2)
    $doc.Save()
    $pdf = [System.IO.Path]::ChangeExtension($Docx, '.pdf')
    $doc.ExportAsFixedFormat($pdf, 17)
    $doc.Close($false)
    "{`"pages`": $pages}" | Out-File -Encoding ascii "$PSScriptRoot\word_pages.json"
    "pages=$pages"
} finally {
    $word.Quit()
    [System.Runtime.InteropServices.Marshal]::ReleaseComObject($word) | Out-Null
}
