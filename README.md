# ai-platform-lab
Security-first AI platform on Kubernetes — FastAPI + Next.js chatbot with RAG, self-hosted model serving (vLLM), observability, guardrails, and model gateway, deployed on Azure AKS.

UNSEAL_KEY=$(cat vault-init.json | jq -r '.unseal_keys_b64[0]')
kubectl exec -n vault vault-0 -- vault operator unseal "$UNSEAL_KEY"
kubectl exec -n vault vault-0 -- vault status