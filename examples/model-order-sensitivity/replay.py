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
    if not isinstance(protocol, dict) or protocol.get('study_id') != 'model-order-sensitivity-v1':
        raise ValueError('Unexpected frozen protocol')
    cases = protocol.get('cases')
    if not isinstance(cases, list) or any(not isinstance(c, dict) or not isinstance(c.get('id'), str) for c in cases):
        raise ValueError('Invalid frozen cases')
    expected_ids = {condition: condition for condition in conditions}
    for case in cases:
        condition = case.get('id')
        if condition not in expected_ids or case.get('a_price') != (48 if condition.startswith('L') else 88) or case.get('display_order') != condition[2:]:
            raise ValueError('Frozen case condition mismatch')
    if len(cases) != len(expected_ids) or {case['id'] for case in cases} != set(expected_ids):
        raise ValueError('Frozen case coverage mismatch')
    for case in cases:
        if case.get('prompt_file') != expected_ids[case['id']] + '.prompt.txt':
            raise ValueError('Frozen prompt mapping mismatch')
    rows = []
    for case in cases:
        row = dict(case_id=case['id'], decision=None, status='missing', raw=None)
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
    choices = {row['case_id']: row['decision'] for row in rows}
    def comparison(first, second):
        return None if choices[first] is None or choices[second] is None else choices[first] == choices[second]
    return dict(study_id=protocol['study_id'], source='actual isolated conversation-model role outputs',
                rows=rows, order_agreement={p: comparison(p+'_AB', p+'_BA') for p in ('L', 'H')},
                same_choice_across_prices={o: comparison('L_'+o, 'H_'+o) for o in ('AB', 'BA')},
                failures=sum(row['status'] != 'valid' for row in rows), executed_ledger_commands=0,
                real_payments=0, real_revenue=0,
                limits='One role per cell, same model family, no sampling seed; exploratory comparisons only, no human calibration or elasticity estimate.')


if __name__ == '__main__':
    directory = Path(__file__).parent
    result = summarize(directory)
    (directory / 'results.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({k: result[k] for k in ('order_agreement','same_choice_across_prices','failures')}))
