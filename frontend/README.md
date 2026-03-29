# Job Hunter AI - Frontend

The **Job Hunter AI** frontend is a modern and dynamic interface designed to simplify the job search process. Built as a **Single Page Application (SPA)** using **React 19** and **Vite**, it is optimized for high performance, responsiveness, and a seamless user experience.

---

## 🛠️ Tech Stack

- **Core**: [React 19](https://react.dev/)
- **Build Tool**: [Vite](https://vitejs.dev/)
- **Routing**: [React Router 7](https://reactrouter.com/)
- **UI & Styling**: [Bootstrap 5](https://getbootstrap.com/), [Bootstrap Icons](https://icons.getbootstrap.com/), and custom Vanilla CSS.
- **Testing**: [Vitest](https://vitest.dev/) & [React Testing Library](https://testing-library.com/docs/react-testing-library/intro/)
- **Code Quality**: [ESLint](https://eslint.org/)

---

## 🏗️ Technical Architecture

The project follows a modular structure based on clear separation of concerns:

### 1. State Management (Context API)
We use the **React Context API** to manage global state without the overhead of external libraries:
- **`AuthContext`**: Manages user identity, JWT token persistence, and login/logout states.
- **`SearchContext`**: Coordinates active search status, real-time polling for updates, and results loading.
- **`ToastContext`**: A centralized notification system for user feedback messages (success, error, warning).

### 2. Provider Layer & API Communication (`src/services` & `src/lib`)
All backend communication is handled through a centralized **`ApiClient`**:
- **JWT Automation**: Automatically injects the `Authorization` header for protected requests.
- **Auto-Refresh**: Includes a mechanism to automatically renew the access token using the `refresh_token` when it expires.
- **Error Handling**: Intercepts network errors and invalid HTTP responses, notifying the application globally via custom events.

### 3. Components & UX (`src/components`)
Components are designed to be small, reusable, and single-responsibility:
- **SearchProgress**: Provides detailed visual feedback (progress bars, real-time logs) during scraping and analysis phases.
- **JobTable/History**: Granular tabular views of found jobs, supporting both client-side and server-side filtering.
- **FilterBar**: Advanced filtering system for affinity scores, geolocation-based distance, and application status.

### 4. Search Lifecycle
The frontend is more than just a passive client. it manages a complex search lifecycle:
1. **Configuration**: User defines the search profile (CV, skills, location).
2. **Execution**: Triggers the asynchronous background task on the backend.
3. **Monitoring**: Intelligent polling of logs and completion percentages.
4. **Visualization**: Normalization and rendering of filtered job data.

---

## 🚀 Development

### Installation
```bash
npm install
```

### Available Scripts
- `npm run dev`: Starts the development server with Hot Module Replacement (HMR).
- `npm run build`: Compiles the application for production (output in `dist/`).
- `npm run lint`: Checks for style errors or potential bugs.
- `npm run test`: Executes the unit and integration test suite.
- `npm run preview`: Locally previews the production build.

### Environment Variables
Create a `.env` (or `.env.local`) file in the frontend root:
```env
VITE_API_URL=http://localhost:8000/api/v1
```

---

## 🧪 Testing Strategy

We use **Vitest** to test:
- **Services**: API communication logic and data transformation.
- **Contexts**: Correctness of global state updates.
- **Components**: User interaction verification and dynamic rendering of information.

Every new component should be accompanied by its respective `.test.jsx` file.

---

## 📐 Design Principles
- **Single Responsibility**: Every file and component has a unique purpose.
- **Performance**: Use of `AbortController` to cancel pending requests when components unmount.
- **Accessibility**: Use of semantic HTML and ARIA attributes where appropriate.
- **Premium Aesthetics**: Design based on modern principles (subtle gradients, micro-animations, and responsive layouts).
