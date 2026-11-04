"""Recompute descriptive comparisons from saved replies; no model or ledger calls."""
import hashlib
import json
from pathlib import Path


def summarize(directory):
    directory = Path(directory)
    conditions = ('L_AB', 'L_BA', 'H_AB', 'H_BA')
    required = {'protocol.json'} | {c + '.prompt.txt' for c in conditions}
    entries = {}
    for line in (directory / 'freeze.sha256').read_text(encoding='utf-8').splitlines():
        parts = line.split('  ', 1)
        if len(parts) != 2:
            raise ValueError('Malformed freeze manifest')
        expected, name = parts
        if name not in required or name in entries or len(expected) != 64 or any(c not in '0123456789abcdef' for c in expected):
            raise ValueError('Invalid or duplicate frozen input: ' + name)
        entries[name] = expected
    if set(entries) != required:
        raise ValueError('Incomplete freeze manifest')
    for name, expected in entries.items():
        if hashlib.sha256((directory / name).read_bytes()).hexdigest() != expected:
            raise ValueError('Frozen input mismatch: ' + name)
    protocol = json.loads((directory / 'protocol.json').read_text(encoding='utf-8'))
    if not isinstance(protocol, dict) or protocol.get('study_id') != 'model-order-repeats-v1':
        raise ValueError('Unexpected frozen protocol')
    cases = protocol.get('runs')
    if not isinstance(cases, list) or any(not isinstance(c, dict) or not isinstance(c.get('id'), str) for c in cases):
        raise ValueError('Invalid frozen cases')
    expected_ids = {condition + '_r' + str(repeat): condition
                    for condition in conditions for repeat in (1, 2)}
    for case in cases:
        if case.get('condition') != expected_ids.get(case.get('id')):
            raise ValueError('Frozen run condition mismatch')
    if len(cases) != len(expected_ids) or {case['id'] for case in cases} != set(expected_ids):
        raise ValueError('Frozen case coverage mismatch')
    for case in cases:
        if case.get('prompt_file') != expected_ids[case['id']] + '.prompt.txt':
            raise ValueError('Frozen prompt mapping mismatch')
    rows = []
    for case in cases:
        row = dict(case_id=case['id'], condition=case['condition'], decision=None, status='missing', raw=None)
        path = directory / (case['id'] + '.raw.txt')
        if path.exists():
            raw_bytes = path.read_bytes()
            row['sha256'] = hashlib.sha256(raw_bytes).hexdigest()
            try:
                raw = raw_bytes.decode('utf-8')
                row['raw'] = raw.rstrip('\n')
                value = json.loads(raw)
                if set(value) != {'decision', 'reason'} or value['decision'] not in ('A', 'B', 'no_buy') or not isinstance(value['reason'], str) or not value['reason'].strip():
                    raise ValueError('Invalid reply')
                row.update(decision=value['decision'], reason=value['reason'], status='valid')
            except (ValueError, TypeError):
                row['status'] = 'invalid'
        rows.append(row)
    cells = {}
    for condition in ('L_AB','L_BA','H_AB','H_BA'):
        cell_rows = [r for r in rows if r['condition'] == condition]
        valid = [r['decision'] for r in cell_rows if r['status'] == 'valid']
        cells[condition] = dict(planned_n=len(cell_rows), valid_n=len(valid),
                                counts={k:valid.count(k) for k in ('A','B','no_buy')},
                                within_prompt_disagreement=len(set(valid)) > 1 if len(valid)==len(cell_rows) else None)
    return dict(study_id=protocol['study_id'], source='actual isolated conversation-model role outputs',
                rows=rows, cells=cells, failures=sum(row['status'] != 'valid' for row in rows),
                executed_ledger_commands=0, real_payments=0, real_revenue=0,
                limits='Two new roles per cell; no pooling previous study. Shared model family, unverified seeds; within-prompt disagreement is descriptive, no causal order or human calibration claim.')



if __name__ == '__main__':
    directory = Path(__file__).parent
    result = summarize(directory)
    (directory / 'results.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({k: result[k] for k in ('cells','failures')}))
