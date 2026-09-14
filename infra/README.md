# Terraform Infrastructure

This directory contains Terraform configuration files for deploying the agent framework to Azure.

## Structure

```
infra/
├── main.tf                          # Main infrastructure configuration
├── variables.tf                     # Input variable definitions
├── outputs.tf                       # Output values
├── provider.tf                      # Provider configurations
├── terraform.tfvars.example         # Example variable values
└── modules/
  └── app-service/                 # App Service module
        ├── main.tf
        ├── variables.tf
        └── outputs.tf
```

## Resources Created

- **Resource Group**: Container for all resources
- **Managed Identity**: System-assigned identity on the App Service
- **Microsoft Foundry**: Terraform-managed `AIServices` account, `web-agents`
  project, and `gpt-5.6-luna` deployment
  (version `2026-07-09`, DataZoneStandard capacity 10), with key authentication
  disabled and the app identity granted `Cognitive Services OpenAI User`
- **App Service Plan**: Linux-based hosting plan
- **App Service**: Web app for running the Chainlit application
- **Cosmos DB**: Durable chat/configuration database, including global `skills`
  and owner-isolated `user-skills` containers

The `user-skills` container uses partition key `/user_id`. Its Terraform output
is wired to App Service as `AZURE_COSMOS_USER_SKILLS_CONTAINER`; runtime-created
skills use atomic create operations and never overwrite an existing owner/name
pair.

## Deployment with Azure Developer CLI

The Azure Developer CLI (azd) automatically uses Terraform when configured in `azure.yaml`:

```bash
# Initialize the environment
azd init

# Provision and deploy
azd up
```

The `azure.yaml` file is configured to use Terraform:

```yaml
infra:
  provider: terraform
  path: infra
```

## Manual Terraform Deployment

If you prefer to use Terraform directly:

```bash
# Navigate to the infra directory
cd infra

# Initialize Terraform
terraform init

# Review the plan
terraform plan -var="environment_name=dev" -var="location=eastus" -var="subscription_id=YOUR_SUBSCRIPTION_ID"

# Apply the configuration
terraform apply -var="environment_name=dev" -var="location=eastus" -var="subscription_id=YOUR_SUBSCRIPTION_ID"
```

## Variables

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `environment_name` | Name of the environment | - | Yes |
| `location` | Azure region | - | Yes |
| `subscription_id` | Azure subscription ID | "" | No* |
| `principal_id` | User/app principal ID | "" | No |
| `app_service_plan_sku` | App Service Plan SKU | "B1" | No |
| `python_version` | Python version | "3.12" | No |
| `azure_openai_account_name` | OpenAI account name | Empty derives `aoai-<environment_name>-luna` | No |

*Required for azd deployments, handled automatically

Set `AZURE_OPENAI_ACCOUNT_NAME` to override the derived account name. The
`azd-web-agents` environment uses `aoai-web-agents-luna-20260914`; that account
and its Luna deployment have been imported into this environment's Terraform
state. Preserve this state when provisioning again. In another state, import
existing resources before applying or choose a new globally unique account name.

The Foundry account `foundry-<environment_name>-luna`, project, and deployment
are defined in `openai.tf`. The earlier OpenAI-only account and its deployment
remain managed and protected; Azure rejected an in-place kind conversion. They
are not the application's configured target. Remove them only through an
explicitly reviewed cleanup plan.

The selected region must
support the model and have sufficient DataZoneStandard quota. The deploying
principal must be able to create the account, deployments, and role assignments.
The application authenticates with its system-assigned managed identity.
`AZURE_OPENAI_RESOURCE_ID`, `AZURE_OPENAI_ENDPOINT`, and `AZURE_OPENAI_MODEL`
are now resource-derived outputs, not Terraform inputs. The account has
`prevent_destroy` enabled to guard against accidental replacement.

The backend continues using the Foundry account's OpenAI-compatible endpoint
and `AZURE_OPENAI_*` settings. The project endpoint is exposed separately as
`AZURE_AI_PROJECT_ENDPOINTS`; it is not a replacement for the chat client's
inference endpoint. Creating the Foundry resources with a targeted apply does
not update App Service or its role assignments; those require the normal
reviewed provisioning plan.

## Outputs

- `AZURE_LOCATION`: Deployment region
- `AZURE_TENANT_ID`: Azure tenant ID
- `RESOURCE_GROUP_NAME`: Resource group name
- `WEB_APP_NAME`: App Service name
- `WEB_APP_URL`: App Service URL
- `MANAGED_IDENTITY_PRINCIPAL_ID`: App Service system identity principal ID
