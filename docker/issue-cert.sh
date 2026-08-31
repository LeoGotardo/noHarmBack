#!/usr/bin/env bash
# Issue (and later renew) the Let's Encrypt certificate for this host.
#
# Uses the webroot challenge, not standalone, so it runs while the app is up:
# nginx already serves /.well-known/acme-challenge/ over plain :80 from
# /var/www/certbot — that location sits above the catch-all redirect in
# server.tls.conf precisely so renewal is never 301'd away.
#
# Two things must be true before this can work, and neither is fixable here:
#   - noharm.site and www.noharm.site resolve to THIS machine's public IP
#   - the security group allows :80 from 0.0.0.0/0 (Let's Encrypt connects
#     from addresses it does not publish, so it cannot be narrowed)
#
#   ./issue-cert.sh you@example.com
#
set -euo pipefail
cd "$(dirname "$0")"

email="${1:?usage: ./issue-cert.sh <email for expiry notices>}"
domains=(noharm.site www.noharm.site)

mkdir -p certs certbot-www letsencrypt

# Fail early and legibly rather than after a challenge timeout.
publicIp="$(curl -s --max-time 5 https://checkip.amazonaws.com || true)"
for domain in "${domains[@]}"; do
    resolved="$(getent hosts "$domain" | awk '{print $1}' | head -1 || true)"
    if [[ "$resolved" != "$publicIp" ]]; then
        echo "FATAL: $domain resolves to '${resolved:-nothing}', this host is $publicIp" >&2
        echo "Point the DNS at this machine before issuing a certificate." >&2
        exit 1
    fi
done

args=()
for domain in "${domains[@]}"; do args+=(-d "$domain"); done

docker run --rm \
    -v "$PWD/certbot-www:/var/www/certbot" \
    -v "$PWD/letsencrypt:/etc/letsencrypt" \
    certbot/certbot certonly \
    --webroot -w /var/www/certbot \
    "${args[@]}" \
    --email "$email" --agree-tos --no-eff-email --non-interactive

# nginx reads /etc/nginx/certs, which is ./certs mounted read-only. Copy rather
# than symlink: the container cannot follow a link into a directory it has no
# mount for.
sudo cp "letsencrypt/live/${domains[0]}/fullchain.pem" certs/fullchain.pem
sudo cp "letsencrypt/live/${domains[0]}/privkey.pem"   certs/privkey.pem
sudo chown "$(id -u):$(id -g)" certs/fullchain.pem certs/privkey.pem
chmod 644 certs/fullchain.pem
chmod 600 certs/privkey.pem

# A running nginx holds the old certificate in memory until told otherwise.
docker exec noharm nginx -s reload 2>/dev/null || \
    docker compose --env-file prod.env -f compose.host.yaml restart app

echo
echo "certificate installed; expires $(openssl x509 -enddate -noout -in certs/fullchain.pem | cut -d= -f2)"
echo
echo "For renewal, install this as a cron entry (Let's Encrypt lasts 90 days,"
echo "renews at 30 left, and a certificate that quietly expires takes the site"
echo "down for every visitor at once):"
echo
echo "  0 3 * * 1  $PWD/issue-cert.sh $email >> $PWD/certbot.log 2>&1"
