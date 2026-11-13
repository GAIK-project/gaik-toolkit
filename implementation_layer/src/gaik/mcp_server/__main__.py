"""``python -m gaik.mcp_server``: the same as the console script ``gaik-mcp``."""

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
