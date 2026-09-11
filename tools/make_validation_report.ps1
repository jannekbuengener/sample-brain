param(
  [string]$Db = "data/catalog.db",
  [string]$Out = "reports/VALIDATION_REPORT.md"
)

python .\tools\validate_report.py --db $Db --out $Out
