<div align="center">

# Velox

**Distributed Real-Time Inference Pipeline for High-Frequency Data Streams**

[![CI/CD](https://github.com/atharva-m/Velox/actions/workflows/ci.yml/badge.svg)](https://github.com/atharva-m/Velox/actions/workflows/ci.yml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![PyTorch](https://img.shields.io/badge/PyTorch-2.0+-ee4c2c.svg)](https://pytorch.org/)
[![Kafka](https://img.shields.io/badge/Apache%20Kafka-7.4.0-black.svg)](https://kafka.apache.org/)
[![Kubernetes](https://img.shields.io/badge/Kubernetes-Ready-326CE5.svg)](https://kubernetes.io/)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED.svg)](https://www.docker.com/)
[![Code Style: Black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![Security: Trivy](https://img.shields.io/badge/security-trivy-blue)](https://github.com/aquasecurity/trivy)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

[Overview](#overview) | [Performance](#performance) | [Architecture](#architecture) | [Quick Start](#quick-start) | [Kubernetes Deployment](#kubernetes-deployment) | [GPU Configuration](#gpu-configuration) | [Monitoring](#monitoring) | [Contributing](#contributing)

</div>

---

## Overview

This project implements a **production-ready, real-time image classification pipeline** using Apache Kafka for stream processing and PyTorch for GPU-accelerated inference. The system is designed to process high-throughput image streams with low latency, making it suitable for applications in computer vision, anomaly detection, and real-time monitoring systems.

### Key Features

- **High Throughput** — 1,683 images/sec with 8 GPU-accelerated pods
- **GPU Time-Slicing** — 8 pods share a single NVIDIA GPU efficiently
- **8.8x Scaling** — From 192 img/sec (single) to 1,683 img/sec (distributed)
- **Horizontal Pod Autoscaling** — Automatic scaling from 1-8 pods based on CPU utilization
- **High Accuracy** — 98.5% model confidence on shape classification
- **Observable** — Built-in Prometheus metrics and Grafana dashboards
- **Kubernetes Native** — Production-ready with auto-scaling and persistent storage
- **Containerized** — Fully Dockerized with health checks and dependency management

### Use Cases

- Real-time quality control in manufacturing
- Anomaly detection in video surveillance
- Automated content moderation
- Scientific image analysis pipelines

---

## Performance

### Benchmark Results

Tested on NVIDIA RTX 4070 with Minikube (8 CPUs, 20GB RAM):

| Metric | Single Process | Kubernetes (8 pods) | Improvement |
|--------|---------------|---------------------|-------------|
| **Throughput** | 192 img/sec | 1,683 img/sec | **8.8x** |
| **Per-Pod Throughput** | — | 210 img/sec | — |
| **Peak Throughput** | — | 1,949 img/sec | — |
| **Model Confidence** | 100% | 98.5% | — |

### Resource Utilization

| Resource | Per Pod | Total (8 pods) |
|----------|---------|----------------|
| **CPU** | ~950m | ~7.6 cores |
| **Memory** | ~1.5 GB | ~12 GB |
| **GPU** | 1/8 slice | 1 GPU (shared) |

### Scalability

```text
Pods    Throughput      Per-Pod         Efficiency
--------------------------------------------------
1       ~210 img/sec    210 img/sec     100%
4       ~840 img/sec    210 img/sec     100%
8       ~1,683 img/sec  210 img/sec     100%

```

The system scales linearly with GPU time-slicing, maintaining consistent per-pod throughput as replicas increase.

---

## Architecture

```text
+--------------------------------------------------------------------------------------+
|                         KAFKA ML INFERENCE PIPELINE                                  |
|                           with GPU Time-Slicing                                      |
+--------------------------------------------------------------------------------------+

                                                    +----------------------------------+
                                                    |      GPU (Time-Sliced)           |
                                                    |  +----+----+-----+----+          |
                                                    |  | C1 | C2 | ... | C8 |          |
                                                    |  +----+----+-----+----+          |
                                                    +----------------------------------+
                                                                  ^
+--------------+      +--------------+      +---------------------+--------------------+
|              |      |              |      |       CONSUMER PODS (HPA: 1-8)           |
|  PRODUCER    | ---> |    KAFKA     | ---> |  +------------+    +------------+        |
|    POD       |      |     POD      |      |  | Consumer 1 |    | Consumer 2 | ...    |
|              |      |              |      |  |   (GPU)    |    |   (GPU)    |        |
|  Synthetic   |      |  8 Partitions|      |  +------+-----+    +------+-----+        |
|  Image Gen   |      |  1,700+/sec  |      |         |                 |              |
+--------------+      +--------------+      +---------|-----------------|--------------+
                                                      |                 |
                      +--------------+      +---------v-----------------v--------------+
                      |   GRAFANA    |      |            PROMETHEUS                    |
                      |     POD      | <--- |               POD                        |
                      |              |      |                                          |
                      |  Dashboards  |      |        Metrics (8 pods)                  |
                      +--------------+      +------------------------------------------+
                                                     |
                                            +--------v----------+
                                            |                   |
                                            |    MONGODB POD    |
                                            |   + PVC Storage   |
                                            |                   |
                                            +-------------------+

```

### Components

| Component | Description | Technology |
| --- | --- | --- |
| **Producer** | Generates synthetic shape images at 1,700+ msg/sec | Python, OpenCV |
| **Consumer** | GPU-accelerated inference, 210 img/sec per pod | PyTorch, CUDA |
| **Model Trainer** | One-time Kubernetes Job to train model on GPU | PyTorch |
| **Kafka** | Distributed message broker with 8 partitions | Apache Kafka |
| **MongoDB** | Document store for persisting detection results | MongoDB |
| **Prometheus** | Time-series metrics from all consumer pods | Prometheus |
| **Grafana** | Real-time monitoring dashboards | Grafana |

---

## Quick Start

### Option 1: Docker Compose (Development)

Best for local development and testing.

#### Prerequisites

* [Docker](https://docs.docker.com/get-docker/) (v20.10+)
* [Docker Compose](https://docs.docker.com/compose/install/) (v2.0+)
* [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html) (for GPU support)

#### Build and Start

```bash
git clone [https://github.com/atharva-m/Velox.git](https://github.com/atharva-m/Velox.git)
cd Velox

# Build the image
docker build -t ml-inference-app:latest .

# Start all services
docker-compose up -d

```

#### Verify Services

```bash
docker-compose ps
docker-compose logs -f consumer

```

You should see detections for all shape/color combinations:

```text
MATCH: red_circle (Conf: 0.99)
MATCH: green_square (Conf: 0.98)
MATCH: red_square (Conf: 0.97)
MATCH: green_circle (Conf: 0.99)

```

---

### Option 2: Kubernetes (Production)

Best for production deployments with GPU time-slicing and auto-scaling.

See [Kubernetes Deployment](https://www.google.com/search?q=%23kubernetes-deployment) section below.

---

## Kubernetes Deployment

Deploy the pipeline on Kubernetes with GPU time-slicing, Horizontal Pod Autoscaler, and automatic model training.

### Prerequisites

* [Minikube](https://minikube.sigs.k8s.io/docs/start/) or any Kubernetes cluster
* [kubectl](https://kubernetes.io/docs/tasks/tools/)
* NVIDIA GPU with drivers installed
* [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html)

### Quick Deploy

Use the provided management script for one-command deployment:

**Windows (PowerShell):**

```powershell
# Start cluster with GPU time-slicing (8 pods sharing 1 GPU)
.\k8s.ps1 -Action start

# Start with custom resources
.\k8s.ps1 -Action start -CPUs 16 -Memory 32768 -Partitions 8

# Stop and cleanup
.\k8s.ps1 -Action stop

```

**Linux/macOS:**

```bash
./k8s.sh start
./k8s.sh stop

```

### What the Script Does

1. Starts Minikube with GPU passthrough (`--gpus all`)
2. Configures NVIDIA GPU time-slicing (8 replicas per GPU)
3. Enables metrics server for HPA
4. Builds the Docker image inside Minikube
5. Deploys infrastructure (Kafka, Zookeeper, MongoDB)
6. Creates Kafka topic with 8 partitions
7. Runs model training Job (one-time)
8. Deploys monitoring stack (Prometheus, Grafana)
9. Deploys consumer with HPA (auto-scales 1-8 pods)
10. Deploys producer

---

## GPU Configuration

### GPU Time-Slicing

This project uses NVIDIA GPU time-slicing to allow 8 consumer pods to share a single GPU, achieving **8.8x throughput scaling**.

```yaml
# gpu-sharing-config.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: time-slicing-config
  namespace: kube-system
data:
  config.yaml: |
    version: v1
    sharing:
      timeSlicing:
        resources:
        - name: [nvidia.com/gpu](https://nvidia.com/gpu)
          replicas: 8    # Allow 8 pods to share 1 GPU

```

---

## Configuration

All configuration is managed through environment variables.

### Configuration Reference

| Variable | Description | Default |
| --- | --- | --- |
| `KAFKA_BOOTSTRAP_SERVER` | Kafka broker address | `kafka:29092` |
| `KAFKA_TOPIC` | Topic for image streaming | `image_data` |
| `KAFKA_CONSUMER_GROUP` | Consumer group ID | `gpu_rtx_4070` |
| `BATCH_SIZE` | Inference batch size | `8` |
| `QUEUE_SIZE` | Internal queue size | `200` |
| `METRICS_PORT` | Prometheus metrics port | `8000` |
| `MONGO_URI` | MongoDB connection string | `mongodb://mongo:27017/` |
| `DB_NAME` | Database name | `lab_discovery_db` |
| `STORAGE_PATH` | Path to save detected images | `./discoveries` |
| `MODEL_PATH` | Path to model weights | `model.pth` |
| `CLASSES_PATH` | Path to class labels | `classes.json` |
| `CONFIDENCE_THRESHOLD` | Minimum confidence for detection | `0.90` |
| `MAX_STORED_FILES` | Max images to keep in storage | `100` |

---

## Monitoring

### Prometheus Metrics

Access Prometheus:

* **Docker Compose:** [http://localhost:9090](https://www.google.com/search?q=http://localhost:9090)
* **Kubernetes:** `kubectl port-forward svc/prometheus 9090:9090`

Available metrics:

* `batch_avg_confidence` — Average model confidence per batch
* `target_shapes_found_total` — Counter of detected shapes (all classes)

### Grafana Dashboards

Access Grafana:

* **Docker Compose:** [http://localhost:3000](https://www.google.com/search?q=http://localhost:3000)
* **Kubernetes:** `kubectl port-forward svc/grafana 3000:3000`

Default credentials: `admin` / `admin`

---

## CI/CD

This project uses **GitHub Actions** for continuous integration and delivery.

### Pipeline Overview

| Job | Description |
| --- | --- |
| **Lint & Validate** | Runs flake8 linting and validates docker-compose configuration |
| **Build Image** | Builds Docker image and pushes to GitHub Container Registry |
| **Integration Tests** | Starts infrastructure services and tests connectivity |
| **Security Scan** | Scans for vulnerabilities using Trivy |
| **Release Info** | Generates release summary on successful builds |

---

## Project Structure

```text
Velox/
├── .github/
│   └── workflows/
│       └── ci.yml               # CI/CD pipeline
├── k8s-manifests/               # Kubernetes manifests
├── consumer.py                  # ML inference consumer
├── producer.py                  # Synthetic image generator
├── train.py                     # Model training script
├── start.sh                     # Container entrypoint
├── k8s.sh                       # Kubernetes management (Linux/macOS)
├── k8s.ps1                      # Kubernetes management (Windows)
├── docker-compose.yml           # Docker Compose orchestration
├── Dockerfile                   # Container image definition
└── .env                         # Environment configuration

```

---

## Performance Tuning

### High Throughput (Kubernetes)

```bash
# Ensure 8 Kafka partitions for parallel processing
kubectl exec deployment/kafka -- kafka-topics.sh \
  --alter --topic image_data --partitions 8 \
  --bootstrap-server localhost:29092

# Scale to 8 consumers (or let HPA auto-scale)
kubectl scale deployment consumer --replicas=8

```

---

## Troubleshooting

### Kubernetes Issues

**Pods stuck in Pending (GPU):**

```bash
# Check if GPU slices are available
kubectl get nodes -o jsonpath='{.items[0].status.allocatable.nvidia\.com/gpu}'

# Check device plugin is running
kubectl get pods -n kube-system -l name=nvidia-device-plugin-ds

```

---

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

---

## License

This project is licensed under the MIT License - see the [LICENSE]([https://www.google.com/search?q=LICENSE](https://github.com/atharva-m/Velox/LICENSE) file for details.

---

<div align="center">

**Built with ❤️ using PyTorch, Kafka, Kubernetes, and Docker**

</div>
