FROM node:20-alpine

WORKDIR /app

# Copy dependency files
COPY package*.json ./

# Install dependencies in container build
RUN npm ci --only=production

# Copy source code
COPY . .

# Expose microservice port
EXPOSE 3002

# Environment defaults
ENV PORT=3002
ENV NODE_ENV=production

# Run service
CMD ["node", "src/index.js"]
