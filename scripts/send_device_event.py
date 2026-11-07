"""Example signed sensor sender. For HTTPS only; no dependencies outside stdlib.

Set OSMANX_DEVICE_ID, OSMANX_DEVICE_SECRET and OSMANX_SENSOR_URL in your
sensor gateway environment. Never place these values in a browser frontend.

Usage:
 python -m scripts.send_device_event --kind traffic --quantity 1 --external-id entrance-001
 python -m scripts.send_device_event --kind zones --quantity 2 --external-id fitting-001 --zone-code fitting
"""
from __future__ import annotations
import argparse
import hashlib
import hmac
import json
import os
import secrets
import sys
import time
import urllib.request
from datetime import datetime,timezone
from urllib.parse import urlparse


def signed_request(public_id: str, secret: str, payload:dict, kind:str, url:str, timestamp:int|None=None) -> urllib.request.Request:
    if kind not in ('traffic','zones'): raise ValueError('kind must be traffic or zones')
    parsed=urlparse(url)
    if parsed.scheme!='https' and not (parsed.scheme=='http' and parsed.hostname in ('localhost','127.0.0.1')):
        raise ValueError('Use HTTPS except for local development')
    stamp=str(timestamp if timestamp is not None else int(time.time()))
    data=json.dumps(payload,ensure_ascii=False,separators=(',',':')).encode()
    sig=hmac.new(secret.encode(),stamp.encode()+b'\n'+public_id.encode()+b'\n'+data,hashlib.sha256).hexdigest()
    path='/api/ingest/v2/'+kind
    return urllib.request.Request(url.rstrip('/')+path,data=data,headers={
      'Content-Type':'application/json','X-OSMANX-Device':public_id,
      'X-OSMANX-Timestamp':stamp,'X-OSMANX-Signature':sig},method='POST')


def main() -> None:
    parser=argparse.ArgumentParser(description='Send one signed aggregated retail sensor event')
    parser.add_argument('--kind',choices=('traffic','zones'),required=True)
    parser.add_argument('--quantity',type=int,required=True)
    parser.add_argument('--external-id',default=None)
    parser.add_argument('--zone-code',default=None)
    args=parser.parse_args()
    device=os.getenv('OSMANX_DEVICE_ID','')
    secret=os.getenv('OSMANX_DEVICE_SECRET','')
    base=os.getenv('OSMANX_SENSOR_URL','http://127.0.0.1:8000')
    if not device or len(secret)<32: parser.error('Set OSMANX_DEVICE_ID and OSMANX_DEVICE_SECRET securely')
    if not 1<=args.quantity<=10000: parser.error('Quantity must be 1-10000')
    if args.kind=='zones' and not args.zone_code: parser.error('--zone-code required for zones')
    payload={'quantity':args.quantity,'external_id':args.external_id or secrets.token_hex(12),
             'occurred_at':datetime.now(timezone.utc).isoformat(timespec='seconds')}
    if args.kind=='zones': payload['zone_code']=args.zone_code
    request=signed_request(device,secret,payload,args.kind,base)
    with urllib.request.urlopen(request,timeout=10) as response:
        print(response.read().decode())

if __name__=='__main__':main()
