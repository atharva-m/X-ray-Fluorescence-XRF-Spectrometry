<div align="center">

# Velox

**Distributed Real-Time Inference Pipeline for High-Frequency Data Streams**

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![PyTorch](https://img.shields.io/badge/PyTorch-2.0+-ee4c2c.svg)](https://pytorch.org/)
[![Kafka](https://img.shields.io/badge/Apache%20Kafka-7.4.0-black.svg)](https://kafka.apache.org/)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED.svg)](https://www.docker.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

[Overview](#overview) •
[Architecture](#architecture) •
[Quick Start](#quick-start) •
[Configuration](#configuration) •
[Monitoring](#monitoring) •
[Contributing](#contributing)

</div>

---

## Overview

This project implements a **production-ready, real-time image classification pipeline** using Apache Kafka for stream processing and PyTorch for GPU-accelerated inference. The system is designed to process high-throughput image streams with low latency, making it suitable for applications in computer vision, anomaly detection, and real-time monitoring systems.

### Key Features

- **Real-Time Processing** — Sub-second inference on streaming images via Kafka
- **GPU-Accelerated** — Batched inference using PyTorch with CUDA support
- **Observable** — Built-in Prometheus metrics and Grafana dashboards
- **Containerized** — Fully Dockerized with health checks and dependency management
- **Configurable** — Environment-based configuration for all components
- **Persistent Storage** — MongoDB integration for storing detection results

### Use Cases

- Real-time quality control in manufacturing
- Anomaly detection in video surveillance
- Automated content moderation
- Scientific image analysis pipelines

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│                            KAFKA ML INFERENCE PIPELINE                           │
└──────────────────────────────────────────────────────────────────────────────────┘

┌──────────────┐      ┌──────────────┐      ┌──────────────────────────────────────┐
│              │      │              │      │               CONSUMER               │
│  PRODUCER    │ ---> │    KAFKA     │ ---> │  ┌────────────┐      ┌────────────┐  │
│              │      │              │      │  │  Fetcher   │      │ Inference  │  │
│  Synthetic   │      │  Message     │      │  │  Process   │ ---> |  Process   │  │
│  Image Gen   │      │  Broker      │      │  │            │      │   (GPU)    │  │
└──────────────┘      └──────────────┘      │  └────────────┘      └─────┬──────┘  │
                                            └────────────────────────────|─────────┘
                                                                         |
                      ┌──────────────┐      ┌──────────────┐             |
                      │              │      │              │             |
                      │   GRAFANA    │ <--- │  PROMETHEUS  │ <-----------+
                      │              │      │              │
                      │  Dashboards  │      │   Metrics    │
                      └──────────────┘      └──────────────┘             |
                                                                         |
                                            ┌──────────────┐             |
                                            │              │             |
                                            │   MONGODB    │ <-----------+
                                            │              │
                                            │  Detection   │
                                            │  Storage     │
                                            └──────────────┘


```

### Components

| Component | Description | Technology |
|-----------|-------------|------------|
| **Producer** | Generates synthetic shape images and streams them to Kafka | Python, OpenCV |
| **Consumer** | Multi-process application with network fetcher and GPU inference | PyTorch, CUDA |
| **Kafka** | Distributed message broker for high-throughput streaming | Confluent Kafka |
| **MongoDB** | Document store for persisting detection results | MongoDB |
| **Prometheus** | Time-series metrics collection | Prometheus |
| **Grafana** | Real-time monitoring dashboards | Grafana |

---

## Quick Start

### Prerequisites

- [Docker](https://docs.docker.com/get-docker/) (v20.10+)
- [Docker Compose](https://docs.docker.com/compose/install/) (v2.0+)
- [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html) (for GPU support)

### 1. Clone the Repository

```bash
git clone https://github.com/atharva-m/kafka-ml-inference-pipeline.git
cd kafka-ml-inference-pipeline
```

The default configuration works out of the box for local development.

### 2. Start the Pipeline

Launch all services with Docker Compose:

```bash
docker-compose up -d
```

This will start:
- Zookeeper and Kafka (message broker)
- MongoDB (detection storage)
- Prometheus and Grafana (monitoring)
- Producer (image generator)
- Consumer (ML inference)

### 3. Verify Services

Check that all services are running:

```bash
docker-compose ps
```

Expected output:
```
NAME                    STATUS
data-streaming-kafka-1      Up (healthy)
data-streaming-zookeeper-1  Up (healthy)
data-streaming-mongo-1      Up (healthy)
data-streaming-consumer-1   Up
data-streaming-producer-1   Up
data-streaming-prometheus-1 Up
data-streaming-grafana-1    Up
```

### 4. View Logs

Monitor the inference pipeline:

```bash
# View consumer logs (ML inference)
docker-compose logs -f consumer

# View producer logs (image generation)
docker-compose logs -f producer
```

You should see output like:
```
consumer-1  | 2024-01-15 10:30:45 - INFO - GPU Inference Started
consumer-1  | 2024-01-15 10:30:46 - INFO - TARGET MATCH: red_circle (Conf: 0.98)
consumer-1  | 2024-01-15 10:30:46 - INFO - Saved to database: red_circle
```

---

## Configuration

All configuration is managed through environment variables in the `.env` file.

### Infrastructure

| Variable | Description | Default |
|----------|-------------|---------|
| `KAFKA_BOOTSTRAP_SERVER` | Kafka broker address | `kafka:29092` |
| `KAFKA_TOPIC` | Topic for image streaming | `image_data` |
| `KAFKA_CONSUMER_GROUP` | Consumer group ID | `gpu_cluster_h100` |

### Producer Settings

| Variable | Description | Default |
|----------|-------------|---------|
| `IMG_HEIGHT` | Generated image height | `512` |
| `IMG_WIDTH` | Generated image width | `512` |
| `PRODUCER_INTERVAL` | Delay between messages (seconds) | `0.05` |
| `COLORS_RED` | BGR tuple for red | `(0, 0, 255)` |
| `COLORS_GREEN` | BGR tuple for green | `(0, 255, 0)` |
| `SHAPES` | List of shapes to generate | `["circle", "square"]` |

### Consumer Settings

| Variable | Description | Default |
|----------|-------------|---------|
| `BATCH_SIZE` | Inference batch size | `8` |
| `QUEUE_SIZE` | Internal queue size | `200` |
| `METRICS_PORT` | Prometheus metrics port | `8000` |
| `MODEL_PATH` | Path to model weights | `model.pth` |
| `CLASSES_PATH` | Path to class labels | `classes.json` |

### Training Settings

| Variable | Description | Default |
|----------|-------------|---------|
| `SAMPLES_PER_CLASS` | Training samples per class | `300` |
| `EPOCHS` | Number of training epochs | `3` |

### Database

| Variable | Description | Default |
|----------|-------------|---------|
| `MONGO_URI` | MongoDB connection string | `mongodb://mongo:27017/` |
| `DB_NAME` | Database name | `lab_discovery_db` |
| `STORAGE_PATH` | Path to save detected images | `./discoveries` |

---

## Monitoring

### Prometheus Metrics

Access Prometheus at [http://localhost:9090](http://localhost:9090)

Available metrics:
- `batch_avg_confidence` — Average model confidence per batch
- `target_shapes_found` — Counter of detected target shapes

### Grafana Dashboards

Access Grafana at [http://localhost:3000](http://localhost:3000)

Default credentials:
- **Username:** `admin`
- **Password:** `admin`

#### Setting Up a Dashboard

1. Navigate to **Configuration** → **Data Sources**
2. Add Prometheus with URL: `http://prometheus:9090`
3. Create a new dashboard with the following queries:

```promql
# Average Confidence Over Time
batch_avg_confidence

# Detection Rate (per minute)
rate(target_shapes_found[1m]) * 60
```

---

## Project Structure

```
kafka-ml-inference-pipeline/
├── consumer.py          # Multi-process inference consumer
├── producer.py          # Synthetic image generator
├── train.py             # Model training script
├── start.sh             # Container entrypoint script
├── docker-compose.yml   # Service orchestration
├── Dockerfile           # Container image definition
├── prometheus.yml       # Prometheus configuration
├── requirements.txt     # Python dependencies
├── .env                 # Environment configuration
└── discoveries/         # Saved detection images
```

---

## Development

### Running Without Docker

For local development without Docker:

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Start Kafka and MongoDB separately (or use Docker for infra only)
docker-compose up -d kafka mongo prometheus grafana

# Train the model
python train.py

# Run consumer (in one terminal)
python consumer.py

# Run producer (in another terminal)
python producer.py
```

### Rebuilding After Changes

```bash
# After changing requirements.txt or Dockerfile
docker-compose up --build

# After changing only Python files (with volume mounting)
docker-compose restart consumer producer
```

### Training a New Model

To retrain the model with different parameters:

```bash
# Delete existing model
rm model.pth classes.json

# Restart consumer (triggers training via start.sh)
docker-compose restart consumer
```

Or train manually:

```bash
docker-compose exec consumer python train.py
```

---

## Extending the Pipeline

### Adding New Shapes

1. Update `SHAPES` in `.env`:
   ```
   SHAPES=["circle", "square", "triangle"]
   ```

2. Add drawing logic in `producer.py` and `train.py`:
   ```python
   elif shape == "triangle":
       pts = np.array([...])
       cv2.drawContours(img, [pts], 0, color, -1)
   ```

3. Retrain the model and restart services.

### Adding New Colors

1. Add to `.env`:
   ```
   COLORS_BLUE=(255, 0, 0)
   ```

2. Update the `COLORS` dictionary in `producer.py` and `train.py`.

3. Retrain and restart.

### Changing the Target Detection

Modify the detection logic in `consumer.py`:

```python
# Current: detects red circles
is_target = "red_circle" in clean_label

# Example: detect all blue shapes
is_target = "blue" in clean_label
```

---

## Troubleshooting

### Common Issues

**Kafka connection refused**
```bash
# Ensure Kafka is healthy
docker-compose ps kafka
# Wait for health check to pass before starting producer/consumer
```

**CUDA not available**
```bash
# Verify NVIDIA Container Toolkit is installed
docker run --rm --gpus all nvidia/cuda:11.0-base nvidia-smi
```

**Model not found error**
```bash
# Trigger training by removing existing model
rm model.pth classes.json
docker-compose restart consumer
```

**MongoDB connection failed**
```bash
# Check MongoDB health
docker-compose logs mongo
```

### Viewing Detection Results

```bash
# List saved images
ls -la discoveries/

# Query MongoDB
docker-compose exec mongo mongosh lab_discovery_db --eval "db.shapes_found.find().limit(5)"
```

---

## Performance Tuning

### High Throughput

For maximum throughput, adjust these parameters:

```env
BATCH_SIZE=32           # Larger batches for GPU efficiency
QUEUE_SIZE=500          # Larger buffer for burst handling
PRODUCER_INTERVAL=0.01  # Faster image generation
```

### Low Latency

For minimum latency:

```env
BATCH_SIZE=1            # Process immediately
QUEUE_SIZE=50           # Smaller buffer
```

---

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

---

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

<div align="center">

**Built with ❤️ using PyTorch, Kafka, and Docker**

[Report Bug](https://github.com/atharva-m/kafka-ml-inference-pipeline/issues) •
[Request Feature](https://github.com/atharva-m/kafka-ml-inference-pipeline/issues)

</div>
