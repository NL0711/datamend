# M0 Scaffolding & Environment Architecture Plan: SkyGuard AI

## 1. Executive Summary & Problem Boundary

SkyGuard AI is a production-grade, real-time meteorological anomaly detection and sensor health monitoring platform. Milestone M0 (Phase 0 of `TODO.md`) establishes the complete repository foundation, configuration files, backend and frontend directory structures, dependency management, initial FastAPI entrypoint, initial React/Vite/Tailwind frontend shell, and baseline test suite.

This document specifies the exact directory layout, configuration files, dependencies, code templates, and execution boundaries for the implementation worker agent.

---

## 2. Environment & Dependency Specifications

### 2.1 Python Environment (`requirements.txt`)
Target Python version: Python 3.10+ (recommended: 3.10 / 3.11 / 3.12).

The core dependencies cover web serving, asynchronous APIs, database ORM, data science, machine learning (classical and deep learning), explainability, and testing:

```text
# Web & API Framework
fastapi>=0.110.0,<0.116.0
uvicorn[standard]>=0.28.0,<0.35.0
pydantic>=2.6.0,<3.0.0
pydantic-settings>=2.2.0,<3.0.0
python-multipart>=0.0.9,<0.1.0
websockets>=12.0,<14.0

# Database & Async ORM
sqlalchemy>=2.0.28,<2.1.0
aiosqlite>=0.20.0,<0.21.0

# Data Processing & Numerics
numpy>=1.26.0,<2.0.0
pandas>=2.2.0,<3.0.0
scipy>=1.12.0,<2.0.0

# Machine Learning & AI
scikit-learn>=1.4.0,<1.6.0
torch>=2.2.0,<2.6.0
shap>=0.45.0,<0.47.0
joblib>=1.3.2,<1.5.0

# Testing & Utilities
pytest>=8.0.0,<9.0.0
pytest-asyncio>=0.23.0,<0.25.0
httpx>=0.27.0,<0.29.0
```

### 2.2 Frontend Environment (`frontend/package.json`)
Target Node.js version: Node 18+ (LTS). Package manager: `npm`.
Frontend stack: React 18, TypeScript, Vite 5, Tailwind CSS 3, Recharts 2, Lucide React.

```json
{
  "name": "skyguard-frontend",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc && vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "clsx": "^2.1.0",
    "lucide-react": "^0.344.0",
    "react": "^18.2.0",
    "react-dom": "^18.2.0",
    "recharts": "^2.12.2",
    "tailwind-merge": "^2.2.1"
  },
  "devDependencies": {
    "@types/react": "^18.2.66",
    "@types/react-dom": "^18.2.22",
    "@vitejs/plugin-react": "^4.2.1",
    "autoprefixer": "^10.4.18",
    "postcss": "^8.4.35",
    "tailwindcss": "^3.4.1",
    "typescript": "^5.2.2",
    "vite": "^5.1.6"
  }
}
```

---

## 3. Complete Target Directory Tree

```text
c:\Users\ARYAN - AYUSH\OneDrive\Desktop\skyguard\
├── .env.example
├── .gitignore
├── Dockerfile.backend
├── Dockerfile.frontend
├── README.md
├── docker-compose.yml
├── requirements.txt
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── config.py
│   │   ├── main.py
│   │   ├── api/
│   │   │   ├── __init__.py
│   │   │   ├── routes.py
│   │   │   └── websocket.py
│   │   ├── db/
│   │   │   ├── __init__.py
│   │   │   ├── database.py
│   │   │   ├── models.py
│   │   │   └── repositories.py
│   │   ├── ml/
│   │   │   ├── __init__.py
│   │   │   ├── fusion.py
│   │   │   ├── pipeline.py
│   │   │   ├── preprocessor.py
│   │   │   ├── tier1_qc.py
│   │   │   ├── tier2_point_ml.py
│   │   │   ├── tier2_temporal_ml.py
│   │   │   ├── tier3_multivariate.py
│   │   │   ├── tier4_classifier.py
│   │   │   ├── tier5_explain.py
│   │   │   └── tier5_health.py
│   │   └── services/
│   │       ├── __init__.py
│   │       ├── analytics_service.py
│   │       ├── ingestion_service.py
│   │       └── simulation_service.py
│   └── simulator/
│       ├── __init__.py
│       ├── anomaly_injector.py
│       ├── cli.py
│       ├── diurnal_generator.py
│       └── scenarios.py
├── data/
│   └── .gitkeep
├── docs/
│   └── evaluation_report.md
├── frontend/
│   ├── index.html
│   ├── package.json
│   ├── postcss.config.js
│   ├── tailwind.config.js
│   ├── tsconfig.json
│   ├── tsconfig.node.json
│   ├── vite.config.ts
│   └── src/
│       ├── App.tsx
│       ├── index.css
│       ├── main.tsx
│       ├── components/
│       │   ├── AlertCenterView.tsx
│       │   ├── AnomalyInjectorUI.tsx
│       │   ├── DataExplorerView.tsx
│       │   ├── EventDetailView.tsx
│       │   ├── ExplainabilityViewer.tsx
│       │   ├── LiveMonitoringView.tsx
│       │   ├── OverviewView.tsx
│       │   └── SensorHealthView.tsx
│       ├── services/
│       │   ├── api.ts
│       │   └── websocket.ts
│       └── types/
│           └── index.ts
├── models/
│   └── .gitkeep
├── scripts/
│   ├── generate_datasets.py
│   ├── test_anomaly_detection.py
│   └── train_models.py
└── tests/
    ├── __init__.py
    ├── conftest.py
    ├── test_api.py
    ├── test_edge_cases.py
    ├── test_fusion.py
    ├── test_ingestion.py
    ├── test_sanity.py
    ├── test_simulator.py
    ├── test_tier1_qc.py
    ├── test_tier2_ml.py
    ├── test_tier3_multivariate.py
    ├── test_tier4_classifier.py
    └── test_tier5_health_explain.py
```

