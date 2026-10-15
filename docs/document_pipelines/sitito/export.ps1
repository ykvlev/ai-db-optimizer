$ErrorActionPreference='Stop'
$folder='C:\Users\Артём\Documents\Science\Научные материалы\01 Статьи\МГУ — СИТИТО 2026'
$stem=Join-Path $folder 'Яковлев — сравнение моделей SQL — СИТИТО'
$before=@(Get-Process WINWORD -ErrorAction SilentlyContinue | ForEach-Object Id)
$word=New-Object -ComObject Word.Application
$own=@(Get-Process WINWORD -ErrorAction SilentlyContinue | Where-Object {$before -notcontains $_.Id})
if(-not $own){[Runtime.InteropServices.Marshal]::ReleaseComObject($word)|Out-Null;throw 'Word подключился к пользовательскому процессу'}
$word.Visible=$false
$word.DisplayAlerts=0
try {
 $doc=$word.Documents.Open("$stem.docx",$false,$false)
 $doc.Fields.Update()|Out-Null
 $doc.Repaginate()
 $doc.Save()
 $doc.ExportAsFixedFormat("$stem.pdf",17)
 $doc.SaveAs2("$stem.doc",0)
 $doc.Close($false)
 $converted=$word.Documents.Open("$stem.doc",$false,$true)
 $converted.Repaginate()
 $converted.ExportAsFixedFormat('C:\Users\Артём\Documents\Science\ai-db-optimizer\tmp\sitito\from-doc.pdf',17)
 Write-Output "DOC pages=$($converted.ComputeStatistics(2))"
 $converted.Close($false)
}finally{$word.Quit();[Runtime.InteropServices.Marshal]::ReleaseComObject($word)|Out-Null}
