# Deploying to AWS

AWS offers more deployment options than GCP for MCP servers because the platform's serverless and container runtimes are more fragmented. This guide ranks them by fit for our specific workload (Streamable HTTP MCP server) and covers each in detail.

## Decision matrix — which AWS target should I choose?

| Target | Fit | When to choose | What it costs you |
|---|---|---|---|
| **Bedrock AgentCore Runtime** | ⭐⭐⭐⭐⭐ Purpose-built | First choice if you're MCP-focused. AWS designed this for hosting MCP servers and agents specifically. Native OAuth, native streaming, native session affinity. | Newer service (2025), fewer Stack Overflow answers when things go wrong; ARM64 container required. |
| **App Runner** | ⭐⭐⭐⭐ Drop-in | If you want the GCP Cloud Run experience on AWS — push container, get HTTPS URL, autoscaling. Simplest non-MCP-specific option. | Less granular control than ECS/Fargate; pricing slightly higher than Fargate per-vCPU-minute. |
| **ECS on Fargate (behind ALB)** | ⭐⭐⭐⭐ Standard | If you already have ECS, want infrastructure-as-code (Terraform/CDK), need fine-grained networking control, or need to share a VPC with other workloads. | Significantly more setup than App Runner; you manage the ALB, target groups, security groups, etc. |
| **EKS (Kubernetes)** | ⭐⭐⭐ Standard | If you already have EKS and want to colocate. | Substantial operational overhead if you don't already have a cluster. |
| **Lambda + LWA + Function URL streaming** | ⭐⭐⭐ Possible | True pay-per-request scaling for stateless tool-call workloads. Cold start tradeoff. Requires session-state caveats. | Adapter setup; 20MB response cap; session-resumability requires external state store. |
| **EC2** | ⭐⭐ Last resort | Predictable monthly cost on a long-running VM. | You manage the OS, the Docker daemon, the TLS certs, the load balancer, the autoscaling — everything. Don't choose this unless you have a specific reason. |

The rest of this doc covers each option in detail.

---

## Option 1: AWS Bedrock AgentCore Runtime (recommended)

**What it is.** A purpose-built AWS managed runtime, GA in 2025, specifically for hosting MCP servers and agents. AWS designed it for exactly this use case — it's the first AWS service whose contract is the MCP protocol itself.

### Why it's the recommended choice

