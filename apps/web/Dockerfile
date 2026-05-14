FROM node:22-alpine AS runtime-base

WORKDIR /workspace

ENV NEXT_TELEMETRY_DISABLED=1

RUN corepack enable
RUN apk add --no-cache chromium

FROM runtime-base AS dev

CMD ["sh", "-c", "cd /workspace/apps/web && pnpm dev --hostname 0.0.0.0 --port ${PORT:-10000}"]

FROM runtime-base AS prod-deps

COPY package.json pnpm-workspace.yaml turbo.json ./
COPY apps/web/package.json apps/web/package.json
COPY packages ./packages
COPY apps/web ./apps/web

RUN pnpm install --frozen-lockfile=false

FROM prod-deps AS prod-build

RUN cd /workspace/apps/web && pnpm build

FROM runtime-base AS prod

COPY --from=prod-build /workspace /workspace

CMD ["sh", "-c", "cd /workspace/apps/web && pnpm start --hostname 0.0.0.0 --port ${PORT:-10000}"]
