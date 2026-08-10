FROM node:24-alpine AS build

ARG VITE_API_BASE_URL
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL

WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .

RUN npm run build

FROM node:24-alpine

RUN mkdir -p /home/alfr3d && \
    adduser -D -u 1001 -h /home/alfr3d -s /bin/sh alfr3d || true

WORKDIR /app

COPY --from=build /app/dist ./dist

RUN npm install -g serve

EXPOSE 8000

USER 1001

CMD ["serve", "-s", "dist", "-l", "8000"]
