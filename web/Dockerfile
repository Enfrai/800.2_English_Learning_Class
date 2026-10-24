# Build and run the Next.js frontend with Node.js in Docker.
# Author: Shuohui Liu
# Date: 19 Oct 2026

FROM node:24-alpine AS builder
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
RUN npm run build

FROM node:24-alpine
WORKDIR /app
ENV NODE_ENV=production
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
USER node
EXPOSE 3000
ENV HOSTNAME=0.0.0.0
CMD ["node", "server.js"]
