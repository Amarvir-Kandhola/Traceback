# Traceback

AI-assisted incident investigation. Describe an incident in plain language; Traceback
retrieves the relevant evidence, reconstructs a timeline, and produces a root-cause
hypothesis where every claim cites the evidence behind it.

## Development

Requires Python 3.12.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

pytest                                   # tests
ruff check . && ruff format --check .    # lint
uvicorn tracebackai.main:app --reload    # run the API at http://localhost:8000
```
