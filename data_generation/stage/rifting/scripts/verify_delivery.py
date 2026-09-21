"""Verify source preservation, review links, executed evidence and scope."""
from __future__ import annotations
import ast
import hashlib
import json
import re
import subprocess
from urllib.parse import unquote
from workspace import PROJECT, ROOT, digest, utc_now, write_json

def main():
    results=[]
    def check(name,condition,details=None):
        results.append(dict(check=name,passed=bool(condition),details=details))
    frozen=json.loads((ROOT/'output/checks/local_source_manifest.json').read_text(encoding='utf-8'))['files']
    for record in frozen:
        from pathlib import Path
        check('frozen_and_original_hash',digest(ROOT/record['frozen'])==record['sha256']==digest(Path(record['original'])),record['frozen'])
    receipts=[]
    for path in sorted((ROOT/'output/checks').glob('acquisition-*_receipt.json')):
        receipts.extend(json.loads(path.read_text(encoding='utf-8')))
    for record in receipts:
        if record['status']=='downloaded':
            path=ROOT/record['path']
            check('download_hash',path.exists() and digest(path)==record['sha256'],record['path'])
            if record.get('expected_md5'):
                check('publisher_md5',hashlib.md5(path.read_bytes()).hexdigest()==record['expected_md5'],record['path'])
    links=[]
    for file in ROOT.glob('*.md'):
        content=file.read_text(encoding='utf-8')
        for raw in re.findall(r'\]\(([^)]+)\)',content):
            if re.match(r'^[a-z]+://',raw) or raw.startswith('#'):continue
            path=(file.parent/unquote(raw.split('#')[0])).resolve()
            links.append(dict(document=file.name,target=raw,exists=path.exists()))
        check('text_not_placeholder',not any(s in content for s in ['TODO_FILL','TBD_FILL','{w[','{gem[']),file.name)
    check('all_local_review_links',all(v['exists'] for v in links),links)
    for path in (ROOT/'scripts').glob('*.py'):
        ast.parse(path.read_text(encoding='utf-8'))
    check('python_syntax',True)
    notebook=json.loads((ROOT/'notebooks/evidence_review.ipynb').read_text(encoding='utf-8'))
    code_cells=[c for c in notebook['cells'] if c['cell_type']=='code']
    check('notebook_executed',len(code_cells)==4 and all(c['execution_count'] for c in code_cells))
    check('notebook_no_errors',not any(o.get('output_type')=='error' for c in code_cells for o in c['outputs']))
    methods=json.loads((ROOT/'output/checks/method_checks.json').read_text(encoding='utf-8'))
    check('method_scope_not_production',methods['production_ready'] is False)
    check('method_actual_results',methods['mechanics']['unbalanced_load_rejected'] and methods['kinematics']['deterministic_repeat_exact'])
    baseline=json.loads((ROOT/'output/checks/worktree_at_start.json').read_text(encoding='utf-8'))
    status=subprocess.check_output(['git','status','--short'],cwd=PROJECT,text=True)
    outside=lambda s:sorted(line for line in s.splitlines() if 'data_generation/stage/rifting' not in line)
    check('outside_git_status_unchanged',outside(status)==outside(baseline['status']))
    for record in json.loads((ROOT/'output/checks/code_review.json').read_text(encoding='utf-8')):
        check('reviewed_code_unchanged',digest(PROJECT/record['path'])==record['sha256'],record['path'])
    write_json('output/checks/verification.json',dict(created_utc=utc_now(),passed=all(r['passed'] for r in results),checks=results,
        unavailable_downloads=[r for r in receipts if r['status']!='downloaded'],
        data_findings='output/checks/quality_findings.json',
        scope='Artifact consistency, frozen sources and executed diagnostics; geological acceptance is separate.'))
    manifest=[]
    for path in sorted(ROOT.rglob('*')):
        if path.is_file() and path.name!='manifest.json' and '__pycache__' not in path.parts:
            manifest.append(dict(path=path.relative_to(ROOT).as_posix(),bytes=path.stat().st_size,sha256=digest(path)))
    write_json('output/checks/manifest.json',dict(created_utc=utc_now(),files=manifest))
    print(f"{sum(r['passed'] for r in results)}/{len(results)} delivery checks passed; {len(manifest)} files recorded.")
    if not all(r['passed'] for r in results):
        raise RuntimeError([r for r in results if not r['passed']])

if __name__=='__main__':main()
