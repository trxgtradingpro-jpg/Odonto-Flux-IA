FROM node:22-alpine

WORKDIR /workspace

RUN corepack enable
RUN apk add --no-cache chromium

COPY package.json pnpm-workspace.yaml turbo.json ./
COPY apps/web/package.json apps/web/package.json
COPY packages ./packages
COPY apps/web ./apps/web

RUN pnpm install --frozen-lockfile=false

WORKDIR /workspace/apps/web

CMD ["pnpm", "dev", "--host", "0.0.0.0", "--port", "3000"]
