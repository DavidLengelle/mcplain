"""Entry point of the API container: apply the database migrations, then serve the API"""

import os
import sys
from pathlib import Path

import uvicorn
from alembic import command
from alembic.config import Config

ALEMBIC_INI_ENV = "MCPLAIN_ALEMBIC_INI"
DEFAULT_ALEMBIC_INI = "/app/alembic.ini"
HOST = "0.0.0.0"
PORT = 8000


def main() -> int:
    """Run alembic upgrade head, then uvicorn without access log: request paths may carry any text"""

    config = Config(str(Path(os.environ.get(ALEMBIC_INI_ENV, DEFAULT_ALEMBIC_INI))))
    command.upgrade(config, "head")
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
