# Deploying safedata_server (AWS Lightsail)

This guide covers setting up and maintaining the production server. For local
development setup, see the main [README](../README.md).

**Why a persistent server?** The database is SpatiaLite, a single SQLite file on
local disk. Serverless platforms (Lambda, Cloud Run) run stateless containers
and can't safely share one SQLite file, so a small always-on instance is the
better fit.

---

## 1. Create the instance

In the Lightsail console:

1. **Create instance**, in a region close to your users.
2. Platform **Linux/Unix**, blueprint **OS Only → Ubuntu 24.04 LTS**. Don't use
   an app blueprint such as WordPress.
3. Plan: **2 GB RAM or larger** ($10/month at the time of writing). The 512 MB
   plan ran out of memory during a routine `apt upgrade`.
4. Name it clearly, e.g. `safedata-server`, and create it.
5. **Networking tab → Create static IP** and attach it. Without this the public
   address changes whenever the instance restarts.
6. **Networking tab → IPv4 Firewall:** add HTTP (80) and HTTPS (443), source
   "Anywhere IPv4". SSH (22) is open by default. If the instance has IPv6
   enabled, add the same rules on the IPv6 firewall tab.

If you resize by creating a new instance from a snapshot, move the static IP
across and delete the old instance and snapshot afterwards (snapshots are
billed). Your SSH client will then warn that the host key has changed. That is
expected after a swap: run `ssh-keygen -R <ip>` and reconnect.

## 2. SSH access

Each maintainer should use their own key rather than sharing Lightsail's
default key. If you don't already have a public key generated, run:

```bash
# On your own machine
ssh-keygen -t ed25519 -C "your.name@example.com"
cat ~/.ssh/id_ed25519.pub
```

Open the browser-based SSH from the Lightsail console and append the public
key line (keep the quotes):

```bash
echo "ssh-ed25519 AAAA... your.name@example.com" >> ~/.ssh/authorized_keys
```

Then connect from your own terminal:

```bash
ssh ubuntu@<static-ip>
```

Repeat for each person who needs access. Never share your private key.

## 3. System setup

```bash
sudo apt update && sudo apt upgrade -y
sudo reboot        # if the output says "Pending kernel upgrade"
```

Reconnect, then check memory and install the dependencies:

```bash
free -h            # Mem total should be ~1.9Gi on the 2 GB plan

sudo apt install -y gdal-bin libgdal-dev libgeos-dev \
  libsqlite3-mod-spatialite spatialite-bin \
  nginx git build-essential

curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.bashrc
```

Check that Python can load SpatiaLite. On Ubuntu 24.04 this works with the
system Python, with no rebuild needed (unlike macOS):

```bash
python3 -c "
import sqlite3
conn = sqlite3.connect(':memory:')
conn.enable_load_extension(True)
conn.load_extension('mod_spatialite')
print(conn.execute('select spatialite_version()').fetchone())
"
```

## 4. Get the code and configure it

```bash
git clone https://github.com/<owner>/<repo>.git ~/safedata_server
cd ~/safedata_server
uv sync
```

The repository is public, so no credentials are needed. If it ever becomes
private, add a read-only deploy key under the repo's Settings → Deploy keys
(this needs admin rights on the repo).

Generate a secret key, then create the production `.env`:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(50))"
```

```bash
cat > .env << 'EOF'
GAZETTEER_LOCAL_EPSG=32650
DJANGO_SECRET_KEY=<paste the generated key>
DJANGO_DEBUG=0
DJANGO_ALLOWED_HOSTS=<domain-or-ip>
DJANGO_HTTPS=0
EOF
chmod 600 .env
```

See the environment variable table in the README for what each setting does.
Never reuse a secret key from another environment, and never commit `.env`.

Then:

```bash
uv run python manage.py check --deploy
uv run python manage.py migrate
uv run python manage.py collectstatic --noinput
uv run python manage.py createsuperuser
uv run python manage.py drf_create_token <username>
```

`check --deploy` will warn about HSTS, SSL redirect and secure cookies until
HTTPS is configured (section 7). That is expected. Any other warning is worth
investigating. Save the token printed by the last command.

## 5. gunicorn as a service

Test gunicorn by hand first:

```bash
uv run gunicorn config.wsgi:application --bind 127.0.0.1:8000 --workers 2
```

In a second session:

```bash
curl -I -H "Host: <value from DJANGO_ALLOWED_HOSTS>" http://127.0.0.1:8000/
```

Expect a `200`. A plain `curl http://127.0.0.1:8000/` returns `400`, because
`127.0.0.1` isn't in `ALLOWED_HOSTS`. That is Django rejecting an unlisted host,
not a fault.

**Stop the manual gunicorn (Ctrl+C) before starting the service**, or the
service can't bind the port.

```bash
sudo tee /etc/systemd/system/safedata.service > /dev/null << 'EOF'
[Unit]
Description=safedata_server (gunicorn)
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/safedata_server
ExecStart=/home/ubuntu/safedata_server/.venv/bin/gunicorn config.wsgi:application --bind 127.0.0.1:8000 --workers 2 --timeout 120
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now safedata
sudo systemctl status safedata --no-pager
```

