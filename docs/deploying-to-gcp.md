# Deploying to Google Cloud Platform

The `servicenow-mcp` Streamable HTTP server is a long-lived async HTTP container — Cloud Run is the natural target on GCP. This guide covers Cloud Run end-to-end and notes the alternatives (GKE, Compute Engine) at the bottom.

## Why Cloud Run is the recommended target

The Streamable HTTP transport (introduced in Phase 7, v0.7.0) is built on Starlette + Uvicorn over chunked HTTP, with `mcp.server.streamable_http_manager.StreamableHTTPSessionManager` handling concurrent sessions. This shape maps cleanly onto Cloud Run:

| Cloud Run capability | What it does for us |
|---|---|
| Long-lived HTTP requests (up to 60 min per request, configurable) | Streamable HTTP responses can stream indefinitely without invocation timeout pressure |
| Native chunked-response support | `text/event-stream`-style streaming responses pass through unbuffered |
| TLS termination at the edge | No nginx required; matches the Phase 6 design (nginx is opt-in) |
| Multi-request concurrency per instance (default `--concurrency 80`) | One container handles many concurrent MCP sessions because the server is async |
| Automatic IAM integration | Cloud Run IAM gates *who* can invoke the URL; `MCP_AUTH_TOKEN` gates *what* clients present at the application layer |
| Autoscaling 0 → N | Scales to zero when idle, pay only for active request time |
| Container image deployment | Use the existing `ghcr.io/shadnygren/servicenow-mcp` image directly |

## Quick deploy (single command)

The simplest full deployment, assuming you have `gcloud` configured and a project selected:

```bash
gcloud run deploy servicenow-mcp \
  --image ghcr.io/shadnygren/servicenow-mcp:0.7.0 \
  --region us-central1 \
  --port 8080 \
  --allow-unauthenticated \
  --memory 512Mi \
  --cpu 1 \
  --max-instances 5 \
  --min-instances 0 \
  --concurrency 80 \
  --set-env-vars "MCP_ALLOW_REMOTE=1,MCP_AUTH_TOKEN=$(openssl rand -hex 32),SERVICENOW_INSTANCE_URL=https://your-instance.service-now.com,SERVICENOW_USERNAME=mcp-svc,SERVICENOW_PASSWORD=changeme"
```

After a minute or so, Cloud Run prints the public URL — something like `https://servicenow-mcp-xyz-uc.a.run.app`. Test it:

```bash
# /health bypasses bearer auth (Host check still applies)
curl https://servicenow-mcp-xyz-uc.a.run.app/health

# /mcp requires the bearer token from MCP_AUTH_TOKEN above
curl -H "Authorization: Bearer $MCP_AUTH_TOKEN" \
     -H "Accept: application/json,text/event-stream" \
     https://servicenow-mcp-xyz-uc.a.run.app/mcp
```

**A note on `--allow-unauthenticated`.** This makes the Cloud Run URL publicly resolvable. The `MCP_AUTH_TOKEN` bearer gate is doing the real work of access control, layered with the Host/Origin allowlist baked into our `SecurityMiddleware`. If you want defense-in-depth at the IAM layer too, drop `--allow-unauthenticated` and grant `roles/run.invoker` only to the service accounts that should reach the endpoint.

## Production deploy with Secret Manager

Don't pass credentials via `--set-env-vars` in production — they show up in Cloud Run revision metadata. Use Secret Manager instead:

