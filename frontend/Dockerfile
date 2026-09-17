# Multi-stage build for Next.js application
FROM node:22-alpine AS base

# Set working directory
WORKDIR /app

# Install dependencies only when needed
FROM base AS deps
# Check https://github.com/nodejs/docker-node/tree/b4117f9333da4138b03a546ec926ef50a31506c3#nodealpine to understand why libc6-compat might be needed.
RUN apk add --no-cache libc6-compat

# Copy package files
COPY package.json package-lock.json* ./

# Install dependencies
RUN npm ci

# Development stage
FROM base AS development

# Copy node_modules from deps
COPY --from=deps /app/node_modules ./node_modules

# Copy application code
COPY . .

# Expose port
EXPOSE 3000

# Set environment variable for Next.js
ENV PORT 3000
ENV HOSTNAME "0.0.0.0"

# Run the application in development mode
CMD ["npm", "run", "dev"]

# Build stage
FROM base AS builder

# Copy node_modules from deps
COPY --from=deps /app/node_modules ./node_modules

# Copy application code
COPY . .

# Set environment variables for build
ENV NEXT_TELEMETRY_DISABLED 1

# Build the application
RUN npm run build

# Production stage
FROM base AS production

ENV NODE_ENV production
ENV NEXT_TELEMETRY_DISABLED 1

# Create non-root user
RUN addgroup --system --gid 1001 nodejs && \
    adduser --system --uid 1001 nextjs

# Copy built application
COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs

# Expose port
EXPOSE 3000

ENV PORT 3000
ENV HOSTNAME "0.0.0.0"

# Run the application
CMD ["node", "server.js"]
