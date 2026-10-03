# Copyright (C) 2026 SeekerBow
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""支持 ``python -m lime`` 启动。"""

import sys

from .app import main

if __name__ == "__main__":
    sys.exit(main())
