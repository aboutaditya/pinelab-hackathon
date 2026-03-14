#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Pine Labs Reconciliation Agent — AWS Copilot Deploy (Redis, Postgres, backend, ai-agent, mcp)
#
# Usage:
#   ./deploy.sh                    # full deploy: app init, env, all services
#   ./deploy.sh --env prod         # deploy to prod (default)
#
# Requires: AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_DEFAULT_REGION
# Optional: AWS_SESSION_TOKEN (STS/SSO), AWS_ACCOUNT_ID (auto-detected)
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

info()    { echo -e "${CYAN}[INFO]${NC}  $*"; }
success() { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*" >&2; exit 1; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/.env"
COPILOT_APP_NAME="pinelabs-project"
COPILOT_ENV_NAME="${COPILOT_ENV_NAME:-prod}"

# ── Parse args ────────────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --env) COPILOT_ENV_NAME="$2"; shift 2 ;;
    -h|--help)
      head -20 "$0" | grep '^#' | sed 's/^# \?//'
      exit 0 ;;
    *) error "Unknown option: $1" ;;
  esac
done

# ── Load .env ─────────────────────────────────────────────────────────────────
if [[ -f "$ENV_FILE" ]]; then
  info "Loading ${ENV_FILE}"
  set -o allexport
  # shellcheck disable=SC1090
  source <(grep -v '^#' "$ENV_FILE" | grep -v '^\s*$')
  set +o allexport
else
  warn ".env not found; using exported env vars."
fi

# ── AWS credentials ───────────────────────────────────────────────────────────
: "${AWS_ACCESS_KEY_ID:?'Set AWS_ACCESS_KEY_ID in .env or environment'}"
: "${AWS_SECRET_ACCESS_KEY:?'Set AWS_SECRET_ACCESS_KEY in .env or environment'}"
: "${AWS_DEFAULT_REGION:?'Set AWS_DEFAULT_REGION in .env or environment'}"

export AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_DEFAULT_REGION
[[ -n "${AWS_SESSION_TOKEN:-}" ]] && export AWS_SESSION_TOKEN

if [[ -z "${AWS_ACCOUNT_ID:-}" ]]; then
  info "Resolving AWS_ACCOUNT_ID..."
  AWS_ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
fi
export AWS_ACCOUNT_ID

cd "$SCRIPT_DIR"

echo ""
echo -e "${BOLD}═══════════════════════════════════════════════════════${NC}"
echo -e "${BOLD}  Pine Labs — Copilot Deploy (redis, postgres, mcp, ai-agent, backend)${NC}"
echo -e "${BOLD}═══════════════════════════════════════════════════════${NC}"
info "App: ${COPILOT_APP_NAME}  Env: ${COPILOT_ENV_NAME}  Region: ${AWS_DEFAULT_REGION}"
echo ""

# ── Install Copilot CLI if missing ────────────────────────────────────────────
if ! command -v copilot &>/dev/null; then
  info "Installing AWS Copilot CLI..."
  COPILOT_VERSION="v1.32.0"
  CASE="$(uname -s)"
  if [[ "$CASE" == "Darwin" ]]; then
    COPILOT_OS="darwin"
  else
    COPILOT_OS="linux"
  fi
  COPILOT_URL="https://github.com/aws/copilot-cli/releases/download/${COPILOT_VERSION}/copilot-${COPILOT_OS}-amd64"
  curl -sSLo /tmp/copilot "$COPILOT_URL" && chmod +x /tmp/copilot
  if [[ "$CASE" == "Darwin" ]]; then
    sudo mv /tmp/copilot /usr/local/bin/copilot
  else
    sudo mv /tmp/copilot /usr/local/bin/copilot
  fi
  success "Copilot installed."
fi

# ── App init ──────────────────────────────────────────────────────────────────
if ! copilot app show --name "$COPILOT_APP_NAME" &>/dev/null; then
  info "Initializing Copilot app: ${COPILOT_APP_NAME}"
  copilot app init "$COPILOT_APP_NAME"
  success "App initialized."