---

## 4. Initial File Templates & Exact Implementations for M0

The implementation worker should create each file with clean, production-grade boilerplate.

### 4.1 Root Configuration Files

#### `.gitignore`
```gitignore
# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
env/
venv/
.venv/
ENV/
build/
develop-eggs/
dist/
downloads/
eggs/
.eggs/
lib/
lib64/
parts/
sdist/
var/
wheels/
*.egg-info/
.installed.cfg
*.egg

# Testing & Coverage
.pytest_cache/
.coverage
htmlcov/
.tox/
.nox/

# Machine Learning Artifacts & SQLite DB
*.pkl
*.joblib
*.pt
*.pth
*.onnx
*.sqlite3
*.db
backend/skyguard.db

# Frontend / Node
frontend/node_modules/
frontend/dist/
frontend/.vite/
npm-debug.log*
yarn-debug.log*
yarn-error.log*

# Environment & IDE
.env
.env.local
.vscode/
.idea/
*.swp
*.swo
.DS_Store

# Agent Metadata (keep tracking minimal)
.agents/*/BRIEFING_ARCHIVE.md
```

#### `.env.example`
```env
# SkyGuard AI Environment Configuration
PROJECT_NAME="SkyGuard AI"
ENVIRONMENT="development"
DEBUG=True

# Backend Server
HOST="0.0.0.0"
PORT=8000
CORS_ORIGINS="http://localhost:5173,http://127.0.0.1:5173"

# Database
DATABASE_URL="sqlite+aiosqlite:///./skyguard.db"

# ML Pipeline Settings
INFERENCE_WINDOW_SIZE=30
HEALTH_ROLLING_WINDOW=288
HEALTH_EMA_ALPHA=0.10
ANOMALY_THRESHOLD=0.50
```

#### `Dockerfile.backend`
```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install build essentials for C-extensions if needed
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./backend/
COPY scripts/ ./scripts/

ENV PYTHONPATH=/app

EXPOSE 8000

CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

#### `Dockerfile.frontend`
```dockerfile
FROM node:18-alpine AS builder

WORKDIR /app
COPY frontend/package*.json ./
RUN npm install

COPY frontend/ ./
RUN npm run build

FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
```

#### `docker-compose.yml`
```yaml
version: '3.8'

services:
  backend:
    build:
      context: .
      dockerfile: Dockerfile.backend
    ports:
      - "8000:8000"
    environment:
      - ENVIRONMENT=production
      - DATABASE_URL=sqlite+aiosqlite:///./skyguard.db
    volumes:
      - ./data:/app/data
      - ./models:/app/models

  frontend:
    build:
      context: .
      dockerfile: Dockerfile.frontend
    ports:
      - "5173:80"
    depends_on:
      - backend
```

#### `README.md`
```markdown
# SkyGuard AI — Intelligent Real-Time Anomaly Detection & Sensor Health for AWS

SkyGuard AI is a production-grade, real-time meteorological anomaly detection, fault classification, explainability, and sensor health monitoring platform for Automatic Weather Stations (AWS).

