#!/usr/bin/env bash
#####################################################################
# Project:       Juniper
# Application:   juniper-deploy
# File Name:     scripts/test_k8s.sh
# Author:        Paul Calnon
#
# Description:
#    Integration test harness for the Juniper Helm chart.
#    Creates a local Kubernetes cluster (kind or minikube), builds
#    container images, installs the chart, validates health endpoints,
#    runs helm tests, and tears down.
#
# Usage:
#    bash scripts/test_k8s.sh                 # Auto-detect kind or minikube
#    bash scripts/test_k8s.sh --driver kind   # Force kind
#    bash scripts/test_k8s.sh --driver minikube
#    bash scripts/test_k8s.sh --no-teardown   # Keep cluster after test
#
# Prerequisites:
#    - Docker
#    - kind (https://kind.sigs.k8s.io/) or minikube
#    - helm >= 3.0
#    - kubectl
#####################################################################

set -euo pipefail

# ── Configuration ──────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
CHART_DIR="$REPO_DIR/k8s/helm/juniper"
CLUSTER_NAME="${JUNIPER_K8S_TEST_CLUSTER:-juniper-test}"
NAMESPACE="${JUNIPER_K8S_TEST_NAMESPACE:-juniper}"
RELEASE_NAME="${JUNIPER_K8S_TEST_RELEASE:-juniper}"
TIMEOUT="${JUNIPER_K8S_TEST_TIMEOUT:-300}"  # seconds
DRIVER=""
TEARDOWN=true

# ── Argument parsing ──────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case $1 in
        --driver)
            DRIVER="$2"
            shift 2
            ;;
        --no-teardown)
            TEARDOWN=false
            shift
            ;;
        -h|--help)
            echo "Usage: $0 [--driver kind|minikube] [--no-teardown]"
            exit 0
            ;;
        *)
            echo "Unknown option: $1" >&2
            exit 1
            ;;
    esac
done

# ── Utilities ─────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
NC='\033[0m'

log_info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*"; }

step_count=0
step() {
    step_count=$((step_count + 1))
    echo ""
    echo -e "${GREEN}━━━ Step $step_count: $* ━━━${NC}"
}

check_command() {
    if ! command -v "$1" &>/dev/null; then
        log_error "$1 is required but not found in PATH"
        return 1
    fi
}

cleanup() {
    if [[ "$TEARDOWN" == "true" ]]; then
        log_info "Cleaning up..."
        helm uninstall "$RELEASE_NAME" --namespace "$NAMESPACE" 2>/dev/null || true
        kubectl delete namespace "$NAMESPACE" --wait=false 2>/dev/null || true

        if [[ "$DRIVER" == "kind" ]]; then
            kind delete cluster --name "$CLUSTER_NAME" 2>/dev/null || true
        elif [[ "$DRIVER" == "minikube" ]]; then
            minikube delete --profile "$CLUSTER_NAME" 2>/dev/null || true
        fi
    else
        log_warn "Skipping teardown (--no-teardown). Cluster '$CLUSTER_NAME' is still running."
        log_warn "  helm uninstall $RELEASE_NAME -n $NAMESPACE"
        if [[ "$DRIVER" == "kind" ]]; then
            log_warn "  kind delete cluster --name $CLUSTER_NAME"
        else
            log_warn "  minikube delete --profile $CLUSTER_NAME"
        fi
    fi
}

# ── Preflight ─────────────────────────────────────────────────────
step "Preflight checks"

check_command docker
check_command helm
check_command kubectl

# Auto-detect driver
if [[ -z "$DRIVER" ]]; then
    if command -v kind &>/dev/null; then
        DRIVER="kind"
    elif command -v minikube &>/dev/null; then
        DRIVER="minikube"
    else
        log_error "Neither 'kind' nor 'minikube' found. Install one of them."
        exit 1
    fi
fi
check_command "$DRIVER"

log_info "Driver: $DRIVER"
log_info "Cluster: $CLUSTER_NAME"
log_info "Namespace: $NAMESPACE"
log_info "Chart: $CHART_DIR"

if [[ ! -f "$CHART_DIR/Chart.yaml" ]]; then
    log_error "Chart.yaml not found at $CHART_DIR"
    exit 1
fi

trap cleanup EXIT

# ── Step: Create cluster ──────────────────────────────────────────
step "Create local Kubernetes cluster"

if [[ "$DRIVER" == "kind" ]]; then
    if kind get clusters 2>/dev/null | grep -q "^${CLUSTER_NAME}$"; then
        log_info "Cluster '$CLUSTER_NAME' already exists, reusing."
    else
        kind create cluster --name "$CLUSTER_NAME" --wait 60s
    fi
elif [[ "$DRIVER" == "minikube" ]]; then
    if minikube status --profile "$CLUSTER_NAME" &>/dev/null; then
        log_info "Cluster '$CLUSTER_NAME' already running, reusing."
    else
        minikube start --profile "$CLUSTER_NAME" --wait=all
    fi
fi

kubectl cluster-info
log_info "Cluster is ready."

# ── Step: Build and load images ───────────────────────────────────
step "Build container images"

PARENT_DIR="$(cd "$REPO_DIR/.." && pwd)"

