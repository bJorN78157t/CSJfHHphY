# Zero-Downtime Deployments on EKS: Blue-Green and Canary Strategies

> A practical guide to implementing zero-downtime deployments using Argo Rollouts on Amazon EKS

**Reading Time:** 10 minutes  
**Prerequisites:** Running EKS cluster, containerized application, basic Kubernetes knowledge

---

## Table of Contents

1. [Introduction](#introduction)
2. [Argo Rollouts Setup](#argo-rollouts-setup)
3. [Blue-Green Deployment](#blue-green-deployment)
4. [Canary Deployment](#canary-deployment)
5. [Monitoring and Rollbacks](#monitoring-and-rollbacks)
6. [Best Practices](#best-practices)

---

## Introduction

Zero-downtime deployments ensure your application updates without service interruption. This guide covers two battle-tested strategies using Argo Rollouts on EKS:

**Blue-Green Deployment:**
- Maintains two complete environments (Blue = current, Green = new)
- Instant traffic cutover when ready (< 2 seconds)
- Perfect for critical systems requiring immediate rollback
- Trade-off: 2x resources during deployment

**Canary Deployment:**
- Progressive traffic shifting: 10% → 25% → 50% → 100%
- Validates at each stage with metrics
- Limited blast radius - only small percentage affected by issues
- Best for high-risk changes and gradual rollouts

### When to Use Each Strategy

| Use Case | Strategy | Why |
|----------|----------|-----|
| Critical system with strict SLA | Blue-Green | Instant rollback |
| High-risk deployment | Canary | Gradual validation |
| Database migration | Blue-Green | Deploy code, test, then migrate |
| ML model deployment | Canary | A/B testing capabilities |
| Emergency hotfix | Blue-Green | Speed |

---

## Argo Rollouts Setup

[Argo Rollouts](https://argoproj.github.io/rollouts/) extends Kubernetes with advanced deployment strategies.

### Installation

```bash
# Install Argo Rollouts
kubectl create namespace argo-rollouts
kubectl apply -n argo-rollouts -f \
  https://github.com/argoproj/argo-rollouts/releases/download/v2.38.1/install.yaml

# Verify
kubectl get pods -n argo-rollouts

# Install kubectl plugin (optional)
curl -LO https://github.com/argoproj/argo-rollouts/releases/download/v2.38.1/kubectl-argo-rollouts-linux-amd64
chmod +x kubectl-argo-rollouts-linux-amd64
sudo mv kubectl-argo-rollouts-linux-amd64 /usr/local/bin/kubectl-argo-rollouts

# Verify plugin
kubectl argo rollouts version
```

---

## Blue-Green Deployment

Blue-Green maintains two environments and switches traffic instantly when ready.

### Implementation

**1. Create Rollout:**

```yaml
# blue-green-rollout.yaml
apiVersion: argoproj.io/v1alpha1
kind: Rollout
metadata:
  name: myapp-blue-green
spec:
  replicas: 3
  selector:
    matchLabels:
      app: myapp
  
  template:
    metadata:
      labels:
        app: myapp
    spec:
      containers:
      - name: myapp
        image: your-registry/myapp:v1
        ports:
        - containerPort: 8080
        
        resources:
          requests:
            memory: "128Mi"
            cpu: "100m"
          limits:
            memory: "256Mi"
            cpu: "200m"
        
        readinessProbe:
          httpGet:
            path: /ready
            port: 8080
          initialDelaySeconds: 5
          periodSeconds: 3
        
        livenessProbe:
          httpGet:
            path: /health
            port: 8080
          initialDelaySeconds: 10
          periodSeconds: 5
  
  strategy:
    blueGreen:
      activeService: myapp-active      # Production traffic
      previewService: myapp-preview    # Preview/testing
      autoPromotionEnabled: false      # Manual approval required
      scaleDownDelaySeconds: 30
```

**2. Create Services:**

```yaml
# blue-green-services.yaml
---
apiVersion: v1
kind: Service
metadata:
  name: myapp-active
spec:
  type: LoadBalancer
  selector:
    app: myapp
  ports:
  - port: 80
    targetPort: 8080

---
apiVersion: v1
kind: Service
metadata:
  name: myapp-preview
spec:
  type: LoadBalancer
  selector:
    app: myapp
  ports:
  - port: 80
    targetPort: 8080
```

**3. Deploy:**

```bash
kubectl apply -f blue-green-rollout.yaml
kubectl apply -f blue-green-services.yaml

# Watch status
kubectl argo rollouts get rollout myapp-blue-green --watch
```

### Deploy New Version

```bash
# Update to v2
kubectl argo rollouts set image myapp-blue-green myapp=your-registry/myapp:v2

# New version deploys to preview
# Test preview endpoint
PREVIEW_URL=$(kubectl get svc myapp-preview -o jsonpath='{.status.loadBalancer.ingress[0].hostname}')
curl http://$PREVIEW_URL/health

# If tests pass, promote to production
kubectl argo rollouts promote myapp-blue-green

# Traffic instantly switches to new version
```

### Automated Analysis

Add metric validation before promotion:

```yaml
# In rollout strategy
strategy:
  blueGreen:
    activeService: myapp-active
    previewService: myapp-preview
    autoPromotionEnabled: false
    
    prePromotionAnalysis:
      templates:
      - templateName: success-rate

---
# Analysis Template
apiVersion: argoproj.io/v1alpha1
kind: AnalysisTemplate
metadata:
  name: success-rate
spec:
  metrics:
  - name: success-rate
    interval: 30s
    count: 5
    successCondition: result >= 0.95
    failureLimit: 2
    provider:
      prometheus:
        address: http://prometheus:9090
        query: |
          sum(rate(http_requests_total{service="myapp-preview", status=~"2.."}[1m]))
          /
          sum(rate(http_requests_total{service="myapp-preview"}[1m]))
```

Analysis runs for 2.5 minutes. If success rate ≥ 95%, promotion allowed. If fails twice, automatic abort.

### Rollback

```bash
# Instant rollback (< 2 seconds)
kubectl argo rollouts abort myapp-blue-green
kubectl argo rollouts undo myapp-blue-green
```

---

## Canary Deployment

Canary gradually shifts traffic from old to new version with validation at each stage.

### Implementation

**1. Create Canary Rollout:**

```yaml
# canary-rollout.yaml
apiVersion: argoproj.io/v1alpha1
kind: Rollout
metadata:
  name: myapp-canary
spec:
  replicas: 5
  selector:
    matchLabels:
      app: myapp-canary
  
  template:
    metadata:
      labels:
        app: myapp-canary
    spec:
      containers:
      - name: myapp
        image: your-registry/myapp:v1
        ports:
        - containerPort: 8080
        
        resources:
          requests:
            memory: "128Mi"
            cpu: "100m"
          limits:
            memory: "256Mi"
            cpu: "200m"
        
        readinessProbe:
          httpGet:
            path: /ready
            port: 8080
          initialDelaySeconds: 5
          periodSeconds: 3
  
  strategy:
    canary:
      canaryService: myapp-canary
      stableService: myapp-stable
      
      steps:
      - setWeight: 20
      - pause: {duration: 2m}
      
      - setWeight: 40
      - pause: {duration: 2m}
      
      - setWeight: 60
      - pause: {duration: 2m}
      
      - setWeight: 80
      - pause: {duration: 2m}
      
      - setWeight: 100
      
      maxSurge: "25%"
      maxUnavailable: 0
```

**2. Create Services:**

```yaml
# canary-services.yaml
---
apiVersion: v1
kind: Service
metadata:
  name: myapp-stable
spec:
  type: LoadBalancer
  selector:
    app: myapp-canary
  ports:
  - port: 80
    targetPort: 8080

---
apiVersion: v1
kind: Service
metadata:
  name: myapp-canary
spec:
  type: ClusterIP
  selector:
    app: myapp-canary
  ports:
  - port: 80
    targetPort: 8080
```

**3. Deploy:**

```bash
kubectl apply -f canary-rollout.yaml
kubectl apply -f canary-services.yaml
```

### Deploy New Version

```bash
# Update to v2
kubectl argo rollouts set image myapp-canary myapp=your-registry/myapp:v2

# Watch progressive rollout
kubectl argo rollouts get rollout myapp-canary --watch

# Timeline:
# 0:00 - 20% traffic to v2, pause 2min
# 2:00 - 40% traffic to v2, pause 2min
# 4:00 - 60% traffic to v2, pause 2min
# 6:00 - 80% traffic to v2, pause 2min
# 8:00 - 100% traffic to v2, complete
```

### Control Deployment

```bash
# Skip pause and promote to next step
kubectl argo rollouts promote myapp-canary

# Complete immediately (skip all steps)
kubectl argo rollouts promote myapp-canary --full

# Abort and rollback
kubectl argo rollouts abort myapp-canary
```

### Automated Analysis

Add validation at each stage:

```yaml
strategy:
  canary:
    steps:
    - setWeight: 20
    - pause: {duration: 30s}
    - analysis:
        templates:
        - templateName: http-metrics
    
    - setWeight: 40
    - pause: {duration: 30s}
    - analysis:
        templates:
        - templateName: http-metrics
    
    - setWeight: 60
    - pause: {duration: 1m}
    - setWeight: 80
    - pause: {duration: 1m}
    - setWeight: 100

---
apiVersion: argoproj.io/v1alpha1
kind: AnalysisTemplate
metadata:
  name: http-metrics
spec:
  metrics:
  # Success rate check
  - name: success-rate
    interval: 1m
    count: 3
    successCondition: result >= 0.95
    failureLimit: 2
    provider:
      prometheus:
        address: http://prometheus:9090
        query: |
          sum(rate(http_requests_total{service="myapp-canary", status=~"2.."}[2m]))
          /
          sum(rate(http_requests_total{service="myapp-canary"}[2m]))
  
  # Latency p95 check
  - name: latency-p95
    interval: 1m
    count: 3
    successCondition: result <= 500
    failureLimit: 2
    provider:
      prometheus:
        address: http://prometheus:9090
        query: |
          histogram_quantile(0.95,
            sum(rate(http_request_duration_seconds_bucket{service="myapp-canary"}[2m])) by (le)
          ) * 1000
```

At each stage: checks success rate and latency. If metrics fail twice, automatic rollback.

---

## Monitoring and Rollbacks

### Key Prometheus Queries

```promql
# Error rate by version
sum(rate(http_requests_total{status=~"5..", version="v2"}[5m]))
/ sum(rate(http_requests_total{version="v2"}[5m]))

# Latency p95 by version
histogram_quantile(0.95,
  sum(rate(http_request_duration_seconds_bucket{version="v2"}[5m])) by (le)
)

# Pod restarts
increase(kube_pod_container_status_restarts_total{pod=~"myapp-.*"}[5m])

# Traffic split percentage
(sum(rate(http_requests_total{revision="canary"}[1m]))
/ sum(rate(http_requests_total[1m]))) * 100
```

### Essential Alerts

```yaml
groups:
- name: rollouts
  rules:
  - alert: RolloutFailed
    expr: rollout_phase{phase="Degraded"} == 1
    for: 2m
    labels:
      severity: critical
  
  - alert: CanaryHighErrorRate
    expr: |
      (sum(rate(http_requests_total{status=~"5..", revision="canary"}[2m]))
      / sum(rate(http_requests_total{revision="canary"}[2m]))) > 0.05
    for: 3m
    labels:
      severity: warning
```

### Common Issues

**Rollout stuck:**
```bash
kubectl describe rollout myapp
kubectl logs -l app=myapp,revision=canary --tail=50

# Force next step or abort
kubectl argo rollouts promote myapp
kubectl argo rollouts abort myapp
```

**Traffic not shifting:**
```bash
# Verify service selectors match rollout labels
kubectl get svc myapp-stable -o yaml | grep selector
kubectl get endpoints myapp-stable
```

**Analysis failing:**
```bash
kubectl get analysisrun
kubectl describe analysisrun myapp-xxx

# Test Prometheus query directly
kubectl port-forward -n monitoring svc/prometheus 9090:9090
```

---

## Best Practices

### Strategy Selection

**Use Blue-Green when:**
- Need instant rollback (< 2 seconds)
- Deploying to critical systems
- Performing database migrations
- Deploying emergency hotfixes

**Use Canary when:**
- High-risk deployments need validation
- Deploying ML models or A/B tests
- Want gradual user exposure
- Limited resources (only +20% overhead)

### Resource Planning

**Blue-Green:**
- Peak usage: 2x resources during deployment (~5 minutes)
- Plan capacity accordingly

**Canary:**
- Peak usage: 1.2x resources throughout deployment
- More resource-efficient for large applications

### Multi-Region Deployment

Deploy sequentially, not simultaneously:

```bash
# 1. Deploy Region 1
kubectl --context us-east-1 argo rollouts set image myapp myapp=v2
kubectl --context us-east-1 argo rollouts status myapp --watch

# 2. After validation, deploy Region 2
kubectl --context eu-west-1 argo rollouts set image myapp myapp=v2
```

Limits blast radius to one region at a time.

### Database Migrations

Use backward-compatible approach:

```
Phase 1: Deploy code v2 (supports old AND new schema)
Phase 2: Run database migration (add columns, backfill)
Phase 3: Deploy code v3 (uses new schema only)
Phase 4: Clean up old columns
```

### Production Checklist

- [ ] Readiness and liveness probes configured
- [ ] Resource requests and limits set
- [ ] Prometheus metrics exported
- [ ] Alert rules configured
- [ ] Rollback procedures documented and tested
- [ ] Analysis templates validate critical metrics
- [ ] Multi-region deployment plan ready
- [ ] Database migration strategy defined

---

## Conclusion

Zero-downtime deployments with Argo Rollouts provide:

✅ **Confidence** - Deploy fearlessly with automated safety nets  
✅ **Speed** - Instant rollbacks when needed  
✅ **Validation** - Data-driven deployment decisions  
✅ **Flexibility** - Choose the right strategy for each situation

### Quick Comparison

| Aspect | Blue-Green | Canary |
|--------|-----------|--------|
| **Rollback Speed** | < 2 seconds | 30-60 seconds |
| **Resource Usage** | 2x peak | 1.2x peak |
| **Validation** | Pre-promotion | Continuous |
| **Complexity** | Simple | Moderate |
| **Best For** | Critical systems | High-risk changes |

### Getting Started

1. **Start simple:** Deploy Blue-Green in dev environment
2. **Add monitoring:** Integrate Prometheus metrics
3. **Automate validation:** Create analysis templates
4. **Graduate to Canary:** Use for high-risk deployments
5. **Test rollbacks:** Practice failure scenarios regularly

### Resources

- **Argo Rollouts:** https://argoproj.github.io/rollouts/
- **EKS Best Practices:** https://aws.github.io/aws-eks-best-practices/
- **Prometheus:** https://prometheus.io/docs/

---

Zero-downtime deployments aren't just technology—they're about **confidence** to deploy multiple times per day and fix issues in seconds when things go wrong.

**Start small, measure everything, and gradually adopt more advanced patterns.**

---

**Keywords:** Kubernetes, EKS, Zero-Downtime Deployment, Blue-Green, Canary, Argo Rollouts, AWS, DevOps

**Last Updated:** October 9, 2025
