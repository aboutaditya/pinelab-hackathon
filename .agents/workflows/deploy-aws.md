---
description: How to build and push containers to AWS ECR
---

# AWS ECR Deployment Flow

This workflow guides you through building and pushing the three core services to AWS Elastic Container Registry (ECR).

## Prerequisites
- AWS CLI installed and configured.
- Docker running.
- ECR Repositories created for `ai-agent`, `mcp`, and `backend`.

## Steps

### 1. Set Environment Variables
Set your AWS Account ID and preferred Region.

```bash
export AWS_ACCOUNT_ID=YOUR_ACCOUNT_ID
export AWS_REGION=us-east-1
```

### 2. Login to ECR
Authenticate your Docker client to the ECR registry.

```bash
aws ecr get-login-password --region $AWS_REGION | docker login --username AWS --password-stdin $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com
```

### 3. Build & Tag Images
Build individual images using Docker Compose and tag them for ECR.

```bash
# Build all services
docker compose build

# Tag services for ECR
docker tag pine-labs-reconciliation-ai-agent:latest $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/pine-labs-reconciliation-ai-agent:latest
docker tag pine-labs-reconciliation-mcp:latest $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/pine-labs-reconciliation-mcp:latest
docker tag pine-labs-reconciliation-backend:latest $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/pine-labs-reconciliation-backend:latest
```

### 4. Push to ECR
Push the tagged images to your AWS repositories.

```bash
docker push $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/pine-labs-reconciliation-ai-agent:latest
docker push $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/pine-labs-reconciliation-mcp:latest
docker push $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/pine-labs-reconciliation-backend:latest
```

### 5. Deployment Note
After pushing, you can use these images in AWS ECS (Fargate) or EKS. Ensure your execution environment has the following environment variables set:
- `AWS_ACCESS_KEY_ID`
- `AWS_SECRET_ACCESS_KEY`
- `AWS_DEFAULT_REGION`
- `DATABASE_URL` (pointing to your RDS instance)
- `REDIS_URL` (pointing to your ElastiCache instance)
