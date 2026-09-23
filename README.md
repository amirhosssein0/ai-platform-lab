# 🛡️ Aegis AI Platform Lab

> A production-grade, security-first AI platform built entirely on a single local Kubernetes cluster — from container to CUDA, from GitOps to guardrails. No cloud. No shortcuts.

**Repo:** `ai-platform-lab` · **Cluster:** k3s (single-node, bare metal, local GPU) · **Branching:** `develop` (dev) → `master` (prod)

---

## Table of Contents

1. [Why This Exists](#why-this-exists)
2. [Architecture](#architecture)
3. [Tech Stack](#tech-stack)
4. [Repository Structure](#repository-structure)
5. [Branching & GitOps Workflow](#branching--gitops-workflow)
6. [Bootstrap From Zero](#bootstrap-from-zero)
7. [Application Layer](#application-layer)
8. [Data Layer](#data-layer)
9. [Secrets Management — Vault](#secrets-management--vault)
10. [CI Pipeline](#ci-pipeline)
11. [CD Pipeline — ArgoCD](#cd-pipeline--argocd)
12. [Network Security & Resource Governance](#network-security--resource-governance)
13. [Supply Chain Security](#supply-chain-security)
14. [Runtime Security — Falco](#runtime-security--falco)
15. [Backup & Disaster Recovery — Velero](#backup--disaster-recovery--velero)
16. [Observability](#observability)
17. [AI Platform Layer](#ai-platform-layer)
18. [Self-Hosted GPU Model Serving](#self-hosted-gpu-model-serving)
19. [GPU Resource Management & Autoscaling](#gpu-resource-management--autoscaling)
20. [Model Gateway & Routing](#model-gateway--routing)
21. [Guardrails](#guardrails)
22. [RAG Evaluation Pipeline](#rag-evaluation-pipeline)
23. [AI Artifact Versioning](#ai-artifact-versioning)
24. [Known Limitations & Deliberate Tradeoffs](#known-limitations--deliberate-tradeoffs)
25. [Local Environment Notes](#local-environment-notes)

---

## Why This Exists

This is a hands-on lab built to go deep on **AI Platform Engineering** from the DevOps/Platform side — not the ML side. The explicit goal was to stay in the infrastructure seat (build the plumbing an AI product needs) rather than become an AI/ML engineer.

Everything here was built incrementally, verified manually before being handed to GitOps, and debugged in public — including the mistakes. Nothing was scaffolded from a template; every StatefulSet, NetworkPolicy, and Vault role was written and understood by hand before automating it.

---

## Architecture

```
┌─────────────────────────────────────────────┐
│                GitHub (source)               │
│  develop branch (dev) ── PR ──▶ master (prod)  │
└───────────────────────┬───────────────────────┘
                         │ push
               ┌─────────▼─────────┐
               │   GitHub Actions   │
               │  lint · build ·    │
               │  Trivy · Checkov · │
               │  migration test ·  │
               │  Cosign sign ·     │
               │  Syft SBOM ·       │
               │  AI artifact check │
               └─────────┬─────────┘
                         │ push image (GHCR) + bump tag in Git
               ┌─────────▼─────────┐
               │       ArgoCD       │  (App-of-Apps + ApplicationSet)
               └─────────┬─────────┘
                         │ sync
     ┌───────────────────┼────────────────────┐
     │                   │                    │
  Security &         Observability        AI Platform
  Governance             Stack               Layer
```

## Tech Stack

| Layer | Tools |
|---|---|
| **Application** | FastAPI (backend), Next.js (frontend) |
| **Data** | Postgres (chat/conversation history), Qdrant (RAG vector store) |
| **Secrets** | HashiCorp Vault (Kubernetes auth + Agent Injector) |
| **CI** | GitHub Actions |
| **CD** | ArgoCD (raw manifest install, App-of-Apps + ApplicationSet) |
| **IaC / Deploy** | Helm |
| **Supply Chain Security** | Trivy, Checkov, Cosign (keyless/Sigstore), Syft (SBOM) |
| **Policy Enforcement** | Kyverno (`verifyImages`, Enforce mode) |
| **Runtime Security** | Falco (custom rules) |
| **Backup/DR** | Velero + MinIO (Kopia filesystem backup) |
| **Observability** | Prometheus, Grafana, Alertmanager, OpenTelemetry, Tempo, Elasticsearch, Kibana, Filebeat |
| **GPU Stack** | NVIDIA driver + CUDA 12.0, NVIDIA Container Toolkit, k3s containerd `nvidia` RuntimeClass, NVIDIA k8s-device-plugin, DCGM Exporter |
| **Self-Hosted Serving** | llama.cpp (CUDA build, Maxwell/sm_50) |
| **Model Gateway** | LiteLLM Proxy |
| **Guardrails** | slowapi (rate limiting), Microsoft Presidio (PII detection/redaction) |
| **Registry** | GitHub Container Registry (GHCR) |

## Repository Structure

```
ai-platform-lab/
├── app-of-apps.yaml                     # Root ArgoCD Application (bootstraps everything else)
├── argocd/                              # Child Applications + one ApplicationSet
│   ├── aegis-environments-appset.yaml   # Generates dev/prod app instances
│   ├── kyverno-app.yaml / kyverno-policies-app.yaml
│   ├── falco-app.yaml
│   ├── minio-app.yaml / velero-app.yaml / velero-schedule-app.yaml
│   ├── kube-prometheus-stack-app.yaml
│   ├── elasticsearch-app.yaml / kibana-app.yaml / filebeat-app.yaml
│   ├── nvidia-device-plugin-app.yaml / dcgm-exporter-app.yaml / prometheus-adapter-app.yaml
│   ├── local-llm-app.yaml / llm-gateway-app.yaml
│   └── grafana-dashboards-app.yaml / slo-rules-app.yaml / eval-app.yaml
├── backend/                             # FastAPI app
├── frontend/                            # Next.js app
├── prompts/                             # Versioned prompt templates (AI artifacts)
├── eval/                                # RAG evaluation harness (golden dataset + LLM-as-judge)
├── local-llm/                           # llama.cpp CUDA Dockerfile
├── k8s/
│   ├── helm/ai-platform/                # Main app Helm chart (backend, frontend, postgres, qdrant, migration, HPA, NetworkPolicy, ResourceQuota)
│   ├── falco/                           # Custom Falco rules
│   ├── kyverno/                         # verifyImages ClusterPolicy
│   ├── velero/                          # MinIO backup storage
│   ├── velero-schedule/                 # Daily backup Schedule
│   ├── grafana/                         # Custom dashboards + Tempo datasource (ConfigMaps)
│   ├── monitoring/                      # SLO/SLA PrometheusRules
│   ├── local-llm/                       # RuntimeClass, Deployment, Service, HPA for the GPU model
│   ├── llm-gateway/                     # LiteLLM ServiceAccount, ConfigMap, Deployment, Service
│   └── eval/                            # Nightly evaluation CronJob
└── .github/workflows/ci.yml
```

## Branching & GitOps Workflow

- **`develop`** — active development branch. Everything is built and tested here first.
- **`master`** — production. Only reached via Pull Request, gated on CI (lint, build, Trivy, Checkov, migration schema test, AI artifact validation).
- The `ApplicationSet` in `argocd/` generates one Application per environment, each tracking a different branch:

| Environment | Branch | Namespace |
|---|---|---|
| dev | `develop` | `dev` |
| prod | `master` | `prod` |

Once a PR merges to `master`, ArgoCD's `selfHeal` picks up the new commit automatically — **no manual `helm upgrade` is ever run** on a GitOps-managed resource.

## Bootstrap From Zero

```bash
# 1. Install ArgoCD (raw manifest, not Helm)
kubectl create namespace argocd
kubectl apply -n argocd --server-side --force-conflicts \
  -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml

# 2. Bootstrap everything from Git
kubectl apply -f app-of-apps.yaml -n argocd
```

That's it. The App-of-Apps pattern discovers every other Application in `argocd/` and reconciles the entire platform — apps, security tooling, observability stack, and the GPU stack — from that one command.

## Application Layer

- **Backend (FastAPI):** chat + streaming chat (SSE) endpoints, document/image upload, conversation history (pin/rename/delete), Prometheus `/metrics`, OpenTelemetry auto-instrumentation.
- **Frontend (Next.js):** dark/lime themed chat UI, streaming token-by-token rendering, sidebar with resizable/collapsible conversation list, staged file/image attachment.
- Both are Dockerized as multi-stage, non-root (UID 10001), `HEALTHCHECK`-equipped images.
- **Ingress (Traefik)** routes `/api/*` to the backend and `/*` to the frontend under one host — this also eliminates CORS entirely, since the browser only ever sees one origin.

## Data Layer

- **Postgres** — StatefulSet with per-namespace PersistentVolumeClaim, schema managed via Alembic (not `create_all`), migrations run as an ArgoCD PreSync hook Job before every sync.
- **Qdrant** — StatefulSet with persistence, used as real infrastructure (not just an SDK call) for RAG. Embeddings generated with `fastembed` (`BAAI/bge-small-en-v1.5`), chunked with overlap, tagged with an embedding-model version for drift detection.

## Secrets Management — Vault

- Installed standalone (file storage, Shamir 1-of-1 for this lab), unsealed manually — sealing/unsealing is one of the few things that intentionally stays imperative.
- Kubernetes auth method: each component (backend, postgres, litellm) has its own dedicated ServiceAccount, bound to a namespace-scoped Vault role and policy — least privilege per component, not one shared identity.
- Vault Agent Injector (`agent-pre-populate-only`) writes secrets to `/vault/secrets/*` as init containers; application entrypoints source these files before starting.
- Postgres reads its password via the official image's `POSTGRES_PASSWORD_FILE` mechanism — no entrypoint hacking required.
- Zero secrets committed to Git. Zero long-lived Kubernetes Secret objects for anything Vault-managed.

## CI Pipeline

GitHub Actions (`.github/workflows/ci.yml`):

- **`backend-check` / `frontend-check`** — lint (non-blocking) + Docker build verification + Trivy image scan.
- **`migration-test`** — spins up an ephemeral Postgres service container, runs Alembic migrations against it, and asserts the resulting schema matches what the code expects. This exists because of a real incident: a schema drift between dev and prod (caused by `alembic stamp head` being trusted instead of verified) that only surfaced as a live 500 error.
- **`checkov-scan`** — scans the rendered Helm chart for Kubernetes misconfigurations. Blocking.
- **`ai-artifacts-check`** — validates every file in `prompts/` has a semver version header, fails the build if content changed without a version bump, and asserts required template placeholders exist.
- **`release`** (push only) — builds and pushes backend/frontend images to GHCR by commit SHA, signs them keylessly with Cosign (Sigstore/Fulcio, tied to this exact GitHub Actions workflow identity), generates an SPDX SBOM with Syft and attests it to the image, then bumps the image tag in the correct `values-{dev,prod}.yaml` and commits back to the branch (`[skip ci]`).

Branch protection on `master` requires all of the above to pass before merge.

## CD Pipeline — ArgoCD

- Installed via raw manifest (not Helm) — deliberately chosen after hitting reproducibility issues.
- App-of-Apps pattern: one root Application watching the `argocd/` directory, which contains every other Application and one ApplicationSet.
- `sync-wave` annotations enforce ordering where a real dependency exists (e.g., Kyverno's CRDs must exist before `kyverno-policies` can apply a ClusterPolicy; the NVIDIA device plugin before DCGM; DCGM before the Prometheus Adapter).
- `ignoreDifferences` on `spec.replicas` for backend/frontend Deployments so the HPA and ArgoCD's `selfHeal` don't fight each other.
- Multi-source Applications (e.g., Falco) pull the Helm chart from its upstream repo while sourcing values from a file in this repo — keeping third-party chart config in version control without forking the chart.

## Network Security & Resource Governance

- Default-deny NetworkPolicy baseline in dev/prod, with explicit allow rules for every real traffic path (Ingress → frontend/backend, backend → Postgres/Qdrant/Vault/OTel Collector/LiteLLM gateway, Postgres/migration Jobs → Vault). Backend has no direct internet egress — all LLM traffic is forced through the internal gateway.
- ResourceQuota per namespace (tighter in dev, looser in prod), which required adding explicit `resources.requests/limits` to every workload — Kubernetes rejects pod creation in a quota'd namespace otherwise.
- HPA (CPU-based) on backend/frontend, plus a GPU-utilization-based HPA on the self-hosted model (see [GPU Resource Management](#gpu-resource-management--autoscaling)).

## Supply Chain Security

- **Trivy** — CRITICAL/HIGH vulnerability scanning on every built image (CI, non-blocking pending triage).
- **Checkov** — Helm chart misconfiguration scanning (CI, blocking). Accepted/deferred findings are either globally skipped with a documented reason (e.g., `IfNotPresent` pull policy is intentional given immutable per-commit tags) or suppressed per-resource via `checkov.io/skip*` annotations with an inline justification (e.g., Postgres's UID is hardcoded by its own image and already owns live PVC data — forcing a "high UID" would break it).
- **Cosign** — keyless signing (Sigstore/Fulcio/Rekor) of every released image, tied to this repo's exact GitHub Actions workflow identity via `subjectRegExp`.
- **Syft** — SPDX SBOM generated and attested (signed) alongside every image.
- **Kyverno** — `verifyImages` ClusterPolicy in Enforce mode: only images signed by this exact CI pipeline can be admitted into dev/prod. Started in Audit, verified, then flipped to Enforce.

## Runtime Security — Falco

Custom rules (on top of Falco's defaults, which already cover shells-in-containers and privileged containers) detect:

- `curl`/`wget` execution inside a container
- Kubernetes ServiceAccount token reads (with an explicit exception for Vault Agent and Kyverno's own controllers, which legitimately read their token for K8s API auth)
- Suspicious host-path access (`docker.sock`, mounted `/host`, cross-process `/proc/*/root` access)
- Container escape indicators (`release_agent` writes — the CVE-2022-0492 pattern — and `nsenter`/`unshare` execution)

## Backup & Disaster Recovery — Velero

- MinIO deployed as the S3-compatible backup target (self-written StatefulSet, not a third-party chart) since `local-path` storage has no native snapshot support.
- Velero + Kopia (`defaultVolumesToFsBackup: true`) does real filesystem-level PV backup, not just resource-manifest backup.
- A `Schedule` resource runs nightly backups of dev/prod; ad-hoc backup/restore remain intentionally imperative (CLI), same as Vault's unseal step — some operations don't belong in Git.
- Restore was tested two ways: same-namespace restore (works cleanly) and cross-namespace restore into a differently-named namespace (correctly blocked by Vault's namespace-scoped Kubernetes auth roles — a deliberate defense-in-depth outcome, not a bug).

## Observability

- **Prometheus + Grafana + Alertmanager** (kube-prometheus-stack), with default control-plane alerts (`KubeControllerManagerDown`, etc.) disabled since k3s doesn't expose those components the way upstream Kubernetes does.
- **Alertmanager → Gmail SMTP** for real email alerting, tested via both synthetic alerts and a real induced outage (scaling Postgres to zero).
- **AI-specific metrics:** `llm_requests_total`, `llm_request_duration_seconds`, `llm_prompt_tokens_total`/`llm_completion_tokens_total`, `llm_cost_usd_total` (wired for paid models; currently $0 since all models used are free-tier), `guardrail_pii_detections_total` — all on a dedicated Grafana dashboard.
- **OpenTelemetry** — FastAPI/httpx auto-instrumentation plus a manual span around Qdrant retrieval, exported via an OTel Collector to Tempo, viewable in Grafana's trace explorer.
- **SLO/SLA** — multi-window, multi-burn-rate alerting (Google SRE style) for HTTP availability (99% target) and LLM call latency (95% under 5s), backed by Prometheus recording rules and a live "error budget remaining" gauge. Validated by intentionally breaking availability and watching the budget drop in real time.
- **ELK** (Elasticsearch + Kibana + Filebeat) for cluster-wide log aggregation, with Kubernetes metadata enrichment (namespace/pod/container) via Filebeat's autodiscover.

## AI Platform Layer

The four pieces that make this an AI platform lab and not just a Kubernetes lab:

### Self-Hosted GPU Model Serving

- Hardware: NVIDIA Quadro M2000M (Maxwell, compute capability 5.0, 4GB VRAM) — confirmed incompatible with vLLM/TGI (both require compute capability ≥7.0).
- llama.cpp, built from source with `-DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES=50`, running Llama 3.2 1B Instruct (Q4_K_M) fully offloaded to GPU.
- Real, measured GPU throughput (~26 tok/s generation, ~90 tok/s prompt processing) and verified KV-cache reuse across a multi-turn conversation.
- Dockerized (multi-stage CUDA build, linked against CUDA driver stub libraries since `libcuda.so` isn't present at build time — only injected by the container runtime at `docker run`/pod start).

### GPU Resource Management & Autoscaling

- k3s containerd auto-registered the `nvidia` runtime; only a RuntimeClass and the NVIDIA k8s-device-plugin were needed to expose `nvidia.com/gpu` as a schedulable resource.
- Full metrics pipeline: DCGM Exporter → Prometheus → Prometheus Adapter (custom metrics API) → HPA scaling on real `DCGM_FI_DEV_GPU_UTIL`.
- `maxReplicas: 1` by design — with one physical GPU, there's nowhere to scale to; the pipeline is built and proven, ready to raise `maxReplicas` the moment real multi-GPU capacity exists.

### Model Gateway & Routing

LiteLLM Proxy routes three logical model names:

| Alias | Backend(s) |
|---|---|
| `text-primary` | OpenRouter (Gemma) |
| `text-local` | Self-hosted llama.cpp (above) |
| `vision` | 3-model OpenRouter fallback group |

`router_settings.fallbacks: [{"text-primary": ["text-local"]}]` means an OpenRouter rate limit now automatically and silently fails over to the local GPU model — solving a real, recurring pain point from earlier in the project. Adding the gateway also let the backend's NetworkPolicy drop its broad internet egress rule entirely, since all model traffic now flows through one internal service.

### Guardrails

Applied before every request reaches any model:

- Rate limiting (`slowapi`, 20/min on chat, 10/min on uploads)
- Input validation (empty/oversized message rejection)
- PII redaction (Microsoft Presidio — NER-based, not just regex) — the original message is stored as-is in Postgres, but only the redacted version is ever sent to a model, whether local or external.

### RAG Evaluation Pipeline

- A golden dataset (`eval/golden_dataset.json`) covering three distinct failure modes: general knowledge, RAG-dependent fact retrieval, and hallucination resistance.
- An LLM-as-judge (via the gateway's `text-primary` route) scores each answer 0–10.
- Runs as a nightly CronJob, pushing `eval_average_score`/`eval_pass_rate` to Prometheus via a Pushgateway (since it's a short-lived batch job, not a scrapeable service).

### AI Artifact Versioning

- Prompt templates live as standalone files in `prompts/`, each with a `# version: X.Y.Z` header — not buried as string literals in application code.
- The embedding model name/version is tagged onto every vector stored in Qdrant, with a startup check that flags (via a Prometheus gauge) if previously-stored vectors were embedded with a different model version than the one currently configured — the first line of defense against silent RAG degradation from an embedding-model change.
- CI enforces that prompt content can't change without a version bump, and that required template placeholders are never accidentally removed.

## Known Limitations & Deliberate Tradeoffs

Documented honestly, not hidden:

- Rate limiting is per-pod, not global — with 2 backend replicas in prod, the effective limit is roughly double the configured value. A shared Redis backend would fix this; not added yet.
- MinIO/Velero credentials are a manual Kubernetes Secret, not Vault-managed — the blast radius is limited to a local-only backup store, and Vault-integrating a third-party Helm chart's entrypoint isn't worth the complexity here.
- `CKV_K8S_22` (read-only root filesystem) is deferred — would need per-service testing (especially Postgres) to confirm nothing breaks; not yet done.
- `CKV_K8S_43` (image digest pinning) is deferred — currently deploying by immutable per-commit-SHA tag, which is safe but not equivalent to digest pinning.
- Elasticsearch security (`xpack.security`) is disabled — a deliberate lab simplification to avoid certificate/credential management for a single-node, non-internet-facing logging stack.
- ArgoCD occasionally hits transient TLS handshake timeout errors against the in-cluster API server — root-caused to this being a single physical machine running an unusually dense stack (ArgoCD, Vault, Kyverno, Falco, the full Prometheus stack, ELK, and the GPU stack) that occasionally spikes under host suspend/resume cycles. Self-resolves via ArgoCD's built-in retry; not a defect in any manifest.
- No cloud, by choice, not by design goal — Azure credits ran out early in the project; everything here proves the entire platform is buildable and demonstrable on a single local machine, which was arguably a better lesson than the original cloud plan.

## Local Environment Notes

- **Cluster:** k3s, single node, running directly on the host (not virtualized) — bare-metal, `systemd-detect-virt` returns `none`.
- **GPU:** NVIDIA Quadro M2000M, driver 580.173.02, CUDA Toolkit pinned to 12.0 (CUDA 13.x dropped compilation support for pre-Turing architectures — upgrading the toolkit would break llama.cpp's GPU build).
- **Storage:** `local-path` (Rancher's default k3s provisioner) throughout — no cloud block storage anywhere in this project.