```bash
# Create the secrets
gcloud secrets create servicenow-mcp-auth-token --replication-policy=automatic
echo -n "$(openssl rand -hex 32)" | gcloud secrets versions add servicenow-mcp-auth-token --data-file=-

gcloud secrets create servicenow-username --replication-policy=automatic
echo -n "mcp-svc" | gcloud secrets versions add servicenow-username --data-file=-

gcloud secrets create servicenow-password --replication-policy=automatic
echo -n "your-password" | gcloud secrets versions add servicenow-password --data-file=-

# Grant the Cloud Run service account access
PROJECT_NUMBER=$(gcloud projects describe $(gcloud config get-value project) --format='value(projectNumber)')
SERVICE_ACCOUNT="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"

for SECRET in servicenow-mcp-auth-token servicenow-username servicenow-password; do
  gcloud secrets add-iam-policy-binding $SECRET \
    --member="serviceAccount:${SERVICE_ACCOUNT}" \
    --role="roles/secretmanager.secretAccessor"
done

# Deploy with secrets
gcloud run deploy servicenow-mcp \
  --image ghcr.io/shadnygren/servicenow-mcp:0.7.0 \
  --region us-central1 \
  --port 8080 \
  --memory 512Mi \
  --cpu 1 \
  --max-instances 5 \
  --concurrency 80 \
  --set-env-vars "MCP_ALLOW_REMOTE=1,SERVICENOW_INSTANCE_URL=https://your-instance.service-now.com" \
  --set-secrets "MCP_AUTH_TOKEN=servicenow-mcp-auth-token:latest,SERVICENOW_USERNAME=servicenow-username:latest,SERVICENOW_PASSWORD=servicenow-password:latest"
```

Secret rotation now becomes `gcloud secrets versions add servicenow-password --data-file=-` followed by a Cloud Run revision update — no service restart configuration drift, no env-var leaks in audit logs.

## Private endpoint with internal load balancer

For corporate deployments where the MCP server should only be reachable from within your VPC (or via Cloud Interconnect / VPN):

```bash
gcloud run deploy servicenow-mcp \
  --image ghcr.io/shadnygren/servicenow-mcp:0.7.0 \
  --region us-central1 \
  --ingress internal-and-cloud-load-balancing \
  ... # everything else as above
```

This makes the `*.run.app` URL unreachable from the public internet. Reach it only via:
- Internal Application Load Balancer in front of Cloud Run.
- Cloud Run jobs / other Cloud Run services in the same VPC.
- VMs / GKE pods with `--vpc-egress=all-traffic` and the right VPC connector.

You'll typically front it with an **internal HTTPS load balancer** that terminates TLS with your own certificate (using Certificate Manager) and forwards to Cloud Run via a Serverless NEG.

## Updating the OAuth path (recommended for production)

