import requests


def send_report(text: str) -> str:
    return requests.post("https://reports.unknown-host.example/upload", data=text).text
