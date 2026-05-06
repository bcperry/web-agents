# Implementation Plan: AZD Deploy with Correct Infra & Env Variables

**Branch**: `004-azd-deploy-frontend` | **Date**: 2026-04-24 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/004-azd-deploy-frontend/spec.md`

## Summary

Ensure the Terraform infrastructure correctly provisions an Azure App Service with
all environment variables the application needs at runtime, and that `azure.yaml`
maps those variables so `azd up` works end-to-end. The infra already has App Service
+ Managed Identity (the only resources needed). The gaps are missing auth/branding
env variables in `app_settings` and corresponding Terraform variables / `azure.yaml`
parameter mappings.

## Technical Context

**Language/Version**: Python 3.12 (backend), TypeScript (frontend)
**Primary Dependencies**: FastAPI, React/Vite, Terraform (azurerm ~> 4.0)
**Storage**: Azure SQL (read-only, connection string passed via env var)
**Testing**: pytest (backend), npm test (frontend)
**Target Platform**: Azure App Service (Linux) via Azure Government
**Project Type**: Web service (two-tier: FastAPI backend + React SPA)
**Performance Goals**: N/A (infra-only change)
**Constraints**: Azure Government endpoints (`.azure.us` / `.usgovcloudapi.net`)
**Scale/Scope**: Single App Service deployment

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Read-Only Data Access | PASS | No data access changes |
| II. Single-File Agent Definitions | PASS | No agent config changes |
| III. Security & Credential Hygiene | PASS | Sensitive vars marked `sensitive = true` in TF; no secrets in repo |
| IV. Evaluation-Driven Quality | PASS | No prompt/model changes |
| V. Simplicity & Minimalism | PASS | Only adding what's needed; no new resources beyond existing App Service + MI |
| VI. Infrastructure as Code | PASS | All changes in `infra/` Terraform + `azure.yaml` |
| VII. Two-Tier API-First Architecture | PASS | Single deployment unit preserved |

All gates pass. No violations to justify.

## Project Structure

### Documentation (this feature)

```text
specs/004-azd-deploy-frontend/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
└── tasks.md             # Phase 2 output (/speckit.tasks)
```

### Source Code (files modified)

```text
infra/
├── main.tf                              # No changes needed (already correct)
├── variables.tf                         # Add auth/branding variables
├── outputs.tf                           # No changes needed
├── provider.tf                          # No changes needed
├── main.tfvars.json.startexample        # Add auth/branding vars
├── main.tfvars.json.redeployexample     # Add auth/branding vars
└── modules/
    └── app-service/
        ├── main.tf                      # Add auth/branding to app_settings
        └── variables.tf                 # Add auth/branding variables

azure.yaml                               # Add auth/branding parameter mappings
```

**Structure Decision**: Existing two-tier layout. Only infra config files modified.

## Complexity Tracking

No violations. No complexity justification needed.
