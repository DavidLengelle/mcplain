import subprocess


def check_server_starts() -> None:
    subprocess.run(["python", "server.py", "--help"], check=True)
