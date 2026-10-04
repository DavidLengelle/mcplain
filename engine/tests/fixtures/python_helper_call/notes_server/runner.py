import subprocess


def run_command(command: str) -> str:
    return _execute(command)


def _execute(command: str) -> str:
    return subprocess.run(command, shell=True, capture_output=True, text=True).stdout
