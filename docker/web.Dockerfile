# Web image cho profile `proxy`: build SPA (React + Vite) rồi đóng gói Caddyfile.
# Người self-host KHÔNG cần Node trên máy — build diễn ra trong Docker.
#   docker compose --profile proxy build web
#   docker compose --profile proxy up -d
#
# Stage 1 (node): npm install + npm run build → dist static.
# Stage 2 (caddy): chép dist vào /srv + Caddyfile (serve SPA + proxy API).

FROM node:22-alpine AS spa
WORKDIR /build
# Lockfile (nếu có) copy trước để tận dụng layer cache: sửa code không phải
# tải lại toàn bộ dependencies. `npm install` chấp nhận cả khi chưa có lockfile.
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM caddy:2-alpine
COPY --from=spa /build/dist /srv
COPY Caddyfile /etc/caddy/Caddyfile
