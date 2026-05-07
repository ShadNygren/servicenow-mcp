# Deploying the ServiceNow MCP Server

This guide covers production deployment options for the Streamable HTTP transport. **Most users don't need any of this** — see "When you DON'T need this guide" below.

## Concurrency model (read this first if you're deploying for multiple agents)

As of v0.9.10 the server is fully async end-to-end. A single process can serve **many MCP sessions concurrently from many AI agents** without blocking the event loop on slow ServiceNow API calls. Practical capacity guidance:

| Resource | Limit | What hits it first |
|---|---|---|
| Concurrent in-flight ServiceNow API calls per process | ~100 | `httpx.Limits.max_connections` ceiling in `utils/async_http.py`. Tunable. |
| Concurrent keepalive sockets per process | 20 | `max_keepalive_connections`. Beyond this, sockets are closed after the call. Tunable. |
| OAuth token POSTs per expiry window per process | **1** | Serialised by an `asyncio.Lock` regardless of concurrent agent count. |
| Memory per concurrent MCP session | ~few MiB | Mostly the StreamableHTTPSessionManager session state + InMemoryEventStore. |

**Scaling shape:** Vertical first (one bigger instance), horizontal when you hit ~100 concurrent agents on one process. The official MCP `Mcp-Session-Id` header gives session affinity if you put a load balancer in front (sticky sessions per Mcp-Session-Id). On AWS Bedrock AgentCore Runtime this is automatic — see `docs/deploying-to-aws.md`.

**What the async refactor changed for deployment:**

- A slow ServiceNow call no longer blocks other agents' calls in the same process. Before Phase 9, three concurrent slow calls queued up; the third agent saw delay. Now each suspends its own coroutine and the event loop services others.
- The shared httpx connection pool reduces socket-creation overhead under heavy load. Cloud Run / App Runner cold starts hold up better under burst traffic.
- Process shutdown closes the connection pool cleanly via the FastMCP lifespan integration, so kubectl drain / Cloud Run revision swap doesn't drop in-flight ServiceNow connections mid-call.

See README §"Concurrency and async architecture" for the full architectural notes.

## Choose your scenario