declare -A IMAGES=(
    ["juniper-data"]="$PARENT_DIR/juniper-data"
    ["juniper-cascor"]="$PARENT_DIR/juniper-cascor"
    ["juniper-canopy"]="$PARENT_DIR/juniper-canopy"
    ["juniper-cascor-worker"]="$PARENT_DIR/juniper-cascor-worker"
)

for image_name in "${!IMAGES[@]}"; do
    build_context="${IMAGES[$image_name]}"
    if [[ -f "$build_context/Dockerfile" ]]; then
        log_info "Building $image_name from $build_context..."
        docker build -t "$image_name:latest" "$build_context"
    else
        log_warn "Dockerfile not found for $image_name at $build_context, skipping."
    fi
done

step "Load images into cluster"

for image_name in "${!IMAGES[@]}"; do
    if docker image inspect "$image_name:latest" &>/dev/null; then
        if [[ "$DRIVER" == "kind" ]]; then
            log_info "Loading $image_name into kind..."
            kind load docker-image "$image_name:latest" --name "$CLUSTER_NAME"
        elif [[ "$DRIVER" == "minikube" ]]; then
            log_info "Loading $image_name into minikube..."
            minikube image load "$image_name:latest" --profile "$CLUSTER_NAME"
        fi
    fi
done

# ── Step: Helm dependency build ───────────────────────────────────
step "Resolve Helm dependencies"

helm dependency build "$CHART_DIR" || {
    log_warn "Dependency build failed (may be offline). Continuing with available charts..."
}

# ── Step: Lint ────────────────────────────────────────────────────
step "Lint Helm chart"

helm lint "$CHART_DIR"
log_info "Lint passed."

# ── Step: Install ─────────────────────────────────────────────────
step "Install Helm chart"

kubectl create namespace "$NAMESPACE" --dry-run=client -o yaml | kubectl apply -f -

helm install "$RELEASE_NAME" "$CHART_DIR" \
    --namespace "$NAMESPACE" \
    --set worker.autoscaling.enabled=false \
    --set worker.replicaCount=1 \
    --set networkPolicies.enabled=false \
    --set data.image.pullPolicy=Never \
    --set cascor.image.pullPolicy=Never \
    --set canopy.image.pullPolicy=Never \
    --set worker.image.pullPolicy=Never \
    --wait \
    --timeout "${TIMEOUT}s"

log_info "Helm install completed."

# ── Step: Wait for pods ──────────────────────────────────────────
step "Wait for all pods to be ready"

kubectl wait --for=condition=ready pod \
    --all \
    --namespace "$NAMESPACE" \
    --timeout="${TIMEOUT}s"

log_info "All pods are ready."

kubectl get pods -n "$NAMESPACE" -o wide

# ── Step: Health checks ──────────────────────────────────────────
step "Validate service health endpoints"

FAILED=0

for svc_info in "data:8100:/v1/health" "cascor:8200:/v1/health" "canopy:8050:/v1/health"; do
    IFS=':' read -r svc port path <<< "$svc_info"
    full_svc="${RELEASE_NAME}-juniper-${svc}"

    log_info "Checking $full_svc ($path)..."

    response=$(kubectl exec deploy/"$full_svc" -n "$NAMESPACE" -- \
        python -c "
import urllib.request, json, sys
try:
    resp = urllib.request.urlopen('http://localhost:${port}${path}', timeout=10)
    data = resp.read().decode()
    print(data)
    sys.exit(0)
except Exception as e:
    print(f'FAILED: {e}', file=sys.stderr)
    sys.exit(1)
" 2>&1) || {
        log_error "Health check failed for $full_svc: $response"
        FAILED=$((FAILED + 1))
        continue
    }

    log_info "$full_svc: $response"
done

if [[ $FAILED -gt 0 ]]; then
    log_error "$FAILED health check(s) failed."
    kubectl get events -n "$NAMESPACE" --sort-by='.lastTimestamp' | tail -20
    exit 1
fi

log_info "All health checks passed."

# ── Step: Helm test ──────────────────────────────────────────────
step "Run Helm tests"

helm test "$RELEASE_NAME" --namespace "$NAMESPACE" --timeout "${TIMEOUT}s"
log_info "Helm tests passed."

# ── Step: Verify resources ────────────────────────────────────────
step "Verify resource counts"

expected_deployments=4  # data, cascor, canopy, worker
expected_services=3     # data, cascor, canopy (+ redis if enabled)
expected_pvcs=3         # data-datasets, cascor-snapshots, cascor-logs

actual_deployments=$(kubectl get deployments -n "$NAMESPACE" -l "app.kubernetes.io/part-of=juniper" --no-headers 2>/dev/null | wc -l)
actual_services=$(kubectl get services -n "$NAMESPACE" -l "app.kubernetes.io/part-of=juniper" --no-headers 2>/dev/null | wc -l)
actual_pvcs=$(kubectl get pvc -n "$NAMESPACE" -l "app.kubernetes.io/part-of=juniper" --no-headers 2>/dev/null | wc -l)

log_info "Deployments: $actual_deployments (expected: $expected_deployments)"
log_info "Services:    $actual_services (expected: $expected_services)"
log_info "PVCs:        $actual_pvcs (expected: $expected_pvcs)"

if [[ "$actual_deployments" -lt "$expected_deployments" ]]; then
    log_error "Expected at least $expected_deployments deployments, got $actual_deployments"
    exit 1
fi

# ── Done ──────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}  All integration tests passed!${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
