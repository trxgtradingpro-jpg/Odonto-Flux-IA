FROM node:22-alpine

WORKDIR /workspace

ENV NEXT_TELEMETRY_DISABLED=1

RUN corepack enable
RUN apk add --no-cache chromium

COPY package.json pnpm-workspace.yaml turbo.json ./
COPY apps/web/package.json apps/web/package.json
COPY packages ./packages
COPY apps/web ./apps/web

RUN pnpm install --frozen-lockfile=false
RUN pnpm --filter @odontoflux/web build

CMD ["sh", "-c", "pnpm --filter @odontoflux/web start --hostname 0.0.0.0 --port ${PORT:-10000}"]