## Key Capabilities
- **Physics-Informed Quality Control (Tier 1)**: WMO range bounds, rate-of-change, and persistence checks.
- **Multivariate ML & Deep Learning (Tier 2-3)**: Isolation Forest point detector, PyTorch GRU/LSTM Autoencoder temporal detector, Clausius-Clapeyron physical dew-point consistency, and Mahalanobis covariance distance.
- **Fault Taxonomy Classification (Tier 4)**: Differentiates SPIKE, DRIFT, FROZEN, DROPOUT, MULTIVARIATE_INCONSISTENCY, DATA_CORRUPTION, and METEOROLOGICAL_EXTREMES.
- **Sensor Health Index & Explainability (Tier 5)**: Rolling 24h Sensor Health score (0-100) and TreeSHAP/feature attribution explanations.
- **Operational Dashboard**: Real-time telemetry monitoring, alert center, interactive on-the-fly anomaly injector UI, and live WebSocket streaming.

## Getting Started

### 1. Backend Setup
```bash
# Create virtual environment
python -m venv venv
# On Windows:
.\venv\Scripts\activate
# On Linux/macOS:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run tests
pytest tests/ -v

# Start FastAPI backend
uvicorn backend.app.main:app --reload --port 8000
```

### 2. Frontend Setup
```bash
cd frontend
npm install
npm run dev
```

### 3. Docker Deployment
```bash
docker-compose up --build
```
```

---

### 4.2 Backend Implementation Files for M0

#### `backend/app/config.py`
```python
from pydantic_settings import BaseSettings
from typing import List

class Settings(BaseSettings):
    PROJECT_NAME: str = "SkyGuard AI"
    VERSION: str = "0.1.0"
    API_PREFIX: str = "/api"
    DEBUG: bool = True
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    CORS_ORIGINS: List[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
    ]
    DATABASE_URL: str = "sqlite+aiosqlite:///./skyguard.db"

    # ML Pipeline defaults
    INFERENCE_WINDOW_SIZE: int = 30
    HEALTH_ROLLING_WINDOW: int = 288
    HEALTH_EMA_ALPHA: float = 0.10
    ANOMALY_THRESHOLD: float = 0.50

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()
```

#### `backend/app/main.py`
```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.app.config import settings

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="SkyGuard AI Real-Time Anomaly Detection & Sensor Health System",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return {
        "status": "online",
        "project": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "docs_url": "/docs"
    }

@app.get("/api/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "backend",
        "version": settings.VERSION
    }
```

---

### 4.3 Frontend Configuration & Boilerplate for M0

#### `frontend/vite.config.ts`
```typescript
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/ws': {
        target: 'ws://localhost:8000',
        ws: true,
      },
    },
  },
});
```

#### `frontend/tsconfig.json`
```json
{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true
  },
  "include": ["src"],
  "references": [{ "path": "./tsconfig.node.json" }]
}
```

#### `frontend/tsconfig.node.json`
```json
{
  "compilerOptions": {
    "composite": true,
    "skipLibCheck": true,
    "module": "ESNext",
    "moduleResolution": "bundler",
    "allowSyntheticDefaultImports": true
  },
  "include": ["vite.config.ts"]
}
```

#### `frontend/tailwind.config.js`
```javascript
/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        skyguard: {
          bg: '#0f172a',
          card: '#1e293b',
          border: '#334155',
          primary: '#38bdf8',
          accent: '#0284c7',
          success: '#10b981',
          warning: '#f59e0b',
          danger: '#ef4444',
        }
      }
    },
  },
  plugins: [],
}
```

#### `frontend/postcss.config.js`
```javascript
export default {
  plugins: {
    tailwindcss: {},
    autoprefixer: {},
  },
}
```

#### `frontend/index.html`
```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <link rel="icon" type="image/svg+xml" href="/vite.svg" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>SkyGuard AI — Meteorological AWS Monitoring</title>
  </head>
  <body class="bg-slate-950 text-slate-100 min-h-screen">
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

#### `frontend/src/index.css`
```css
@tailwind base;
@tailwind components;
@tailwind utilities;

body {
  margin: 0;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
  background-color: #090d16;
  color: #f1f5f9;
}
```

