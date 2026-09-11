param(
  [string]$Db = "data/catalog.db",
  [string]$ProfilesDir = "profiles",
  [string]$Config = "pipeline_config.yaml",
  [string]$OutCsv = "reports/TITLE_SUGGESTIONS.csv",
  [switch]$Apply
)

python .\tools\title_pipeline.py --db $Db --profiles $ProfilesDir --config $Config --out $OutCsv --emit-ps1 reports\RENAME_PREVIEW.ps1

if ($Apply) {
  pwsh -File .\reports\RENAME_PREVIEW.ps1 -Apply
}
