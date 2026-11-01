"""Deterministic comparison. All databases are deleted on exit."""
import json
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from refund_lab import Ledger, Provider


def run():
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        baseline = Provider(root / 'baseline.db')
        baseline.add_payment('payment-demo', 10000)
        try:
            baseline.submit('payment-demo', 2000, lose_response=True)
        except TimeoutError:
            pass
        baseline.submit('payment-demo', 2000)  # same intent, no durable identity
        for event in baseline.events():
            baseline.settle(event.refund_id)
        result = {'simulation_only': True, 'baseline': {'logical_intents': 1, 'provider_refunds': len(baseline.events()), 'refunded_minor_units': baseline.total('payment-demo')}}
        baseline.close()
        provider = Provider(root / 'provider.db')
        provider.add_payment('payment-demo', 10000)
        ledger = Ledger(root / 'ledger.db')
        first = ledger.send(provider, 'return-line-7', 'payment-demo', 2000, lose_response=True)
        ledger.close()
        provider.close()
        provider = Provider(root / 'provider.db')
        ledger = Ledger(root / 'ledger.db')
        stale = ledger.observe(provider, 'return-line-7', visible=False)
        retry = ledger.send(provider, 'return-line-7', 'payment-demo', 2000)
        accepted = provider.events()[0]
        final = provider.settle(accepted.refund_id)
        ledger.reconcile(final)
        duplicate = ledger.reconcile(final)
        late = ledger.reconcile(replace(accepted, event_id=accepted.event_id + ':redelivery'))
        result['durable'] = {'after_lost_response': first['status'], 'after_stale_read': stale['status'], 'after_restart_retry': retry['status'], 'eventual_status': ledger.get('return-line-7')['status'], 'provider_refunds': len(provider.events()), 'refunded_minor_units': provider.total('payment-demo'), 'duplicate_event': duplicate, 'late_accepted_event': late}
        ledger.close()
        provider.close()
        return result


if __name__ == '__main__':
    print(json.dumps(run(), indent=2, sort_keys=True))
