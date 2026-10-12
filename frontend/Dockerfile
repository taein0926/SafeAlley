FROM node:22-alpine AS build

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
RUN npm list cesium @cesium/engine @cesium/widgets @zip.js/zip.js --depth=0

COPY . .

ARG VITE_CESIUM_ION_TOKEN=""
ENV VITE_CESIUM_ION_TOKEN=${VITE_CESIUM_ION_TOKEN}
ARG VITE_OSM_TILE_URL="https://tile.openstreetmap.org/"
ENV VITE_OSM_TILE_URL=${VITE_OSM_TILE_URL}
ARG VITE_BUILDING_SOURCE="molit-gis-building"
ENV VITE_BUILDING_SOURCE=${VITE_BUILDING_SOURCE}
ARG VITE_SHOW_STREETLIGHTS="true"
ENV VITE_SHOW_STREETLIGHTS=${VITE_SHOW_STREETLIGHTS}
ARG VITE_SHOW_CCTVS="true"
ENV VITE_SHOW_CCTVS=${VITE_SHOW_CCTVS}
ARG VITE_SHOW_HELP_POINTS="true"
ENV VITE_SHOW_HELP_POINTS=${VITE_SHOW_HELP_POINTS}

RUN npm run build

FROM nginx:1.27-alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

# Extracted sources can inherit a restrictive server umask. Nginx workers
# must be able to traverse and read every public asset (never private .env).
RUN find /usr/share/nginx/html -type d -exec chmod 755 {} + \
    && find /usr/share/nginx/html -type f -exec chmod 644 {} +

EXPOSE 80
