"""Optional mDNS announcer for the Airthings FastAPI server.

Install dependency in the Python environment running AirthingsAPI.py:
    pip install zeroconf

Start the announcer alongside the API process:
    python tools/airthings_api_mdns.py --port 8000

Keep this process running while the API is available. Home Assistant will then
discover the API via the `_airthings-api._tcp.local.` service type.

This helper advertises only the API endpoint; it does not connect to BLE.
"""
import argparse
import signal
import time
from zeroconf import ServiceInfo, Zeroconf
import socket

SERVICE_TYPE = "_airthings-api._tcp.local."

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--name", default="Airthings Local API")
    args = parser.parse_args()

    hostname = socket.gethostname()
    addresses = []
    for info in socket.getaddrinfo(hostname, None, socket.AF_INET, socket.SOCK_STREAM):
        address = info[4][0]
        if not address.startswith("127."):
            packed = socket.inet_aton(address)
            if packed not in addresses:
                addresses.append(packed)
    if not addresses:
        raise SystemExit("Could not determine a LAN IPv4 address")

    instance = args.name.replace(".", "-") + "." + SERVICE_TYPE
    service = ServiceInfo(
        SERVICE_TYPE,
        instance,
        addresses=addresses,
        port=args.port,
        properties={b"scheme": b"http", b"path": b"/"},
        server=f"{hostname}.local.",
    )
    zeroconf = Zeroconf()
    zeroconf.register_service(service)
    print(f"Advertising http://{socket.inet_ntoa(addresses[0])}:{args.port}")
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        pass
    finally:
        zeroconf.unregister_service(service)
        zeroconf.close()

if __name__ == "__main__":
    main()
