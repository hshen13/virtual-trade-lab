"""Optional synthetic inspection before commitment. Neither choice is a purchase.

Original serial event protocol, no network identity/authentication or payment.
"""
from copy import deepcopy
import json


class Precommit:
    def __init__(self, available=True, report=None):
        if type(available) is not bool:
            raise ValueError('available must be boolean')
        if report is not None and (not isinstance(report,dict) or not report):
            raise ValueError('inspection fixture must be a nonempty object')
        json.dumps(report,allow_nan=False)
        self.available=available
        self._fixture=deepcopy(report)
        self.choices={}
        self.commitments={}
        self.withdrawn=None
        self.events=[]

    def apply(self,key,actor,action,value):
        event=dict(key=key,actor=actor,action=action,value=value)
        if not isinstance(key,str) or not key:
            raise ValueError('nonempty operation key required')
        for old in self.events:
            if old['key']==key:
                if json.dumps(old,sort_keys=True)!=json.dumps(event,sort_keys=True):
                    raise ValueError('key payload conflict')
                return False
        if actor not in ('buyer','seller'):
            raise ValueError('participant required')
        if action=='inspection_choice':
            if actor in self.choices or self.commitments or self.withdrawn:
                raise ValueError('inspection choice already fixed or closed')
            if value not in ('inspect','skip','exit','defer'):
                raise ValueError('invalid inspection choice')
            self.choices[actor]=value
        elif action=='commit':
            if self.status() not in ('ready_inspected','ready_uninspected','awaiting_other_commit'):
                raise ValueError('commit requires both compatible inspection choices and stock')
            if actor in self.commitments or value not in ('accept','decline','defer'):
                raise ValueError('invalid or repeated commitment')
            self.commitments[actor]=value
        elif action=='withdraw':
            if self.withdrawn or self.status()=='committed' or not isinstance(value,str) or not value:
                raise ValueError('withdrawal requires reason before mutual commitment')
            self.withdrawn=dict(actor=actor,reason=value)
        else:
            raise ValueError('unknown action')
        self.events.append(deepcopy(event))
        return True

    def status(self):
        if self.withdrawn:return 'withdrawn'
        if 'exit' in self.choices.values():return 'exited'
        if not self.available:return 'unavailable'
        if len(self.choices)<2:return 'awaiting_inspection_choices'
        if len(set(self.choices.values()))!=1 or 'defer' in self.choices.values():return 'inspection_unresolved'
        if self.choices['buyer']=='inspect' and self._fixture is None:return 'inspection_unavailable'
        if 'decline' in self.commitments.values():return 'declined'
        if 'defer' in self.commitments.values():return 'commit_deferred'
        if len(self.commitments)==2:return 'committed'
        if self.commitments:return 'awaiting_other_commit'
        return 'ready_inspected' if self.choices['buyer']=='inspect' else 'ready_uninspected'

    def report(self):
        if self.available and self.choices=={'buyer':'inspect','seller':'inspect'}:
            return deepcopy(self._fixture)
        return None

    def snapshot(self):
        return dict(status=self.status(),available=self.available,choices=deepcopy(self.choices),
                    commitments=deepcopy(self.commitments),inspection_report=self.report(),
                    withdrawn=deepcopy(self.withdrawn),events=deepcopy(self.events),ledger_operations=0)

    @classmethod
    def replay(cls,available,report,events):
        state=cls(available,report)
        for e in events:
            if not state.apply(**e):raise ValueError('duplicate persisted event')
        return state
