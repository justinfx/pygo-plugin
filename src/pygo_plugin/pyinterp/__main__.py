from __future__ import absolute_import, print_function

import sys

from .plugin import serve


if __name__ == '__main__':
    import logging
    logging.basicConfig(level=logging.INFO)
    try:
        serve()
    except KeyboardInterrupt:
        sys.exit(0)
