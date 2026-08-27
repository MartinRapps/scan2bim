[CmdletBinding()]
param(
    [string]$VideoPath = "01_video\Alurohr_THWS.mp4",
    [string]$BenchmarkRoot = "04_benchmark",
    [string]$EnvironmentName = "colmap_env",
    [int[]]$FpsValues = @(5, 10, 20),
    [int[]]$TargetHeights = @(1080, 720, 480),
    [ValidateSet("SIMPLE_RADIAL", "OPENCV", "PINHOLE", "OPENCV_FISHEYE", "SIMPLE_RADIAL_FISHEYE")]
    [string]$CameraModel = "OPENCV",
    [string]$ProgressFile = "",
    [int]$SequentialOverlap = 15,
    [int]$FeatureThreads = 4,
    [int]$MatchingThreads = 4,
    [int]$RandomSeed = 42,
    [int]$MaxFeatures = 2048,
    [int]$FeatureMaxImageSize = 0,
    [switch]$DomainSizePooling,
    [switch]$EstimateAffineShape,
    [switch]$GuidedMatching,
    [switch]$Force,
    [switch]$RetryFailed,
    [switch]$PlanOnly
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

function Read-ProgressState {
    param([string]$Path)
    if ([string]::IsNullOrWhiteSpace($Path) -or !(Test-Path -LiteralPath $Path -PathType Leaf)) {
        return $null
    }
    try {
        return ((Get-Content -LiteralPath $Path -Raw) | ConvertFrom-Json)
    } catch {
        return $null
    }
}

function Resolve-ProjectPath {
    param([string]$Path)
    if ([System.IO.Path]::IsPathRooted($Path)) {
        return $Path
    }
    return Join-Path $ProjectRoot $Path
}

function Assert-File {
    param([string]$Path)
    if (!(Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "Datei nicht gefunden: $Path"
    }
}

function Get-Number {
    param(
        [string]$Text,
        [string]$Pattern,
        [double]$Default = 0
    )
    if ($Text -match $Pattern) {
        return [double]$Matches[1]
    }
    return $Default
}

function Format-Number {
    param(
        [object]$Value,
        [string]$Format = "0.00"
    )
    if ($null -eq $Value -or "$Value" -eq "") {
        return "-"
    }
    return ([double]$Value).ToString($Format, [Globalization.CultureInfo]::InvariantCulture)
}

function Read-MetricsFiles {
    param([string]$Root)
    $Metrics = @()
    if (!(Test-Path -LiteralPath $Root)) {
        return $Metrics
    }
    foreach ($File in @(Get-ChildItem -LiteralPath $Root -Filter "metrics.json" -File -Recurse)) {
        try {
            $Metrics += ((Get-Content -LiteralPath $File.FullName -Raw) | ConvertFrom-Json)
        } catch {
            Write-Warning "Ueberspringe ungueltige Metrikdatei: $($File.FullName)"
        }
    }
    return $Metrics
}

function Get-QualityScores {
    param([object[]]$Results)
    $Successful = @($Results | Where-Object { $_.Status -eq "OK" })
    if ($Successful.Count -eq 0) {
        return @()
    }

    $MaxPointDensity = [double](@($Successful | ForEach-Object { [double]$_.PointsPerRegisteredImage } | Measure-Object -Maximum).Maximum)
    $MaxObservations = [double](@($Successful | ForEach-Object { [double]$_.MeanObservationsPerImage } | Measure-Object -Maximum).Maximum)
    $MaxTrackLength = [double](@($Successful | ForEach-Object { [double]$_.MeanTrackLength } | Measure-Object -Maximum).Maximum)
    $MinReprojection = [double](@($Successful | ForEach-Object { [double]$_.MeanReprojectionErrorNormalized } | Measure-Object -Minimum).Minimum)

    foreach ($Result in $Successful) {
        $RegistrationScore = [math]::Min(1, [double]$Result.RegistrationRatio)
        $PointScore = if ($MaxPointDensity -gt 0) { [math]::Min(1, [double]$Result.PointsPerRegisteredImage / $MaxPointDensity) } else { 0 }
        $ObservationScore = if ($MaxObservations -gt 0) { [math]::Min(1, [double]$Result.MeanObservationsPerImage / $MaxObservations) } else { 0 }
        $TrackScore = if ($MaxTrackLength -gt 0) { [math]::Min(1, [double]$Result.MeanTrackLength / $MaxTrackLength) } else { 0 }
        $ReprojectionScore = if ([double]$Result.MeanReprojectionErrorNormalized -gt 0) {
            [math]::Min(1, $MinReprojection / [double]$Result.MeanReprojectionErrorNormalized)
        } else {
            0
        }

        # Heuristic only: this is not a substitute for a ground-truth scan.
        $Score = 100 * (
            0.40 * $RegistrationScore +
            0.25 * $PointScore +
            0.15 * $ObservationScore +
            0.10 * $TrackScore +
            0.10 * $ReprojectionScore
        )
        $Result | Add-Member -MemberType NoteProperty -Name QualityProxy -Value ([math]::Round($Score, 2)) -Force
    }
    return $Successful
}

function Write-BenchmarkReport {
    param(
        [string]$Root,
        [string]$ReportPath,
        [string]$Video,
        [int]$SourceWidth,
        [int]$SourceHeight,
        [object[]]$Results
    )

    $Scored = @(Get-QualityScores $Results | Sort-Object TargetHeight, Fps)
    $All = @($Results | Sort-Object TargetHeight, Fps)
    $Lines = New-Object System.Collections.Generic.List[string]
    [void]$Lines.Add("COLMAP Video-Benchmark")
    [void]$Lines.Add("======================")
    [void]$Lines.Add("Video: $Video")
    [void]$Lines.Add("Originalaufloesung: ${SourceWidth}x${SourceHeight}")
    [void]$Lines.Add("Erstellt: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')")
    [void]$Lines.Add("")
    [void]$Lines.Add("Hinweis: Dieser Benchmark erzeugt Sparse-Punktwolken. Der installierte")
    [void]$Lines.Add("COLMAP-Build ist CPU-only; Dense-PatchMatch benoetigt CUDA/NVIDIA-GPU.")
    [void]$Lines.Add("")
    [void]$Lines.Add("Ergebnisse")
    [void]$Lines.Add("----------")
    [void]$Lines.Add("Fall             FPS Hoehe Bilder Regist. Reg.-%   Paare   Punkte  Pkt/Reg  Tracks  Obs/Bild  Reproj  Zeit[s] Qualitaet Status")
    [void]$Lines.Add("---------------- --- ----- ------ ------- ------- ------- -------- -------- -------- -------- ------- -------- -------- ------")

    foreach ($Result in $All) {
        $Quality = if ($Result.Status -eq "OK") { Format-Number $Result.QualityProxy "0.00" } else { "-" }
        $Line = "{0,-16} {1,3} {2,5} {3,6} {4,7} {5,7} {6,7} {7,8} {8,8} {9,8} {10,8} {11,7} {12,8} {13,8} {14,-6}" -f `
            $Result.CaseName,
            $Result.Fps,
            $Result.TargetHeight,
            $Result.InputFrames,
            $Result.RegisteredImages,
            (Format-Number ([double]$Result.RegistrationRatio * 100) "0.0"),
            $Result.GeometricPairCount,
            $Result.Points3D,
            (Format-Number $Result.PointsPerRegisteredImage "0"),
            (Format-Number $Result.MeanTrackLength "0.00"),
            (Format-Number $Result.MeanObservationsPerImage "0.0"),
            (Format-Number $Result.MeanReprojectionErrorPx "0.000"),
            (Format-Number $Result.ElapsedSeconds "0.0"),
            $Quality,
            $Result.Status
        [void]$Lines.Add($Line)
    }

    $Successful = @($Scored | Where-Object { $_.Status -eq "OK" })
    [void]$Lines.Add("")
    [void]$Lines.Add("Empfehlungen")
    [void]$Lines.Add("------------")
    if ($Successful.Count -eq 0) {
        [void]$Lines.Add("Noch keine erfolgreiche Rekonstruktion vorhanden.")
    } else {
        $BestQuality = @($Successful | Sort-Object QualityProxy -Descending)[0]
        $Fastest = @($Successful | Sort-Object ElapsedSeconds)[0]
        $Threshold = [double]$BestQuality.QualityProxy * 0.90
        $BestTradeoff = @($Successful | Where-Object { [double]$_.QualityProxy -ge $Threshold } | Sort-Object ElapsedSeconds)[0]

        [void]$Lines.Add(("Hoechste heuristische Qualitaet: {0} (Score {1}, {2}s)" -f $BestQuality.CaseName, (Format-Number $BestQuality.QualityProxy "0.00"), (Format-Number $BestQuality.ElapsedSeconds "0.0")))
        [void]$Lines.Add(("Schnellster erfolgreicher Lauf: {0} ({1}s, Score {2})" -f $Fastest.CaseName, (Format-Number $Fastest.ElapsedSeconds "0.0"), (Format-Number $Fastest.QualityProxy "0.00")))
        [void]$Lines.Add(("Bester Zeit/Qualitaets-Kompromiss: {0} ({1}s, Score {2}; mindestens 90% des besten Scores)" -f $BestTradeoff.CaseName, (Format-Number $BestTradeoff.ElapsedSeconds "0.0"), (Format-Number $BestTradeoff.QualityProxy "0.00")))
    }

    [void]$Lines.Add("")
    [void]$Lines.Add("Metrik-Erklaerung")
    [void]$Lines.Add("-----------------")
    [void]$Lines.Add("Reg.-%: Anteil der Eingabebilder, die in einem gemeinsamen Modell registriert wurden; hoeher ist besser.")
    [void]$Lines.Add("Punkte: Anzahl triangulierter 3D-Punkte; absolute Anzahl ist bei mehr Bildern naturgemaess hoeher.")
    [void]$Lines.Add("Pkt/Reg: 3D-Punkte pro registriertem Bild; proxy fuer Punktdichte und Vergleichbarkeit.")
    [void]$Lines.Add("Tracks: mittlere Anzahl Beobachtungen je 3D-Punkt; hoeher bedeutet meist stabilere Geometrie.")
    [void]$Lines.Add("Obs/Bild: mittlere 2D-Beobachtungen pro Bild; hoeher bedeutet mehr verwertbare Verknuepfungen.")
    [void]$Lines.Add("Reproj: mittlerer Reprojektionsfehler in Pixeln; niedriger ist besser. Der Score nutzt zusaetzlich Reproj/Bilddiagonale.")
    [void]$Lines.Add("Zeit: komplette Laufzeit inklusive Frame-Extraktion, SIFT, Matching, Mapping und PLY-Export.")
    [void]$Lines.Add("Overlap: fester Frame-Overlap; bei hoeherem FPS entspricht derselbe Wert einem kuerzeren Zeitfenster.")
    [void]$Lines.Add("Qualitaet: heuristischer relativer Proxy, keine absolute Genauigkeitsmessung.")
    [void]$Lines.Add("Metrikbasis: https://colmap.github.io/faq.html")
    [void]$Lines.Add("")
    [void]$Lines.Add("Wichtige Einschraenkung")
    [void]$Lines.Add("-----------------------")
    [void]$Lines.Add("Ohne Ground-Truth-Scan oder bekannte Kameraposen kann die metrische Genauigkeit nicht direkt bestimmt werden.")
    [void]$Lines.Add("Fuer eine belastbare Genauigkeit waeren Cloud-to-Cloud-Distanz (Chamfer/Hausdorff), Precision/Recall/F-score,")
    [void]$Lines.Add("Vollstaendigkeit und absolute Genauigkeit nach einer registrierten Referenzmessung geeigneter als der Proxy.")
    [void]$Lines.Add("Die COLMAP-Punktwolke besitzt ausserdem nur eine relative Skala, solange keine Referenz oder Massstab vorliegt.")
    [void]$Lines.Add("")
    [void]$Lines.Add("Fehler")
    [void]$Lines.Add("------")
    foreach ($Result in @($All | Where-Object { $_.Status -ne "OK" })) {
        [void]$Lines.Add("$($Result.CaseName): $($Result.Error)")
    }

    $Lines | Set-Content -LiteralPath $ReportPath -Encoding UTF8
}

$VideoPath = Resolve-ProjectPath $VideoPath
$BenchmarkRoot = Resolve-ProjectPath $BenchmarkRoot
$RunScriptPath = Join-Path $ProjectRoot "run_colmap.ps1"
Assert-File $VideoPath
Assert-File $RunScriptPath
$PowerShellCommand = Get-Command powershell.exe -ErrorAction SilentlyContinue
if ($null -eq $PowerShellCommand) {
    throw "powershell.exe wurde nicht gefunden."
}

$MambaCommand = Get-Command mamba -ErrorAction SilentlyContinue
if ($null -eq $MambaCommand) {
    throw "mamba wurde nicht gefunden. Bitte zuerst Mamba/Anaconda aktivieren."
}
$CondaBase = Split-Path (Split-Path $MambaCommand.Source -Parent) -Parent
$EnvironmentPath = Join-Path $CondaBase (Join-Path "envs" $EnvironmentName)
$ColmapPath = Join-Path $EnvironmentPath "Library\bin\colmap.exe"
$FfprobePath = Join-Path $EnvironmentPath "Library\bin\ffprobe.exe"
$SqlitePath = Join-Path $EnvironmentPath "Library\bin\sqlite3.exe"
Assert-File $ColmapPath
Assert-File $FfprobePath
Assert-File $SqlitePath

$env:PATH = "$EnvironmentPath;$EnvironmentPath\Library\bin;$EnvironmentPath\Scripts;$env:PATH"
$VideoSizeText = (& $FfprobePath -v error -select_streams v:0 -show_entries stream=width,height -of csv=p=0:s=x $VideoPath 2>&1 | Out-String).Trim()
if ($VideoSizeText -notmatch "^(\d+)x(\d+)x?$") {
    throw "Die Videoaufloesung konnte nicht gelesen werden: $VideoSizeText"
}
$SourceWidth = [int]$Matches[1]
$SourceHeight = [int]$Matches[2]

$Cases = @()
foreach ($Height in $TargetHeights) {
    if ($Height -lt 1) {
        throw "TargetHeights muessen positiv sein."
    }
    $TargetWidth = [int]([math]::Round($Height * $SourceWidth / $SourceHeight))
    if (($TargetWidth % 2) -ne 0) {
        $TargetWidth++
    }
    foreach ($Fps in $FpsValues) {
        if ($Fps -lt 1 -or $Fps -gt 30) {
            throw "FpsValues muessen zwischen 1 und 30 liegen."
        }
        $CaseName = "fps{0:D2}_h{1}" -f $Fps, $Height
        $Cases += [pscustomobject]@{
            CaseName = $CaseName
            Fps = $Fps
            TargetHeight = $Height
            TargetWidth = $TargetWidth
            FeatureMaxImageSize = if ($FeatureMaxImageSize -gt 0) { $FeatureMaxImageSize } else { $TargetWidth }
            CasePath = Join-Path $BenchmarkRoot $CaseName
            LogPath = Join-Path $BenchmarkRoot "$CaseName.log"
            MetricsPath = Join-Path (Join-Path $BenchmarkRoot $CaseName) "metrics.json"
        }
    }
}

if ($PlanOnly) {
    Write-Host "Benchmarkplan fuer $VideoPath ($SourceWidth`:$SourceHeight):"
    foreach ($Case in $Cases) {
        Write-Host ("{0}: {1} fps, {2}x{3}, FeatureMaxImageSize={4}" -f $Case.CaseName, $Case.Fps, $Case.TargetWidth, $Case.TargetHeight, $Case.FeatureMaxImageSize)
    }
    return
}

New-Item -ItemType Directory -Path $BenchmarkRoot -Force | Out-Null
$ReportPath = Join-Path $BenchmarkRoot "benchmark_report.txt"

$CaseNumber = 0
$CaseTotal = $Cases.Count
foreach ($Case in $Cases) {
    $CaseNumber++
    $Existing = $null
    if (Test-Path -LiteralPath $Case.MetricsPath -PathType Leaf) {
        try {
            $Existing = (Get-Content -LiteralPath $Case.MetricsPath -Raw) | ConvertFrom-Json
        } catch {
            $Existing = $null
        }
    }
    if (!$Force -and $null -ne $Existing -and $Existing.Status -eq "OK") {
        Write-Host "Ueberspringe abgeschlossenen Lauf: $($Case.CaseName)"
        continue
    }
    if (!$Force -and !$RetryFailed -and $null -ne $Existing -and $Existing.Status -ne "OK") {
        Write-Host "Ueberspringe fehlgeschlagenen Lauf: $($Case.CaseName) (RetryFailed verwenden)"
        continue
    }

    $CaseProgressPath = if ([string]::IsNullOrWhiteSpace($ProgressFile)) {
        Join-Path $BenchmarkRoot "$($Case.CaseName).progress.json"
    } else {
        $ProgressFile
    }
    Write-Progress -Id 10 -Activity "COLMAP Benchmark ($CaseNumber/$CaseTotal)" -Status "$($Case.CaseName) wird vorbereitet" -PercentComplete ([math]::Round((($CaseNumber - 1) / $CaseTotal) * 100, 1))
    $Timer = [Diagnostics.Stopwatch]::StartNew()
    $Status = "OK"
    $ErrorText = ""
    $Result = $null

    try {
        $RunArguments = @(
            "-VideoPath", $VideoPath,
            "-FramesPath", (Join-Path $Case.CasePath "frames"),
            "-WorkspacePath", $Case.CasePath,
            "-EnvironmentName", $EnvironmentName,
            "-Matcher", "sequential",
            "-CameraModel", $CameraModel,
            "-Fps", $Case.Fps.ToString(),
            "-TargetHeight", $Case.TargetHeight.ToString(),
            "-SequentialOverlap", $SequentialOverlap.ToString(),
            "-FeatureThreads", $FeatureThreads.ToString(),
            "-MatchingThreads", $MatchingThreads.ToString(),
            "-RandomSeed", $RandomSeed.ToString(),
            "-MaxFeatures", $MaxFeatures.ToString(),
            "-MaxImageSize", $Case.FeatureMaxImageSize.ToString()
        )
        if ($DomainSizePooling) { $RunArguments += "-DomainSizePooling" }
        if ($EstimateAffineShape) { $RunArguments += "-EstimateAffineShape" }
        if ($GuidedMatching) { $RunArguments += "-GuidedMatching" }
        $RunArguments += "-ExtractFrames"
        $RunArguments += "-Rebuild"
        $RunArguments += "-ProgressFile"
        $RunArguments += $CaseProgressPath
        $Process = Start-Process -FilePath $PowerShellCommand.Source -ArgumentList (@("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $RunScriptPath) + $RunArguments) -PassThru -NoNewWindow -RedirectStandardOutput $Case.LogPath -RedirectStandardError (Join-Path $BenchmarkRoot "$($Case.CaseName).err.log")
        do {
            $Process.Refresh()
            $ProgressState = Read-ProgressState $CaseProgressPath
            if ($null -ne $ProgressState) {
                $StagePercent = [double]$ProgressState.Percent
                $OverallPercent = ((($CaseNumber - 1) * 100) + $StagePercent) / $CaseTotal
                $StageStatus = "$($Case.CaseName): $($ProgressState.Status)"
            } else {
                $OverallPercent = (($CaseNumber - 1) / $CaseTotal) * 100
                $StageStatus = "$($Case.CaseName): Unterprozess wird gestartet"
            }
            Write-Progress -Id 10 -Activity "COLMAP Benchmark ($CaseNumber/$CaseTotal)" -Status $StageStatus -PercentComplete $OverallPercent
            if (!$Process.HasExited) { Start-Sleep -Milliseconds 500 }
        } while (!$Process.HasExited)
        $Process.WaitForExit()
        $Process.Refresh()
        $FinalProgressState = Read-ProgressState $CaseProgressPath
        Write-Progress -Id 10 -Activity "COLMAP Benchmark ($CaseNumber/$CaseTotal)" -Status "$($Case.CaseName): Metriken werden ausgewertet" -PercentComplete ([math]::Round((($CaseNumber * 100) - 1) / $CaseTotal, 1))
        $ChildExitCode = $Process.ExitCode
        if ($null -eq $ChildExitCode -and $null -ne $FinalProgressState -and [int]$FinalProgressState.Percent -ge 100) {
            $ChildExitCode = 0
        }
        if ($ChildExitCode -ne 0) {
            throw "run_colmap.ps1 ist fehlgeschlagen (Exit-Code $ChildExitCode). Siehe $($Case.LogPath)."
        }

        $ModelDirectories = @(Get-ChildItem -LiteralPath (Join-Path $Case.CasePath "sparse") -Directory | Sort-Object Name | Where-Object {
            Test-Path -LiteralPath (Join-Path $_.FullName "points3D.bin")
        })
        if ($ModelDirectories.Count -eq 0) {
            throw "Kein Sparse-Modell gefunden. Siehe $($Case.LogPath)."
        }
        $ModelPath = $ModelDirectories[0].FullName
        $DatabasePath = Join-Path $Case.CasePath "database.db"
        $PlyPath = Join-Path $Case.CasePath "sparse_pointcloud.ply"
        $AnalyzerText = (& $ColmapPath model_analyzer --log_target stdout --path $ModelPath 2>&1 | Out-String)
        $InputFrames = @(Get-ChildItem -LiteralPath (Join-Path $Case.CasePath "frames") -Filter "*.jpg" -File).Count
        $RegisteredImages = [int](Get-Number $AnalyzerText "Registered images:\s+(\d+)" 0)
        # model_analyzer reports images in the reconstructed model, not all input frames.
        $TotalImages = $InputFrames
        $Points3D = [int](Get-Number $AnalyzerText "Points:\s+(\d+)" 0)
        $Observations = [int](Get-Number $AnalyzerText "Observations:\s+(\d+)" 0)
        $MeanTrackLength = Get-Number $AnalyzerText "Mean track length:\s+([0-9.]+)" 0
        $MeanObservations = Get-Number $AnalyzerText "Mean observations per image:\s+([0-9.]+)" 0
        $MeanReprojection = Get-Number $AnalyzerText "Mean reprojection error:\s+([0-9.]+)px" 0
        $ImageDiagonal = [math]::Sqrt([math]::Pow($Case.TargetWidth, 2) + [math]::Pow($Case.TargetHeight, 2))
        $NormalizedReprojection = if ($ImageDiagonal -gt 0) { $MeanReprojection / $ImageDiagonal } else { 0 }
        $PairCount = [int]((& $SqlitePath $DatabasePath "SELECT count(*) FROM two_view_geometries;" 2>&1 | Out-String).Trim())
        $FrameBytes = [int64](@(Get-ChildItem -LiteralPath (Join-Path $Case.CasePath "frames") -Filter "*.jpg" -File | Measure-Object -Property Length -Sum).Sum)
        $PlyBytes = [int64](Get-Item -LiteralPath $PlyPath).Length
        $RegisteredRatio = if ($TotalImages -gt 0) { [double]$RegisteredImages / $TotalImages } else { 0 }
        $PointsPerRegisteredImage = if ($RegisteredImages -gt 0) { [double]$Points3D / $RegisteredImages } else { 0 }
        $ReconstructionStatus = if ($RegisteredRatio -ge 0.90) { "OK" } else { "INCOMPLETE" }
        $CompletenessNote = if ($ReconstructionStatus -eq "OK") { "" } else { "Nur $RegisteredImages von $InputFrames Bildern registriert." }
        $Result = [ordered]@{
            CaseName = $Case.CaseName
            Status = $ReconstructionStatus
            Fps = $Case.Fps
            TargetHeight = $Case.TargetHeight
            TargetWidth = $Case.TargetWidth
            InputFrames = $InputFrames
            TotalImages = $TotalImages
            RegisteredImages = $RegisteredImages
            RegistrationRatio = [math]::Round($RegisteredRatio, 6)
            Points3D = $Points3D
            Observations = $Observations
            PointsPerRegisteredImage = [math]::Round($PointsPerRegisteredImage, 3)
            MeanTrackLength = [math]::Round($MeanTrackLength, 6)
            MeanObservationsPerImage = [math]::Round($MeanObservations, 6)
            MeanReprojectionErrorPx = [math]::Round($MeanReprojection, 6)
            MeanReprojectionErrorNormalized = [math]::Round($NormalizedReprojection, 8)
            GeometricPairCount = $PairCount
            FrameBytes = $FrameBytes
            PlyBytes = $PlyBytes
            ModelPath = $ModelPath
            Error = $CompletenessNote
        }
    } catch {
        $Status = "FAILED"
        $ErrorText = $_.Exception.Message
        $Result = [ordered]@{
            CaseName = $Case.CaseName
            Status = $Status
            Fps = $Case.Fps
            TargetHeight = $Case.TargetHeight
            TargetWidth = $Case.TargetWidth
            InputFrames = 0
            TotalImages = 0
            RegisteredImages = 0
            RegistrationRatio = 0
            Points3D = 0
            Observations = 0
            PointsPerRegisteredImage = 0
            MeanTrackLength = 0
            MeanObservationsPerImage = 0
            MeanReprojectionErrorPx = 0
            MeanReprojectionErrorNormalized = 0
            GeometricPairCount = 0
            FrameBytes = 0
            PlyBytes = 0
            ModelPath = ""
            Error = $ErrorText
        }
        Write-Warning "$($Case.CaseName) fehlgeschlagen: $ErrorText"
    }

    $Timer.Stop()
    New-Item -ItemType Directory -Path $Case.CasePath -Force | Out-Null
    $Result.ElapsedSeconds = [math]::Round($Timer.Elapsed.TotalSeconds, 3)
    $Result.CompletedAt = Get-Date -Format "yyyy-MM-ddTHH:mm:ss"
    ($Result | ConvertTo-Json -Depth 4) | Set-Content -LiteralPath $Case.MetricsPath -Encoding UTF8
    $CurrentResults = @(Read-MetricsFiles $BenchmarkRoot)
    Write-BenchmarkReport -Root $BenchmarkRoot -ReportPath $ReportPath -Video $VideoPath -SourceWidth $SourceWidth -SourceHeight $SourceHeight -Results $CurrentResults
    Write-Host "Abgeschlossen: $($Case.CaseName), Status=$($Result.Status), Zeit=$($Result.ElapsedSeconds)s"
}

$FinalResults = @(Read-MetricsFiles $BenchmarkRoot)
Write-BenchmarkReport -Root $BenchmarkRoot -ReportPath $ReportPath -Video $VideoPath -SourceWidth $SourceWidth -SourceHeight $SourceHeight -Results $FinalResults
Write-Progress -Id 10 -Activity "COLMAP Benchmark" -Status "Benchmark abgeschlossen" -PercentComplete 100 -Completed
Write-Host "`nBenchmark beendet. Bericht: $ReportPath"
