FROM node:20-alpine AS build

WORKDIR /app

# NEXT_PUBLIC_* values are compiled into the bundle at build time, so they are
# build arguments (an ARG is visible to the RUN steps below).
ARG NEXT_PUBLIC_CHAT_API
ARG NEXT_PUBLIC_API_KEY
ARG NEXT_PUBLIC_SITE_URL
ARG NEXT_PUBLIC_HELP_URL
ARG NEXT_PUBLIC_SENTRY_DSN
ARG NEXT_PUBLIC_SENTRY_ENVIRONMENT

# Install dependencies (npm ci for reproducible, lockfile-faithful builds)
COPY package.json package-lock.json ./
RUN npm ci

# Build the static site (only the files .dockerignore allows)
COPY . .
RUN NEXT_TELEMETRY_DISABLED=1 npm run build

# ====================================
FROM node:20-alpine AS release

WORKDIR /app

# A pinned static server, installed at build time (not `serve@latest` on
# every start). public/serve.json sets the security headers.
RUN npm install -g serve@14.2.4

# Only the built site goes into the image.
COPY --from=build /app/out ./out

# Drop root: the `node` user ships with the official node image.
USER node

EXPOSE 3000
CMD ["sh", "-c", "exec serve -s out -l tcp://0.0.0.0:${PORT:-3000}"]