| AgentCore Runtime gives us | What this means in practice |
|---|---|
| **Native MCP protocol contract** at the platform level | The runtime understands `Mcp-Session-Id` headers and routes requests to the same microVM for session affinity automatically — no extra config |
| **`/mcp` endpoint contract** matches our server | Our `Mount("/mcp", ...)` path is exactly what AgentCore expects. Zero application changes. |
| **Native Streamable HTTP** (both stateless and stateful modes since March 2026) | Stateless mode is the recommended default and works out-of-the-box with our `StreamableHTTPSessionManager`. Stateful mode (for elicitation/sampling/progress notifications) is also supported. |
| **OAuth 2.0 inbound auth managed by AWS** | AgentCore handles the OAuth Resource Server side natively (Auth0, Cognito, any OAuth IdP). Returns RFC 7235-compliant 401 with `WWW-Authenticate: Bearer resource_metadata=...` per the MCP authorization spec. This is the Phase 10 north-bound OAuth 2.1 work *for free*. |
| **Long-lived invocations** | Up to 8 hours per `InvokeAgentRuntime` call (vs Lambda's 15-minute hard cap) |
| **Pay-per-invocation pricing** | No idle cost; bills per active invocation second |
| **Available in 14 AWS regions** | Including all major US, EU, and APAC regions |

The downside: it's newer. ARM64 container required (your image must be `linux/arm64`); fewer community resources than App Runner or Fargate; the `agentcore` CLI is the canonical deployment tool and is npm-distributed (`@aws/agentcore`).

### Container compatibility check

AgentCore's protocol contract requires:

| Requirement | Our server's status |
|---|---|
| Listen on `0.0.0.0:8000` | ✅ We default to `127.0.0.1:8080` but `--host 0.0.0.0 --port 8000 --allow-remote` reconfigures cleanly |
| `/mcp` POST endpoint | ✅ Already there from Phase 7 |
| Streamable HTTP transport | ✅ Phase 7 |
| Stateless mode (`stateless_http=True`) recommended | ⚠️ Our `StreamableHTTPSessionManager` is configured with `json_response=False` (SSE-style streaming). May need to verify behavior in stateless mode; likely a no-op since AgentCore injects `Mcp-Session-Id` headers automatically. |
| Accept platform-injected `Mcp-Session-Id` header | ✅ Pass-through; the official MCP SDK respects it |
| ARM64 container | ⚠️ Our current image is `linux/amd64`. Need to add `--platform linux/arm64` to the Dockerfile build (or use buildx multi-arch). |

### Deployment recipe

#### Step 1: Build an ARM64 image

```bash
# From the repo root
docker buildx build --platform linux/arm64 -t servicenow-mcp:arm64-0.7.0 .
```

#### Step 2: Push to ECR

```bash
# Create ECR repo
aws ecr create-repository --repository-name servicenow-mcp --region us-west-2

# Authenticate Docker
aws ecr get-login-password --region us-west-2 | \
  docker login --username AWS --password-stdin \
    $(aws sts get-caller-identity --query Account --output text).dkr.ecr.us-west-2.amazonaws.com

# Tag and push
ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
docker tag servicenow-mcp:arm64-0.7.0 \
  $ACCOUNT.dkr.ecr.us-west-2.amazonaws.com/servicenow-mcp:arm64-0.7.0
docker push $ACCOUNT.dkr.ecr.us-west-2.amazonaws.com/servicenow-mcp:arm64-0.7.0
```

#### Step 3: Configure AgentCore project

Install the AgentCore CLI:

```bash
npm install -g @aws/agentcore
```

In a working directory:

```bash
agentcore create --protocol MCP
```

When prompted, point the entrypoint at our existing console script:

```yaml
# agentcore/agentcore.json
{
  "protocol": "MCP",
  "container_image": "<ACCOUNT>.dkr.ecr.us-west-2.amazonaws.com/servicenow-mcp:arm64-0.7.0",
  "command": ["servicenow-mcp-http"],
  "args": ["--host", "0.0.0.0", "--port", "8000", "--allow-remote"],
  "environment": {
    "MCP_ALLOW_REMOTE": "1",
    "SERVICENOW_INSTANCE_URL": "https://your-instance.service-now.com"
  },
  "secrets": {
    "MCP_AUTH_TOKEN": "arn:aws:secretsmanager:us-west-2:ACCOUNT:secret:servicenow-mcp-auth-token-XXXXXX",
    "SERVICENOW_USERNAME": "arn:aws:secretsmanager:us-west-2:ACCOUNT:secret:servicenow-username-XXXXXX",
    "SERVICENOW_PASSWORD": "arn:aws:secretsmanager:us-west-2:ACCOUNT:secret:servicenow-password-XXXXXX"
  }
}
```

#### Step 4: Set up Cognito (or Auth0) for inbound OAuth

AgentCore Runtime requires OAuth 2.0 for invocations. The setup script from the AgentCore docs creates a Cognito user pool:

```bash
export REGION=us-west-2
export USERNAME=mcp-test-user
export PASSWORD='YourSecurePassword123!'
source setup_cognito.sh   # from the AgentCore docs
# Outputs: POOL_ID, CLIENT_ID, BEARER_TOKEN
```

This gives you a Cognito user pool whose tokens AgentCore Runtime will accept.

#### Step 5: Deploy

```bash
agentcore deploy
```

The CLI packages the project, uploads to S3, creates the AgentCore runtime, and prints an ARN:

```
arn:aws:bedrock-agentcore:us-west-2:ACCOUNT:runtime/servicenow-mcp-xyz123
```

#### Step 6: Invoke

The Cognito bearer token is what MCP clients now present. The endpoint URL is:

```
https://bedrock-agentcore.us-west-2.amazonaws.com/runtimes/<URL_ENCODED_ARN>/invocations?qualifier=DEFAULT
```

Standard MCP Python SDK pattern:

```python
import asyncio
import os
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

async def main():
    agent_arn = os.environ["AGENT_ARN"]
    bearer = os.environ["BEARER_TOKEN"]
    encoded_arn = agent_arn.replace(":", "%3A").replace("/", "%2F")
    url = f"https://bedrock-agentcore.us-west-2.amazonaws.com/runtimes/{encoded_arn}/invocations?qualifier=DEFAULT"

    async with streamablehttp_client(
        url,
        headers={"Authorization": f"Bearer {bearer}"},
        timeout=120,
    ) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            print(await session.list_tools())

asyncio.run(main())
```

You're done — agents can now invoke the deployed server with full MCP protocol semantics.

### What our SecurityMiddleware does on AgentCore

Note that **AgentCore's OAuth handles the inbound auth at the platform level**, *before* the request reaches our container. Our `SecurityMiddleware` still runs and provides defense-in-depth:

- The `MCP_AUTH_TOKEN` bearer gate is now redundant with AgentCore's OAuth — but harmless. You can disable it by leaving `MCP_AUTH_TOKEN` unset and binding to loopback only (which then fails because we require a token for non-loopback). Practical answer: keep `MCP_AUTH_TOKEN` set to a random value and use it as defense-in-depth.
- The Host allowlist needs the AgentCore-injected internal hostname. Set `MCP_ALLOWED_HOSTS=*.bedrock-agentcore.amazonaws.com` (or whatever AgentCore uses internally — this should be confirmed during testing).
- The Origin allowlist still applies for browser-originated requests.
- `/health` bypass still works for liveness probes.

### Stateful vs stateless mode

Our `StreamableHTTPSessionManager` was configured with `json_response=False` (SSE-style streaming responses by default). For AgentCore stateless mode, this is fine — AgentCore handles session-affinity via `Mcp-Session-Id` injection. For AgentCore stateful mode (only needed if you use elicitation, sampling, or progress notifications), you'd want to verify the `StreamableHTTPSessionManager` is in stateful configuration (this is the default behavior; `stateless_http=True` is a separate flag in FastMCP that we'd port if needed).

