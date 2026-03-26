# **Guidelines for AI Agents: Job Hunter AI**

Welcome, AI Agent. Follow these rules to keep implementations reliable, testable, and aligned with the current architecture.

## **1. Absolute Objectivity, Truthfulness, and Completeness (CRITICAL)**

*   **Do not invent success:** If a test fails, state clearly that it failed. NEVER hallucinate or pretend that tests passed when they did not. 
*   **Do not invent functionality:** If something is broken, report it as broken. Do not assume an implementation works without verification.
*   **Do not invent skills:** If you lack the necessary context to develop a specific feature safely, explicitly state "I cannot do this reliably."
*   **No placeholders:** Never use placeholders like `// ...` or `TODO` instead of real implementation.

## **2. Workspace, Logging, and Temporary Files**

The `cmd_outputs/` directory is your designated safe workspace and scratchpad. It is ignored by Git (`.gitignore`).

*   **Command Logging:** Redirect significant terminal output to `cmd_outputs/` (example: `npm run build > cmd_outputs/frontend_build.log 2>&1`).
*   **Verification:** After logging a command, read the log file to verify success instead of relying solely on truncated snapshot outputs.
*   **Temporary & Utility Files:** Use `cmd_outputs/` to store temporary text dumps, JSON API payloads, data validations, or utility scripts that are not meant to be integrated into the final `Job Hunter AI` production codebase. Do not pollute the root directory.

## **3. Git Workflow & Branching Strategy**

You must adhere to a clean and safe Git workflow to protect the stability of the application.

*   **Branching for large/risky features:** Do not work directly on `main`/`master` for major changes. Create an isolated branch.
*   **Local Testing Requisite:** Write the necessary unit or integration tests for the new feature while on the branch. Validate that *all* existing project tests still pass.
*   **Merging:** Only after finishing the feature entirely and testing it locally should you merge the branch back into `master`/`main` (or instruct the user that it is safe to do so).
*   **Commit Atomicity:** Keep your commits logical and organized. Use descriptive commit messages detailing *what* changed and *why*.

## **4. Testing and Deployment Philosophy**

*   **Docker First:** Prefer Docker (`docker-compose up -d --build`) for full-stack validation.
*   **Manual Fallback:** Only if Docker setup fails fundamentally, run frontend/backend manually.
*   **Test Integrity:** Before concluding implementation, run relevant backend/frontend tests and verify logs.
*   **CI/CD Pipeline Awareness:** Consider how your code modifications interact with the GitHub Actions pipelines defined in `.github/workflows/ci.yml`. If you create a new suite of tests, ensure they are registered in the CI configuration so they run automatically on the user's PRs.

## **5. Project Architecture Principles**

Job Hunter AI employs a strict separation of concerns. Monolithic files are strictly forbidden unless temporary.

### **Backend (FastAPI & Clean Architecture)**
*   **API Layer (`backend/api/routes/`)**: Pure HTTP transport layer. Handles receiving requests and Pydantic validation via dependencies. No business logic.
*   **Service Layer (`backend/services/`)**: The core business rules and orchestration engines (e.g., LLM generation coordination, job lifecycle execution).
*   **Repository Layer (`backend/repositories/`)**: Abstract data persistence implementing the Repository Pattern. Decouples Services from SQLAlchemy.
*   **Provider Layer (`backend/providers/`)**: External world integrations (e.g., LLM API clients, target Web Scrapers).
*   **Schemas & Models**: Pydantic validation goes in `backend/schemas/`. SQLAlchemy ORM mapping goes in `backend/models/`.
*   **Search Runtime Rule:** Current pipeline is normalization-first:
	1) fetch + deduplicate,
	2) persist to shared `ScrapedJob`,
	3) normalize (`provider_bootstrap` then LLM NORMALIZE step),
	4) structured filtering via normalized fields (domain, seniority, qualification, experience, skills),
	5) deep analysis (MATCH step) and user-job save.
	Normalization is the **sole gatekeeper** before the expensive MATCH step — there is no separate RELEVANCE or SUMMARY step.
*   **Search Task Concurrency Rule:** Use reservation lifecycle (`reserve_task`/`release_task`) around background search task startup to prevent duplicate concurrent runs.

### **Frontend (React 19 & Vite)**
*   **Component Structure**: We use React with Vite. Keep components extremely small and functionally focused (Single Responsibility). If a component exceeds 15KB or ~150 lines, plan to extract its sub-elements.
*   **State Management**: Use the Context API (`AuthContext`, `SearchContext`) for global polling and state propagation.
*   **Styling**: Rely heavily on vanilla CSS architecture or existing UI frameworks imported within the project, aiming for modern glassmorphism or sleek, responsive standard designs. 

## **6. General Working Rules**

*   **Context Discovery:** Read `README.md` before changing core domain logic (LLM prompts, scoring, normalization, or filtering behavior).
*   **Reuse Existing Tools:** Do not reinvent the wheel. Check `backend/services/utils.py` and existing database helpers before proposing new utility functions.
*   **Database Schema Evolutions:** If you encounter a database schema issue or add a new SQLAlchemy column during development, perform the necessary Alembic migrations. Alternatively, if testing on a totally fresh, stateless run (and explicit permission is granted), you may wipe the Docker volumes (`docker-compose down -v`) to reset the schema.

**Acknowledge these rules intrinsically before you proceed with code execution.**