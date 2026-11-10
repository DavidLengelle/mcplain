ARG TARGETARCH

FROM node:24.22.1-trixie-slim@sha256:89c5244bc22a9bc3287d89ebc7e49b9cb5bb84cd40e6175ac3421d5a9f68b95a AS base

FROM base AS pnpm-amd64
ADD --checksum=sha256:786ad4802b199a255e21c135538c39745ee9d0e4e77da641c7726c60b03f5bc1 \
    https://github.com/pnpm/pnpm/releases/download/v11.28.1/pnpm-linux-x64.tar.gz /tmp/pnpm.tar.gz

FROM base AS pnpm-arm64
ADD --checksum=sha256:6132260275fc4c21de97a737caa02b8907d4f8ff639f111b27f129a50af83707 \
    https://github.com/pnpm/pnpm/releases/download/v11.28.1/pnpm-linux-arm64.tar.gz /tmp/pnpm.tar.gz

FROM pnpm-${TARGETARCH} AS build
RUN mkdir /opt/pnpm \
    && tar -xzf /tmp/pnpm.tar.gz -C /opt/pnpm \
    && rm /tmp/pnpm.tar.gz \
    && printf '#!/bin/sh\nexec node /opt/pnpm/dist/pnpm.mjs "$@"\n' > /usr/local/bin/pnpm \
    && chmod 0755 /usr/local/bin/pnpm
ENV PNPM_HOME=/opt/pnpm-home \
    CI=true
WORKDIR /src/auth
COPY auth/package.json auth/pnpm-lock.yaml auth/pnpm-workspace.yaml ./
RUN pnpm --version \
    && pnpm install --frozen-lockfile --prod

FROM base
RUN groupadd --system --gid 10004 mcplain \
    && useradd --system --uid 10004 --gid 10004 --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin mcplain
WORKDIR /app
COPY --from=build /src/auth/node_modules ./node_modules
COPY auth/package.json ./package.json
COPY auth/src ./src
ENV NODE_ENV=production \
    BETTER_AUTH_TELEMETRY=0 \
    MCPLAIN_GUICHET_PORT=3100
USER 10004:10004
EXPOSE 3100
CMD ["node", "src/server.ts"]
