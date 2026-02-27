FROM node:20-alpine

ARG VITE_API_BASE_URL
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL

WORKDIR /app

COPY package*.json ./
RUN npm install

COPY . .

RUN npm run build

# Install a static file server
RUN npm install -g serve

EXPOSE 8000

CMD ["serve", "-s", "dist", "-l", "8000"]
