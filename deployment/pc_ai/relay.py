"""VM의 Docker 내부 연결을 PC의 SSH 역방향 포트로 전달한다."""
import argparse
import ipaddress
import select
import socket
import socketserver
import threading


def serve(bind, port, upstream, allowed):
    class Handler(socketserver.BaseRequestHandler):
        def handle(self):
            if not any(ipaddress.ip_address(self.client_address[0]) in net for net in allowed):
                return
            try:
                with socket.create_connection(('127.0.0.1', upstream), timeout=3) as remote:
                    remote.settimeout(180)
                    self.request.settimeout(180)
                    while True:
                        ready, _, _ = select.select([self.request, remote], [], [], 180)
                        if not ready:
                            return
                        for source in ready:
                            chunk = source.recv(65536)
                            if not chunk:
                                return
                            (remote if source is self.request else self.request).sendall(chunk)
            except (OSError, TimeoutError):
                return

    class Server(socketserver.ThreadingTCPServer):
        allow_reuse_address = True
        daemon_threads = True

    return Server((bind, port), Handler)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bind', required=True)
    parser.add_argument('--allow', action='append', required=True)
    args = parser.parse_args()
    address = ipaddress.ip_address(args.bind)
    if not address.is_private or address.is_unspecified or address.is_loopback:
        parser.error('Docker 내부 gateway 주소만 사용할 수 있습니다.')
    allowed = [ipaddress.ip_network(value) for value in args.allow]
    # 먼저 세 포트를 모두 확보해 일부 포트만 살아 있는 기동을 방지한다.
    servers = [serve(args.bind, port, upstream, allowed)
               for port, upstream in [(11439, 21434), (11440, 28081), (18763, 28761)]]
    for server in servers:
        threading.Thread(target=server.serve_forever, daemon=True).start()
    threading.Event().wait()
