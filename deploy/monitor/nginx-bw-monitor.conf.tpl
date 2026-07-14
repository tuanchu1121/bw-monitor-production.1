server {
    listen 80;
    listen [::]:80;
    server_name __DOMAIN__;

    client_max_body_size 64m;

    # Compress large dashboard/card responses before sending them to browsers.
    gzip on;
    gzip_comp_level 5;
    gzip_min_length 1024;
    gzip_vary on;
    gzip_proxied any;
    gzip_types text/plain text/css text/xml application/json application/javascript application/xml application/xhtml+xml image/svg+xml;

    location / {
        proxy_pass http://127.0.0.1:__PORT__;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Host $host;
        proxy_set_header X-Forwarded-Port $server_port;
        proxy_set_header Connection "";
        proxy_connect_timeout 15s;
        proxy_send_timeout 300s;
        proxy_read_timeout 300s;

        # Buffered proxying lets Gunicorn finish the request sooner while Nginx
        # handles slower browser/network clients efficiently.
        proxy_buffering on;
        proxy_buffer_size 16k;
        proxy_buffers 16 32k;
        proxy_busy_buffers_size 64k;
    }

    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
    add_header Permissions-Policy "geolocation=(), camera=(), microphone=()" always;
}
