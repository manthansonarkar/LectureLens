# Contributing to LectureLens

Thanks for considering contributing to **LectureLens**!

## Local Development Setup

```bash
git clone https://github.com/manthansonarkar/LectureLens.git
cd LectureLens

python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
pip install -e ".[dev]"
```

For frontend development with hot reload:

```bash
cd frontend
npm install
npm run dev
```

In a separate terminal, run the backend API:

```bash
lecturelens serve --port 8000
```

## Checks Before Opening a Pull Request

1. Ensure Ruff passes with zero warnings:
   ```bash
   ruff check backend tests
   ```
2. Ensure all tests pass:
   ```bash
   pytest -v
   ```
3. If editing `frontend/`, verify the production TypeScript & Vite build succeeds:
   ```bash
   cd frontend && npm run build
   ```
