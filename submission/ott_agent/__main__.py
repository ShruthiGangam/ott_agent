"""Run: python -m ott_agent replay --pack .. --out agent_run"""
import argparse
import hashlib
import json
import math
import os
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path
from .common import iso, jsonl, ts, write_json, write_jsonl
from .audit import audit
from .engine import Agent
from .measurement import evaluate
from .provider import ResilientProvider, ProviderError
from .live_check import load_local_env
from .store import Store
from .recorded_provider import RecordedProvider
from .validation import validate_decisions
from .explanations import export_responses
from importlib.metadata import version

def export(store, out):
    write_jsonl(out / 'decisions.jsonl', store.export_rows('decisions'))
    write_jsonl(out / 'actions.jsonl', store.export_rows('actions'))
    write_jsonl(out / 'control_audit.jsonl', store.export_rows('controls'))
    export_responses(out)
    target = out / 'viewer_state'
    target.mkdir(exist_ok=True)
    for state in store.export_rows('viewer_state'):
        # Never use a user-controlled identifier as a filesystem path.
        name = hashlib.sha256(state['user_id'].encode()).hexdigest()[:24] + '.json'
        write_json(target / name, state)

def replay(args):
    pack, out = args.pack.resolve(), args.out.resolve()
    # Generated output must never overwrite supplied evidence/config/replay inputs.
    protected = [pack / name for name in ('data', 'config', 'replay', 'pilot', 'simulator')]
    if out == pack or any(out == p or out.is_relative_to(p) or p.is_relative_to(out) for p in protected):
        raise ValueError('Output directory overlaps evidence pack')
    out.mkdir(parents=True, exist_ok=True)
    if (out / 'state.sqlite').exists() and not args.resume:
        raise ValueError('Output already contains a run. Choose a new --out or use --resume.')
    if args.provider=='live':
        load_local_env(args.env_file)
        provider=ResilientProvider(timeout=args.model_timeout,cache_path=Path('.llm_response_cache_v2.json'))
    else:
        provider=RecordedProvider(path=args.recordings)
    write_json(out / 'run_config.json', {'provider': 'openai_live' if args.provider=='live' else 'recorded_real_replies', 'model_timeout_s': provider.timeout,
        'max_model_calls': args.max_model_calls, 'max_tool_calls': args.max_tool_calls,
        'decision_deadline_s': args.deadline, 'seed': args.seed,
        'data_authorization':'no_external_transmission' if args.provider=='recorded' else 'explicit_user_override_for_synthetic_pack' if os.getenv('LLM_SYNTHETIC_PACK_AUTHORIZED')=='true' else 'provider_terms_acknowledged',
        'zero_data_retention_verified_by_code':False, 'model':provider.config[2],
        'fallback_model':provider.secondary.config[2] if provider.secondary else None,
        'response_validator':{'library':'jsonschema','version':version('jsonschema'),'draft':'2020-12'},
        'goal_interpretations':json.loads((Path(__file__).resolve().parent/'assets/goal_interpretations.json').read_text()),
        'prompt_version':__import__('ott_agent.prompts',fromlist=['PROMPT_VERSION']).PROMPT_VERSION})
    triggers = list(jsonl(pack / 'replay/triggers.jsonl'))
    first = min(ts(e['deliver_at']) for e in triggers)
    store = Store(out / 'state.sqlite')
    print('Loading local history...', flush=True)
    deferred = []
    with store.db:
        for event in jsonl(pack / 'data/events.jsonl'):
            if ts(event['received_at']) < first:
                store.add_event(event)
            else:
                deferred.append(event)
    agent = Agent(pack, store, provider, args.max_model_calls, args.max_tool_calls, args.deadline)
    faults = {r['trigger_event_id']: r for r in jsonl(pack / 'replay/model_faults.jsonl')}
    controls = sorted(jsonl(pack / 'replay/control_events.jsonl'), key=lambda c: ts(c['at']))
    live = list(jsonl(pack / 'replay/live_events.jsonl')) + deferred
    passive = sorted([(ts(c['at']), 0, c) for c in controls] +
                     [(ts(e.get('deliver_at', e['received_at'])), 1, e) for e in live+triggers], key=lambda x: (x[0], x[1]))
    pointer = 0
    def apply_until(now):
        nonlocal pointer
        while pointer < len(passive) and passive[pointer][0] <= now:
            _, kind, item = passive[pointer]
            if kind == 0:
                agent._apply_control(item)
            else:
                agent.observe(item,now)
            pointer += 1
    last_update = time.monotonic()
    duplicate_deliveries = len(triggers)-len({e['event_id'] for e in triggers})
    previous=store.export_rows('decisions')
    last_finish=max((ts(d['published_at']) for d in previous),default=first)
    for index, trigger in enumerate(sorted(triggers, key=lambda e: ts(e['deliver_at'])), 1):
        if store.decision(trigger['event_id']):
            continue
        with store.db:
            arrival=ts(trigger['deliver_at'])
            processing_start=max(arrival,last_finish)
            apply_until(processing_start)
            if store.decision(trigger['event_id']):
                continue
            store.add_event(trigger)
            decision=agent.decide(trigger, faults.get(trigger['event_id']), apply_until,
                queue_delay_s=max(0,(processing_start-arrival).total_seconds()))
            last_finish=max(last_finish,ts(decision['published_at']))
        if index % 25 == 0 or time.monotonic()-last_update > 20:
            print(f'Processed {index}/{len(triggers)} trigger deliveries', flush=True)
            write_json(out/'progress.json',{'processed_deliveries':index,'total_deliveries':len(triggers),
                'unique_decisions':store.db.execute('SELECT COUNT(*) FROM decisions').fetchone()[0],
                'published_actions':store.db.execute('SELECT COUNT(*) FROM actions').fetchone()[0],
                'last_replay_time':iso(last_finish),'stage':'agent_replay'})
            last_update = time.monotonic()
    with store.db:
        if passive:
            apply_until(passive[-1][0])
    export(store, out)
    decisions = store.export_rows('decisions')
    durations = sorted(d['decided_in_ms'] for d in decisions)
    def percentile(p):
        return durations[max(0,math.ceil(len(durations)*p)-1)] if durations else 0
    latency = {'decisions': len(decisions), 'duplicate_deliveries_suppressed': duplicate_deliveries,
        'p50_ms': percentile(.50), 'p95_ms': percentile(.95), 'p99_ms': percentile(.99), 'max_ms': max(durations, default=0),
        'over_60s': sum(v > 60000 for v in durations), 'over_5min': sum(v > 300000 for v in durations),
        'network_model_attempts':sum(d.get('network_model_calls',0) for d in decisions),
        'max_model_calls': max((d['model_calls'] for d in decisions), default=0),
        'max_tool_calls': max((d['tool_calls'] for d in decisions), default=0),
        'decision_kinds':dict(Counter(d.get('decision_kind','legacy') for d in decisions)),
        'model_sources':dict(Counter(d.get('model_source','not_called') for d in decisions)),
        'total_token_usage':{k:sum(d.get('model_usage',{}).get(k,0) for d in decisions) for k in ('prompt_tokens','completion_tokens','total_tokens')},
        'reasons': dict(Counter(d['reason'] for d in decisions)),
        'model_fallbacks': dict(Counter(d['model_fallback'] for d in decisions if 'model_fallback' in d))}
    write_json(out / 'latency_report.json', latency)
    write_json(out/'response_validation_report.json',validate_decisions(out/'decisions.jsonl'))
    write_jsonl(out/'no_action_decisions.jsonl',[d for d in decisions if d['action']=='NO_ACTION'])
    audit_result = audit(pack, out)
    if audit_result['violation_count']:
        raise ValueError('Independent replay audit failed; inspect verification_report.json')
    if not args.skip_simulator:
        subprocess.run([sys.executable, str(pack / 'simulator/simulate_outcomes.py'), '--pack', str(pack),
            '--actions', str(out / 'actions.jsonl'), '--out', str(out / 'sim'), '--seed', args.seed], check=True)
        evaluate(agent, out, triggers, args.seed)
        export(store, out)
        report = json.loads((out / 'sim/simulator_report.json').read_text())
        summary = (f"# Local build verification\n\nProvider: {args.provider}. {len(decisions)} unique decisions; {len(store.export_rows('actions'))} actions. "
            f"Duplicate deliveries suppressed: {duplicate_deliveries}. "
            f"Measured p95: {latency['p95_ms']:.2f} ms; max: {latency['max_ms']:.2f} ms. "
            f"Simulator policy problems: {report['policy_problem_count']}.\n\n"
            'See impact_report.md for randomized comparisons. model_source and provider_mode distinguish live replies, recorded replies and safe fallbacks. Recorded mode tests the engine without evaluating fresh model quality. Production concurrency remains unverified.\n')
        (out / 'final_report.md').write_text(summary, encoding='utf-8')
    write_json(out/'progress.json',{'stage':'complete','processed_deliveries':len(triggers),'unique_decisions':len(decisions),'published_actions':len(store.export_rows('actions'))})
    store.db.close()
    print(f'Run saved to {out}', flush=True)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    run = commands.add_parser('replay')
    run.add_argument('--pack', type=Path, default=Path('..'))
    run.add_argument('--provider',choices=('live','recorded'),default='live',help='recorded: bundled real replies, no key or network; live: your configured API')
    run.add_argument('--recordings',type=Path,help='Optional compatible recorded response bank')
    run.add_argument('--out', type=Path, default=Path('agent_run'))
    run.add_argument('--model-timeout', type=float, default=8)
    run.add_argument('--env-file', type=Path, default=Path('.env'))
    run.add_argument('--max-model-calls', type=int, default=8)
    run.add_argument('--max-tool-calls', type=int, default=20)
    run.add_argument('--deadline', type=float, default=60)
    run.add_argument('--seed', default='oua-practice')
    run.add_argument('--skip-simulator', action='store_true')
    run.add_argument('--resume', action='store_true', help='Resume durable decisions without republishing actions')
    validation=commands.add_parser('validate-responses',help='Validate stored model proposals with local JSON Schema')
    validation.add_argument('--decisions',type=Path,required=True)
    validation.add_argument('--out',type=Path,help='Optional JSON report path')
    args = parser.parse_args()
    try:
        if args.command=='validate-responses':
            report=validate_decisions(args.decisions)
            if args.out:
                write_json(args.out,report)
            print(json.dumps(report),flush=True)
            return 0 if report['passed'] else 1
        replay(args)
    except (ProviderError, ValueError) as error:
        parser.exit(2, str(error) + '\n')
if __name__ == '__main__':
    raise SystemExit(main())
