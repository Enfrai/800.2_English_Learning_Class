# Build isolated backend, browser and system test runners on Python 3.14.
# Author: Shuohui Liu
# Date: 19 Oct 2026

FROM python:3.14-bookworm AS backend
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /workspace
COPY server/services/user/requirements*.txt /deps/user/
COPY server/services/accessment/requirements*.txt /deps/accessment/
COPY server/services/lesson/requirements*.txt /deps/lesson/
RUN pip install --no-cache-dir -r /deps/user/requirements-dev.txt \
    -r /deps/accessment/requirements-dev.txt -r /deps/lesson/requirements-dev.txt \
    "pytest-html>=4,<5"
COPY server/services /workspace/server/services
COPY tests/docker /runner
ENTRYPOINT ["python", "/runner/run.py", "backend"]

FROM node:24-bookworm AS node-runtime

FROM python:3.14-bookworm AS web
COPY --from=node-runtime /usr/local/bin/node /usr/local/bin/node
COPY --from=node-runtime /usr/local/lib/node_modules/npm /usr/local/lib/node_modules/npm
RUN ln -s ../lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
    && ln -s ../lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx
ENV NEXT_TELEMETRY_DISABLED=1 PLAYWRIGHT_BROWSERS_PATH=/ms-playwright BROWSER_CHANNEL=chromium
WORKDIR /workspace/web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund \
    && npx playwright install --with-deps chromium
COPY web/ ./
RUN npm run build \
    && cp -r .next/static .next/standalone/.next/static
COPY tests/docker /runner
ENTRYPOINT ["python3", "/runner/run.py", "web"]

FROM backend AS system
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright BROWSER_CHANNEL=chromium
COPY tests/system/requirements.txt /deps/system.txt
RUN pip install --no-cache-dir -r /deps/system.txt \
    && python -m playwright install --with-deps chromium
COPY --from=web /usr/local/bin/node /usr/local/bin/node
COPY --from=web /usr/local/lib/node_modules/npm /opt/npm
RUN node /opt/npm/bin/npm-cli.js install --prefix /opt/axe --no-audit --no-fund axe-core@4.10.2
ENV AXE_SCRIPT_PATH=/opt/axe/node_modules/axe-core/axe.min.js
COPY tests/system /workspace/tests/system
ENTRYPOINT ["python", "/runner/run.py", "system"]
