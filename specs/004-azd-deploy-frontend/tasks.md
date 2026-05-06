# Tasks: AZD Deploy with Correct Infra & Env Variables

**Input**: Design documents from `/specs/004-azd-deploy-frontend/`
**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, contracts/

**Tests**: Not requested — no test tasks included.

**Organization**: Tasks grouped by requirement area. All tasks modify infra config files only (no application code changes).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which requirement area (US1=auth vars, US2=branding vars, US3=azure.yaml deploy, US4=tfvars examples)
- Exact file paths included in descriptions

---

## Phase 1: Setup

**Purpose**: No setup needed — project structure already exists. Verify current state.

- [X] T001 Verify existing Terraform configuration is valid by running `terraform validate` in infra/

**Checkpoint**: Existing infra validated, ready for modifications.

---

## Phase 2: Foundational (App-Service Module Variables)

**Purpose**: Add new Terraform input variables to the app-service module. This MUST complete before app_settings can reference them.

**CRITICAL**: No app_settings changes can be made until these variables exist in the module.

- [X] T002 Add auth variables (`entra_tenant_id`, `entra_client_id`, `entra_client_secret`) to infra/modules/app-service/variables.tf
- [X] T003 [P] Add branding variables (`classification_banner`, `app_name`, `app_tagline`, `app_logo`) to infra/modules/app-service/variables.tf

**Checkpoint**: App-service module accepts all new variables.

---

## Phase 3: Auth Environment Variables (Priority: P1) — MVP

**Goal**: App Service has `OAUTH_AZURE_GOV_AD_TENANT_ID` and `OAUTH_AZURE_GOV_AD_CLIENT_ID` in `app_settings` so the backend can authenticate users via Entra ID.

**Independent Test**: Run `terraform plan` — the plan should show the new `app_settings` entries on the `azurerm_linux_web_app` resource.

### Implementation

- [X] T004 [US1] Add auth variables (`entra_tenant_id`, `entra_client_id`, `entra_client_secret`) to root infra/variables.tf
- [X] T005 [US1] Pass auth variables from root infra/main.tf to the app-service module invocation
- [X] T006 [US1] Add `OAUTH_AZURE_GOV_AD_TENANT_ID`, `OAUTH_AZURE_GOV_AD_CLIENT_ID` to `app_settings` block in infra/modules/app-service/main.tf

**Checkpoint**: Auth env vars flow from Terraform variables → module → App Service app_settings.

---

## Phase 4: Branding Environment Variables (Priority: P2)

**Goal**: App Service has `CLASSIFICATION_BANNER`, `APP_NAME`, `APP_TAGLINE`, `APP_LOGO` in `app_settings` so the backend `/api/auth/config` endpoint can serve branding to the frontend.

**Independent Test**: Run `terraform plan` — the plan should show the branding `app_settings` entries.

### Implementation

- [X] T007 [US2] Add branding variables (`classification_banner`, `app_name`, `app_tagline`, `app_logo`) to root infra/variables.tf
- [X] T008 [US2] Pass branding variables from root infra/main.tf to the app-service module invocation
- [X] T009 [US2] Add `CLASSIFICATION_BANNER`, `APP_NAME`, `APP_TAGLINE`, `APP_LOGO` to `app_settings` block in infra/modules/app-service/main.tf

**Checkpoint**: Branding env vars flow through Terraform to App Service.

---

## Phase 5: azure.yaml Deploy Configuration (Priority: P1)

**Goal**: `azd up` builds the frontend before packaging and passes all variables to Terraform.

**Independent Test**: Run `azd package --dry-run` (or inspect azure.yaml) — prepackage hook should be present and all parameter mappings defined.

### Implementation

- [X] T010 [US3] Add `prepackage` service hook to azure.yaml to run `cd frontend && npm install && npm run build`
- [X] T011 [US3] Add Entra ID parameter mappings (`entra_tenant_id`, `entra_client_id`, `entra_client_secret`) to `infra.parameters` in azure.yaml
- [X] T012 [US3] Add branding parameter mappings (`classification_banner`, `app_name`, `app_tagline`, `app_logo`) to `infra.parameters` in azure.yaml

**Checkpoint**: azure.yaml is complete — `azd up` can provision and deploy.

---

## Phase 6: Update tfvars Examples (Priority: P2)

**Goal**: Example tfvars files include all variables so new developers can set up their environment.

**Independent Test**: Compare `main.tfvars.json` template variables against `variables.tf` — all variables should be represented.

### Implementation

- [X] T013 [P] [US4] Update infra/main.tfvars.json.startexample with auth and branding variables
- [X] T014 [P] [US4] Update infra/main.tfvars.json.redeployexample with auth and branding variables
- [X] T015 [US4] Create infra/main.tfvars.json template file with all `${VARIABLE}` references for azd

**Checkpoint**: All example/template files match the full variable set.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Validate the complete configuration end-to-end.

- [X] T016 Run `terraform validate` in infra/ to confirm all variables and references are correct
- [X] T017 Run `terraform plan` with example variable values to verify the plan shows expected app_settings
- [X] T018 Validate azure.yaml structure is valid YAML and hook syntax is correct

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies — start immediately
- **Phase 2 (Foundational)**: Depends on Phase 1 — BLOCKS Phases 3 & 4
- **Phase 3 (Auth vars)**: Depends on Phase 2 (module variables must exist first)
- **Phase 4 (Branding vars)**: Depends on Phase 2 — can run in PARALLEL with Phase 3
- **Phase 5 (azure.yaml)**: Independent of Phases 3 & 4 — can run in PARALLEL
- **Phase 6 (tfvars examples)**: Depends on Phases 3 & 4 (needs to know all variables)
- **Phase 7 (Polish)**: Depends on all previous phases

### Parallel Opportunities

- T002 and T003 (Foundational) can run in parallel (same file but different variable blocks)
- Phase 3 (auth) and Phase 4 (branding) can run in parallel (different variable groups)
- Phase 5 (azure.yaml) can run in parallel with Phases 3 & 4
- T013 and T014 (tfvars examples) can run in parallel (different files)

---

## Parallel Example: Phases 3 + 4 + 5

```bash
# After Phase 2 completes, launch all three in parallel:
# Stream A: Auth variables
Task T004: Add auth vars to root variables.tf
Task T005: Pass auth vars in root main.tf
Task T006: Add auth app_settings in module main.tf

# Stream B: Branding variables (parallel with Stream A)
Task T007: Add branding vars to root variables.tf
Task T008: Pass branding vars in root main.tf
Task T009: Add branding app_settings in module main.tf

# Stream C: azure.yaml (parallel with Streams A & B)
Task T010: Add prepackage hook
Task T011: Add auth parameter mappings
Task T012: Add branding parameter mappings
```

---

## Implementation Strategy

### MVP First (Auth Variables Only)

1. Complete Phase 1: Validate existing infra
2. Complete Phase 2: Add module variables
3. Complete Phase 3: Auth env vars (MVP — enables authentication)
4. **STOP and VALIDATE**: `terraform plan` shows auth app_settings
5. Complete Phase 5: azure.yaml (enables actual deployment)

### Full Delivery

1. Setup → Foundational → Auth vars + Branding vars + azure.yaml (parallel)
2. tfvars examples (once all vars known)
3. Polish (validate everything)

---

## Notes

- All tasks modify infrastructure config files only — zero application code changes
- [P] tasks target different files with no dependencies
- [US*] labels map to requirement areas, not traditional user stories
- Commit after each phase for clean git history
- Sensitive variables (`entra_client_secret`, API keys, connection strings) must use `sensitive = true` in Terraform
