# External test

One button sends `Reply with a short hello.` to a configured agent. This is a separate client, not part of the web-agents backend. It can run on your laptop or another device with network access to the API. It does not use your browser login or `az login`.

The flow is: local Python client authenticates to Entra with its own credential, gets an API access token, creates a session, posts the fixed prompt, reads the response, and closes the active session. The browser only receives the response text. Closing the session does not delete the saved conversation; each click can incur model/tool costs and creates a conversation under the service principal's identity.

## Register the caller (Azure Government)

1. Open https://portal.azure.us and switch to the tenant used by your existing webapp registration.
2. Go to **Microsoft Entra ID > App registrations > New registration**. Name it `web-agents-external-test`, choose **Accounts in this organizational directory only**, and leave the redirect URI empty. Select **Register**. Its service principal is created in this tenant automatically. Hosting this client on your laptop does not change these choices.
3. From **Overview**, put this NEW registration's **Application (client) ID** into `EXTERNAL_CLIENT_ID` and the **Directory (tenant) ID** into `EXTERNAL_TENANT_ID`. Do not use the Object ID.
4. On the NEW registration, open **Certificates & secrets > Client secrets > New client secret**. Use a short expiration. Put its **Value**, not its Secret ID, in `EXTERNAL_CLIENT_SECRET` in the local `.env`. Never paste the secret into chat or commit it. This repository ignores `.env`. The secret belongs to this caller, not to the API.
5. Open your EXISTING webapp/API registration. Put its **Application (client) ID** in `EXTERNAL_API_CLIENT_ID`. The backend's `OAUTH_AZURE_GOV_AD_CLIENT_ID` (or fallback `AZURE_AD_CLIENT_ID`) must still identify this existing registration.
6. On the EXISTING registration, open **Expose an API**. Set the Application ID URI to `api://<EXISTING_API_CLIENT_ID>` if it is not set. If it already uses a different URI, preserve it and adjust the scope in `get_token()` in `client.py` to `<existing-uri>/.default`.
7. On the EXISTING registration, open **Manifest**. Inside `api`, set `requestedAccessTokenVersion` to `2`, preserving all other fields. This makes the API token's audience the client-ID GUID expected by this backend. Test your existing frontend login afterward. Using the v2 token endpoint alone does not force v2 access tokens.

No redirect URI, delegated permission, Microsoft Graph permission, or generation role is needed for this app-only test under your chosen policy: any valid token for the API is accepted.

Entra can issue app-only tokens without roles when the API's Enterprise Application does not require assignment. If token acquisition reports assignment/consent is required, check **Enterprise applications > your API > Properties > Assignment required?** and tenant policies with your administrator. Do not blindly disable an existing restriction. If assignment must stay required, define an application role on the API, add it under the caller's **API permissions > Add a permission > My APIs > your API > Application permissions**, and have an administrator grant consent. The current backend need not inspect that role for your chosen policy, but Entra then controls issuance through assignment.

## Local configuration

Edit `.env` in this folder. A placeholder file is provided locally; it is intentionally untracked. On another device, create `.env` beside `client.py` with these entries:

```dotenv
EXTERNAL_API_URL=https://your-backend-host
EXTERNAL_TENANT_ID=your-api-tenant-guid
EXTERNAL_API_CLIENT_ID=existing-api-registration-client-guid
EXTERNAL_CLIENT_ID=new-caller-registration-client-guid
EXTERNAL_CLIENT_SECRET=your-new-secret-value
EXTERNAL_PROFILE_ID=your-agent-profile-id
EXTERNAL_AUTHORITY=https://login.microsoftonline.us
```

Use the API origin without `/api` at the end. Choose a built-in profile ID from the backend's `config/agents.yaml`, not its display name; a simple agent without user-authenticated MCP tools is best for this test. Your personal custom agents are not automatically owned by this application.

The target backend must have **AUTH_DISABLED=false**, the correct tenant/client IDs, and the matching `AZURE_AD_AUTHORITY`. Testing against a backend with authentication disabled does not prove it accepted the service-principal token. No backend client secret is needed for token validation. HTTP is accepted only for localhost targets; remote targets must use HTTPS and be reachable from your device.

For commercial Azure, use https://portal.azure.com, `EXTERNAL_AUTHORITY=https://login.microsoftonline.com`, and the matching backend authority. Registrations must be in the appropriate cloud; a commercial-cloud token will not authenticate to this Government configuration.

## Run

From the repository root:

```bash
uv run --script "external test/client.py"
```

Open http://127.0.0.1:8765 and click **Ping agent**. On another device, only this folder and `uv` are needed; from this folder run `uv run --script client.py`. Script dependencies are installed independently of the backend. Restart the client after changing `.env`. Set `EXTERNAL_PORT` to another port if 8765 is occupied.

This server binds to loopback only. Keep it local; do not publish or tunnel it. It is a development credential holder, not a production service. Use a certificate or federated credential instead of a shared secret for a production caller where feasible.

## Troubleshooting

- Entra failure: check the tenant, secret value/expiry, application ID URI, and assignment policy.
- API HTTP 401: check the API audience, v2 access-token setting, backend tenant, and cloud authority. The caller ID is NOT the API audience.
- API HTTP 403: check API or hosting-layer access policies.
- API HTTP 400: check the profile ID.
- Agent error: inspect backend logs and model/tool configuration. Authentication to this API does not grant delegated user permissions to downstream tools.
- Connection failure: check the backend URL, TLS certificate, network/firewall access, and that the backend is running.

To validate authentication, also call the enabled backend without a bearer token and verify HTTP 401. A successful authenticated generation plus rejection of an unauthenticated request is the basic acceptance check. Never share tokens or secrets in logs or screenshots.

Mocked local checks (no Entra or model calls), from the repository root:

```bash
uv run --frozen python -m unittest discover -s "external test" -p "test_client.py"
```