"""Authenticated operational CLI. No direct database writes or automatic approvals.

Run from repository root: .venv/bin/python backend/tools/inventory_pilot.py --help
Input and outputs containing real operational data belong in ignored pilot-private/.
"""
import argparse
import getpass
import http.cookiejar
import json
from pathlib import Path
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url',required=True,help='Approved API HTTPS origin')
    parser.add_argument('--allow-loopback-http',action='store_true',help='Isolated local rehearsal only')
    parser.add_argument('--email',required=True)
    parser.add_argument('--location',type=uuid.UUID,required=True)
    parser.add_argument('--action',choices=['catalog-preview','catalog-import','opening-preview','opening-import','reconciliation','openings'],required=True)
    parser.add_argument('--input',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    parsed=urllib.parse.urlsplit(args.base_url)
    if parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ('','/'):
        parser.error('Use an origin without credentials, path, query or fragment')
    if parsed.scheme!='https' and not (args.allow_loopback_http and parsed.scheme=='http' and parsed.hostname in {'localhost','127.0.0.1','::1'}):
        parser.error('HTTPS required; only explicit loopback rehearsal may use HTTP')
    paths={'catalog-preview':'catalog-import/preview','catalog-import':'catalog-import','opening-preview':'opening-import/preview','opening-import':'opening-import','reconciliation':'reconciliation','openings':'openings'}
    origin=args.base_url.rstrip('/')
    opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    def request(path,body=None,csrf=''):
        encoded=json.dumps(body).encode() if body is not None else None
        req=urllib.request.Request(origin+path,data=encoded,headers={'Content-Type':'application/json','X-CSRF-Token':csrf})
        try:
            with opener.open(req,timeout=60) as response:
                if response.status == 204:
                    return None
                return json.load(response)
        except urllib.error.HTTPError as exc:
            try:detail=json.load(exc).get('detail','Request rejected')
            except (ValueError,AttributeError):detail='Request rejected'
            raise SystemExit(f'API rejected operation ({exc.code}): {detail}') from None
    password=getpass.getpass('Password (never stored or printed): ')
    auth=request('/api/v1/auth/login',{'email':args.email,'password':password});password=None
    csrf=auth['csrf_token']
    try:
        if args.action=='openings':body=None
        elif not args.input:parser.error('--input is required')
        else:
            if args.input.stat().st_size>200000:parser.error('Input exceeds 200 KB limit')
            body=json.loads(args.input.read_text())
        result=request(f'/api/v1/inventory/locations/{args.location}/{paths[args.action]}',body,csrf)
        # O_EXCL avoids accidental overwrites of a signed operational report.
        import os
        with os.fdopen(os.open(args.output,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'w') as dest:
            json.dump(result,dest,indent=2);dest.write('\n')
        print(f'Operation completed; private report saved to {args.output}. No automatic approval was requested.')
    finally:
        request('/api/v1/auth/logout',{},csrf)


if __name__=='__main__':main()
