FROM node:20-alpine

WORKDIR /app

RUN apk add --no-cache git

# Copy dependency files
COPY package*.json ./

# Install dependencies in container build
RUN npm install --omit=dev

# Copy source code
COPY . .

# Expose microservice port
EXPOSE 3002

# Environment defaults
ENV PORT=3002
ENV NODE_ENV=production

# Run service
CMD ["node", "src/index.js"]
