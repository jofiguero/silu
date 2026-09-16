FROM node:22-alpine AS build

WORKDIR /app

COPY package.json ./
RUN npm install

COPY . .
RUN npm run build

# La imagen final solo transporta el resultado: al arrancar, copia dist al
# volumen que sirve Caddy y termina. No queda ningun proceso corriendo.
FROM alpine:3.21
COPY --from=build /app/dist /dist-src
CMD ["sh", "-c", "rm -rf /dist/* && cp -a /dist-src/. /dist/ && echo 'frontend publicado'"]
