"""Parse linkedin_scraper.log and generate data/stats/list_health.json with analytics."""

import json
import re
import os
from collections import defaultdict
from datetime import datetime

LOG_FILE = 'logs/linkedin_scraper.log'
OUTPUT_FILE = 'data/stats/list_health.json'


def parse_log():
    with open(LOG_FILE, encoding='utf-8', errors='replace') as f:
        lines = f.readlines()

    runs = []
    current_run = None
    total_history = 0

    for line in lines:
        if 'LINKEDIN SCRAPER GESTARTET' in line:
            date = line.split(' - ')[0].strip()
            current_run = {
                'date': date[:10],
                'started_at': date,
                'lists': defaultdict(lambda: {'new': 0, 'dup': 0, 'pages': 0, 'max_page': 0}),
                'total': None,
                'failed_reason': None,
            }
        elif 'Bereits in Historie:' in line and current_run:
            m = re.search(r'Bereits in Historie: (\d+)', line)
            if m:
                total_history = int(m.group(1))
                current_run['history_size'] = total_history
        elif 'Gesammelte Leads:' in line and current_run:
            m = re.search(r'Gesammelte Leads: (\d+)', line)
            current_run['total'] = int(m.group(1))
            runs.append(current_run)
            current_run = None
        elif current_run and 'neue,' in line and 'Duplikate' in line:
            m = re.search(r'Seite (\d+) \[(.+?)\]: (\d+) neue, (\d+) Duplikate', line)
            if m:
                page = int(m.group(1))
                list_name = m.group(2)
                new = int(m.group(3))
                dup = int(m.group(4))
                current_run['lists'][list_name]['new'] += new
                current_run['lists'][list_name]['dup'] += dup
                current_run['lists'][list_name]['pages'] += 1
                current_run['lists'][list_name]['max_page'] = max(
                    current_run['lists'][list_name]['max_page'], page
                )
        elif current_run and ('Timeout' in line or 'timeout' in line.lower()):
            current_run['failed_reason'] = 'timeout'
        elif current_run and 'ERROR' in line and not current_run['failed_reason']:
            current_run['failed_reason'] = 'error'

    return runs, total_history


def build_monthly_summary(runs):
    months = defaultdict(lambda: {
        'runs': 0, 'successful_runs': 0, 'failed_runs': 0, 'total_leads': 0
    })
    for run in runs:
        month = run['date'][:7]
        months[month]['runs'] += 1
        months[month]['total_leads'] += run['total'] or 0
        if run['total'] and run['total'] > 0:
            months[month]['successful_runs'] += 1
        else:
            months[month]['failed_runs'] += 1

    result = []
    for month in sorted(months.keys()):
        d = months[month]
        avg = d['total_leads'] // d['successful_runs'] if d['successful_runs'] > 0 else 0
        result.append({
            'month': month,
            'runs': d['runs'],
            'successful_runs': d['successful_runs'],
            'failed_runs': d['failed_runs'],
            'total_leads': d['total_leads'],
            'avg_per_run': avg,
        })
    return result


def build_list_health(runs):
    # Use last 30 days of data (roughly last month)
    if not runs:
        return []

    recent_runs = [r for r in runs if r['date'] >= '2026-05-22']
    all_time = defaultdict(lambda: {
        'total_new': 0, 'total_dup': 0, 'total_pages': 0,
        'runs_appeared': 0, 'last_seen': '', 'current_page': 0,
        'trend': defaultdict(lambda: {'new': 0, 'dup': 0}),
    })

    for run in recent_runs:
        if run['total'] is None or run['total'] == 0:
            continue
        for list_name, data in run['lists'].items():
            entry = all_time[list_name]
            entry['total_new'] += data['new']
            entry['total_dup'] += data['dup']
            entry['total_pages'] += data['pages']
            entry['runs_appeared'] += 1
            if run['date'] > entry['last_seen']:
                entry['last_seen'] = run['date']
            entry['current_page'] = max(entry['current_page'], data['max_page'])
            entry['trend'][run['date']]['new'] += data['new']
            entry['trend'][run['date']]['dup'] += data['dup']

    result = []
    for name, d in all_time.items():
        total = d['total_new'] + d['total_dup']
        yield_pct = round(d['total_new'] / total * 100, 1) if total > 0 else 0

        if yield_pct < 3:
            status = 'dead'
        elif yield_pct < 10:
            status = 'exhausted'
        elif yield_pct < 30:
            status = 'declining'
        else:
            status = 'healthy'

        trend = [
            {'date': date, 'new': v['new'], 'dup': v['dup']}
            for date, v in sorted(d['trend'].items())
        ]

        result.append({
            'name': name,
            'current_page': d['current_page'],
            'total_new': d['total_new'],
            'total_duplicates': d['total_dup'],
            'total_pages': d['total_pages'],
            'yield_pct': yield_pct,
            'runs_appeared': d['runs_appeared'],
            'last_seen': d['last_seen'],
            'status': status,
            'trend': trend,
        })

    result.sort(key=lambda x: x['yield_pct'], reverse=True)
    return result


def build_failed_runs(runs):
    result = []
    recent = [r for r in runs if r['date'] >= '2026-05-01' and (r['total'] is None or r['total'] == 0)]
    for run in recent:
        result.append({
            'date': run['date'],
            'started_at': run['started_at'],
            'reason': run.get('failed_reason') or 'timeout',
            'history_size': run.get('history_size', 0),
        })
    return result


def main():
    runs, total_history = parse_log()

    output = {
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'total_history_leads': total_history,
        'monthly_summary': build_monthly_summary(runs),
        'list_health': build_list_health(runs),
        'failed_runs': build_failed_runs(runs),
    }

    out_dir = os.path.dirname(OUTPUT_FILE)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"Generated {OUTPUT_FILE}")
    print(f"  Total history: {total_history} leads")
    print(f"  Monthly entries: {len(output['monthly_summary'])}")
    print(f"  Lists tracked: {len(output['list_health'])}")
    print(f"  Failed runs: {len(output['failed_runs'])}")


if __name__ == '__main__':
    main()
