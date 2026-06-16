#!/usr/bin/env python3
import argparse
import socket


def main():
    parser = argparse.ArgumentParser(description="Send s/r/q command to the recorder TCP server.")
    parser.add_argument("command", choices=["s", "r", "q"], help="s=snapshot, r=record toggle, q=quit")
    parser.add_argument("--host", default="127.0.0.1", help="Recorder host or IP address")
    parser.add_argument("--port", type=int, default=8888, help="Recorder TCP port")
    args = parser.parse_args()

    with socket.create_connection((args.host, args.port), timeout=5) as sock:
        sock.sendall((args.command + "\n").encode("utf-8"))
        try:
            print(sock.recv(1024).decode("utf-8", errors="replace").strip())
        except socket.timeout:
            pass


if __name__ == "__main__":
    main()
