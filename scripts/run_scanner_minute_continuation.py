"""Thin entry point for the fixed scanner-minute continuation."""
import sys
from hosted_scanner_source_cli import main
from momentumbot.research import scanner_minute_continuation

if __name__ == '__main__':
    try: sys.exit(main(scanner_minute_continuation))
    except Exception:
        print('Scanner minute continuation failed; evidence retained; no retry.', file=sys.stderr)
        sys.exit(2)
