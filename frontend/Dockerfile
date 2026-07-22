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
# *.template at startup, substituting ONLY ${BACKEND_URL} and ${DNS_RESOLVER}
# (NGINX_ENVSUBST_FILTER — an env-var-name regex — protects nginx's own
# $host/$uri/$request_uri/... variables). Defaults target the compose service +
# Docker's embedded DNS; hosted deploys override both (backend internal URL and
# Fly's internal resolver [fdaa::3]:53) via frontend.fly.toml.
COPY frontend/nginx.conf /etc/nginx/templates/default.conf.template
ENV BACKEND_URL=http://backend:8000
ENV DNS_RESOLVER=127.0.0.11
ENV NGINX_ENVSUBST_FILTER=BACKEND_URL|DNS_RESOLVER
EXPOSE 3000
CMD ["nginx", "-g", "daemon off;"]
