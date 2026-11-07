"""Maintenance: python -m scripts.purge_surveys [--apply]. Dry-run by default."""
import argparse
import json
from backend.database import connect,initialize_db
from backend.privacy import purge_expired_feedback


def main() -> None:
    parser=argparse.ArgumentParser(description='Survey retention enforcement')
    parser.add_argument('--apply',action='store_true',help='Permanently remove expired survey answers and reward codes')
    args=parser.parse_args()
    initialize_db(demo=False)
    with connect() as db:
        print(json.dumps(purge_expired_feedback(db,dry_run=not args.apply),ensure_ascii=False,indent=2))

if __name__=='__main__':
    main()
