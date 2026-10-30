# #1320 Signal Probe — VENUE_HOLD

**Status:** `VENUE_HOLD`  
**Exit claimed:** none — **not** `FL_WORKFLOW_SIGNAL_CONTRACT_PROVEN`  
**Parent:** #1319  
**Date:** 2026-10-30

## Summary

A managed Linux Cloud Agent prepared the throwaway probe package and attempted live execution on the authorized Windows/FL Studio machine (self-hosted worker Jannek). Live FL + Windows signal capture did **not** run. No signal results were invented.

## Venue evidence

| Check | Result |
|---|---|
| Required venue | Windows + FL Studio (owner machine Jannek) |
| Coordinator runtime | Managed Linux (`runtime=managed`) |
| Worker Jannek listed | Connected, `os=windows`, approved, idle, `eligibleForSubagent=true` |
| Task placement `machine.type=self_hosted_worker` | Rejected (only `same_machine` \| `new_cloud_vm`) |
| Cursor Agents UI automation | Login blocked |
| Public Agents API machine create | Needs `CURSOR_API_KEY` (absent) |

## Prepared package (throwaway)

Repo path: [`tools/fl_workflow_signal_probe/`](../../tools/fl_workflow_signal_probe/)

- `SBWorkflowSignalProbe/device_SBWorkflowSignalProbe.py`
- `win_fl_input_probe.py`
- `fuse_probe_matrix.py`
- `install_fl_script.ps1`
- `MATRIX_RUNBOOK.md`

Local spool (never commit): `%LOCALAPPDATA%/sample-brain/workflow-observer-probe/`

## Decision outputs (live unset)

| Output | State |
|---|---|
| `V1_SIGNAL_SET` | unset — no live proof |
| `DEFERRED_SIGNALS` | unset |
| `BLIND_SPOTS` | unset (playlist active-tool remains a plan **candidate** blind spot) |
| `REA` | provisional default only: `REA_NOT_REQUIRED_FOR_V1` until live gaps measured |
| `#1321` readiness | **not** `READY_FOR_IMPLEMENTATION` |

## Unblock

1. Run a Cloud Agent **on My Machine Jannek (Windows)** and execute `tools/fl_workflow_signal_probe/` per README + MATRIX_RUNBOOK.
2. Or provide `CURSOR_API_KEY` / enable Task self-hosted placement from the Linux coordinator.

## Scope

No #1321/#1322/#1323 recorder/analyzer/reports. No product behavior change. No virtual MIDI driver auto-install. No REA.
