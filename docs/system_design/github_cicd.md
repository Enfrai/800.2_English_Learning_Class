```yaml
name: Python CI/CD Pipeline

# 1. Define trigger events
on:
  push:
    branches: [ "main" ]  # Triggered when code is pushed to the main branch
  pull_request:
    branches: [ "main" ]  # Triggered when a PR is submitted to the main branch

# 2. Define jobs
jobs:
  build-and-test:
    runs-on: ubuntu-latest # Use the Ubuntu virtual environment provided by GitHub

    steps:
      # Step 1: Check out code into the virtual environment
      - name: Checkout code
        uses: actions/checkout@v4

      # Step 2: Set up Python environment
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.10'
          cache: 'pip' # Cache dependencies to speed up subsequent runs

      # Step 3: Install dependencies
      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt

      # Step 4: Run tests (Core CI phase)
      - name: Run tests with pytest
        run: |
          pytest

  # The deployment job (CD) below will only execute after the tests pass successfully
  deploy:
    needs: build-and-test
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main' && github.event_name == 'push' # Deploy only when there is a push to the main branch

    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Deploy to Cloud / Server
        run: |
          echo "Connecting to the server and deploying the application..."
          # You can write your deployment script, SSH connection commands, or trigger cloud provider (e.g., AWS/Vercel) deployment here
          # Sensitive information (like server IPs, passwords, tokens) must never be written in plain text here; store them in GitHub Secrets
          echo "Deployment successful!"
```