| Scenario | What to do | Skip to |
|---|---|---|
| Local development, Claude Desktop talks to the server on your laptop | Run via **stdio** — `claude_desktop_config.json` launches the server as a subprocess. No network, no Docker, no Nginx. | [README §"Integration with Claude Desktop"](README.md#integration-with-claude-desktop) — stop reading this guide. |
| One developer wants the Streamable HTTP transport locally for testing | `python -m servicenow_mcp.server_http` — binds to `127.0.0.1:8080` by default, bearer token auto-generated. | [README §"Streamable HTTP Mode"](README.md#streamable-http-mode) |
| Containerized deployment on a private network | `docker run` the image with `MCP_AUTH_TOKEN` set; rely on your existing network boundary. No Nginx needed. | This guide §1 |
| Behind your org's existing reverse proxy / API gateway | Run the container, route the proxy's MCP path at the container's `:8080`. The proxy handles TLS. No Nginx in this repo. | This guide §1 |
| VPS with a public IP, want HTTPS, no other infra | Use the Docker Compose + Nginx recipe in this guide (§2). | This guide §2 |
| Cloud Run / App Runner / Fly / similar PaaS | Use the platform's TLS termination; `MCP_AUTH_TOKEN` for auth. | This guide §3 |

## When you DON'T need this guide

If **any** of these describe your deployment, stop and use a simpler path:

- **Local stdio** (the default in [`README.md`](README.md)) — no HTTP, no TLS, no auth headers needed. Claude Desktop launches the server, talks to it via stdin/stdout, done.
- **Single-tenant Docker on a private network** — no Internet exposure means no nginx and no TLS-from-us; you can rely on the network boundary your infra already provides.
- **Behind an existing reverse proxy** — your org's existing nginx / Apache / Traefik / cloud LB / API gateway already terminates TLS. The MCP server just speaks plain HTTP to it.

The Nginx setup in this repo is one specific recipe for one specific scenario: "I have a Linux VPS, no other infra, and want a public HTTPS endpoint." That's it.

---

## §1. Bare Docker (private network)

Quickest production-ish path. No Nginx, no TLS-from-us.

```bash
docker build -t servicenow-mcp-http .
docker run --rm -p 127.0.0.1:8080:8080 \
  --env-file .env \
  -e MCP_AUTH_TOKEN="<long-random-secret>" \
  -e MCP_ALLOW_REMOTE=1 \
  servicenow-mcp-http
```

`-p 127.0.0.1:8080` binds only to the loopback interface of the host. If you want it reachable on a private LAN, use `-p 10.0.0.5:8080` (your private IP) instead.

Connect MCP clients with `Authorization: Bearer <MCP_AUTH_TOKEN>`.

---

## §2. Docker Compose with optional Nginx (public VPS, this repo's recipe)

This guide walks through deploying the ServiceNow MCP server on a VPS (e.g. Hostinger) using Docker Compose, optionally with Nginx as an SSL-terminating reverse proxy.

**Nginx is opt-in.** The `nginx` service in `docker-compose.yml` sits behind a Compose profile, so by default only the MCP container starts:

```bash
# Default: just the MCP container, no nginx.
docker compose up -d

# Opt-in: include nginx for TLS termination.
docker compose --profile with-nginx up -d
```

**Why is Nginx opt-in?** The Python MCP process speaks plain HTTP on `127.0.0.1:8080`. To expose it as HTTPS on the public Internet you need TLS termination on `:443` somewhere. Most production environments already have that somewhere — a cloud load balancer (AWS ALB, GCP Load Balancer, Azure Application Gateway), Cloudflare/Fastly at the edge, an existing reverse proxy, or a PaaS edge (Cloud Run, App Runner). In those cases, **don't run our nginx.** Bare `docker compose up -d` is the right shape.

Use the `with-nginx` profile only when:
- You have a VPS with a public IP and no other TLS infrastructure.
- You want a self-contained stack where TLS termination lives in this repo.

If you run with nginx, the MCP server will be accessible at `https://<YOUR_VPS_IP>/mcp`. If you skip nginx, the MCP server will be on `127.0.0.1:8080` (or whatever you set via `MCP_BIND_ADDR`) and you handle TLS in your upstream load balancer.

Skip to §3 if you're using a PaaS that does TLS for you.

### Prerequisites

On your VPS:
- Docker Engine 20.10 or newer
- Docker Compose v2 (`docker compose` command, or `docker-compose` v1.29+)
- Port **443** open in your firewall / security group
- Git installed

On your local machine (or the VPS):
- OpenSSL (to generate the self-signed certificate, if not using Let's Encrypt)

---

## Step 1 — Clone the Repository

```bash
git clone https://github.com/<your-username>/servicenow-mcp.git
cd servicenow-mcp
```

---

## Step 2 — Generate a Self-Signed SSL Certificate

Because no domain name is used, we create a self-signed certificate.
Run this **once** before the first deployment.

```bash
chmod +x nginx/generate-certs.sh
./nginx/generate-certs.sh
```

This creates:
- `nginx/certs/server.key` — private key (kept secret, gitignored)
- `nginx/certs/server.crt` — certificate (valid 365 days)

> **Important:** These files are gitignored. You must re-run this script on each new
> server or after a fresh clone.

---

## Step 3 — Configure Environment Variables

```bash
cp .env.example .env
nano .env      # or your preferred editor
```

At minimum, set the following values:

| Variable | Required | Description |
|---|---|---|
| `SERVICENOW_INSTANCE_URL` | Yes | Your ServiceNow instance, e.g. `https://dev12345.service-now.com` |
| `SERVICENOW_AUTH_TYPE` | Yes | `basic`, `oauth`, or `api_key` |
| `SERVICENOW_USERNAME` | If basic/oauth | ServiceNow username |
| `SERVICENOW_PASSWORD` | If basic/oauth | ServiceNow password |
| `SERVICENOW_API_KEY` | If api_key | ServiceNow API key |
| `MCP_AUTH_TOKEN` | Recommended | Secret key that MCP clients must present |

**Example `.env` for API key authentication to ServiceNow:**

```dotenv
SERVICENOW_INSTANCE_URL=https://dev12345.service-now.com
SERVICENOW_AUTH_TYPE=api_key
SERVICENOW_API_KEY=your-servicenow-api-key

MCP_AUTH_TOKEN=a-very-long-random-secret-you-generate
MCP_TOOL_PACKAGE=full
```

**Generating a strong `MCP_AUTH_TOKEN`:**

```bash
openssl rand -hex 32
```

---

## Step 4 — Build and Deploy

```bash
# Build the MCP container image and start all services
docker compose up -d --build

# Check that both containers are running
docker compose ps
```

Expected output:

```
NAME                    STATUS          PORTS
servicenow-mcp-mcp-1    running         8080/tcp
servicenow-mcp-nginx-1  running         0.0.0.0:443->443/tcp
```

---

## Step 5 — Verify the Deployment

Send a test request to the `/mcp` endpoint. The `-k` flag ignores the self-signed
certificate warning.

```bash
curl -k -v https://<YOUR_VPS_IP>/mcp \
  -H "Authorization: Bearer <YOUR_MCP_AUTH_TOKEN>"
```

A successful response will:
- Return **HTTP 200**
- Have `Content-Type: text/event-stream`
- Keep the connection open (streaming response)

Press `Ctrl+C` to close.

**Without the API key (expected 401):**

```bash
curl -k -o - https://<YOUR_VPS_IP>/mcp
# → {"error":"Unauthorized","message":"Invalid or missing API key"}
```

---

## Step 6 — Add to the OpenAI API Platform

In the OpenAI API Platform (platform.openai.com), navigate to your project and add a
remote MCP server:

| Field | Value |
|---|---|
| **Server URL** | `https://<YOUR_VPS_IP>/mcp` |
| **Authentication** | Header-based |
| **Header name** | `Authorization` |
| **Header value** | `Bearer <YOUR_MCP_AUTH_TOKEN>` |

> **Self-signed certificate note:** Some clients reject self-signed certificates by
> default. If the OpenAI platform does not support accepting self-signed certs, you may
> need to obtain a certificate from a public CA (e.g. Let's Encrypt) using a domain name.

---

## Validate against your ServiceNow instance

After deploying, verify the server actually behaves correctly against your specific ServiceNow instance — different releases (Yokohama, Zurich, Australia) and different plugin sets cause real differences in Table API ACLs, schema, and state-machine behavior.

The project ships an audit-ready integration test program in [`tests/integration/`](tests/integration/) — 56 tests across 5 tiers (foundation, smoke, CRUD, lifecycle, edge cases). Run against your instance:

```bash
# from a checkout of the repo, with .env pointing at your instance
SN_INTEGRATION_TESTS=1 pytest tests/integration/ -v
```

A successful run writes `tests/integration/results/RESULTS_<UTC-iso>.md` stamped with your ServiceNow family + build tag, the per-tier results, and cleanup verification (every record the tests created is deleted at session end). For the manual MCP-client verification flow, see [`tests/integration/MCP_CLIENT_CHECKLIST.md`](tests/integration/MCP_CLIENT_CHECKLIST.md). For the test architecture and findings catalog, see [`tests/integration/README.md`](tests/integration/README.md).

## Maintenance

### View logs

```bash
docker compose logs -f mcp        # MCP server logs (auth type, tool calls)
docker compose logs -f nginx      # Nginx access/error logs
```

### Update the MCP server

```bash
git pull
docker compose up -d --build
```

### Renew the self-signed certificate (after 365 days)

```bash
./nginx/generate-certs.sh
docker compose restart nginx
```

### Stop the services

```bash
docker compose down
```

---

## Troubleshooting

### 401 Unauthorized
- Verify that the `Authorization: Bearer <key>` header value exactly matches `MCP_AUTH_TOKEN` in your `.env`.
- Check logs: `docker compose logs mcp`

### /mcp connection drops immediately
- Check `proxy_read_timeout` in `nginx/nginx.conf` (set to `3600s`).
- Ensure `proxy_buffering off` is present in the `/mcp` location block (note: nginx still needs `proxy_buffering off` for Streamable HTTP just like it did for SSE).

### Certificate errors in MCP client
- The client must either accept self-signed certificates or have the certificate added to its trust store.
- Copy `nginx/certs/server.crt` to the client and add it as a trusted CA, or use `--insecure` / equivalent for testing.

### Container fails to start
- Run `docker compose logs mcp` to see the error.
- Common causes: missing required env vars (`SERVICENOW_INSTANCE_URL`, auth vars).
- Test your `.env` locally: `servicenow-mcp-http` (after `pip install -e .`).

### Port 443 already in use
- Check what is listening: `ss -tlnp | grep 443`
- Stop the conflicting service or change the Nginx port in `docker-compose.yml`.

---

## §3. PaaS deployments (Cloud Run, App Runner, Fly, Render, etc.)

Most modern PaaS platforms terminate TLS at their edge for you and route to your container's HTTP port. You don't need Nginx in your container — the platform does it.

General pattern:

1. Build the Docker image as in §1.
2. Push it to your platform's container registry (or use their build-from-source flow).
3. Set environment variables: `SERVICENOW_INSTANCE_URL`, `SERVICENOW_*` credentials, `MCP_AUTH_TOKEN`, `MCP_ALLOW_REMOTE=1`, `MCP_ALLOWED_HOSTS=<your-public-hostname>`.
4. Configure the platform to route to port `8080` and use `/health` for liveness probes (it's unauthenticated by design — see [PR #36](https://github.com/echelon-ai-labs/servicenow-mcp/pull/36)).

Specific guides for a few platforms:

- **Google Cloud Platform** — see [`docs/deploying-to-gcp.md`](docs/deploying-to-gcp.md) for the full Cloud Run recipe (Secret Manager integration, private endpoints, IAM, monitoring).
- **AWS** — see [`docs/deploying-to-aws.md`](docs/deploying-to-aws.md) for a side-by-side comparison of the six AWS targets (Bedrock AgentCore Runtime, App Runner, ECS Fargate, EKS, Lambda + LWA, EC2) with deployment recipes for each. **AgentCore Runtime is the recommended target on AWS** — AWS designed it specifically for hosting MCP servers, with native protocol support and managed OAuth 2.0 inbound auth.
- **Fly.io / Render** — set `MCP_ALLOW_REMOTE=1` in `fly.toml` / `render.yaml`, add `MCP_AUTH_TOKEN` to secrets.

### What we deliberately don't ship

We do not include platform-specific deployment files (Procfiles, `railway.json`, `render.yaml`, Cloud Run `service.yaml`, etc.). These tie the codebase to one vendor's lifecycle and tend to bit-rot. Roll your own from the env-var list in `.env.example`.