Most ServiceNow tool-call workloads are stateless — agent issues a tool call, gets a result, done. **Default to stateless mode** unless you specifically need multi-turn elicitation.

### When to choose AgentCore Runtime

✅ **Choose it if:** This is a greenfield AWS deployment focused on MCP, you want OAuth 2.1 inbound managed by AWS, you want session affinity managed by the platform, you're comfortable with a 2025-era service.

❌ **Don't choose it if:** Your security team requires services to be GA for ≥2 years, you have an existing Fargate/EKS estate this should fit into, you want maximum vendor-neutrality (your container could move to GCP/Azure trivially otherwise).

**References:**
- [Deploy MCP servers in AgentCore Runtime](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-mcp.html)
- [MCP protocol contract](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-mcp-protocol-contract.html)
- [AgentCore Runtime stateful MCP announcement (March 2026)](https://aws.amazon.com/about-aws/whats-new/2026/03/amazon-bedrock-agentcore-runtime-stateful-mcp/)

---

## Option 2: AWS App Runner

**What it is.** AWS's "push-a-container, get-an-HTTPS-URL" managed service — the closest analog to GCP Cloud Run.

### Why it's a strong second choice

- **Drop-in compatible** with our existing Docker image (no ARM64 requirement, no protocol contract to satisfy beyond standard HTTP).
- **Native HTTPS termination** at the App Runner edge (no nginx).
- **Autoscaling** based on concurrent requests, scales to a configurable minimum (not zero — App Runner keeps at least one provisioned instance, which costs ~$8/month at 0.25 vCPU / 0.5GB).
- **Native ECR integration** with auto-deploy on image push.
- **VPC connector** for outbound access to private ServiceNow instances.

### Deployment recipe

#### Step 1: Push to ECR

```bash
aws ecr create-repository --repository-name servicenow-mcp --region us-west-2

ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
aws ecr get-login-password --region us-west-2 | \
  docker login --username AWS --password-stdin $ACCOUNT.dkr.ecr.us-west-2.amazonaws.com

docker tag ghcr.io/shadnygren/servicenow-mcp:0.7.0 \
  $ACCOUNT.dkr.ecr.us-west-2.amazonaws.com/servicenow-mcp:0.7.0
docker push $ACCOUNT.dkr.ecr.us-west-2.amazonaws.com/servicenow-mcp:0.7.0
```

#### Step 2: Create the App Runner service

```bash
aws apprunner create-service \
  --service-name servicenow-mcp \
  --source-configuration '{
    "ImageRepository": {
      "ImageIdentifier": "'$ACCOUNT'.dkr.ecr.us-west-2.amazonaws.com/servicenow-mcp:0.7.0",
      "ImageRepositoryType": "ECR",
      "ImageConfiguration": {
        "Port": "8080",
        "RuntimeEnvironmentVariables": {
          "MCP_ALLOW_REMOTE": "1",
          "SERVICENOW_INSTANCE_URL": "https://your-instance.service-now.com"
        },
        "RuntimeEnvironmentSecrets": {
          "MCP_AUTH_TOKEN": "arn:aws:secretsmanager:us-west-2:'$ACCOUNT':secret:servicenow-mcp-auth-token",
          "SERVICENOW_USERNAME": "arn:aws:secretsmanager:us-west-2:'$ACCOUNT':secret:servicenow-username",
          "SERVICENOW_PASSWORD": "arn:aws:secretsmanager:us-west-2:'$ACCOUNT':secret:servicenow-password"
        }
      }
    },
    "AutoDeploymentsEnabled": true
  }' \
  --instance-configuration '{"Cpu": "0.25 vCPU", "Memory": "0.5 GB"}' \
  --health-check-configuration '{"Protocol": "HTTP", "Path": "/health", "Interval": 10}'
```

App Runner returns a public URL like `https://abcdef.us-west-2.awsapprunner.com`. Same `/mcp` and `/health` path semantics as Cloud Run.

#### Step 3: For private endpoint — VPC connector + private endpoint

```bash
# Create a VPC connector for App Runner to reach private resources
aws apprunner create-vpc-connector \
  --vpc-connector-name servicenow-mcp-vpc \
  --subnets subnet-aaa subnet-bbb \
  --security-groups sg-xxx

# Update the service to use it
aws apprunner update-service \
  --service-arn arn:aws:apprunner:... \
  --network-configuration '{
    "EgressConfiguration": {
      "EgressType": "VPC",
      "VpcConnectorArn": "arn:aws:apprunner:...:vpcconnector/..."
    }
  }'
```

For a *private* App Runner URL (only reachable from within VPC), use VPC ingress (introduced in 2024).

### When to choose App Runner

✅ **Choose it if:** You want the simplest container deploy on AWS, you're not committing to AgentCore Runtime, you don't need the AgentCore native MCP features.

❌ **Don't choose it if:** You need strict pay-per-request scaling (App Runner has a minimum provisioned instance), you need fine-grained ALB/network control (use Fargate instead).

---

## Option 3: ECS on Fargate (behind an ALB)

**What it is.** Standard AWS managed-container option — Fargate runs your image, ALB terminates TLS and routes traffic, target groups link them.

### Deployment recipe (Terraform-style outline)

```hcl
resource "aws_ecs_cluster" "servicenow_mcp" {
  name = "servicenow-mcp"
}

resource "aws_ecs_task_definition" "servicenow_mcp" {
  family                   = "servicenow-mcp"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = "256"
  memory                   = "512"
  execution_role_arn       = aws_iam_role.task_execution.arn

  container_definitions = jsonencode([{
    name      = "servicenow-mcp"
    image     = "${aws_ecr_repository.servicenow_mcp.repository_url}:0.7.0"
    portMappings = [{ containerPort = 8080, protocol = "tcp" }]
    environment = [
      { name = "MCP_ALLOW_REMOTE",        value = "1" },
      { name = "SERVICENOW_INSTANCE_URL", value = "https://your-instance.service-now.com" },
    ]
    secrets = [
      { name = "MCP_AUTH_TOKEN",        valueFrom = aws_secretsmanager_secret.auth_token.arn },
      { name = "SERVICENOW_USERNAME",   valueFrom = aws_secretsmanager_secret.username.arn },
      { name = "SERVICENOW_PASSWORD",   valueFrom = aws_secretsmanager_secret.password.arn },
    ]
    healthCheck = {
      command = ["CMD-SHELL", "curl -f http://localhost:8080/health || exit 1"]
      interval = 30
    }
  }])
}

resource "aws_lb" "servicenow_mcp" {
  # Application Load Balancer — terminates TLS, supports HTTP/2 + chunked streaming
  load_balancer_type = "application"
  # ... subnets, security groups, etc.
}

resource "aws_lb_target_group" "servicenow_mcp" {
  port        = 8080
  protocol    = "HTTP"
  target_type = "ip"
  health_check {
    path = "/health"
    matcher = "200"
  }
}

resource "aws_ecs_service" "servicenow_mcp" {
  cluster         = aws_ecs_cluster.servicenow_mcp.id
  task_definition = aws_ecs_task_definition.servicenow_mcp.arn
  desired_count   = 2
  launch_type     = "FARGATE"

  load_balancer {
    target_group_arn = aws_lb_target_group.servicenow_mcp.arn
    container_name   = "servicenow-mcp"
    container_port   = 8080
  }
}
```

### A note on ALB vs streaming responses

Application Load Balancers handle **HTTP/2 chunked streaming responses** correctly and forward them unbuffered to the client. This was historically a concern with some older AWS load balancers, but ALB is the right choice. **Don't use Network Load Balancer (NLB)** for this — NLB is layer 4 only and doesn't terminate HTTP, so TLS would have to terminate in your container (defeating the point of a managed service).

Make sure the ALB listener is HTTPS with a valid ACM cert. The target group can be HTTP (since traffic between ALB and Fargate is on the AWS internal network).

### When to choose Fargate

✅ **Choose it if:** You already have ECS infrastructure, you need Terraform/CDK control, you need to colocate in a specific VPC, you want to share security groups / IAM patterns with other ECS workloads.

❌ **Don't choose it if:** This is your first AWS container deployment (App Runner is dramatically simpler), or you specifically want MCP-aware infrastructure (use AgentCore).

---

## Option 4: Lambda + Lambda Web Adapter + Function URL streaming

**What it is.** Run our Streamable HTTP server inside Lambda, using the [Lambda Web Adapter (LWA)](https://github.com/aws/aws-lambda-web-adapter) to bridge between Lambda's invocation model and our HTTP-server expectations. Use Lambda Function URLs in `RESPONSE_STREAM` mode to get streaming responses back.

This works, but with caveats. Read this section carefully before choosing it.

### What works

| Capability | How |
|---|---|
| Container deployment | Lambda supports container images up to 10GB via ECR; LWA is a small extension layer added to the image |
| HTTP server compatibility | LWA proxies Lambda's invocation events into HTTP requests to your container's port, so our Starlette app runs unchanged |
| Streaming responses | Function URLs with `InvokeMode: RESPONSE_STREAM` + `AWS_LWA_INVOKE_MODE=RESPONSE_STREAM` env var lets responses stream back |
| Per-request pay-per-use | Lambda's standard pricing model — pay only for invocation time |
| 15-minute max execution | Hard cap; longer than most MCP tool calls but shorter than long-lived sessions |

### What doesn't work cleanly

1. **Session state across invocations.** Our `InMemoryEventStore` is per-process. Lambda's invocation model means:
   - **Stateless tool calls** (single request → response): work fine.
   - **Long-lived sessions with resumability via `Last-Event-ID`**: the event store doesn't survive cold starts or scaling events. You'd need a `RedisEventStore` (ElastiCache) or `DynamoDBEventStore` swap-in. Not currently shipped — would be Phase 10+ work.
2. **20MB response cap.** Lambda's response streaming has a 20MB soft limit per invocation. Most MCP tool responses are well under this; very large `list_*` operations might exceed it.
3. **Cold start latency.** A few-hundred-MB Python container takes 1–3 seconds to cold-start. Use **provisioned concurrency** to pre-warm if cold starts are unacceptable, but this defeats the pay-per-request model.

### Deployment recipe

#### Step 1: Modify the Dockerfile to bundle LWA

Append to the existing `Dockerfile`:

```dockerfile
# Add Lambda Web Adapter as an extension layer
COPY --from=public.ecr.aws/awsguru/aws-lambda-adapter:0.8.4 /lambda-adapter /opt/extensions/lambda-adapter

# LWA configuration for response streaming
ENV AWS_LWA_INVOKE_MODE=RESPONSE_STREAM
ENV AWS_LWA_PORT=8080
ENV AWS_LWA_READINESS_CHECK_PATH=/health
```

LWA reads `AWS_LWA_PORT` to know where to forward requests to your app. `AWS_LWA_READINESS_CHECK_PATH` makes LWA poll `/health` until the app is ready before accepting requests.

#### Step 2: Build, tag, push to ECR

Same as the AgentCore / App Runner recipe — `docker build`, `docker tag`, `docker push` to ECR.

#### Step 3: Create the Lambda function

```bash
aws lambda create-function \
  --function-name servicenow-mcp \
  --package-type Image \
  --code ImageUri=$ACCOUNT.dkr.ecr.us-west-2.amazonaws.com/servicenow-mcp:0.7.0 \
  --role arn:aws:iam::$ACCOUNT:role/servicenow-mcp-execution \
  --memory-size 1024 \
  --timeout 900 \
  --environment 'Variables={MCP_ALLOW_REMOTE=1,SERVICENOW_INSTANCE_URL=https://your-instance.service-now.com}' \
  --architectures x86_64
```

#### Step 4: Wire up secrets via Secrets Manager

```bash
aws lambda update-function-configuration \
  --function-name servicenow-mcp \
  --environment 'Variables={
    MCP_ALLOW_REMOTE=1,
    SERVICENOW_INSTANCE_URL=https://your-instance.service-now.com
  }'

# Use Lambda's built-in Secrets Manager integration
# (You'd typically inject these via IAM and SDK calls inside the container,
#  or use the Lambda Powertools secrets parameter store extension)
```

#### Step 5: Create a Function URL with streaming

```bash
aws lambda create-function-url-config \
  --function-name servicenow-mcp \
  --auth-type NONE \
  --invoke-mode RESPONSE_STREAM
```

`AuthType: NONE` is fine because our `SecurityMiddleware` enforces the bearer-token gate at the application layer. Alternatively, use `AuthType: AWS_IAM` for IAM-gated access (you'd then use SigV4-signed requests).

The Function URL response includes a public URL like `https://abc123.lambda-url.us-west-2.on.aws/`.

### When to choose Lambda

✅ **Choose it if:** Your usage is sporadic and stateless (single tool calls, no long sessions), you specifically want pay-per-request scaling to zero, you can tolerate 1–3 second cold starts.

❌ **Don't choose it if:** You need session resumability (use AgentCore or Cloud Run), responses might exceed 20MB, you can't tolerate cold starts (unless paying for provisioned concurrency), or you want simpler infrastructure (App Runner is dramatically simpler).

**References:**
- [LWA + FastAPI response streaming example](https://github.com/aws/aws-lambda-web-adapter/blob/main/examples/fastapi-response-streaming/README.md)
- [AWS Lambda response streaming announcement (April 2026, all regions)](https://aws.amazon.com/about-aws/whats-new/2026/04/aws-lambda-response-streaming/)

---

## Option 5: EKS (Kubernetes)

**What it is.** Self-managed-ish Kubernetes — same Helm chart pattern as any other workload.

If you have an existing EKS cluster, deploy with a standard `Deployment` + `Service` + `Ingress` set:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: servicenow-mcp
spec:
  replicas: 2
  template:
    spec:
      containers:
        - name: servicenow-mcp
          image: ghcr.io/shadnygren/servicenow-mcp:0.7.0
          ports:
            - containerPort: 8080
          envFrom:
            - secretRef: { name: servicenow-mcp-secrets }
            - configMapRef: { name: servicenow-mcp-config }
          livenessProbe:
            httpGet: { path: /health, port: 8080 }
          readinessProbe:
            httpGet: { path: /health, port: 8080 }
```

Use AWS Load Balancer Controller for the Ingress to get an ALB (same streaming-friendly recommendation as the Fargate section). Use AWS Secrets Manager CSI driver to mount secrets as env vars.

### When to choose EKS

✅ **Choose it if:** You already have EKS, want to colocate this MCP with other workloads, want the cluster's existing observability/networking/policy stack to apply.

❌ **Don't choose it if:** This is the only thing you'd run on Kubernetes — the operational overhead far exceeds the benefit.

---

## Option 6: EC2 (last resort)

A long-running EC2 VM with Docker + nginx + Let's Encrypt is the lowest-tech option. Predictable monthly cost, but you manage everything: OS patching, Docker daemon, TLS certificate renewal, log rotation, autoscaling (which doesn't exist).

The Phase 6 `docker-compose.yml` with the `with-nginx` profile is exactly this pattern:

```bash
# On the EC2 host
docker compose --profile with-nginx up -d
```

Practical only if you have a specific reason to avoid managed services (regulatory? cost-predictability for very low traffic?). Almost always worse than App Runner or Cloud Run on cost AND reliability.

---

## Cross-cutting AWS notes

### Secrets management

For all options above except EC2, use **AWS Secrets Manager** rather than env vars in plain config:

```bash
aws secretsmanager create-secret \
  --name servicenow-mcp-auth-token \
  --secret-string "$(openssl rand -hex 32)"

aws secretsmanager create-secret \
  --name servicenow-username \
  --secret-string "mcp-svc"

aws secretsmanager create-secret \
  --name servicenow-password \
  --secret-string "your-password"
```

Each AWS compute service has its own way of injecting Secrets Manager secrets as env vars at runtime — this is documented per-option above.

### IAM least privilege

The execution role / task role / function role for the MCP server needs:

- `secretsmanager:GetSecretValue` on the specific secret ARNs (not `*`)
- `logs:CreateLogStream`, `logs:PutLogEvents` for CloudWatch Logs
- For App Runner / Fargate: `ecr:GetDownloadUrlForLayer`, `ecr:BatchGetImage` etc. on the specific repo
- For private ServiceNow instances reached via VPC: VPC + security group permissions
- **Nothing else.** Specifically: no `secretsmanager:*`, no `s3:*`, no `dynamodb:*` unless you've added Phase 10+ session storage.

### CloudWatch dashboards / alarms

Whichever runtime you pick, set CloudWatch alarms on:

- HTTP 401 / 421 / 403 responses from `SecurityMiddleware` (auth/Host/Origin failures — leading indicator of misconfiguration or attack)
- HTTP 5xx responses (server errors)
- Container/Lambda restart count (instability indicator)
- For Lambda: `Throttles`, `Duration p99`, `IteratorAge` if using event sources

### Multi-region

If you need to run this in multiple AWS regions (for latency or DR), all five managed options (AgentCore, App Runner, Fargate, Lambda, EKS) support per-region deployment with per-region ECR repos. There's no shared session state across regions in our current implementation, so each regional deployment is independent.

### Outbound to ServiceNow

ServiceNow's REST API is reached over the public internet from AWS. All options above support outbound HTTPS by default. If your ServiceNow instance is on a private VPN/peering connection (some enterprise customers), use the appropriate AWS networking primitive:

- **VPC Connector** for App Runner
- **VPC subnet attachment** for Fargate / EKS / Lambda
- **VPC for AgentCore Runtime** — supported via the AgentCore VPC integration (ARN-scoped)

---

## End-to-end checklist (pick your option)

For **AgentCore Runtime**:
- [ ] ARM64 image built (`docker buildx build --platform linux/arm64`)
- [ ] Pushed to ECR
- [ ] `agentcore` CLI installed (`npm install -g @aws/agentcore`)
- [ ] Cognito user pool created (or other OAuth IdP configured)
- [ ] `agentcore.json` references the image and entrypoint
- [ ] `agentcore deploy` succeeded; ARN captured
- [ ] Test invocation succeeds with bearer token

For **App Runner**:
- [ ] Image in ECR
- [ ] Secrets Manager secrets created (auth_token, ServiceNow creds)
- [ ] App Runner service created with `--health-check-configuration` pointing at `/health`
- [ ] `MCP_ALLOWED_HOSTS=<service-id>.<region>.awsapprunner.com` set so Host check passes
- [ ] Test `/health` and `/mcp` endpoints

For **Fargate**:
- [ ] ECS cluster / task definition / service / ALB / target group all wired up (Terraform/CDK recommended)
- [ ] ALB listener: HTTPS with ACM cert
- [ ] Health check: `GET /health` returns 200
- [ ] `MCP_ALLOWED_HOSTS` includes your ALB domain
- [ ] Security group allows inbound 443 from your CIDR / from internet, outbound 443 to ServiceNow

For **Lambda + LWA**:
- [ ] LWA layer baked into Dockerfile
- [ ] `AWS_LWA_INVOKE_MODE=RESPONSE_STREAM` env var set
- [ ] Function URL with `InvokeMode: RESPONSE_STREAM`
- [ ] Memory ≥1024MB (Python container needs headroom)
- [ ] Timeout 900s (15-min max)
- [ ] Provisioned concurrency configured if cold starts are unacceptable
- [ ] Acknowledged the session-resumability limitation

For **all options**:
- [ ] `MCP_ALLOW_REMOTE=1` and `MCP_AUTH_TOKEN` both set
- [ ] CloudWatch alarms on auth-failure rates
- [ ] Tested: `/health` returns 200, `/mcp` returns 401 without bearer, `/mcp` returns 200 with valid bearer
- [ ] Tested: a real MCP client (Claude Desktop, MCP Inspector, or our own Python client) can list tools and invoke at least one ServiceNow operation end-to-end
