from __future__ import annotations

import re
import socket

_PRIVATE_172 = re.compile(r"^172\.(1[6-9]|2\d|3[01])\.")


def _rank(address: str) -> int:
    if address.startswith("192.168."):
        return 0
    if address.startswith("10."):
        return 1
    if _PRIVATE_172.match(address):
        return 2
    if address.startswith("100."):
        return 4
    return 3


def _usable(address: str) -> bool:
    return bool(address) and not address.startswith(("127.", "169.254.", "0."))


def _probe_address() -> str | None:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.settimeout(0.5)
            probe.connect(("8.8.8.8", 80))
            return probe.getsockname()[0]
    except OSError:
        return None


def is_local_client(host: str | None) -> bool:
    """True, когда запрос пришёл с этого же компьютера, а не из локальной сети."""
    value = (host or "").strip()
    if not value:
        return False
    if value in {"127.0.0.1", "::1", "localhost"}:
        return True
    try:
        infos = socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)
    except OSError:
        return False
    return any(str(info[4][0]) == value for info in infos)


def lan_address() -> str | None:
    """Локальный IPv4, по которому компьютер виден другим устройствам в Wi-Fi."""
    addresses: set[str] = set()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            addresses.add(str(info[4][0]))
    except OSError:
        pass
    probed = _probe_address()
    if probed:
        addresses.add(probed)
    candidates = [address for address in addresses if _usable(address)]
    if not candidates:
        return None
    return sorted(candidates, key=_rank)[0]
