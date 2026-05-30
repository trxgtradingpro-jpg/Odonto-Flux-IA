from __future__ import annotations

from outreach_intelligence import main


if __name__ == "__main__":
    raise SystemExit(main(["weekly-summary", *(__import__("sys").argv[1:])]))
