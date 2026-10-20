### 1. Setup environment to develop

1.1 Python environment checking

```shell
python3 -c "import argparse, os, platform, shutil, subprocess, sys, tempfile, urllib.request; from pathlib import Path; print('All modules are available')" 
```

1.2 Setup

```shell
python buildup_dev_environment.py
```

### 2. Deploy & Run

2.1 Steps

```sh
cp .env.example .env
cat .env
docker compose config
docker compose up -d --build
```

2.2 Individually update

```sh
docker compose up -d --build user1 user2 ...
```

2.3 Checking 

```sh
docker compose ps
```

2.4 Real-time logs

```sh
docker compose logs -f
```

### 3. Testing

3.1 Working testing

```sh
curl -i -X POST http://localhost:8080/api/user/login -H "Content-Type: application/json" -d '{"username":"demo","password":"DemoPass123!"}'

curl -i -X POST http://localhost:8080/api/access/check -H "Content-Type: application/json" -d '{"role":"admin","resource":"lessons"}'

curl -i -X POST http://localhost:8080/api/lesson/create -H "Content-Type: application/json" -d '{"title":"FastAPI Basics"}'
```

3.2 Load Balancor Testing

```sh
for i in {1..10}; do
    curl -s -X POST http://localhost:8080/api/user/login -H "Content-Type: application/json" -d '{"username":"demo","password":"DemoPass123!"}'
    echo
done
```

### 4. PostgreSQL self-testing example

Execute SQL statements.

```sh
docker compose exec postgres-user psql -U user_app -d userdb -c "SELECT * FROM users;"
```

### 5. Terminate / Stop running

5.1 Terminate & remove containers

```sh
docker compose down

# With removing data
docker compose down -v

# rerun
docker compose up -d --build
```

5.2 Stop containers

```sh 
docker compose stop

# restart
docker compose start
```

### 6. Formatting (Ruff)

6.1 

```sh
# Formatting
ruff format . # ruff format --check .

# Importing 
ruff check --select I --fix .

# Importing - remove unused.
ruff check --select F401 --fix .

# Checking
ruff check .
```

6.2 Automaticall ruff

[ruff.toml](../server/ruff.toml)

```sh
ruff check --fix .
ruff format .
```