"""Minimal POS HMAC sender for an authorized integrator.

Environment: OSMANX_POS_SOURCE_ID and OSMANX_POS_SOURCE_SECRET.
Usage: python -m scripts.send_pos_batch --url https://example.org/api/ingest/pos \
  --file receipts.json
Example receipts.json: {"receipts":[{"external_id":"receipt-1234",
 "amount_rub":"1999.90","occurred_at":"2026-11-08T10:00:00+03:00"}]}
"""
from __future__ import annotations
import argparse
import hashlib
import hmac
import os
import time
import urllib.request
from pathlib import Path


def signed_request(url: str, raw: bytes, source: str, secret: str):
    if not url.startswith('https://'):
        raise ValueError('Real POS URLs must use HTTPS')
    if not source or not secret:
        raise ValueError('Set OSMANX_POS_SOURCE_ID and OSMANX_POS_SOURCE_SECRET')
    stamp=str(int(time.time()))
    msg=stamp.encode()+b'\n'+source.encode()+b'\n'+raw
    sig=hmac.new(secret.encode(),msg,hashlib.sha256).hexdigest()
    req=urllib.request.Request(url,data=raw,method='POST',headers={
        'Content-Type':'application/json',
        'X-OSMANX-Source':source,
        'X-OSMANX-Timestamp':stamp,
        'X-OSMANX-Signature':sig})
    with urllib.request.urlopen(req,timeout=15) as res:
        return res.read().decode('utf-8')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url',required=True)
    parser.add_argument('--file',type=Path,required=True)
    args=parser.parse_args()
    print(signed_request(args.url,args.file.read_bytes(),
          os.getenv('OSMANX_POS_SOURCE_ID',''),os.getenv('OSMANX_POS_SOURCE_SECRET','')))

if __name__=='__main__':main()
