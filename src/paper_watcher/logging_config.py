import logging

DEFAULT_LOG_FORMAT = (
    "%(asctime)s " 
    "%(levelname)-8s" 
    "%(name)s: "
    "%(message)s"
)

def setup_logging(
    level: int = logging.INFO,
) -> None:
    logging.basicConfig(
        level=level,
        format=DEFAULT_LOG_FORMAT,
        datefmt="%Y-%m-%d %H:%M:%S",
    )