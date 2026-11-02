"""Uncalibrated synthetic behavior, paired counterfactuals; NOT market evidence."""
import argparse
from dataclasses import asdict, dataclass, replace
import hashlib
import json
from pathlib import Path
import random


@dataclass(frozen=True)
class Offer:
    relevance: float = .7
    clarity: float = .7
    quality: float = .7
    promised_quality: float = .7
    price: float = 18
    friction: float = .1
    repetition: float = .2
    production_cost: float = 80
    channel_cost: float = .2
    delivery_cost: float = 5


@dataclass(frozen=True)
class Person:
    identity: int
    segment: str
    budget: float
    need: float
    taste: float
    outside: float
    patience: float


def people(seed, count=120):
    rng = random.Random(seed)
    return [Person(i, ['budget', 'balanced', 'quality'][i % 3],
                   rng.uniform(8, 22) if i % 3 == 0 else rng.uniform(18, 45),
                   rng.uniform(.1, 1), rng.uniform(.3, 1), rng.uniform(.05, .65),
                   rng.uniform(.25, .9)) for i in range(count)]


def draw(seed, identity, period):
    # Assignment independent of iteration order or arm name.
    return random.Random(f'{seed}:{identity}:{period}').random()


def utility(person, offer, demand=1, competition=1, expected_quality=None):
    return (person.need * demand * offer.relevance * person.taste +
            (offer.promised_quality if expected_quality is None else expected_quality) * .4 - offer.price / 40 - offer.friction - person.outside * competition)


def simulate(offer, cohort, seed, *, demand=1, fatigue=1, competition=1):
    rows = []
    for person in sorted(cohort, key=lambda p: p.identity):
        seen, previous_buy, satisfaction = 0, False, 0.
        expected_quality = offer.promised_quality
        for period in range(3):
            attention = max(0., min(1., person.need * demand * offer.relevance * offer.clarity
                            * person.patience - seen * offer.repetition * fatigue + max(0., satisfaction) * .05))
            view = draw(seed, person.identity, period) < attention
            decision = utility(person, offer, demand, competition, expected_quality) + satisfaction * .15 - seen * offer.repetition * fatigue * .1
            buy = view and person.budget >= offer.price and decision > 0
            paid = offer.price if buy else 0.
            # Same realized taste/quality, not an independent lucky refund coin.
            experience = offer.quality * person.taste - offer.promised_quality
            refund = paid if buy and experience < -.3 else 0.
            repeat = buy and previous_buy
            rows.append(dict(person=person.identity, segment=person.segment, period=period,
                             attention=attention, viewed=view, bought=buy, repeat=repeat,
                             utility=decision, expected_quality=expected_quality, paid=paid, refund=refund,
                             delivery_cost=offer.delivery_cost if buy else 0., channel_cost=offer.channel_cost))
            if view:
                seen += 1
            if buy:
                previous_buy = True
                satisfaction = experience
                expected_quality = offer.quality * person.taste
    paid = sum(r['paid'] for r in rows); refunds = sum(r['refund'] for r in rows)
    costs = offer.production_cost + sum(r['delivery_cost'] + r['channel_cost'] for r in rows)
    return dict(people=len(cohort), segment_counts={segment: sum(p.segment == segment for p in cohort) for segment in sorted({p.segment for p in cohort})}, opportunities=len(rows), views=sum(r['viewed'] for r in rows),
                purchases=sum(r['bought'] for r in rows), repeat_purchases=sum(r['repeat'] for r in rows),
                paid=round(paid, 6), refunds=round(refunds, 6), costs=round(costs, 6),
                net=round(paid-refunds-costs, 6),
                periods=[dict(period=period, opportunities=len(cohort), views=sum(r['viewed'] for r in rows if r['period'] == period), purchases=sum(r['bought'] for r in rows if r['period'] == period), repeat_purchases=sum(r['repeat'] for r in rows if r['period'] == period)) for period in range(3)], rows=rows)


def compare(baseline, candidate, cohort, seed, **cell):
    a, b = simulate(baseline, cohort, seed, **cell), simulate(candidate, cohort, seed, **cell)
    keys = ['views', 'purchases', 'repeat_purchases', 'paid', 'refunds', 'costs', 'net']
    return dict(baseline={k: v for k, v in a.items() if k != 'rows'},
                candidate={k: v for k, v in b.items() if k != 'rows'},
                delta={k: round(b[k]-a[k], 6) for k in keys})


def campaign():
    baseline = Offer()
    candidate = replace(baseline, clarity=.85, quality=.8, price=20, production_cost=110)
    config = dict(schema='synthetic-realism/v2-exploratory', periods=3, people_per_seed=120,
                  development_seeds=[11, 12], holdout_seeds=[101, 102, 103],
                  demand=[.5, 1., 1.5], fatigue=[.5, 1.5], competition=[.5, 1.5],
                  baseline=asdict(baseline), candidate=asdict(candidate),
                  frozen_rule='Report every cell; no empirical superiority gate; prior inspected holdout consumed by model correction, rerun exploratory',
                  assumptions='Attributes, utility coefficients and seed design assumed, not fitted or artifact-quality measurements')
    control_offers = {'identical': baseline, 'overpriced': replace(candidate, price=1000),
                      'irrelevant': replace(candidate, relevance=0),
                      'fatiguing': replace(candidate, repetition=1),
                      'costly_low_quality': replace(candidate, price=5, quality=0, production_cost=1000)}
    config['controls'] = {name: asdict(offer) for name, offer in control_offers.items()}
    config['control_seed'] = 201
    config['model_source_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    encoded = json.dumps(config, sort_keys=True).encode()
    cells = []
    for split, seeds in [('development', config['development_seeds']), ('holdout', config['holdout_seeds'])]:
        for demand in config['demand']:
            for fatigue in config['fatigue']:
                for competition in config['competition']:
                    conditions = dict(demand=demand, fatigue=fatigue, competition=competition)
                    results = [compare(baseline, candidate, people(seed), seed, **conditions) for seed in seeds]
                    deltas = [r['delta']['net'] for r in results]
                    cells.append(dict(split=split, conditions=conditions, seeds=seeds, results=results,
                                      net_delta_range=[min(deltas), max(deltas)],
                                      uncertainty='finite synthetic seed range, NOT empirical confidence interval'))
    controls = {name: compare(baseline, offer, people(201), 201) for name, offer in control_offers.items()}
    return dict(config=config, config_sha256=hashlib.sha256(encoded).hexdigest(), synthetic_only=True,
                empirically_calibrated=False, real_market_validated=False, robustness='not_demonstrated',
                cells=cells, controls=controls,
                limitations=['No observed preferences or elasticity', 'No real competitor measured',
                             'Three periods do not establish sustainability', 'Structural sensitivity is not market uncertainty',
                             'Both former development and holdout seeds are consumed; this corrected rerun is exploratory, not independent validation'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    result = campaign()
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(dict(cells=len(result['cells']), config_sha256=result['config_sha256'], robustness=result['robustness'])))


if __name__ == '__main__':
    main()
