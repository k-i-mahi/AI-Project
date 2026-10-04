"""Allow ``python -m neon_pursuit``."""

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
