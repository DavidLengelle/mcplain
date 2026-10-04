import os


def disk_usage() -> str:
    return os.popen("df -h").read()
