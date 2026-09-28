FROM nginx:1.27-alpine
COPY index.html styles.css app.js config.js logo.svg upload.svg /usr/share/nginx/html/
COPY nginx.conf /etc/nginx/conf.d/default.conf
