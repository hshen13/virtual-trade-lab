"""Metadata-only design gate. No participant ingestion, fitting or certification."""
import argparse
import json
from pathlib import Path

PATH = Path(__file__).with_name('calibration_protocol.json')
GATES = ('product_versions_and_experience', 'participant_provenance_and_consent',
         'blinded_allocation_and_labels', 'household_disjoint_split',
         'preregistered_metrics_tolerance_and_sample_size', 'model_backend_and_version',
         'fresh_unseen_holdout', 'cost_refund_observation_window',
         'independent_result_review')


def template():
    return json.loads(PATH.read_text(encoding='utf-8'))


def validate(spec):
    """Validate this design-only contract; never turn self-reported flags into proof."""
    reference = template()
    if not isinstance(spec, dict) or set(spec) != set(reference):
        raise ValueError('Exact metadata-only top-level fields required; no participant rows')
    for key in ('schema', 'scope', 'sources', 'study_designs', 'axes', 'price_contract',
                'partition_contract', 'outcome_contract'):
        if spec[key] != reference[key]:
            raise ValueError(f'{key}: fixed reviewed design contract changed; requires a new reviewed version')
    if spec['calibration_status'] != 'not_evaluated':
        raise ValueError('This design-only module cannot certify calibrated/aligned/validated status')
    # Null is unavailable, not a zero-sized observed sample or zero-error result.
    if spec['unavailable_evidence'] != reference['unavailable_evidence']:
        raise ValueError('No observations, model outputs or evidence claims accepted in this metadata-only version')
    gates = spec['gates']
    if not isinstance(gates, dict) or set(gates) != set(GATES):
        raise ValueError('All declared gates required')
    for name, gate in gates.items():
        if not isinstance(gate, dict) or set(gate) != {'status', 'evidence_ref'}:
            raise ValueError(f'{name}: invalid gate')
        if gate['status'] not in ('unavailable', 'planned') or gate['evidence_ref'] is not None:
            raise ValueError(f'{name}: this module accepts planning only, not self-certified gate completion')
    return {'scope': 'design_only', 'schema_valid': True, 'calibration_status': 'not_evaluated',
            'human_validation_performed': False, 'participant_rows_imported': 0,
            'model_calls': 0, 'gates_satisfied': 0, 'gates_required': len(GATES),
            'missing_gates': list(GATES)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--spec', type=Path, help='Metadata JSON only; default is bundled protocol')
    args = parser.parse_args()
    try:
        spec = json.loads(args.spec.read_text(encoding='utf-8')) if args.spec else template()
        print(json.dumps(validate(spec), ensure_ascii=False, indent=2))
    except (OSError, ValueError, TypeError) as exc:
        parser.exit(2, str(exc)+'\n')


if __name__ == '__main__':
    main()
