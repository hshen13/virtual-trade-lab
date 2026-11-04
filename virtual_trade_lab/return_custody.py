"""Original return-custody state machine; actor names are simulation labels, not auth."""
from copy import deepcopy
import json


class ReturnProtocol:
    def __init__(self,order='return-order',label='return-A',unit='unit-B',deadline=2,arrival=3):
        if any(not isinstance(x,str) or not x for x in (order,label,unit)):
            raise ValueError('nonempty order/label/unit required')
        if any(type(x) is not int or x<0 for x in (deadline,arrival)):
            raise ValueError('integer nonnegative timing required')
        self.order,self.label,self.unit=order,label,unit
        self.deadline,self.arrival=deadline,arrival
        self.request=self.review=self.shipping=None
        self.handoff=self.receipt=None
        self.events=[]

    def apply(self,key,actor,action,value):
        event=dict(key=key,actor=actor,action=action,value=value)
        if not isinstance(key,str) or not key:raise ValueError('operation key required')
        for old in self.events:
            if old['key']==key:
                if json.dumps(old,sort_keys=True)!=json.dumps(event,sort_keys=True):raise ValueError('key conflict')
                return False
        if action=='request':
            if actor!='buyer' or self.request is not None or value not in ('request_refund','keep','defer'):raise ValueError('invalid buyer request')
            self.request=value
        elif action=='review':
            if actor!='seller' or self.request!='request_refund' or self.review is not None or value not in ('approve_return','request_evidence','deny','defer'):raise ValueError('invalid seller review')
            self.review=value
        elif action=='shipping':
            if actor!='buyer' or self.review!='approve_return' or self.shipping is not None or value not in ('ship','keep','defer'):raise ValueError('invalid shipping choice')
            self.shipping=value
        elif action in ('handoff','receipt'):
            if actor!='carrier' or self.shipping!='ship':raise ValueError('carrier evidence without buyer shipping consent')
            if not isinstance(value,dict) or set(value)!={'order','label','unit','tick'}:raise ValueError('carrier evidence fields')
            if (value['order'],value['label'],value['unit'])!=(self.order,self.label,self.unit):raise ValueError('carrier evidence identity mismatch')
            if type(value['tick']) is not int or value['tick']<0:raise ValueError('invalid carrier tick')
            if action=='handoff':
                if self.handoff is not None or value['tick']>self.deadline:raise ValueError('repeated or late handoff')
                self.handoff=deepcopy(value)
            else:
                if self.receipt is not None or self.handoff is None or value['tick']<max(self.handoff['tick'],self.arrival):raise ValueError('missing handoff, repeated or premature receipt')
                self.receipt=deepcopy(value)
        else:raise ValueError('unknown action')
        self.events.append(deepcopy(event));return True

    def status(self):
        if self.receipt:return 'received_refund_ready'
        if self.handoff:return 'awaiting_receipt'
        if self.request=='keep' or self.shipping=='keep':return 'buyer_keeps'
        if self.shipping=='defer':return 'shipping_deferred'
        if self.shipping=='ship':return 'awaiting_handoff'
        if self.review=='approve_return':return 'awaiting_buyer_shipping'
        if self.review in ('request_evidence','deny','defer'):return 'review_unresolved'
        if self.request=='request_refund':return 'awaiting_seller_review'
        if self.request=='defer':return 'buyer_deferred'
        return 'awaiting_buyer_request'

    def snapshot(self):
        return dict(status=self.status(),request=self.request,review=self.review,shipping=self.shipping,
                    custody='seller' if self.receipt else 'carrier' if self.handoff else 'buyer',
                    refund_ready=self.receipt is not None,label=self.label if self.review=='approve_return' else None,
                    handoff=deepcopy(self.handoff),receipt=deepcopy(self.receipt),events=deepcopy(self.events))

    def configuration(self):
        return dict(order=self.order,label=self.label,unit=self.unit,deadline=self.deadline,arrival=self.arrival)

    @classmethod
    def replay(cls,events,configuration=None):
        state=cls(**(configuration or {}))
        for event in events:
            if not state.apply(**event):raise ValueError('duplicate persisted event')
        return state
