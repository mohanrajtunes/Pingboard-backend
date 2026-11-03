import ipaddress
import socket
from urllib.parse import urlparse

from django.conf import settings


class UnsafeURL(ValueError):
    pass


def _check_ip(raw_ip):
    ip = ipaddress.ip_address(raw_ip.split("%")[0])
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    if not ip.is_global or ip.is_multicast:
        raise UnsafeURL("That address points to a private or internal network.")


def validate_public_url(url):
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise UnsafeURL("Only http and https URLs can be monitored.")
    if not parsed.hostname:
        raise UnsafeURL("The URL has no host name.")
    if parsed.username or parsed.password:
        raise UnsafeURL("URLs with a username or password aren't allowed.")
    if settings.ALLOW_PRIVATE_URLS:
        return
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        infos = socket.getaddrinfo(parsed.hostname, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        raise UnsafeURL("We couldn't find that host. Check the spelling of the address.")
    for info in infos:
        _check_ip(info[4][0])