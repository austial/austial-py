# Examples

| Example | Shows |
|---|---|
| [`hello-world`](hello-world/main.py) | DI, a controller, a guard, DTO validation, 404 handling and Swagger UI in one file |

Run one:

```bash
pip install austial uvicorn
cd examples/hello-world
uvicorn main:app --reload      # http://localhost:8000/docs
```

For a full scaffolded project, run `austial new my-app`.
