import uvicorn
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

if __name__ == "__main__":
    from core.config import config

    # Behind nginx the only peer is the proxy on loopback, so binding there
    # means nothing outside the container can reach the app at all — that, not
    # the TLS termination point, is what keeps X-Forwarded-For unforgeable.
    # BIND_HOST overrides it for a run with no proxy in front (dev compose
    # publishes a port, so it needs 0.0.0.0).
    host = os.environ.get("BIND_HOST") or ("0.0.0.0" if config.DEBUG else "127.0.0.1")

    uvicorn.run(
        "main:app",
        host=host,
        port=config.PORT,
        reload=config.DEBUG,
        app_dir="src",
        # Uvicorn's own forwarded-header handling defaults to ON and trusts
        # 127.0.0.1 — exactly the peer nginx presents. Left enabled it rewrites
        # request.client.host from X-Forwarded-For before any of our code runs,
        # which silently retires security/clientIp.py: the trusted-chain walk,
        # the hop validation and the canonical form all stop happening and the
        # key becomes whatever uvicorn's parser returned. One resolver, ours.
        proxy_headers=False,
    )