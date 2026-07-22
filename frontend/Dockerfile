# EPM Wizard frontend — build with Vite, serve with nginx.
FROM node:20-alpine AS build
WORKDIR /app

COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci || npm install

COPY frontend/ ./
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
# Templated config: the nginx entrypoint runs envsubst on /etc/nginx/templates/
# *.template at startup, substituting ONLY ${BACKEND_URL} (NGINX_ENVSUBST_FILTER
# protects nginx's own $host/$uri/... variables). Default targets the compose
# service; hosted deploys override BACKEND_URL with the backend's internal URL.
COPY frontend/nginx.conf /etc/nginx/templates/default.conf.template
ENV BACKEND_URL=http://backend:8000
ENV NGINX_ENVSUBST_FILTER=BACKEND_URL
EXPOSE 3000
CMD ["nginx", "-g", "daemon off;"]
