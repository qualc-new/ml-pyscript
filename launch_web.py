"""双击启动本地网页。打包后的程序也会走这里。"""

from __future__ import annotations

import sys
from pathlib import Path

if not getattr(sys, "frozen", False):
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from web.server import main


if __name__ == "__main__":
    if "--open" not in sys.argv and "--help" not in sys.argv and "-h" not in sys.argv:
        sys.argv.append("--open")
    main()
