[CmdletBinding()]
param(
    [string]$VideoPath = "01_video\Alurohr_THWS.mp4",
    [string]$BenchmarkRoot = "05_crf_benchmark",
    [string]$EnvironmentName = "colmap_env",
    [int[]]$FpsValues = @(5, 10),
    [int[]]$CrfValues = @(18, 23, 28, 35),
    [int]$TargetHeight = 720,
    [ValidateSet("SIMPLE_RADIAL", "OPENCV", "PINHOLE", "OPENCV_FISHEYE", "SIMPLE_RADIAL_FISHEYE")]
    [string]$CameraModel = "OPENCV",
    [string]$ProgressFile = "",
    [int]$FeatureThreads = 4,
    [int]$MatchingThreads = 4,
    [int]$RandomSeed = 42,
    [int]$MaxFeatures = 2048,
    [int]$SequentialOverlap = 15,
    [switch]$Force,
    [switch]$RetryFailed,
    [switch]$PlanOnly
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

function Read-ProgressState {
    param([string]$Path)
    if ([string]::IsNullOrWhiteSpace($Path) -or !(Test-Path -LiteralPath $Path -PathType Leaf)) { return $null }
    try { return ((Get-Content -LiteralPath $Path -Raw) | ConvertFrom-Json) }
    catch { return $null }
}

function Resolve-ProjectPath {
    param([string]$Path)
    if ([System.IO.Path]::IsPathRooted($Path)) { return $Path }
    return Join-Path $ProjectRoot $Path
}

function Assert-File {
    param([string]$Path)
    if (!(Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "Datei nicht gefunden: $Path"
    }
}

function Format-Number {
    param([object]$Value, [string]$Format = "0.00")
    if ($null -eq $Value -or "$Value" -eq "") { return "-" }
    return ([double]$Value).ToString($Format, [Globalization.CultureInfo]::InvariantCulture)
}

function Read-Json {
    param([string]$Path)
    if (!(Test-Path -LiteralPath $Path -PathType Leaf)) { return $null }
    try { return ((Get-Content -LiteralPath $Path -Raw) | ConvertFrom-Json) }
    catch { return $null }
}

function Get-QualityScores {
    param([object[]]$Results)
    $Successful = @($Results | Where-Object { $_.Status -eq "OK" })
    if ($Successful.Count -eq 0) { return @() }
    $MaxPointDensity = [double](@($Successful | ForEach-Object { [double]$_.PointsPerRegisteredImage } | Measure-Object -Maximum).Maximum)
    $MaxObservations = [double](@($Successful | ForEach-Object { [double]$_.MeanObservationsPerImage } | Measure-Object -Maximum).Maximum)
    $MaxTrackLength = [double](@($Successful | ForEach-Object { [double]$_.MeanTrackLength } | Measure-Object -Maximum).Maximum)
    $MinReprojection = [double](@($Successful | ForEach-Object { [double]$_.MeanReprojectionErrorNormalized } | Measure-Object -Minimum).Minimum)

    foreach ($Result in $Successful) {
        $RegistrationScore = [math]::Min(1, [double]$Result.RegistrationRatio)
        $PointScore = if ($MaxPointDensity -gt 0) { [math]::Min(1, [double]$Result.PointsPerRegisteredImage / $MaxPointDensity) } else { 0 }
        $ObservationScore = if ($MaxObservations -gt 0) { [math]::Min(1, [double]$Result.MeanObservationsPerImage / $MaxObservations) } else { 0 }
        $TrackScore = if ($MaxTrackLength -gt 0) { [math]::Min(1, [double]$Result.MeanTrackLength / $MaxTrackLength) } else { 0 }
        $ErrorScore = if ([double]$Result.MeanReprojectionErrorNormalized -gt 0) {
            [math]::Min(1, $MinReprojection / [double]$Result.MeanReprojectionErrorNormalized)
        } else { 0 }
        $Score = 100 * (0.40 * $RegistrationScore + 0.25 * $PointScore + 0.15 * $ObservationScore + 0.10 * $TrackScore + 0.10 * $ErrorScore)
        $Result | Add-Member -MemberType NoteProperty -Name QualityProxy -Value ([math]::Round($Score, 2)) -Force
    }
    return $Successful
}

function Write-CrfReport {
    param([string]$ReportPath, [string]$Video, [int]$TargetWidth, [int]$TargetHeight, [object[]]$Results)
    $Scored = @(Get-QualityScores $Results | Sort-Object Fps, Crf)
    $Lines = New-Object System.Collections.Generic.List[string]
    [void]$Lines.Add("COLMAP CRF-Benchmark")
    [void]$Lines.Add("====================")
    [void]$Lines.Add("Originalvideo: $Video")
    [void]$Lines.Add("Vergleichsaufloesung: ${TargetWidth}x${TargetHeight}")
    [void]$Lines.Add("CRF: H.264/x264, preset medium; source = Originalvideo ohne zusaetzliche CRF-Kodierung")
    [void]$Lines.Add("")
    [void]$Lines.Add("Ergebnisse")
    [void]$Lines.Add("----------")
    [void]$Lines.Add("Fall             FPS CRF Video[MB] Encode[s] Recon[s] Gesamt[s] Reg.-%   Punkte Pkt/Reg Tracks Obs/Bild Reproj Qualitaet Status")
    [void]$Lines.Add("---------------- --- --- --------- --------- -------- --------- ------- -------- -------- ------ -------- ------ -------- ------")
    foreach ($Result in $Scored) {
        $CrfText = if ([int]$Result.Crf -lt 0) { "src" } else { "$($Result.Crf)" }
        $Quality = if ($Result.Status -eq "OK") { Format-Number $Result.QualityProxy "0.00" } else { "-" }
        [void]$Lines.Add(("{0,-16} {1,3} {2,3} {3,9} {4,9} {5,8} {6,9} {7,7} {8,8} {9,8} {10,6} {11,8} {12,6} {13,8} {14,-6}" -f `
            $Result.CaseName, $Result.Fps, $CrfText,
            (Format-Number ([double]$Result.VideoBytes / 1MB) "0.00"),
            (Format-Number $Result.EncodingSeconds "0.0"),
            (Format-Number $Result.ReconstructionSeconds "0.0"),
            (Format-Number $Result.TotalSeconds "0.0"),
            (Format-Number ([double]$Result.RegistrationRatio * 100) "0.0"),
            $Result.Points3D,
            (Format-Number $Result.PointsPerRegisteredImage "0"),
            (Format-Number $Result.MeanTrackLength "0.00"),
            (Format-Number $Result.MeanObservationsPerImage "0.0"),
            (Format-Number $Result.MeanReprojectionErrorPx "0.000"),
            $Quality,
            $Result.Status))
    }

    $Successful = @($Scored | Where-Object { $_.Status -eq "OK" })
    [void]$Lines.Add("")
    [void]$Lines.Add("CRF-Vergleich pro FPS")
    [void]$Lines.Add("---------------------")
    foreach ($Fps in @($Successful | Select-Object -ExpandProperty Fps -Unique | Sort-Object)) {
        $Source = @($Successful | Where-Object { $_.Fps -eq $Fps -and $_.Crf -lt 0 })[0]
        if ($null -eq $Source) { continue }
        [void]$Lines.Add(("{0} FPS, Referenz {1}s, {2} Punkte:" -f $Fps, (Format-Number $Source.ReconstructionSeconds "0.0"), $Source.Points3D))
        foreach ($Result in @($Successful | Where-Object { $_.Fps -eq $Fps -and $_.Crf -ge 0 } | Sort-Object Crf)) {
            $PointDelta = if ([double]$Source.Points3D -gt 0) { 100 * ([double]$Result.Points3D / $Source.Points3D - 1) } else { 0 }
            $TimeDelta = if ([double]$Source.TotalSeconds -gt 0) { 100 * ([double]$Result.TotalSeconds / $Source.TotalSeconds - 1) } else { 0 }
            [void]$Lines.Add(("  CRF {0}: Punkte {1} ({2}%), Gesamtzeit {3}s ({4}%)" -f $Result.Crf, $Result.Points3D, (Format-Number $PointDelta "0.0"), (Format-Number $Result.TotalSeconds "0.0"), (Format-Number $TimeDelta "0.0")))
        }
    }

    [void]$Lines.Add("")
    [void]$Lines.Add("Metriken und wissenschaftliche Einordnung")
    [void]$Lines.Add("----------------------------------------")
    [void]$Lines.Add("Reg.-%, Punkte, Tracks, Obs/Bild und Reprojektionsfehler bewerten die Sparse-Rekonstruktion.")
    [void]$Lines.Add("Reprojektionsfehler wird fuer den Score durch die Bilddiagonale normiert.")
    [void]$Lines.Add("CRF ist ein Video-Kompressionsparameter, kein direktes Mass fuer 3D-Genauigkeit.")
    [void]$Lines.Add("Ohne Ground-Truth-Scan sind Chamfer/Hausdorff, Precision/Recall und F-score nicht bestimmbar.")
    [void]$Lines.Add("Der Qualitaets-Score ist ein relativer Proxy innerhalb dieses CRF-Reports.")
    [void]$Lines.Add("Metrikbasis: https://colmap.github.io/faq.html")
    $Lines | Set-Content -LiteralPath $ReportPath -Encoding UTF8
}

$VideoPath = Resolve-ProjectPath $VideoPath
$BenchmarkRoot = Resolve-ProjectPath $BenchmarkRoot
$BenchmarkScript = Join-Path $ProjectRoot "benchmark_colmap.ps1"
Assert-File $VideoPath
Assert-File $BenchmarkScript
$PowerShellCommand = Get-Command powershell.exe -ErrorAction SilentlyContinue
if ($null -eq $PowerShellCommand) { throw "powershell.exe wurde nicht gefunden." }
$MambaCommand = Get-Command mamba -ErrorAction SilentlyContinue
if ($null -eq $MambaCommand) { throw "mamba wurde nicht gefunden." }
$CondaBase = Split-Path (Split-Path $MambaCommand.Source -Parent) -Parent
$EnvironmentPath = Join-Path $CondaBase (Join-Path "envs" $EnvironmentName)
$FfmpegPath = Join-Path $EnvironmentPath "Library\bin\ffmpeg.exe"
$FfprobePath = Join-Path $EnvironmentPath "Library\bin\ffprobe.exe"
Assert-File $FfmpegPath
Assert-File $FfprobePath
$env:PATH = "$EnvironmentPath;$EnvironmentPath\Library\bin;$EnvironmentPath\Scripts;$env:PATH"

$SizeText = (& $FfprobePath -v error -select_streams v:0 -show_entries stream=width,height -of csv=p=0:s=x $VideoPath 2>&1 | Out-String).Trim()
if ($SizeText -notmatch "^(\d+)x(\d+)x?$") { throw "Videoaufloesung konnte nicht gelesen werden: $SizeText" }
$SourceWidth = [int]$Matches[1]
$SourceHeight = [int]$Matches[2]
$TargetWidth = [int]([math]::Round($TargetHeight * $SourceWidth / $SourceHeight))
if (($TargetWidth % 2) -ne 0) { $TargetWidth++ }

foreach ($Crf in $CrfValues) {
    if ($Crf -lt 0 -or $Crf -gt 51) { throw "CRF muss zwischen 0 und 51 liegen." }
}
foreach ($Fps in $FpsValues) {
    if ($Fps -lt 1 -or $Fps -gt 30) { throw "FPS muss zwischen 1 und 30 liegen." }
}

$VideoRoot = Join-Path $BenchmarkRoot "videos"
$ReportPath = Join-Path $BenchmarkRoot "crf_benchmark_report.txt"
$ExperimentDefinitions = @([pscustomobject]@{ Label = "source"; Crf = -1; VideoPath = $VideoPath; EncodingSeconds = 0; VideoBytes = (Get-Item -LiteralPath $VideoPath).Length })

if ($PlanOnly) {
    Write-Host "CRF-Plan fuer ${TargetWidth}x${TargetHeight}:"
    foreach ($Definition in $ExperimentDefinitions) {
        foreach ($Fps in $FpsValues) { Write-Host ("{0}_fps{1:D2}: {2}" -f $Definition.Label, $Fps, $Definition.VideoPath) }
    }
    foreach ($Crf in $CrfValues) {
        $PlanVideo = Join-Path $VideoRoot "source_${TargetHeight}p_crf${Crf}.mp4"
        foreach ($Fps in $FpsValues) { Write-Host ("crf{0}_fps{1:D2}: {2}" -f $Crf, $Fps, $PlanVideo) }
    }
    return
}

foreach ($Crf in $CrfValues) {
    $CompressedVideo = Join-Path $VideoRoot "source_${TargetHeight}p_crf${Crf}.mp4"
    $EncodingSeconds = 0
    if (!(Test-Path -LiteralPath $CompressedVideo) -or $Force) {
        New-Item -ItemType Directory -Path $VideoRoot -Force | Out-Null
        Write-Host "Erzeuge H.264-Video CRF $Crf in $CompressedVideo"
        $EncodeTimer = [Diagnostics.Stopwatch]::StartNew()
        & $FfmpegPath -hide_banner -loglevel error -y -i $VideoPath -vf "scale=${TargetWidth}:${TargetHeight}:flags=lanczos" -c:v libx264 -preset medium -crf $Crf -pix_fmt yuv420p -an $CompressedVideo
        if ($LASTEXITCODE -ne 0) { throw "FFmpeg CRF $Crf ist fehlgeschlagen." }
        $EncodeTimer.Stop()
        $EncodingSeconds = [math]::Round($EncodeTimer.Elapsed.TotalSeconds, 3)
    }
    $ExistingEncode = Read-Json (Join-Path $VideoRoot "crf${Crf}.json")
    if ($EncodingSeconds -eq 0 -and $null -ne $ExistingEncode) { $EncodingSeconds = $ExistingEncode.EncodingSeconds }
    $ExperimentDefinitions += [pscustomobject]@{ Label = "crf$Crf"; Crf = $Crf; VideoPath = $CompressedVideo; EncodingSeconds = $EncodingSeconds; VideoBytes = (Get-Item -LiteralPath $CompressedVideo).Length }
    ([ordered]@{ Crf = $Crf; EncodingSeconds = $EncodingSeconds; VideoBytes = (Get-Item -LiteralPath $CompressedVideo).Length }) | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $VideoRoot "crf${Crf}.json") -Encoding UTF8
}

New-Item -ItemType Directory -Path $BenchmarkRoot -Force | Out-Null
$Results = @()
$CrfCaseNumber = 0
$CrfCaseTotal = $ExperimentDefinitions.Count * $FpsValues.Count
foreach ($Definition in $ExperimentDefinitions) {
    foreach ($Fps in $FpsValues) {
        $CrfCaseNumber++
        $CaseName = "{0}_fps{1:D2}" -f $Definition.Label, $Fps
        $CaseRoot = Join-Path $BenchmarkRoot $CaseName
        $FpsTag = $Fps.ToString("D2")
        $MetricsPath = Join-Path (Join-Path $CaseRoot "fps${FpsTag}_h${TargetHeight}") "metrics.json"
        $Existing = Read-Json $MetricsPath
        if (!$Force -and $null -ne $Existing -and $Existing.Status -eq "OK") {
            Write-Host "Ueberspringe abgeschlossenen CRF-Lauf: $CaseName"
            $Metric = $Existing
        } else {
            Write-Host "Starte $CaseName, Log unter $CaseRoot"
            New-Item -ItemType Directory -Path $CaseRoot -Force | Out-Null
            $LogPath = Join-Path $BenchmarkRoot "$CaseName.log"
            $CaseProgressPath = if ([string]::IsNullOrWhiteSpace($ProgressFile)) {
                Join-Path $BenchmarkRoot "$CaseName.progress.json"
            } else {
                $ProgressFile
            }
            $Arguments = @(
                "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $BenchmarkScript,
                "-VideoPath", $Definition.VideoPath,
                "-BenchmarkRoot", $CaseRoot,
                "-EnvironmentName", $EnvironmentName,
                "-CameraModel", $CameraModel,
                "-FpsValues", $Fps.ToString(),
                "-TargetHeights", $TargetHeight.ToString(),
                "-SequentialOverlap", $SequentialOverlap.ToString(),
                "-FeatureThreads", $FeatureThreads.ToString(),
                "-MatchingThreads", $MatchingThreads.ToString(),
                "-RandomSeed", $RandomSeed.ToString(),
                "-MaxFeatures", $MaxFeatures.ToString(),
                "-ProgressFile", $CaseProgressPath,
                "-Force"
            )
            $Process = Start-Process -FilePath $PowerShellCommand.Source -ArgumentList $Arguments -PassThru -NoNewWindow -RedirectStandardOutput $LogPath -RedirectStandardError (Join-Path $BenchmarkRoot "$CaseName.err.log")
            do {
                $Process.Refresh()
                $ProgressState = Read-ProgressState $CaseProgressPath
                if ($null -ne $ProgressState) {
                    $StagePercent = [double]$ProgressState.Percent
                    $OverallPercent = ((($CrfCaseNumber - 1) * 100) + $StagePercent) / $CrfCaseTotal
                    $StageStatus = "$CaseName`: $($ProgressState.Status)"
                } else {
                    $OverallPercent = (($CrfCaseNumber - 1) / $CrfCaseTotal) * 100
                    $StageStatus = "$CaseName`: Unterprozess wird gestartet"
                }
                Write-Progress -Id 20 -Activity "COLMAP CRF-Benchmark ($CrfCaseNumber/$CrfCaseTotal)" -Status $StageStatus -PercentComplete $OverallPercent
                if (!$Process.HasExited) { Start-Sleep -Milliseconds 500 }
            } while (!$Process.HasExited)
            $Process.WaitForExit()
            if ($Process.ExitCode -ne 0) { Write-Warning "$CaseName Benchmarkprozess Exit-Code $($Process.ExitCode)" }
            $Metric = Read-Json $MetricsPath
        }
        if ($null -eq $Metric) {
            $Metric = [pscustomobject]@{ CaseName = $CaseName; Status = "FAILED"; Error = "Keine metrics.json erzeugt."; Fps = $Fps; TargetHeight = $TargetHeight; TargetWidth = $TargetWidth; Points3D = 0; PointsPerRegisteredImage = 0; MeanTrackLength = 0; MeanObservationsPerImage = 0; MeanReprojectionErrorPx = 0; MeanReprojectionErrorNormalized = 0; RegistrationRatio = 0 }
        }
        $Metric | Add-Member -MemberType NoteProperty -Name CaseName -Value $CaseName -Force
        $Metric | Add-Member -MemberType NoteProperty -Name Crf -Value $Definition.Crf -Force
        $Metric | Add-Member -MemberType NoteProperty -Name VideoBytes -Value $Definition.VideoBytes -Force
        $Metric | Add-Member -MemberType NoteProperty -Name EncodingSeconds -Value $Definition.EncodingSeconds -Force
        $Metric | Add-Member -MemberType NoteProperty -Name ReconstructionSeconds -Value $Metric.ElapsedSeconds -Force
        $Metric | Add-Member -MemberType NoteProperty -Name TotalSeconds -Value ([double]$Definition.EncodingSeconds + [double]$Metric.ElapsedSeconds) -Force
        $Results += $Metric
        Write-CrfReport -ReportPath $ReportPath -Video $VideoPath -TargetWidth $TargetWidth -TargetHeight $TargetHeight -Results $Results
    }
}
Write-CrfReport -ReportPath $ReportPath -Video $VideoPath -TargetWidth $TargetWidth -TargetHeight $TargetHeight -Results $Results
Write-Progress -Id 20 -Activity "COLMAP CRF-Benchmark" -Status "Benchmark abgeschlossen" -PercentComplete 100 -Completed
Write-Host "CRF-Benchmark beendet. Bericht: $ReportPath"
