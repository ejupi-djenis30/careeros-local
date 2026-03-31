# Job Hunter AI - Backend

The **Job Hunter AI** backend is a high-performance, asynchronous API designed to orchestrate the entire job search lifecycle. Built with **FastAPI** and **Python 3.12+**, it leverages advanced LLM integrations and a structured search pipeline to automate job discovery, normalization, and deep profile matching.

---

## 🛠️ Tech Stack

- **Core Framework**: [FastAPI](https://fastapi.tiangolo.com/) (Asynchronous, Type-safe)
- **Data Validation**: [Pydantic v2](https://docs.pydantic.dev/)
- **ORM & Database**: [SQLAlchemy 2.0](https://www.sqlalchemy.org/) with [Alembic](https://alembic.sqlalchemy.org/) for migrations.
- **Authentication**: JWT (JSON Web Tokens) with [PyJWT](https://pyjwt.readthedocs.io/) and [Passlib](https://passlib.readthedocs.io/).
- **LLM Engine**: Provider-agnostic integrations for Gemini, OpenAI-compatible APIs, Ollama, and g4f.
- **Task Scheduling**: [APScheduler](https://apscheduler.readthedocs.io/) for background maintenance and automated searches.
- **HTTP Client**: [HTTPX](https://github.com/encode/httpx) with HTTP/2 support and [Tenacity](https://tenacity.readthedocs.io/) for robust retries.
- **Semantic Analysis**: [Sentence-Transformers](https://www.sbert.net/) for local embedding-based skill matching.
- **File Processing**: [PyMuPDF](https://pymupdf.readthedocs.io/) for high-fidelity CV parsing.

---

## 🏗️ Technical Architecture

The backend implements a **Clean Architecture** with a strict separation of concerns into four primary layers:

### 1. API Layer (`backend/api`)
- **Transport**: Handles HTTP requests, response serialization, and dependency injection.
- **Routing**: Modular routers organized by domain (Auth, Search, Jobs, Profiles).
- **Security**: Implements JWT verification, role-based access control, and rate limiting via **SlowAPI**.

### 2. Service Layer (`backend/services`)
- **Business Logic**: This is the "brain" of the application. It orchestrates complex workflows like the Search Pipeline.
- **Search Status**: A real-time monitoring system that tracks the progress of asynchronous tasks using a reservation lifecycle (`reserve_task`/`release_task`).
- **LLM Coordination**: Manages prompt templating, response parsing, and fallback strategies for different AI providers.

### 3. Repository Layer (`backend/repositories`)
- **Data Persistence**: Implements the **Repository Pattern** to decouple the service layer from the database engine.
- **Abstraction**: Services interact with abstract repository interfaces, allowing for easy testing and potential database swaps in the future.

### 4. Provider Layer (`backend/providers`)
- **External Integrations**: Contains specialized drivers for external APIs.
- **Job Scrapers**: Modular adapters for various job platforms (SwissDevJobs, JobRoom, etc.) implementing a common `BaseScraper` interface.
- **LLM Factory**: A provider factory that dynamically instantiates the correct LLM client (Gemini, OpenAI-compatible, Ollama, g4f) based on configuration.

---

## 🔍 Technical Flow: The Search Pipeline

The core value of Job Hunter AI lies in its sophisticated **6-step Search Pipeline**, designed for maximum precision and resource efficiency:

1.  **Direct Fetch & Deduplication**: The system triggers multiple scrapers simultaneously. Jobs are fetched and immediately deduplicated using unique URL signatures and normalized identifiers.
2.  **Persistence**: Raw job data is saved to a shared `ScrapedJob` repository to avoid re-scraping the same listings in future runs.
3.  **Normalization (LLM-Driven)**: Jobs pass through an LLM-assisted normalization layer. This transforms messy, unstructured job descriptions into standardized fields:
    -   **Seniority**: (Junior, Mid, Senior, Lead)
    -   **Required Skills**: (Extracted and standardized)
    -   **Work Model**: (On-site, Remote, Hybrid)
4.  **Structured Filtering**: Before expensive analysis, the system applies "Rigid Filters" based on the user's profile (e.g., "Exclude if years of experience > 5" or "Require C#").
5.  **Deep Match Analysis (LLM MATCH)**: The surviving jobs undergo a comprehensive analysis. The system compares the user's CV/Profile against the full job requirements to generate:
    -   **Affinity Score (0-100)**: A weighted probability of recruitment success.
    -   **Detailed Reasoning**: Why the job is (or isn't) a good fit.
6.  **User-Job Binding**: The final results are linked to the specific user search, marked with state triggers for the frontend notifications.

---

## 🚀 Development & Setup

### Requirements
- Python 3.12+
- Docker & Docker Compose (Recommended)

### Local Environment
1.  **Install Dependencies**:
    ```bash
    pip install -r requirements.txt
    ```
2.  **Configure Environment**:
    -   Copy `.env.example` to `.env`.
    -   Configure your database URL and LLM API keys (GEMINI_API_KEY).
3.  **Run Migrations**:
    ```bash
    alembic upgrade head
    ```
4.  **Start Server**:
    ```bash
    python run.py
    ```
    *The API will be available at `http://localhost:8000` with interactive docs at `/docs`.*

---

## 🧪 Testing Strategy

The project maintains a high coverage suite using **Pytest**:
-   **Unit Tests**: Isolated testing of business logic in the service layer.
-   **Integration Tests**: Validating the repository layer and database interactions.
-   **E2E API Tests**: Simulating full request/response cycles using `httpx.AsyncClient`.

Run tests with:
```bash
pytest
```

---

## 📐 Design Principles
- **Agnostic Logic**: The system is designed to be provider-agnostic; adding a new LLM or Job Scraper requires only a new class in the Provider Layer.
- **Concurrency First**: Utilizing `asyncio` for non-blocking I/O during heavy scraping and LLM operations.
- **Resilient Execution**: Uses Circuit Breakers and Retry mechanisms to handle unstable external APIs.
