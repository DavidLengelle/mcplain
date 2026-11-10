"""Entry point of the API container: serve the API; the migrations run before, in the one-shot migrate service"""

import sys

import uvicorn

HOST = "0.0.0.0"
PORT = 8000


def main() -> int:
    """Run uvicorn without access log: request paths may carry any text"""

    uvicorn.run(
        "mcplain_api.app:create_app",
        factory=True,
        host=HOST,
        port=PORT,
        access_log=False,
        server_header=False,
        proxy_headers=False,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