The log should show no "Connection in use" errors. The timeout is raised to
120 s so large web uploads can finish.

## 6. nginx

```bash
sudo tee /etc/nginx/sites-available/safedata > /dev/null << 'EOF'
server {
    listen 80;
    server_name <domain-or-ip>;

    client_max_body_size 50M;

    location /static/ {
        alias /home/ubuntu/safedata_server/staticfiles/;
    }

    location /resources/ {
        alias /home/ubuntu/safedata_server/resources/;
    }

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
    }
}
EOF

sudo ln -s /etc/nginx/sites-available/safedata /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
chmod 711 /home/ubuntu
sudo nginx -t && sudo systemctl reload nginx
```

- `client_max_body_size` matters: nginx's 1 MB default would reject large
  uploads with a 413 error.
- `chmod 711 /home/ubuntu` lets nginx reach the static files. Ubuntu 24.04 makes
  home folders private by default, which breaks the admin's CSS and JavaScript.

Open the site in a browser. Check the home page, and check that `/admin/` is
styled.

## 7. HTTPS

Until this is done, admin logins, upload sessions and API tokens travel
unencrypted. Only use throwaway accounts until HTTPS is on.

Let's Encrypt issues certificates for domain names, not bare IPs, so you need a
domain or subdomain pointing at the static IP first.

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d <domain>
```

Then in `.env` set `DJANGO_ALLOWED_HOSTS=<domain>` and `DJANGO_HTTPS=1`, and
restart:

```bash
sudo systemctl restart safedata
```

Test that login and a file upload both still work. Browsers can reject form
submissions after an HTTP-to-HTTPS change if the CSRF settings don't line up.

## 8. Loading data

Load in this order:

1. **Gazetteer** (GeoJSON)
2. **Datasets** (JSON exports)
3. **Aliases** (CSV)

The aliases file is all-or-nothing, and some rows reference specific datasets,
so it fails if those datasets aren't loaded yet. Use the web upload pages (once
HTTPS is on) or the API for single files. For a batch of dataset files, copy the
folder up and use the management command:

```bash
# from your own machine
rsync -av <local-folder>/ ubuntu@<static-ip>:~/data/

# on the server
cd ~/safedata_server
uv run python manage.py ingest_datasets ~/data/
```

Dataset ingestion with large taxa lists is the heaviest operation. Run
`free -h` in a second session during the first big batch.

Once data is loaded, set the optional notice that safedata clients see via
`/api/message/` in the admin under "Server messages".

## 9. Deploying an update

```bash
cd ~/safedata_server
git pull
uv sync
uv run python manage.py migrate
uv run python manage.py collectstatic --noinput
sudo systemctl restart safedata
```

## 10. Logs

```bash
sudo journalctl -u safedata -n 50 --no-pager     # gunicorn / Django
sudo tail -n 30 /var/log/nginx/error.log         # nginx
```

## 11. Backups (not yet set up)

The database is a single file. Use SQLite's backup command rather than `cp`, as
it is safe while the site is live.

```bash
sudo apt install -y sqlite3
mkdir -p ~/backups
crontab -e
```

Add these lines to the crontab (the `\%` escapes are required inside cron):

```
0 2 * * * sqlite3 /home/ubuntu/safedata_server/db.sqlite3 ".backup '/home/ubuntu/backups/db-$(date +\%F).sqlite3'"
0 3 * * * find /home/ubuntu/backups -name 'db-*.sqlite3' -mtime +30 -delete
```

Backups on the same instance are lost if the instance is lost, so also enable
Lightsail automatic snapshots. Test a restore at least once.

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| `400 Bad Request` from `curl http://127.0.0.1:8000/` | `127.0.0.1` isn't in `DJANGO_ALLOWED_HOSTS`. Send the real host with `-H "Host: ..."` |
| Service says "active" but the log shows `Connection in use` | A manually started gunicorn still holds port 8000. Find it with `sudo ss -ltnp \| grep :8000` and stop it |
| Admin has no CSS | nginx can't read the static files. Run `chmod 711 /home/ubuntu`, and check `collectstatic` has run |
| `413 Request Entity Too Large` on upload | `client_max_body_size` in the nginx config is too small |
| Upload fails after exactly 30 s | gunicorn `--timeout` too low (the service file sets 120) |
| `database is locked` on upload | Two writers at once. SQLite allows one at a time, so retry. If frequent, reduce workers to 1 |
| `Killed` during installs or upgrades | Out of memory. Use the 2 GB plan or larger |
| SSH `REMOTE HOST IDENTIFICATION HAS CHANGED` | The instance was replaced. Run `ssh-keygen -R <ip>` and reconnect |
| SSH `Permission denied (publickey)` | Your public key isn't in `~/.ssh/authorized_keys` on the server |
| App fails to start with `KeyError` | `DJANGO_SECRET_KEY` or `GAZETTEER_LOCAL_EPSG` is missing from `.env` |
