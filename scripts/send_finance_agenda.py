"""Render cron command: python scripts/send_finance_agenda.py (09:30 UTC)."""
import os
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


def main():
    base = os.getenv('PORTAL_BASE_URL', 'https://portal.pathinternalportal.com').rstrip('/')
    token = os.getenv('FINANCE_AGENDA_JOB_TOKEN', '')
    parsed = urlsplit(base)
    if parsed.scheme != 'https' or not parsed.netloc or parsed.path or parsed.query or parsed.fragment or len(token) < 32:
        print('Configure the production HTTPS origin and a job token of at least 32 characters.', file=sys.stderr)
        return 1
    try:
        with urlopen(Request(base + '/internal/jobs/finance-agenda', data=b'', method='POST',
            headers={'Authorization': 'Bearer ' + token}), timeout=90) as response:
            print('Finance agenda job completed (HTTP %s).' % response.status)
        return 0
    except HTTPError as exc:
        print('Finance agenda job failed (HTTP %s). Check the portal notification status.' % exc.code, file=sys.stderr)
    except (URLError, OSError):
        print('Finance agenda job could not reach the portal.', file=sys.stderr)
    return 1


if __name__ == '__main__':
    sys.exit(main())
