# Lifelog API Docker Deployment

## Recommended Production Setup

```bash
# Directory structure
.lifelog/
├── config.toml
├── lifelog.db
docker/
├── Dockerfile
├── docker-compose.yml
├── nginx.conf
```

### Dockerfile

```dockerfile
FROM python:3.11-slim

WORKDIR /app

RUN pip install lifelog gunicorn

COPY . .

CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:5000", "lifelog.app:app"]
```

### docker-compose.yml

```yaml
version: "3.8"

services:
  api:
    build: ./docker
    volumes:
      - ~/.lifelog:/root/.lifelog
    environment:
      - FLASK_ENV=production
    restart: always
    networks:
      - lifelog-net

  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./docker/nginx.conf:/etc/nginx/nginx.conf
      - ./certs:/etc/nginx/certs
    networks:
      - lifelog-net

networks:
  lifelog-net:
```

### nginx.conf

```nginx
events {}
http {
    server {
        listen 80;
        server_name api.yourdomain.com;
        return 301 https://$host$request_uri;
    }

    server {
        listen 443 ssl;
        server_name api.yourdomain.com;

        ssl_certificate /etc/nginx/certs/fullchain.pem;
        ssl_certificate_key /etc/nginx/certs/privkey.pem;

        location / {
            proxy_pass http://api:5000;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        }
    }
}
```

## Security Best Practices

1. **HTTPS**: Always use SSL/TLS encryption
2. **Key Rotation**: Change API keys quarterly
3. **Firewall**: Restrict access to known IPs
4. **Monitoring**: Set up log alerts
5. **Updates**: Regularly update Docker images

## Environment Variables

| Variable            | Description         | Default          |
| ------------------- | ------------------- | ---------------- |
| `FLASK_ENV`         | Runtime environment | `production`     |
| `API_RATE_LIMIT`    | Requests per minute | `100`            |
| `DB_ENCRYPTION_KEY` | Encryption key      | (auto-generated) |