#### `frontend/src/types/index.ts`
```typescript
export interface Observation {
  timestamp: string;
  station_id: string;
  temperature: number;
  pressure: number;
  humidity: number;
  latitude?: number;
  longitude?: number;
  elevation?: number;
}

export interface ContributingFeature {
  feature: string;
  attribution: number;
}

export interface AnomalyExplanation {
  summary: string;
  contributing_features: ContributingFeature[];
}

export interface TierScores {
  tier1_qc_flag: boolean;
  tier2_point_score: number;
  tier2_temporal_score: number;
  tier3_multivariate_score: number;
}

export interface InferenceResult {
  timestamp: string;
  station_id: string;
  is_anomaly: boolean;
  anomaly_score: number;
  confidence: number;
  severity: 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL' | 'NORMAL';
  classification: string;
  explanation: AnomalyExplanation;
  tier_scores: TierScores;
  sensor_health: number;
  recommended_action?: string;
}

export interface Station {
  id?: number;
  station_id: string;
  name: string;
  latitude: number;
  longitude: number;
  elevation: number;
  status: string;
}
```

#### `frontend/src/App.tsx`
```tsx
import React, { useState } from 'react';
import { Activity, AlertTriangle, ShieldCheck, Cpu, Database, Eye, Terminal, Radio } from 'lucide-react';

export default function App() {
  const [activeTab, setActiveTab] = useState<'overview' | 'live' | 'alerts' | 'health' | 'events' | 'explorer' | 'injector' | 'explainability'>('overview');

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col font-sans">
      {/* Header */}
      <header className="border-b border-slate-800 bg-slate-900/80 backdrop-blur px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-sky-500/10 border border-sky-500/30 rounded-lg text-sky-400">
            <Radio className="w-6 h-6 animate-pulse" />
          </div>
          <div>
            <h1 className="text-xl font-bold tracking-tight text-white flex items-center gap-2">
              SkyGuard <span className="text-sky-400">AI</span>
            </h1>
            <p className="text-xs text-slate-400">Real-Time Anomaly Detection & Sensor Health for AWS</p>
          </div>
        </div>
        <div className="flex items-center gap-4 text-xs">
          <div className="flex items-center gap-2 bg-emerald-500/10 border border-emerald-500/30 px-3 py-1.5 rounded-full text-emerald-400">
            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-ping"></span>
            System Live
          </div>
        </div>
      </header>

      {/* Nav Tabs */}
      <nav className="flex border-b border-slate-800 bg-slate-900/40 px-6 gap-2 overflow-x-auto">
        {[
          { id: 'overview', label: 'Overview', icon: Activity },
          { id: 'live', label: 'Live Monitoring', icon: Eye },
          { id: 'alerts', label: 'Alert Center', icon: AlertTriangle },
          { id: 'health', label: 'Sensor Health', icon: ShieldCheck },
          { id: 'events', label: 'Event Detail', icon: Cpu },
          { id: 'explorer', label: 'Data Explorer', icon: Database },
          { id: 'injector', label: 'Anomaly Injector', icon: Terminal },
          { id: 'explainability', label: 'Explainability', icon: Cpu },
        ].map((tab) => {
          const Icon = tab.icon;
          const isActive = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id as any)}
              className={`flex items-center gap-2 px-4 py-3 text-sm font-medium border-b-2 transition-colors ${
                isActive
                  ? 'border-sky-400 text-sky-400 bg-sky-500/5'
                  : 'border-transparent text-slate-400 hover:text-slate-200 hover:border-slate-700'
              }`}
            >
              <Icon className="w-4 h-4" />
              {tab.label}
            </button>
          );
        })}
      </nav>

      {/* Main Content Area */}
      <main className="flex-1 p-6">
        <div className="p-8 border border-slate-800 bg-slate-900/50 rounded-xl">
          <h2 className="text-lg font-semibold text-slate-200 capitalize">{activeTab} View</h2>
          <p className="text-sm text-slate-400 mt-2">
            SkyGuard AI scaffolded successfully. Active view: <span className="text-sky-400 font-mono">{activeTab}</span>.
          </p>
        </div>
      </main>
    </div>
  );
}
```

#### `frontend/src/main.tsx`
```tsx
import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import './index.css';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
```

---

### 4.4 Test Framework Baseline for M0

#### `tests/conftest.py`
```python
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from backend.app.main import app

@pytest_asyncio.fixture
async def async_client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
```

#### `tests/test_sanity.py`
```python
import pytest
from backend.app.config import settings

@pytest.mark.asyncio
async def test_root_endpoint(async_client):
    response = await async_client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "online"
    assert data["project"] == settings.PROJECT_NAME

@pytest.mark.asyncio
async def test_health_check_endpoint(async_client):
    response = await async_client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "backend"

def test_settings_load():
    assert settings.PROJECT_NAME == "SkyGuard AI"
    assert settings.INFERENCE_WINDOW_SIZE == 30
    assert settings.HEALTH_ROLLING_WINDOW == 288
```

