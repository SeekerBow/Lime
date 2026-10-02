"""支持 ``python -m lime`` 启动。"""

import sys

from .app import main

if __name__ == "__main__":
    sys.exit(main())
