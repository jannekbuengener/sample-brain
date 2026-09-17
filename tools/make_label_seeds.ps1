# --- SETTINGS ---------------------------------------------------------------
# Projekt-Root (wo src\ und data\ liegen)
$PROJECT_ROOT = "C:\Users\janne\Desktop\FL Projekt\sample-brain"

# Deine Samples (Master-Ordner mit Techno/Cinematic)
$SAMPLE_ROOT  = "D:\PRODUCING\Schnuffis Soundvitriene\Samples"

# Wieviele Beispiele je Klasse?
$MaxPerClass = 10

# Audio-Endungen
$EXT = @("*.wav","*.aif","*.aiff","*.flac","*.mp3","*.ogg")

# Klassen-Definitionen:
# 1) preferred Folders (relativ zu $SAMPLE_ROOT)
# 2) fallback Filename-Patterns (Regex, case-insensitive)
$CLASSES = @(
    @{
        Label   = "Kick"
        Folders = @(
            "Techno\Drums\Kicks"
        )
        Patterns = @("(^|[^a-z])kick(\d+|[^a-z]|$)","(^|[^a-z])bd(\d+|[^a-z]|$)","subkick")
    },
    @{
        Label   = "Snare"
        Folders = @("Techno\Drums\Snares")
        Patterns = @("(^|[^a-z])snare(\d+|[^a-z]|$)","(^|[^a-z])sd(\d+|[^a-z]|$)")
    },
    @{
        Label   = "HiHat-Closed"
        Folders = @("Techno\Drums\HiHats\Closed")
        Patterns = @("(^|[^a-z])(hat|hihat|hh)(-?c|_?closed)?(\d+|[^a-z]|$)")
    },
    @{
        Label   = "Impact"
        Folders = @(
            "Cinematic\Sounddesign\Trailer FX\Booms",
            "Cinematic\Sounddesign\Trailer FX\Hits"
        )
        Patterns = @("impact","boom","braam","hit(?!hat)")
    },
    @{
        Label   = "Drone"
        Folders = @("Cinematic\Sounddesign\Drones")
        Patterns = @("(^|[^a-z])drone(\d+|[^a-z]|$)")
    },
    @{
        Label   = "Pad"
        Folders = @("Techno\Synth\Pads")
        Patterns = @("(^|[^a-z])pad(\d+|[^a-z]|$)")
    }
)

# --- PREP -------------------------------------------------------------------
$ErrorActionPreference = "Stop"
$null = New-Item -ItemType Directory -Force -Path (Join-Path $PROJECT_ROOT "data") -ErrorAction SilentlyContinue
$CSV  = Join-Path $PROJECT_ROOT "data\label_seeds.csv"

# Hilfsfunktion: sichere, rekursive Dateisuche mit Filter
function Get-AudioFilesUnder {
    param(
        [string]$Root
    )
    if (-not (Test-Path $Root)) { return @() }
    $files = @()
    foreach ($pattern in $EXT) {
        $files += Get-ChildItem -LiteralPath $Root -Recurse -File -Filter $pattern -ErrorAction SilentlyContinue
    }
    return $files | Sort-Object FullName -Unique
}

# String → Regex-IsMatch (case-insensitive)
function Match-Name {
    param(
        [string]$Name,
        [string]$Pattern
    )
    return [System.Text.RegularExpressions.Regex]::IsMatch($Name, $Pattern, "IgnoreCase")
}

# --- SAMMELN ----------------------------------------------------------------
$allLines = New-Object System.Collections.Generic.List[string]

foreach ($cls in $CLASSES) {
    $label = $cls.Label
    $picked = @()

    # 1) bevorzugte Ordner
    foreach ($rel in $cls.Folders) {
        $folder = Join-Path $SAMPLE_ROOT $rel
        if (-not (Test-Path $folder)) { continue }
        $files = Get-AudioFilesUnder -Root $folder
        if ($files.Count -gt 0) {
            # nimm die ersten $MaxPerClass (oder mische per Get-Random)
            $picked += $files | Select-Object -First $MaxPerClass
        }
        if ($picked.Count -ge $MaxPerClass) { break }
    }

    # 2) fallback: Dateinamen-Pattern durchs gesamte SAMPLE_ROOT
    if ($picked.Count -lt $MaxPerClass -and $cls.Patterns -and $cls.Patterns.Count -gt 0) {
        $all = Get-AudioFilesUnder -Root $SAMPLE_ROOT
        $candidates = $all | Where-Object {
            $n = $_.Name
            foreach ($pat in $cls.Patterns) {
                if (Match-Name -Name $n -Pattern $pat) { return $true }
            }
            return $false
        }
        $need = $MaxPerClass - $picked.Count
        if ($need -gt 0) {
            $picked += $candidates | Select-Object -First $need
        }
    }

    # Einträge in CSV-Form
    foreach ($f in ($picked | Sort-Object FullName -Unique)) {
        # CSV ohne Quotes: Pfad darf kein Komma enthalten (bei Windows-Pfade normalerweise ok)
        $line = "$($f.FullName),$label"
        $allLines.Add($line)
    }

    Write-Host ("[{0}] gesammelt: {1}" -f $label, $picked.Count)
}

# --- SCHREIBEN --------------------------------------------------------------
# UTF-8 ohne BOM: -Encoding utf8 reicht i.d.R. (PS 5/7)
$allLines | Set-Content -Encoding UTF8 -NoNewline:$false -Path $CSV
Write-Host ("Seeds geschrieben: {0}" -f $CSV) -ForegroundColor Green
