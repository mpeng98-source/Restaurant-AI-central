"""Background worker foundation; no transaction or AI execution handlers are registered."""
import time

from redis import Redis

from app.config import settings


def main():
    redis = Redis.from_url(settings.redis_url, decode_responses=True, socket_connect_timeout=2, socket_timeout=2)
    try:
        redis.ping()
        while True:
            time.sleep(30)
            redis.ping()
    finally:
        redis.close()


if __name__ == "__main__":
    main()