---

## 5. File Boundaries & Explicit Instructions for Worker

The worker agent assigned to implement Milestone M0 should perform the following actions:

1. **Create Python Dependencies**:
   - Write `requirements.txt` at the repository root.
2. **Create Project Configuration & Metadata**:
   - Write `.gitignore`, `.env.example`, `README.md`, `Dockerfile.backend`, `Dockerfile.frontend`, `docker-compose.yml`.
3. **Create Backend Module Structure**:
   - Create directories: `backend/app/api`, `backend/app/db`, `backend/app/ml`, `backend/app/services`, `backend/simulator`.
   - Write `__init__.py` files in all backend directories.
   - Write `backend/app/config.py` and `backend/app/main.py`.
   - Stub module files with docstrings and pass/placeholder declarations so imports work cleanly:
     - `backend/app/api/routes.py`, `backend/app/api/websocket.py`
     - `backend/app/db/database.py`, `backend/app/db/models.py`, `backend/app/db/repositories.py`
     - `backend/app/ml/tier1_qc.py`, `backend/app/ml/tier2_point_ml.py`, `backend/app/ml/tier2_temporal_ml.py`, `backend/app/ml/tier3_multivariate.py`, `backend/app/ml/tier4_classifier.py`, `backend/app/ml/tier5_health.py`, `backend/app/ml/tier5_explain.py`, `backend/app/ml/fusion.py`, `backend/app/ml/preprocessor.py`, `backend/app/ml/pipeline.py`
     - `backend/app/services/ingestion_service.py`, `backend/app/services/simulation_service.py`, `backend/app/services/analytics_service.py`
     - `backend/simulator/diurnal_generator.py`, `backend/simulator/anomaly_injector.py`, `backend/simulator/scenarios.py`, `backend/simulator/cli.py`
4. **Create Data, Models, Docs, and Scripts Placeholders**:
   - `data/.gitkeep`, `models/.gitkeep`
   - `docs/evaluation_report.md`
   - `scripts/generate_datasets.py`, `scripts/train_models.py`, `scripts/test_anomaly_detection.py`
5. **Create Frontend Structure**:
   - Create `frontend/` and subdirectories (`src/components`, `src/services`, `src/types`).
   - Write `frontend/package.json`, `frontend/tsconfig.json`, `frontend/tsconfig.node.json`, `frontend/vite.config.ts`, `frontend/tailwind.config.js`, `frontend/postcss.config.js`, `frontend/index.html`.
   - Write `frontend/src/index.css`, `frontend/src/main.tsx`, `frontend/src/App.tsx`, `frontend/src/types/index.ts`.
   - Stub component and service files:
     - `frontend/src/services/api.ts`, `frontend/src/services/websocket.ts`
     - `frontend/src/components/OverviewView.tsx`, `LiveMonitoringView.tsx`, `AlertCenterView.tsx`, `SensorHealthView.tsx`, `EventDetailView.tsx`, `DataExplorerView.tsx`, `AnomalyInjectorUI.tsx`, `ExplainabilityViewer.tsx`
6. **Create Test Suite Baseline**:
   - Create `tests/` directory with `__init__.py`.
   - Write `tests/conftest.py` and `tests/test_sanity.py`.
   - Create test stubs for downstream milestones:
     - `test_simulator.py`, `test_tier1_qc.py`, `test_tier2_ml.py`, `test_tier3_multivariate.py`, `test_tier4_classifier.py`, `test_tier5_health_explain.py`, `test_fusion.py`, `test_api.py`, `test_ingestion.py`, `test_edge_cases.py`.
7. **Verify & Test**:
   - Execute `pytest tests/test_sanity.py -v` (or full `pytest tests/ -v`).

---

## 6. Exit Criteria for Milestone M0

- [x] All required project directories are created.
- [x] `requirements.txt` contains pinned/bounded modern dependencies (FastAPI, PyTorch, Scikit-learn, SHAP, etc.).
- [x] `frontend/package.json` and Vite/Tailwind configuration files exist.
- [x] Initial FastAPI entrypoint with CORS and healthcheck endpoints is implemented.
- [x] Base React application shell mounts and renders cleanly.
- [x] Baseline test fixtures and sanity test (`tests/test_sanity.py`) are ready to execute.
