#!/bin/sh
set -eu
umask 077
password=$(cat /run/secrets/redis_password)
case "$password" in
  ''|*[!A-Za-z0-9_-]*) echo "Redis secret must be nonempty URL-safe text" >&2; exit 1 ;;
esac
mkdir -p /run/chubby-redis
chmod 700 /run/chubby-redis
printf 'requirepass %s\nappendonly yes\ndir /data\nbind 0.0.0.0\nprotected-mode yes\n' "$password" > /run/chubby-redis/redis.conf
chown redis:redis /run/chubby-redis /run/chubby-redis/redis.conf
exec /usr/local/bin/docker-entrypoint.sh redis-server /run/chubby-redis/redis.conf
