"""Original synthetic handoff protocol; not an upstream policy or payment engine.

Scheduling surfaces work to each rule participant. It never manufactures consent.
The event log is replayable; caller identity is a test label, not authentication.
"""
from dataclasses import dataclass, field
from copy import deepcopy
import json


@dataclass
class Handoff:
    accepted: bool = False
    slots: dict = field(default_factory=dict)
    slot: str | None = None
    inspection: int | None = None
    confirmations: list = field(default_factory=list)
    status: str = 'negotiating'
    events: list = field(default_factory=list)

    def apply(self, key, actor, action, value=None):
        event = dict(key=key, actor=actor, action=action, value=value)
        if not isinstance(key, str) or not key:
            raise ValueError('nonempty operation key required')
        for old in self.events:
            if old['key'] == key:
                if json.dumps(old, sort_keys=True) != json.dumps(event, sort_keys=True):
                    raise ValueError('operation key reused with different payload')
                return False
        if actor not in ('buyer', 'seller'):
            raise ValueError('participant required; coordinator cannot confirm')
        if self.status in ('completed', 'declined'):
            raise ValueError('terminal handoff')
        if action == 'accept_quote':
            if actor != 'buyer' or self.accepted or self.status != 'negotiating':
                raise ValueError('buyer quote acceptance required once')
            self.accepted, self.status = True, 'accepted'
        elif action == 'availability':
            if not self.accepted or actor in self.slots or self.slot:
                raise ValueError('availability must follow acceptance, once per participant')
            if not isinstance(value, list) or any(not isinstance(s, str) or not s for s in value):
                raise ValueError('explicit slot list required')
            self.slots[actor] = sorted(set(value))
            if len(self.slots) == 2:
                common = sorted(set(self.slots['buyer']) & set(self.slots['seller']))
                if common:
                    self.slot, self.status = common[0], 'scheduled'
        elif action == 'inspect':
            if actor != 'buyer' or not self.slot or self.inspection is not None:
                raise ValueError('buyer inspection after scheduling, once')
            if type(value) is not int or not 0 <= value <= 100:
                raise ValueError('synthetic quality must be integer 0..100')
            self.inspection = value
        elif action == 'confirm':
            if value is not True or not self.slot or actor in self.confirmations:
                raise ValueError('explicit fresh confirmation after scheduling required')
            if actor == 'buyer' and self.inspection is None:
                raise ValueError('buyer must inspect before deciding')
            self.confirmations.append(actor)
            if len(self.confirmations) == 2:
                self.status = 'completed'
        elif action == 'decline':
            if not self.accepted or not isinstance(value, str) or not value:
                raise ValueError('decline needs acceptance and reason')
            self.status = 'declined'
        else:
            raise ValueError('unknown action')
        self.events.append(deepcopy(event))
        return True

    def pending(self):
        if self.status in ('completed', 'declined'):
            return []
        if not self.accepted:
            return [{'actor': 'buyer', 'decision': 'accept_quote_or_no_buy'}]
        if not self.slot:
            missing = [a for a in ('buyer', 'seller') if a not in self.slots]
            return [{'actor': a, 'decision': 'provide_availability_or_decline'} for a in missing] or [
                {'actor': 'both', 'decision': 'no_common_slot_unresolved'}]
        return [dict(actor=a, decision='inspect_then_decide' if a == 'buyer' and self.inspection is None
                     else 'confirm_or_decline') for a in ('buyer', 'seller') if a not in self.confirmations]

    def snapshot(self):
        return dict(status=self.status, accepted=self.accepted, slot=self.slot,
                    inspection=self.inspection, confirmations=sorted(self.confirmations),
                    pending=self.pending(), events=deepcopy(self.events))

    @classmethod
    def replay(cls, events):
        result = cls()
        for e in events:
            if not result.apply(**e):
                raise ValueError('persisted log contains duplicate event')
        return result


def buyer_rule(quality, minimum):
    if any(type(x) is not int or not 0 <= x <= 100 for x in (quality, minimum)):
        raise ValueError('quality and minimum require integer 0..100')
    return ('confirm', True) if quality >= minimum else ('decline', 'quality_below_minimum')


def seller_rule(owns_item, willing):
    if type(owns_item) is not bool or type(willing) is not bool:
        raise ValueError('seller decision inputs must be booleans')
    return ('confirm', True) if owns_item and willing else ('decline', 'seller_cannot_or_will_not_handoff')


def run_case(case):
    for key in ('seller_responds', 'seller_owns_item', 'seller_willing'):
        if type(case[key]) is not bool:
            raise ValueError(f'{key} must be boolean')
    buyer_rule(case['quality'], case['minimum_quality'])
    h = Handoff()
    h.apply('accept', 'buyer', 'accept_quote')
    accepted_snapshot = h.snapshot()
    h.apply('buyer_slots', 'buyer', 'availability', case['buyer_slots'])
    h.apply('seller_slots', 'seller', 'availability', case['seller_slots'])
    if h.slot:
        h.apply('inspect', 'buyer', 'inspect', case['quality'])
        action, value = buyer_rule(case['quality'], case['minimum_quality'])
        h.apply('buyer_decision', 'buyer', action, value)
        if h.status != 'declined' and case['seller_responds']:
            action, value = seller_rule(case['seller_owns_item'], case['seller_willing'])
            h.apply('seller_decision', 'seller', action, value)
    saved = json.loads(json.dumps(h.events))
    restored = Handoff.replay(saved)
    before = restored.snapshot()
    for event in saved:
        if restored.apply(**event) is not False:  # Lost-response retries, even after terminal.
            raise RuntimeError('retry unexpectedly added an event')
    if restored.snapshot() != before or before != h.snapshot():
        raise RuntimeError('replay or retry changed state')
    return dict(case_id=case['id'], decision_source='two separate deterministic rule functions, not model roles',
                accepted_snapshot=accepted_snapshot, final=before, replay_identical=True,
                repeated_operations_added=0, ledger_operations=0, real_payments=0)


def main():
    import argparse
    from pathlib import Path
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--protocol', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    import hashlib
    raw = args.protocol.read_bytes()
    protocol = json.loads(raw)
    result = dict(schema='original-handoff-experiment/v1', protocol_sha256=hashlib.sha256(raw).hexdigest(),
                  results=[run_case(c) for c in protocol['cases']], upstream_mutations=0,
                  upstream_completed_deals_unchanged=0, model_calls=0,
                  limits='Rule-controlled protocol regression, not independent human/model decisions, market success or upstream reproduction. No payment or inventory transfer implemented.')
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')


if __name__ == '__main__':
    main()
