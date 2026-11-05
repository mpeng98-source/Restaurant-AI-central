#!/bin/sh
set -eu
umask 077
password=$(cat /run/secrets/redis_password)
case "$password" in
  ''|*[!A-Za-z0-9_-]*) echo "Redis secret must be nonempty URL-safe text" >&2; exit 1 ;;
esac
printf 'requirepass %s\nappendonly yes\ndir /data\nbind 0.0.0.0\nprotected-mode yes\n' "$password" > /tmp/demo-redis.conf
chown redis:redis /tmp/demo-redis.conf
exec /usr/local/bin/docker-entrypoint.sh redis-server /tmp/demo-redis.conf
