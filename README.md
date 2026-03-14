# Pine Labs Autonomous Reconciliation Agent

A YAML-driven, multi-agent settlement reconciliation system built with **FastAPI**, **Django**, and the **Model Context Protocol (MCP)**.

## Architecture

```
┌───────────────┐     ┌───────────────┐     ┌───────────────┐
│  AI Agent     │────▶│  MCP          │────▶│ Django Backend │
│  (FastAPI)    │     │  (FastMCP)    │     │  (DRF + PG)   │
│  :8000        │     │  :8001        │     │  :8002         │
└──────┬────────┘     └───────────────┘     └───────────────┘
       │
       ▼
   ┌────────┐
   │ Redis  │  (Conversation State)
   │ :6379  │
   └────────┘
```

## Quick Start

### 1. Clone & Configure

```bash
cp .env.example .env
# Edit .env — add your GOOGLE_API_KEY
```

### 2. Launch with Docker Compose

```bash
docker compose up --build
```

### 3. Interact with the Reconciliation Agent

```bash
# Start a conversation
curl -X POST http://localhost:8000/chat/v1/reconciliation \
  -H "Content-Type: application/json" \
  -d '{"message": "Check the last payout", "merchant_id": "M001", "parent_id": null}'

# Follow up (use the message_id from the previous response)
curl -X POST http://localhost:8000/chat/v1/reconciliation \
  -H "Content-Type: application/json" \
  -d '{"message": "What about the GST breakdown?", "merchant_id": "M001", "parent_id": "abc-123"}'
```

### 4. Direct API Access (Django Backend)

```bash
# Health check
curl http://localhost:8002/api/v1/transactions/health/

# Get fee profile for a merchant
curl http://localhost:8002/api/v1/transactions/fee-profile/M001/

# Get transactions for a settlement
curl http://localhost:8002/api/v1/transactions/settlement/STL001/

# List all reconciliation issues
curl http://localhost:8002/api/v1/transactions/issues/
```

## Services

| Service         | Port | Description                              |
|-----------------|------|------------------------------------------|
| AI Agent        | 8000 | FastAPI + LangGraph multi-agent brain    |
| MCP             | 8001 | YAML-driven tool proxy for LLM          |
| Django Backend  | 8002 | Transaction data & REST API              |
| Redis           | 6379 | Conversation state (message ID chain)    |
| PostgreSQL      | 5432 | Persistent transaction data              |

## Agent Configuration

Agents are defined in `ai-agent/agents/*.yml`. The reconciliation agent:

1. Fetches the Merchant Fee Profile for MDR/GST rules
2. Fetches Transactions for the specific settlement
3. Calculates expected payout: `(Amount × MDR) + GST`
4. Flags discrepancies and creates reconciliation tickets

## AWS ECR Deployment

Each service has its own `Dockerfile` optimized for production:

```bash
# Build and tag for ECR
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin <ACCOUNT>.dkr.ecr.us-east-1.amazonaws.com

docker compose build

# Tag and push each service
for svc in ai-agent mcp backend; do
  docker tag pine-labs-reconciliation-$svc:latest <ACCOUNT>.dkr.ecr.us-east-1.amazonaws.com/pine-labs-$svc:latest
  docker push <ACCOUNT>.dkr.ecr.us-east-1.amazonaws.com/pine-labs-$svc:latest
done
```

## Development

```bash
# Run individual services
docker compose up backend     # Django only
docker compose up mcp  # MCP only
docker compose up ai-agent # AI Agent only

# Run tests
docker compose exec backend python manage.py test
docker compose exec ai-agent pytest
```

## License

MIT