else
  info "App ${COPILOT_APP_NAME} already exists."
fi

# ── Register services with app (required for first-time deploy) ───────────────
# Copilot tracks services in AWS SSM; local manifests alone are not enough.
info "Ensuring services are registered with app..."
BACKUP_DIR=""
if [[ -f copilot/redis/manifest.yml ]]; then
  BACKUP_DIR="$(mktemp -d)"
  for svc in redis postgres mcp ai-agent backend; do
    [[ -f "copilot/${svc}/manifest.yml" ]] && cp "copilot/${svc}/manifest.yml" "$BACKUP_DIR/${svc}.yml"
  done
fi

_init_svc() {
  local name="$1" type="$2" port="$3" extra="$4"
  if copilot svc show --name "$name" &>/dev/null; then
    return 0
  fi
  info "Registering service: ${name}"
  # shellcheck disable=SC2086
  copilot svc init --name "$name" --svc-type "$type" --port "$port" $extra || true
}
_init_svc redis "Backend Service" 6379 "--image redis:7-alpine"
_init_svc postgres "Backend Service" 5432 "--image postgres:16-alpine"
_init_svc mcp "Backend Service" 8001 "--dockerfile ./mcp/Dockerfile"
_init_svc ai-agent "Backend Service" 8000 "--dockerfile ./ai-agent/Dockerfile"
_init_svc backend "Load Balanced Web Service" 8002 "--dockerfile ./backend_django/Dockerfile"

if [[ -n "$BACKUP_DIR" && -d "$BACKUP_DIR" ]]; then
  for svc in redis postgres mcp ai-agent backend; do
    [[ -f "$BACKUP_DIR/${svc}.yml" ]] && cp "$BACKUP_DIR/${svc}.yml" "copilot/${svc}/manifest.yml"
  done
  rm -rf "$BACKUP_DIR"
fi
success "Services registered."
echo ""

# ── Env init (idempotent) ─────────────────────────────────────────────────────
if ! copilot env show --name "$COPILOT_ENV_NAME" &>/dev/null; then
  info "Creating environment: ${COPILOT_ENV_NAME}"
  copilot env init --name "$COPILOT_ENV_NAME" --app "$COPILOT_APP_NAME" --default-config --region "$AWS_DEFAULT_REGION"
  success "Env initialized."
else
  info "Environment ${COPILOT_ENV_NAME} already exists."
fi

# ── Env deploy ───────────────────────────────────────────────────────────────
info "Deploying environment: ${COPILOT_ENV_NAME}"
copilot env deploy --name "$COPILOT_ENV_NAME"
success "Environment deployed."
echo ""

# ── Deploy services (redis, postgres first; then mcp, ai-agent, backend) ───────
info "Deploying services (redis → postgres → mcp → ai-agent → backend)..."
copilot svc deploy --name redis --env "$COPILOT_ENV_NAME"
success "Redis deployed."
copilot svc deploy --name postgres --env "$COPILOT_ENV_NAME"
success "Postgres deployed."
copilot svc deploy --name mcp --env "$COPILOT_ENV_NAME"
success "MCP deployed."
copilot svc deploy --name ai-agent --env "$COPILOT_ENV_NAME"
success "AI-Agent deployed."
copilot svc deploy --name backend --env "$COPILOT_ENV_NAME"
success "Backend deployed."
echo ""

# ── Summary ───────────────────────────────────────────────────────────────────
echo -e "${BOLD}═══════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}${BOLD}  Deployment complete${NC}"
echo -e "${BOLD}═══════════════════════════════════════════════════════${NC}"
info "Backend (public URL): run  copilot svc show -n backend -e ${COPILOT_ENV_NAME}"
info "Redis, Postgres, MCP, ai-agent are internal only (service discovery)."
echo ""
echo -e "${YELLOW}Note:${NC} Backend uses DATABASE_URL=postgres://...@postgres:5432/pinelabs. Set DJANGO_SECRET_KEY in manifest or Copilot console."
echo "      Run migrations in the backend container (or add to Dockerfile CMD) on first deploy."
echo ""
