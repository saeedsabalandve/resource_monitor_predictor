# Resource Monitor & Predictor Microservice

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Docker](https://img.shields.io/badge/docker-supported-brightgreen.svg)](https://www.docker.com/)

## 📊 Overview

A production-grade microservice for **periodic monitoring** and **predictive analytics** of server resource utilization. Designed for large-scale web services with private server infrastructure, this system captures real-time resource metrics and employs multiple standardized prediction methods to forecast future resource consumption patterns.

### 🎯 Key Features

- **Real-time Resource Monitoring**: CPU, Memory, Disk I/O, Network bandwidth, Process counts
- **Multi-Method Prediction Engine**: ARIMA, Prophet, LSTM, Exponential Smoothing, Linear Regression
- **Periodic Data Collection**: Configurable intervals with adaptive sampling rates
- **Historical Data Storage**: Time-series database integration (InfluxDB/PostgreSQL)
- **RESTful API**: Comprehensive endpoints for metrics querying and predictions
- **Alert System**: Threshold-based notifications for resource anomalies
- **Visualization Dashboard**: Built-in analytics dashboard
- **Horizontal Scaling**: Designed for distributed deployment

### 🏗️ Architecture

┌─────────────────────────────────────────────────────────────┐
│                     API Gateway (FastAPI)                      │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────────┐ │
│  │  Collector   │  │  Predictor   │  │  Alert Manager     │ │
│  │  Service     │  │  Engine      │  │                    │ │
│  └─────────────┘  └──────────────┘  └────────────────────┘ │
├─────────────────────────────────────────────────────────────┤
│              Time-Series Database (InfluxDB)                  │
├─────────────────────────────────────────────────────────────┤
│              Message Queue (Redis/RabbitMQ)                   │
└─────────────────────────────────────────────────────────────┘

## 🚀 Quick Start

### Prerequisites
- Python 3.9+
- Docker & Docker Compose (optional)
- Redis (for task queue)
- InfluxDB or PostgreSQL

### Installation

```bash
# Clone repository
git clone https://github.com/yourusername/resource-monitor-predictor.git
cd resource-monitor-predictor

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your settings

# Initialize database
python scripts/init_db.py

# Run the service
python src/main.py
```

Docker Deployment

```bash
# Build and run with Docker Compose
docker-compose up -d

# View logs
docker-compose logs -f
```

📈 Prediction Methods

Method Description Best For Accuracy
ARIMA Auto-Regressive Integrated Moving Average Stationary time series High
Prophet Facebook's time series forecasting Seasonal patterns Very High
LSTM Long Short-Term Memory neural network Complex patterns Highest
Exponential Smoothing Weighted moving average Short-term trends Medium
Linear Regression Simple linear trend analysis Linear patterns Medium

🔧 API Endpoints

Metrics Collection

GET    /api/v1/metrics/current          # Current resource usage
POST   /api/v1/metrics/collect          # Trigger manual collection
GET    /api/v1/metrics/history          # Historical data query

Prediction
GET    /api/v1/predict/{resource}       # Get predictions for resource
POST   /api/v1/predict/generate         # Generate new predictions
GET    /api/v1/predict/accuracy         # Model accuracy metrics

System
GET    /api/v1/health                   # Health check
GET    /api/v1/status                   # Service status

Dashboard
Access the monitoring dashboard at http://localhost:8000/dashboard

Testing

```bash
# Run all tests
pytest

# Run specific test suite
pytest tests/test_collector.py
pytest tests/test_predictor.py

# With coverage
pytest --cov=src tests/
```

🔒 Security

· All API endpoints require authentication (JWT tokens)
· Data encryption at rest and in transit
· Rate limiting implemented
· Regular security audits

Configuration
Key configuration options in .env:

# Server Configuration
SERVER_HOST=0.0.0.0
SERVER_PORT=8000

# Database Configuration
INFLUXDB_URL=http://localhost:8086
INFLUXDB_TOKEN=your_token
INFLUXDB_ORG=your_org
INFLUXDB_BUCKET=resource_metrics

# Collection Intervals (seconds)
CPU_COLLECTION_INTERVAL=10
MEMORY_COLLECTION_INTERVAL=10
DISK_COLLECTION_INTERVAL=60
NETWORK_COLLECTION_INTERVAL=30

# Prediction Configuration
PREDICTION_HORIZON=3600  # 1 hour
RETRAIN_INTERVAL=86400   # 24 hours
