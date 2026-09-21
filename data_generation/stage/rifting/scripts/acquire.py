"""Download only explicitly listed public evidence; never execute source code."""
from __future__ import annotations
import argparse
import json
import hashlib
from concurrent.futures import ThreadPoolExecutor, as_completed
import urllib.request
from workspace import ROOT, digest, target, utc_now, write_json

def download(entry):
    dest = target(entry['path'])
    result = dict(entry, checked_utc=utc_now())
    try:
        if not dest.exists():
            request = urllib.request.Request(entry['url'], headers={'User-Agent': 'LEM-evidence-review/0.1 (public scientific sources)'})
            with urllib.request.urlopen(request, timeout=25) as response:
                body = response.read(120_000_001)
                if len(body) > 120_000_000:
                    raise ValueError('File exceeds this review download limit')
                result.update(final_url=response.url, content_type=response.headers.get('Content-Type'), http_status=response.status)
            suffix = dest.suffix.lower()
            if suffix == '.pdf' and not body.startswith(b'%PDF'):
                raise ValueError('Response is not PDF')
            if suffix == '.zip' and not body.startswith(b'PK'):
                raise ValueError('Response is not ZIP')
            if suffix == '.json':
                json.loads(body)
            if suffix == '.csv' and b'<html' in body[:1000].lower():
                raise ValueError('HTML returned for CSV')
            dest.write_bytes(body)
        if entry.get('expected_md5'):
            measured = hashlib.md5(dest.read_bytes()).hexdigest()
            if measured != entry['expected_md5']:
                raise ValueError('Publisher MD5 mismatch')
            result['publisher_md5_verified'] = True
        result.update(status='downloaded', bytes=dest.stat().st_size, sha256=digest(dest))
    except Exception as error:
        result.update(status='unavailable_this_attempt', error=f'{type(error).__name__}: {error}')
    return result

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('listfile')
    args = parser.parse_args()
    entries = json.loads((ROOT / args.listfile).read_text(encoding='utf-8'))
    records = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(download, entry) for entry in entries]
        for future in as_completed(futures):
            result = future.result()
            records.append(result)
            print(result['source_id'], result['path'], result['status'], result.get('bytes', result.get('error')), flush=True)
            write_json('output/checks/' + __import__('pathlib').Path(args.listfile).stem + '_receipt.json', records)

if __name__ == '__main__':
    main()
