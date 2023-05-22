import logging

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s [%(levelname)-5.5s] [%(name)-10s] %(message)s')

def get_logger(name) -> logging.Logger:
    return logging.getLogger(name)
