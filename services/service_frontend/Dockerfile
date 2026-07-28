FROM node:20.20.2-alpine

ARG VITE_API_BASE_URL
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL

RUN mkdir -p /home/alfr3d && \
    adduser -D -u 1001 -h /home/alfr3d -s /bin/sh alfr3d || true

WORKDIR /app

COPY package*.json ./
RUN npm install

COPY . .

RUN npm run build

RUN npm install -g serve

EXPOSE 8000

USER 1001

CMD ["serve", "-s", "dist", "-l", "8000"]
