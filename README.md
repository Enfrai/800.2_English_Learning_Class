# 800.2_English_Learning_Class

- `web` provides user interfaces and uesr interaction
- `server` services origanisation
- `database` data permanently preserved

## Testing

Start Docker Desktop, then run from this directory:

```bash
python3 tests/run_docker_tests.py
```

On Windows use `py tests/run_docker_tests.py`. Results are retained under
`test-results/`. The test project is separate from the development stack.

See [Docker test commands and reports](tests/docker/README.md) for Docker-only
commands, individual suites, report paths, limitations and troubleshooting.
