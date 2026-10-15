'''Repeatable demo flows for local verification and interviews.

Default mode checks services and runs local knowledge retrieval. Planning APIs
run only with --execute-planning because they may consume model quota.
'''
from __future__ import annotations

import argparse
import json
from datetime import date, timedelta
from uuid import uuid4

import httpx


def preferences(city_id: int) -> dict:
    start = date.today() + timedelta(days=14)
    return {
        'destination_city_id': city_id,
        'start_date': str(start),
        'end_date': str(start + timedelta(days=1)),
        'trip_type': 'weekend',
        'budget_level': 'medium',
        'budget_per_day': 300,
        'preferred_categories': ['culture', 'food'],
        'energy_level': 'moderate',
        'travel_mode': 'mixed',
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', default='http://127.0.0.1:8000')
    parser.add_argument('--execute-planning', action='store_true')
    args = parser.parse_args()
    with httpx.Client(base_url=args.base_url, timeout=110, trust_env=False) as client:
        status = client.get('/api/v1/system/status')
        status.raise_for_status()
        print('[status]', json.dumps(status.json(), ensure_ascii=False))
        cities = client.get('/api/v1/cities')
        cities.raise_for_status()
        chengdu = next(c for c in cities.json() if c.get('name') == 'Chengdu' or c.get('name_zh') == '成都')
        city_id = chengdu['id']
        knowledge = client.post('/api/v1/knowledge/ask', json={
            'city_id': city_id, 'poi_name': '武侯祠', 'question': '行李在哪里寄存？'
        })
        knowledge.raise_for_status()
        kd = knowledge.json()
        print('[knowledge]', json.dumps({
            'status': kd['status'], 'retrieval_mode': kd['retrieval_mode'],
            'citations': [c['id'] for c in kd['citations']]
        }, ensure_ascii=False))
        if not args.execute_planning:
            print('[planning] skipped; add --execute-planning to call planning APIs')
            return 0
        body = preferences(city_id)
        normal = client.post('/api/v1/plan-itinerary', headers={'X-Session-ID': str(uuid4())}, json=body)
        normal.raise_for_status()
        nd = normal.json()
        print('[normal]', json.dumps({
            'days': len(nd['days']), 'narrative_source': nd['narrative'].get('source'),
            'poi_status': (nd.get('poi_search') or {}).get('status')
        }, ensure_ascii=False))
        agent = client.post('/api/v1/agent-plan', headers={'X-Session-ID': str(uuid4())},
                            json={'preferences': body, 'user_message': '优先文化和美食，先查询候选地点再安排行程。'})
        agent.raise_for_status()
        ad = agent.json()
        print('[agent]', json.dumps({
            'days': len(ad['itinerary']['days']), 'termination': ad['termination_reason'],
            'provider': ad.get('provider'),
            'narrative_source': ad['itinerary']['narrative'].get('source')
        }, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
