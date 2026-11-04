"""Synthetic single-offer contract in original currency; no fitting or payments.

Deliberately independent of realism.py's arbitrary budget/utility scales.
"""
import argparse
from decimal import Decimal,InvalidOperation
import hashlib
import json
from pathlib import Path

FIELDS={'schema','domain','case_id','product_id','currency','unit','price_basis','list_price','transaction_price','cash_gift','own_spendable_before_gift','budget_source','gift_timing','decline_retains_gift','experience'}

def amount(value):
    if not isinstance(value,str) or len(value)>64:raise ValueError('money must be exact decimal text in original major currency units')
    try:d=Decimal(value)
    except InvalidOperation:raise ValueError('invalid money') from None
    if not d.is_finite() or d<0 or d.as_tuple().exponent < -2 or d>Decimal('1000000000'):raise ValueError('invalid or unsupported precision money')
    return d

def text(value):return format(value.quantize(Decimal('.01')),'f')

def validate(spec):
    if not isinstance(spec,dict) or set(spec)!=FIELDS:raise ValueError('exact fields required; no outcomes, rates or hidden labels')
    if spec['schema']!='synthetic-single-offer/v1' or spec['domain']!='synthetic':raise ValueError('this interface accepts synthetic cases only, not real rows')
    if spec['currency']!='ZMW' or spec['unit']!='major':raise ValueError('only original ZMW major units supported; no conversion or scaling')
    if spec['price_basis']!='full_transaction_price':raise ValueError('effective price cannot replace transaction price')
    for key in ('case_id','product_id'):
        if not isinstance(spec[key],str) or not spec[key].startswith('synthetic-') or len(spec[key])>120:raise ValueError('synthetic identifiers required')
    price,listing,gift=[amount(spec[k]) for k in ('transaction_price','list_price','cash_gift')]
    if price<=0 or price>listing:raise ValueError('positive full transaction price <= list price required')
    if spec['gift_timing']!='before_offer' or spec['decline_retains_gift'] is not True:raise ValueError('unconditional pre-offer gift retained on decline required')
    own=spec['own_spendable_before_gift']
    if own is None:
        if spec['budget_source']!='unknown':raise ValueError('unknown budget must remain unknown')
    else:
        amount(own)
        if spec['budget_source']!='explicit_synthetic_assumption':raise ValueError('known budget requires explicit synthetic assumption, not outcome fitting')
    exp=spec['experience']
    if not isinstance(exp,dict) or set(exp)!={'status','days'} or exp['status'] not in ('not_available','scripted_prior_use'):raise ValueError('synthetic experience status required')
    if exp['status']=='not_available':
        if exp['days'] is not None:raise ValueError('missing experience is not zero days')
    elif type(exp['days']) is not int or not 0<=exp['days']<=3650:raise ValueError('scripted days must be nonnegative integer')
    return spec

def fingerprint(spec):
    validate(spec)
    normalized=dict(spec)
    for key in ('list_price','transaction_price','cash_gift','own_spendable_before_gift'):
        if normalized[key] is not None:normalized[key]=text(amount(normalized[key]))
    return hashlib.sha256(json.dumps(normalized,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()

def choice_context(spec):
    """Allowlisted model-facing facts only; never contains observed results."""
    validate(spec)
    price,gift=amount(spec['transaction_price']),amount(spec['cash_gift'])
    own=spec['own_spendable_before_gift']
    return {'case_id':spec['case_id'],'product_id':spec['product_id'],'source':'synthetic scenario, no real participant or measured product experience','currency':spec['currency'],'unit':spec['unit'],
            'list_price':text(amount(spec['list_price'])),'full_transaction_price':text(price),'unconditional_cash_gift':text(gift),
            'price_minus_gift':text(price-gift),'price_minus_gift_is_payment':False,
            'own_spendable_before_gift':None if own is None else text(amount(own)),
            'total_spendable_after_gift':None if own is None else text(amount(own)+gift),
            'outside_option':'decline retains the entire gift and own cash; buy spends the full transaction price, not the price minus gift',
            'experience':spec['experience'].copy(),'choices':['buy','decline','defer'],
            'note':'One assigned offer only. Unknown budget is unknown, not zero. No rescaling, automatic utility score, forced choice or inferred WTP.'}

def record(spec,choice,*,previous=None):
    """Record a declared synthetic choice, not a receipt, real outcome or preference fit.

A caller may persist the returned record. Reopening with that record verifies the
same offer and decision. A second price/decision is a new experiment, not a retry.
"""
    digest=fingerprint(spec)
    if choice not in ('buy','decline','defer'):raise ValueError('choice must be buy/decline/defer')
    price,gift=amount(spec['transaction_price']),amount(spec['cash_gift'])
    own=spec['own_spendable_before_gift'];total=None if own is None else amount(own)+gift
    affordable=(True if gift>=price else None) if total is None else total>=price
    if choice=='buy':status='pending_budget_evidence' if affordable is None else 'synthetic_purchase_recorded' if affordable else 'infeasible_declared_buy'
    else:status='declined' if choice=='decline' else 'deferred'
    paid=price if status=='synthetic_purchase_recorded' else Decimal(0)
    result={'schema':'synthetic-single-offer-result/v1','offer_sha256':digest,'case_id':spec['case_id'],'choice':choice,'status':status,
            'currency':spec['currency'],'unit':'major','full_transaction_price':text(price),'cash_gift':text(gift),
            'price_minus_gift':text(price-gift),'own_funds_needed_if_buy':text(max(Decimal(0),price-gift)),
            'budget_affordable':affordable,'recorded_simulated_payment':text(paid),
            'total_cash_after':None if total is None else text(total-paid),
            'gift_retained_on_decline':text(gift) if choice=='decline' else None,
            'real_payment':False,'receipt_verified':False,'calibration_status':'not_evaluated',
            'observed_outcomes_used':False,'realism_utility_used':False,'independent_holdout':False}
    if previous is not None:
        try:
            same=isinstance(previous,dict) and json.dumps(previous,sort_keys=True,allow_nan=False)==json.dumps(result,sort_keys=True,allow_nan=False)
        except (TypeError,ValueError):same=False
        if not same:raise ValueError('conflicting offer/decision or corrupted previous record; do not replay as a new choice')
    return result

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--spec',type=Path,required=True);p.add_argument('--choice',choices=['buy','decline','defer']);p.add_argument('--previous',type=Path)
    args=p.parse_args()
    try:
        spec=json.loads(args.spec.read_text());prior=json.loads(args.previous.read_text()) if args.previous else None
        if args.previous and not args.choice:raise ValueError('--previous requires --choice')
        output=record(spec,args.choice,previous=prior) if args.choice else choice_context(spec)
        print(json.dumps(output,ensure_ascii=False,indent=2))
    except (OSError,ValueError,TypeError) as exc:p.exit(2,str(exc)+'\n')
if __name__=='__main__':main()
