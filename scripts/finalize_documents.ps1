$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot
$before = @(Get-Process WINWORD -ErrorAction SilentlyContinue | ForEach-Object Id)
$word = New-Object -ComObject Word.Application
$owned = @(Get-Process WINWORD -ErrorAction SilentlyContinue | Where-Object { $before -notcontains $_.Id })
if (-not $owned) {
    [System.Runtime.InteropServices.Marshal]::ReleaseComObject($word) | Out-Null
    throw 'No isolated Word process; user documents will not be touched.'
}
$word.Visible = $false
$word.DisplayAlerts = 0
$manifest = @()
try {
    $files = @(Get-ChildItem (Join-Path $projectRoot 'docs/articles') -Filter '*.docx')
    $files += Get-Item (Join-Path $projectRoot 'docs/nir/Отчет_о_НИР.docx')
    $files += Get-Item (Join-Path $projectRoot 'docs/techreport/Технический_отчет.docx')
    $files += Get-Item (Join-Path $projectRoot 'docs/human_study/Задания_для_участников.docx')
    foreach ($file in $files) {
        $doc = $word.Documents.Open($file.FullName, $false, $false)
        try {
            foreach ($toc in $doc.TablesOfContents) { $toc.Update() }
            $doc.Fields.Update() | Out-Null
            $doc.Repaginate()
            $pages = $doc.ComputeStatistics(2)
            $doc.Save()
            $pdf = [System.IO.Path]::ChangeExtension($file.FullName, '.pdf')
            $doc.ExportAsFixedFormat($pdf, 17)
            $manifest += [pscustomobject]@{docx=$file.FullName; pdf=$pdf; pages=$pages}
            Write-Output "$($file.Name): $pages pages"
        } finally { $doc.Close($false) }
    }
    $manifest | ConvertTo-Json | Set-Content (Join-Path $projectRoot 'docs/document_manifest.json') -Encoding utf8
} finally {
    $word.Quit()
    [System.Runtime.InteropServices.Marshal]::ReleaseComObject($word) | Out-Null
}
