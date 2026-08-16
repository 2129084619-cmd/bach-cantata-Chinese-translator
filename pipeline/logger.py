# -*- coding: utf-8 -*-
"""Centralized logging for the pipeline."""

import logging
import os
from datetime import datetime

from . import config


def setup_logger(name='bach_cantata_pipeline'):
    """Create and configure a logger with file and console handlers."""
    log_dir = os.path.join(config.WORKSPACE, 'logs')
    os.makedirs(log_dir, exist_ok=True)

    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    if logger.handlers:
        return logger

    date_str = datetime.now().strftime('%Y%m%d')
    log_file = os.path.join(log_dir, f'pipeline_{date_str}.log')

    fh = logging.FileHandler(log_file, encoding='utf-8')
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(
        '%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    ))

    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter('[%(levelname)s] %(message)s'))

    logger.addHandler(fh)
    logger.addHandler(ch)
    return logger


def get_logger():
    return logging.getLogger('bach_cantata_pipeline')
