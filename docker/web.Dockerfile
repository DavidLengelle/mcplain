ARG TARGETARCH

FROM node:24.21.0-trixie-slim@sha256:8ec5d7557396cfe32d21c3f9c13072355ceab22b584578ca4bb28af31120cffe AS base
ENV NEXT_TELEMETRY_DISABLED=1

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
WORKDIR /src/web
COPY web/package.json web/pnpm-lock.yaml web/pnpm-workspace.yaml ./
RUN pnpm --version \
    && pnpm install --frozen-lockfile
COPY web/ ./
ENV MCPLAIN_API_URL=http://api:8000
RUN pnpm build

FROM base
RUN groupadd --system --gid 10003 mcplain \
    && useradd --system --uid 10003 --gid 10003 --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin mcplain
WORKDIR /app
COPY --from=build /src/web/.next/standalone ./
COPY --from=build /src/web/.next/static ./.next/static
COPY --from=build /src/web/public ./public
ENV NODE_ENV=production \
    HOSTNAME=0.0.0.0 \
    PORT=3000 \
    MCPLAIN_API_URL=http://api:8000
USER 10003:10003
EXPOSE 3000
CMD ["node", "server.js"]
