from __future__ import annotations

from .app import create_app
from .config import SidecarConfig


def main() -> None:
    import uvicorn

    config = SidecarConfig.from_env()
    uvicorn.run(
        create_app(config),
        host=config.host,
        port=config.port,
        access_log=False,
        server_header=False,
    )


if __name__ == '__main__':
    main()