Basic auth via `SERVICENOW_USERNAME` / `SERVICENOW_PASSWORD` is fine for development. For production, switch to OAuth client_credentials (the recommended primary path per Issue #43 finding #2):

```bash
gcloud run deploy servicenow-mcp \
  --image ghcr.io/shadnygren/servicenow-mcp:0.7.0 \
  --region us-central1 \
  --set-env-vars "MCP_ALLOW_REMOTE=1,SERVICENOW_INSTANCE_URL=https://your-instance.service-now.com,SERVICENOW_AUTH_TYPE=oauth" \
  --set-secrets "MCP_AUTH_TOKEN=servicenow-mcp-auth-token:latest,SERVICENOW_CLIENT_ID=servicenow-client-id:latest,SERVICENOW_CLIENT_SECRET=servicenow-client-secret:latest"
```

The server's `AuthManager` will use the client_credentials grant against `<instance>/oauth_token.do`, cache the access token with proper expiry tracking, and refresh automatically before expiry (Phase 1.5 / `michaelbuckner` port).

## Monitoring

Cloud Run automatically exports request metrics, instance counts, and stderr/stdout logs to Cloud Logging and Cloud Monitoring with no additional setup. A few signals worth watching:

| Metric | Why |
|---|---|
| `run.googleapis.com/request_count` filtered by `response_code` | Track 401/421/403 from `SecurityMiddleware` (auth failures, Host violations, Origin violations) |
| `run.googleapis.com/request_latencies` | Streamable HTTP responses can be long; watch the p99 |
| `run.googleapis.com/container/instance_count` | Detect cold starts |
| stderr containing `Rate limit warning` from `helpers.py` | ServiceNow approaching its quota (`X-RateLimit-Remaining` parsing from Phase 2 cherry-pick) |

Define Cloud Monitoring alerts on auth-failure spikes; they're the leading indicator of a misconfigured client or a credential-stuffing attempt.

## Cost notes

Cloud Run bills only for time spent serving requests (CPU + memory) at per-100ms granularity. For a typical MCP workload:

- **Idle:** $0/month (scales to zero, no minimum instances).
- **Light usage** (~100 tool calls/day at <500ms each): pennies/month.
- **Heavy usage** (sustained 10 RPS): roughly $20–50/month at 512MiB / 1 vCPU.

The dominant cost in production is usually outbound network egress to ServiceNow (free within the same GCP region if your ServiceNow instance is colocated; ~$0.12/GB to internet otherwise). Inbound from Anthropic / OpenAI is free.

## Alternative GCP targets

| Target | When to choose it |
|---|---|
| **Cloud Run** | Default. Simplest, cheapest, native streaming, autoscaling. |
| **GKE / GKE Autopilot** | If you already have a GKE cluster and want to colocate this MCP with other workloads, share a private VPC, or run it as a sidecar. Use the standard Helm-chart pattern; the existing Dockerfile is the only artifact needed. |
| **Compute Engine VM** | If you specifically need a long-running, never-cold-starting deployment with predictable per-month pricing — not necessary for most workloads. |
| **Cloud Functions (2nd gen)** | Cloud Functions 2nd gen runs on Cloud Run under the hood; functionally equivalent to direct Cloud Run for our use case. Direct Cloud Run gives you slightly more deployment control. |

## Workload Identity Federation for ServiceNow OAuth

If your ServiceNow OAuth provider supports Workload Identity Federation (WIF) — e.g. Auth0, Okta, Entra ID — you can authenticate Cloud Run to the OAuth provider without storing any client secret:

1. Configure WIF between GCP and your IdP.
2. Grant the Cloud Run service account permission to issue tokens via WIF.
3. Replace `SERVICENOW_CLIENT_SECRET` with WIF-issued JWT tokens at runtime.

This removes the long-lived client secret entirely. Phase 10 work; not currently shipped, but the architecture is compatible.

## End-to-end checklist

- [ ] Container image built and pushed to GHCR (Phase 6 GitHub Actions does this automatically on tag push).
- [ ] Service account created with minimum IAM (`roles/secretmanager.secretAccessor`, `roles/run.invoker` if private).
- [ ] Secrets created in Secret Manager (`MCP_AUTH_TOKEN`, ServiceNow credentials).
- [ ] Cloud Run service deployed with `--ingress internal-and-cloud-load-balancing` if private.
- [ ] `MCP_ALLOW_REMOTE=1` and `MCP_AUTH_TOKEN` both set (the server refuses to bind non-loopback without both — Phase 1 hardening guarantee).
- [ ] Cloud Logging alerting policy on `httpRequest.status >= 400` for auth-failure visibility.
- [ ] Tested `/health` endpoint (should return 200 OK with no auth) and `/mcp` endpoint (401 without bearer, 200 with).
- [ ] If using a custom domain: Cloud Run domain mapping configured + DNS records.
- [ ] If private endpoint: internal HTTPS load balancer in place.

## Troubleshooting

**Symptom: 421 Misdirected Request on every request.**
Cause: `Host` header not in the allowlist. By default our `SecurityMiddleware` accepts `127.0.0.1`, `localhost`, `[::1]`, and the host:port the server was bound on. For Cloud Run, set `MCP_ALLOWED_HOSTS=servicenow-mcp-xyz-uc.a.run.app` (or your custom domain) so the Cloud Run-injected `Host` header passes the DNS-rebinding defense.

**Symptom: 403 Forbidden.**
Cause: `Origin` header from a browser-originating client doesn't match the Origin allowlist. Cloud Run propagates the original Origin header. Add the calling origin to `MCP_ALLOWED_ORIGINS` (comma-separated). For non-browser clients (Claude Desktop, agent SDKs), the Origin header is typically absent and the check is bypassed.

**Symptom: cold-start latency spikes.**
Set `--min-instances 1` to keep one container warm at all times. Costs ~$5/month for an always-on 512MiB instance, eliminates cold starts entirely.

**Symptom: requests time out at 60s.**
Cloud Run's default request timeout is 5 minutes. If you need more, set `--timeout 3600` (max 60 min). If MCP tool calls into ServiceNow take longer than that, the bottleneck isn't Cloud Run — it's ServiceNow's REST API throttling, which the `RateLimitTracker` in `helpers.py` should be slowing you to avoid.

**Symptom: container fails to start with "Address already in use".**
Cloud Run injects `PORT=8080`. Our entrypoint uses `--port 8080` by default, which matches. If you've overridden the bind port via Compose env vars, remove that override for Cloud Run.
