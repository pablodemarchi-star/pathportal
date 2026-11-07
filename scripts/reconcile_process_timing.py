"""Optional standalone cron: reconcile date-driven timing gates without a browser.

The existing Finance agenda job already invokes this reconciliation daily.
This command can additionally be scheduled if a separate job is preferred.
"""
import os
import sys
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit


def main():
    base=os.getenv('PORTAL_BASE_URL','https://portal.pathinternalportal.com').rstrip('/')
    token=os.getenv('QUALITY_TIMING_JOB_TOKEN') or os.getenv('FINANCE_AGENDA_JOB_TOKEN','')
    parsed=urlsplit(base)
    if parsed.scheme!='https' or not parsed.netloc or parsed.path or parsed.query or parsed.fragment or len(token)<32:
        print('Configure the portal HTTPS origin and a job token of at least 32 characters.',file=sys.stderr)
        return 1
    try:
        with urlopen(Request(base+'/internal/jobs/process-timing',data=b'',method='POST',headers={'Authorization':'Bearer '+token}),timeout=90) as response:
            print('Process timing reconciliation completed (HTTP %s).'%response.status)
        return 0
    except HTTPError as exc:
        print('Process timing reconciliation failed (HTTP %s).'%exc.code,file=sys.stderr)
    except (URLError,OSError):
        print('Process timing reconciliation could not reach the portal.',file=sys.stderr)
    return 1


if __name__=='__main__':
    sys.exit(main())
