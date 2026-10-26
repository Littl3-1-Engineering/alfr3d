"""TLS sidecar: keeps nginx's leaf cert valid for whatever addresses this host currently has.

The CA (ca.key / ca.crt) lives in CA_DIR, mounted only into this service. The leaf and the
public CA cert are written to OUT_DIR, which nginx and service_api read. Because clients pin
the CA, re-issuing the leaf on an IP/network change is invisible to them.
"""

import logging
import os
import shutil
import time

import docker

import local_tls

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("TlsLog")

CA_DIR = os.getenv("TLS_CA_DIR", "/ca")
OUT_DIR = os.getenv("TLS_OUT_DIR", "/certs")
CHECK_INTERVAL = int(os.getenv("TLS_CHECK_INTERVAL", "60"))
EXTRA_SANS = [s for s in os.getenv("TLS_EXTRA_SANS", "").split(",") if s.strip()]
NGINX_SERVICE = os.getenv("TLS_NGINX_SERVICE", "nginx")


def publish_ca(ca_cert):
    """Copy the public CA cert next to the leaf so nginx/service_api can serve it."""
    shutil.copyfile(os.path.join(CA_DIR, "ca.crt"), os.path.join(OUT_DIR, "ca.crt"))
    logger.info(f"CA fingerprint (SHA-256): {local_tls.cert_fingerprint(ca_cert)}")


def reload_nginx():
    """HUP the nginx container so it picks up the new leaf; nginx only reads certs on reload."""
    try:
        client = docker.from_env()
        containers = client.containers.list(
            filters={"label": f"com.docker.compose.service={NGINX_SERVICE}"}
        )
        for c in containers:
            c.kill(signal="HUP")
            logger.info(f"Signalled {c.name} to reload")
        if not containers:
            logger.info("nginx not running yet; it will read the new cert when it starts")
    except Exception as e:
        logger.error(f"Failed to reload nginx: {e}")


def reconcile(ca_cert, ca_key):
    sans = local_tls.host_sans(EXTRA_SANS)
    leaf_path = os.path.join(OUT_DIR, "server.crt")
    if not local_tls.leaf_needs_reissue(leaf_path, ca_cert, sans):
        return
    local_tls.issue_leaf(ca_cert, ca_key, sorted(sans), OUT_DIR)
    logger.info(f"Issued leaf cert for: {', '.join(sorted(sans))}")
    reload_nginx()


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    ca_cert, ca_key = local_tls.ensure_ca(CA_DIR)
    publish_ca(ca_cert)
    while True:
        try:
            reconcile(ca_cert, ca_key)
        except Exception as e:
            logger.error(f"Reconcile failed: {e}")
        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
