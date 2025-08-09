#!/usr/bin/env python3
"""
Network utilities for drone communication
"""

import socket
from typing import Optional


def get_local_ip() -> Optional[str]:
    """
    Get local IP address as string.
    Returns None if unable to get IP.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return None 


def get_local_ip_id() -> int:
    """
    Get drone ID from the last octet of local IP address.
    Returns the last octet as integer, or 1 if unable to get IP.
    """
    local_ip = get_local_ip()
    if local_ip is not None:
        try:
            # Extract last octet
            last_octet = int(local_ip.split('.')[-1])
            return last_octet
        except Exception:
            pass
    # Return default ID if unable to get IP or parse octet
    return 1