# End-to-end test: real backend + real agent

Runs the productifynow FastAPI backend in-process on a fake database and drives
the compiled agent over `/ws/node/v1`. Docker is replaced by `fake-docker.bat`,
which logs every call so the test can assert the container flags.

```
go build -o test/e2e/productify-agent.exe ./cmd/productify-agent
python test/e2e/e2e.py <path-to-Productify-/backend> test/e2e/productify-agent.exe
```

Needs the backend's Python dependencies plus `uvicorn[standard]`.
