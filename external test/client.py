# /// script
# requires-python = ">=3.12"
# dependencies = ["fastapi", "uvicorn", "httpx>=0.27,<1", "msal", "python-dotenv"]
# ///

import os
from pathlib import Path
import json

import httpx
import msal
import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware

load_dotenv(Path(__file__).with_name(".env"))
app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost"])

HTML = """<!doctype html>
<html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>External test</title>
<style>
body { font-family: Georgia, serif; max-width: 640px; margin: 48px auto; padding: 0 20px; color: #202424; background: #f6f8f7; }
h1 { font-size: 24px; } button { font: inherit; padding: 10px 18px; cursor: pointer; }
pre { font: 16px/1.5 Georgia, serif; white-space: pre-wrap; overflow-wrap: anywhere; }
</style>
<h1>External test</h1>
<button id="ping">Ping agent</button>
<pre id="response" role="status" aria-live="polite"></pre>
<script>
const button = document.getElementById('ping');
const output = document.getElementById('response');
button.onclick = async () => {
  button.disabled = true;
  output.textContent = 'Waiting...';
  try {
    const response = await fetch('/ping', { method: 'POST', headers: { 'X-External-Test': '1' } });
    const data = await response.json();
    output.textContent = response.ok ? data.text : (data.detail || 'Request failed.');
  } catch {
    output.textContent = 'Cannot reach the local test server.';
  } finally {
    button.disabled = false;
  }
};
</script></html>"""


def settings() -> dict[str, str]:
    names = ["API_URL", "TENANT_ID", "API_CLIENT_ID", "CLIENT_ID", "CLIENT_SECRET", "PROFILE_ID"]
    values = {name: os.getenv(f"EXTERNAL_{name}", "").strip() for name in names}
    missing = [f"EXTERNAL_{name}" for name, value in values.items() if not value or value.startswith("<")]
    if missing:
        raise HTTPException(400, "Configure external test/.env: " + ", ".join(missing))
    values["AUTHORITY"] = os.getenv("EXTERNAL_AUTHORITY", "https://login.microsoftonline.us").rstrip("/")
    url = httpx.URL(values["API_URL"])
    if url.scheme != "https" and not (url.scheme == "http" and url.host in {"localhost", "127.0.0.1"}):
        raise HTTPException(400, "API_URL must use HTTPS, except for localhost testing.")
    return values


def get_token(config: dict[str, str]) -> str:
    identity = msal.ConfidentialClientApplication(
        config["CLIENT_ID"],
        authority=f'{config["AUTHORITY"]}/{config["TENANT_ID"]}',
        client_credential=config["CLIENT_SECRET"],
        timeout=30,
    )
    result = identity.acquire_token_for_client(scopes=[f'api://{config["API_CLIENT_ID"]}/.default'])
    if "access_token" not in result:
        raise HTTPException(502, "Entra rejected token acquisition. Check the tenant, caller credential, API URI, and assignment requirements.")
    return result["access_token"]


def generate(client: httpx.Client, profile_id: str) -> str:
    session = client.post("/api/sessions", json={"profile_id": profile_id})
    session.raise_for_status()
    session_id = session.json()["session_id"]
    try:
        text = []
        event = ""
        with client.stream("POST", f"/api/sessions/{session_id}/messages", json={"content": "Reply with a short hello."}) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if line.startswith("event:"):
                    event = line[6:].strip()
                elif line.startswith("data:"):
                    data = json.loads(line[5:])
                    if event == "error":
                        raise HTTPException(502, "The agent returned a generation error. Check the API backend logs.")
                    if event == "text":
                        text.append(data["content"])
                    if event == "done":
                        if not text:
                            raise HTTPException(502, "The agent completed without a text response.")
                        return "".join(text)
        raise HTTPException(502, "The response stream ended before completion.")
    finally:
        try:
            client.delete(f"/api/sessions/{session_id}")
        except httpx.HTTPError:
            pass


@app.get("/", response_class=HTMLResponse)
def index():
    return HTML


@app.post("/ping")
def ping(request: Request):
    if request.headers.get("X-External-Test") != "1":
        raise HTTPException(403, "Use the local test page.")
    config = settings()
    try:
        token = get_token(config)
        with httpx.Client(base_url=config["API_URL"].rstrip("/"), headers={"Authorization": f"Bearer {token}"}, timeout=180) as client:
            return {"text": generate(client, config["PROFILE_ID"])}
    except HTTPException:
        raise
    except httpx.HTTPStatusError as exc:
        raise HTTPException(502, f"API returned HTTP {exc.response.status_code}. Check backend authentication, agent ID, and API logs.") from None
    except Exception:
        raise HTTPException(502, "Request failed. Check Entra/API connectivity and the local configuration.") from None


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=int(os.getenv("EXTERNAL_PORT", "8765")), access_log=False)