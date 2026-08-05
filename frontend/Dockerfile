FROM node:20

WORKDIR /app

# Copy package files
COPY package.json package-lock.json* ./

# Install dependencies
RUN npm install

# Copy source
COPY . .

EXPOSE 5173

CMD ["npx", "vite", "dev", "--host", "0.0.0.0"]
