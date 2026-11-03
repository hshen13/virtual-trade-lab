"""Offline original storyboard/paired-review fixture, NOT a video or human study."""
import argparse
import csv
import hashlib
import html
import json
import random
from pathlib import Path

SCENES = [
    {'duration': 8, 'shot': '雨夜修表铺。阿澄举起一只停在 23:59 的红色闹钟。', 'dialogue': '阿澄：每到午夜，这只钟就会提前响。'},
    {'duration': 10, 'shot': '钟响，门外自行车铃几乎同时响起。师傅放下螺丝刀。', 'dialogue': '师傅：不是提前，是有人在门外等。'},
    {'duration': 10, 'shot': '阿澄拉开门。门外只有一封写着“请别修好”的信。', 'dialogue': '阿澄：谁会希望钟一直坏着？'},
    {'duration': 12, 'shot': '师傅拿出旧照片：年轻的自己和送信员站在同一扇门前。', 'dialogue': '师傅：她说，最后一封信送完，就回来陪我。'},
    {'duration': 10, 'shot': '阿澄拆开信：镇上夜班邮路复开，落款是照片中的名字。', 'dialogue': '阿澄：她一直在送信。今晚，是最后一班。'},
    {'duration': 10, 'shot': '门铃响起，白发送信员递出空白明信片。红钟走向零点。', 'dialogue': '送信员：下一封，我们一起写。'},
]


def candidates():
    baseline = json.loads(json.dumps(SCENES, ensure_ascii=False))
    revised = json.loads(json.dumps(SCENES, ensure_ascii=False))
    revised[0]['shot'] = '红钟突然响起。门缝滑入一封写着“今晚别修好”的信。阿澄抓住信。'
    revised[0]['dialogue'] = '阿澄：信封是干的，可外面下着雨。'
    revised[2]['shot'] = '阿澄拉开门，看见屋檐下刚离开的自行车尾灯。'
    revised[2]['dialogue'] = '阿澄：送信的人还在这条街上。'
    broken = json.loads(json.dumps(revised, ensure_ascii=False))
    broken[4]['shot'] = '白天，阿澄举起蓝色手表。场景没有转场说明。'
    broken[4]['dialogue'] = '阿澄：我们正在机场找丢失的猫。'
    return {'baseline': baseline, 'revision': revised, 'negative_control': broken}


def simulate(scenes, persona):
    """Transparent arbitrary rule sensitivity. No learned viewer or actual viewing."""
    text = ''.join(s['shot'] + s['dialogue'] for s in scenes)
    hook = int('信封是干的' in text)
    grounded = int('自行车尾灯' in text)
    continuity_error = int('机场' in text)
    # These coefficients are assumptions, not fitted audience preference parameters.
    weights = {'pace': (2, 1), 'clarity': (0, 2), 'quiet': (-2, 0)}[persona]
    return 3 + weights[0] * hook + weights[1] * grounded - 4 * continuity_error


def build(output, seed=42):
    output.mkdir(parents=True, exist_ok=True)
    data = candidates()
    rng = random.Random(seed)
    order = list(data)
    rng.shuffle(order)
    mapping = {f'clip-{i + 1:02}': version for i, version in enumerate(order)}
    panels = []
    for label, version in mapping.items():
        shots = data[version]
        (output / f'{label}.json').write_text(json.dumps(shots, ensure_ascii=False, indent=2) + '\n')
        elapsed = 0
        panels.append(f'<article><h2>{label}</h2>')
        for shot in shots:
            end = elapsed + shot['duration']
            panels.append(f'<section><small>{elapsed}–{end} 秒</small><p>{html.escape(shot["shot"])}</p><strong>{html.escape(shot["dialogue"])}</strong></section>')
            elapsed = end
        panels.append('</article>')
    document = '''<!doctype html><html lang="zh"><meta charset="utf-8"><title>午夜来信 · 盲评分镜</title>
<style>body{font:18px system-ui;background:#10212d;color:#eef3f6;max-width:920px;margin:40px auto;padding:20px}article{margin:40px 0}section{background:#1b3444;padding:18px;margin:12px 0;border-radius:12px}small{color:#aecddd}</style>
<h1>午夜来信 · 原创分镜评审包</h1><p>这是文字分镜，不是生成视频。仅用于脚本流程试验，不能评价表演、画面或声音。版本名称已隐藏；请由组织者分开发放片段与分配表。</p>''' + ''.join(panels) + '</html>'
    (output / 'storyboards.html').write_text(document)
    (output / 'organizer-key.json').write_text(json.dumps(mapping, indent=2) + '\n')
    assignments = []
    for i in range(12):
        labels = [next(k for k,v in mapping.items() if v == 'baseline'), next(k for k,v in mapping.items() if v == 'revision')]
        if i % 2:
            labels.reverse()
        assignments.append({'slot': f'planned-{i + 1:02}', 'first': labels[0], 'second': labels[1], 'status': 'not_recruited'})
    (output / 'planned-assignments.json').write_text(json.dumps(assignments, indent=2) + '\n')
    with (output / 'human-ratings-empty.csv').open('w', newline='') as f:
        csv.writer(f).writerow(['anonymous_id','assignment_slot','asset_sha256','first_clip','second_clip','preference_first_second_tie_neither','clarity_1_5','emotion_1_5','would_continue_yes_no','source','consent_record'])
    rows = []
    for persona in ('pace', 'clarity', 'quiet'):
        a, b, c = [simulate(data[v], persona) for v in ('baseline', 'revision', 'negative_control')]
        rows.append({'synthetic_rule': persona, 'baseline': a, 'revision': b, 'negative_control': c, 'revision_delta': b-a})
    report = {'schema_version': 1, 'seed': seed, 'evidence_type': 'synthetic_rule_fixture', 'model_calls': 0, 'paid_api_calls': 0, 'human_participants': 0, 'generated_videos': 0, 'original_storyboards': 3, 'seconds_per_storyboard': {k: sum(s['duration'] for s in v) for k,v in data.items()}, 'synthetic_sensitivity': rows, 'conclusion': 'Preference changes with assumed rule weights. No empirical quality improvement or product superiority established.', 'human_preference': None, 'watch_retention': None, 'vbench_scores': None, 'real_product_comparison': 'not_run'}
    report['artifact_sha256'] = {f.name: hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted(output.iterdir()) if f.is_file() and f.name != 'report.json'}
    (output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    return report


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--output', type=Path, default=Path(__file__).parent / 'output')
    p.add_argument('--seed', type=int, default=42)
    args = p.parse_args()
    print(json.dumps(build(args.output, args.seed), ensure_ascii=False, indent=2))
