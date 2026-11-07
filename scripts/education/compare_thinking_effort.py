"""Replay synthetic teaching fixtures against DeepSeek low/high; never write app state.

Run from the repository root with backend/.venv/Scripts/python.exe.
Credentials are read only from an explicitly supplied local SQLite config database.
Outputs contain synthetic prompts, answers, timings and usage, never credentials.
"""

import argparse
import ast
import asyncio
import copy
import datetime as dt
import hashlib
import json
import random
import sqlite3
import sys
import time
import unicodedata
from pathlib import Path

import httpx
from pydantic import BaseModel, ConfigDict, Field


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def load_validation(root):
    """Load the actual pure validators without importing or initializing the app DB."""
    path = root / 'backend/open_webui/services/education/revision_reading.py'
    tree = ast.parse(path.read_text(encoding='utf-8'))
    names = {'ReadingObservation', 'ReadingFeedback', 'anchor_quote', 'attach_current_revision_draft'}
    nodes = [node for node in tree.body if isinstance(node, (ast.ClassDef, ast.FunctionDef)) and node.name in names]
    namespace = dict(
        BaseModel=BaseModel, ConfigDict=ConfigDict, Field=Field, unicodedata=unicodedata, copy=copy, json=json
    )
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), 'exec'), namespace)
    return namespace


def make_cases(root, validation):
    fixtures = root / 'docs/development/assets/revision-trial-20261107'
    source = json.loads((fixtures / 'final-website-model-trial.json').read_text(encoding='utf-8'))
    cases = []
    for index, case in enumerate(source['cases']):
        reading = case['first_read']
        cases.append(
            dict(
                id=f'initial-{index}',
                name=case['name'],
                kind='reading',
                repeats=3,
                source_text=reading['source_text'],
                messages=reading['context']['attempts'][0]['input'],
                expectation='No substantive defect: acknowledge the bounded argument and finish.'
                if index == 2
                else (
                    'Identify the unsupported inference; give one concrete revision action '
                    'without writing the paragraph.'
                ),
            )
        )
    # Freeze history across both efforts to isolate this response's effort setting.
    for index, name in [(0, '有效修改复看'), (2, '未改稿复看'), (3, '仍有问题但自主结束')]:
        case = source['cases'][index]
        history = [
            dict(role='system', content=case['first_read']['context']['system']),
            dict(role='assistant', content=json.dumps(case['first_read']['feedback'], ensure_ascii=False)),
        ]
        if index == 3:
            history.extend(
                [
                    dict(role='user', content=case['revision_chat']['prompt']),
                    dict(
                        role='assistant', content=case['revision_chat']['response']['choices'][0]['message']['content']
                    ),
                ]
            )
            prompt = case['ending']['prompt']
            expected = (
                'Accept the student ending the discussion; no new task, mandatory revision, '
                'invented approval requirement, or unsupported claim that the argument is now sound.'
            )
        else:
            prompt = '看看这次修改，请先说明我实际改了什么。若没有变化，请如实说明。'
            expected = (
                'Accurately recognize the narrowed claim and explain why it addresses the evidence gap.'
                if index == 0
                else 'State that the draft is unchanged; no invented improvement or manufactured substantive defect.'
            )
        history.append(dict(role='user', content=prompt))
        messages = validation['attach_current_revision_draft'](history, case['revised'])
        # Supply the old draft explicitly for a controlled comparison, as the app does.
        messages[0]['content'] += '\n【上次阅读稿】\n' + case['draft']
        cases.append(
            dict(
                id=f'chat-{index}',
                name=name,
                kind='chat',
                repeats=2,
                source_text=case['revised'],
                messages=messages,
                expectation=expected,
            )
        )
    return cases


def make_retry_cases(path, validation):
    original = json.loads(Path(path).read_text(encoding='utf-8'))
    if not original.get('completed_at'):
        raise ValueError('Wait for the original comparison to complete before retrying')
    by_id = {case['id']: case for case in original['cases']}
    cases = []
    for result in original['results']:
        if result.get('schema_valid') is not False and result.get('quotes_valid') is not False:
            continue
        case = copy.deepcopy(by_id[result['case_id']])
        case.update(
            id=f'{result["case_id"]}-rep{result["repetition"]}-{result["effort"]}-retry',
            repeats=1,
            pinned_effort=result['effort'],
        )
        case['messages'].extend(
            [
                dict(role='assistant', content=result['content']),
                dict(
                    role='user',
                    content=(
                        '输出未满足格式或逐字引文要求。请重新检查：'
                        'understanding、strength、focus、overview 是四个同级字段，focus 不能放入 strength。'
                        '引文必须逐字存在于当前保存稿。只按以下 JSON schema 输出，不改动事实判断：'
                    )
                    + json.dumps(validation['ReadingFeedback'].model_json_schema(), ensure_ascii=False),
                ),
            ]
        )
        cases.append(case)
    return cases


def read_connection(config_db):
    with sqlite3.connect(Path(config_db).resolve().as_uri() + '?mode=ro', uri=True) as db:

        def setting(key):
            row = db.execute('SELECT value FROM config WHERE key=?', (key,)).fetchone()
            if row is None:
                raise ValueError('Required config setting is missing')
            return json.loads(row[0])

        urls, keys = setting('openai.api_base_urls'), setting('openai.api_keys')
    index = next(i for i, url in enumerate(urls) if url.rstrip('/') == 'https://api.deepseek.com')
    endpoint, key = urls[index].rstrip('/') + '/chat/completions', keys[index]
    if not key:
        raise ValueError('DeepSeek connection has no credential')
    return endpoint, key


async def run(args):
    output = Path(args.output)
    if output.exists():
        raise ValueError('Output already exists; choose a new path to preserve previous evidence')
    root = Path(__file__).resolve().parents[2]
    validation = load_validation(root)
    cases = make_cases(root, validation)
    if args.retry_from:
        cases = make_retry_cases(args.retry_from, validation)
    endpoint, key = read_connection(args.config_db)
    output.parent.mkdir(parents=True, exist_ok=True)
    report = dict(
        started_at=dt.datetime.now(dt.UTC).isoformat(),
        model='deepseek-flash',
        scope=(
            'Direct provider replay of frozen synthetic website initial-reading inputs, '
            'plus controlled follow-up conversations; not website end-to-end testing.'
        ),
        protocol=dict(
            efforts=['low', 'high'],
            concurrency=args.concurrency,
            timeout_seconds=240,
            retries=0,
            max_tokens='provider default',
            order_seed=1107,
            platform_mapping={'low': 'low', 'medium': 'high', 'high': 'max'},
        ),
        cases=[{**case, 'input_sha256': digest(case['messages'])} for case in cases],
        results=[],
    )

    def save():
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')

    save()
    if args.retry_from:
        report['retry_source'] = str(Path(args.retry_from))
    jobs = [
        (case, rep, effort)
        for case in cases
        for rep in range(1, case['repeats'] + 1)
        for effort in ([case['pinned_effort']] if 'pinned_effort' in case else ['low', 'high'])
    ]
    random.Random(1107).shuffle(jobs)
    sem = asyncio.Semaphore(args.concurrency)
    async with httpx.AsyncClient(timeout=httpx.Timeout(240, connect=20), trust_env=False) as client:

        async def one(case, rep, effort):
            async with sem:
                payload = dict(
                    model='deepseek-flash',
                    messages=case['messages'],
                    stream=False,
                    thinking={'type': 'enabled'},
                    reasoning_effort=effort,
                )
                result = dict(
                    case_id=case['id'],
                    repetition=rep,
                    effort=effort,
                    input_sha256=digest(case['messages']),
                    started_at=dt.datetime.now(dt.UTC).isoformat(),
                )
                start = time.perf_counter()
                try:
                    response = await client.post(endpoint, headers={'Authorization': 'Bearer ' + key}, json=payload)
                    result['http_status'] = response.status_code
                    response.raise_for_status()
                    data = response.json()
                    choice = data['choices'][0]
                    content = choice['message'].get('content') or ''
                    result.update(
                        response_model=data.get('model'),
                        system_fingerprint=data.get('system_fingerprint'),
                        finish_reason=choice.get('finish_reason'),
                        content=content,
                        usage=data.get('usage'),
                    )
                    if case['kind'] == 'reading':
                        try:
                            parsed = json.loads(content[content.find('{') : content.rfind('}') + 1])
                            feedback = validation['ReadingFeedback'].model_validate(parsed)
                            observations = feedback.focus + ([feedback.strength] if feedback.strength else [])
                            result['schema_valid'] = True
                            result['quotes_valid'] = all(
                                validation['anchor_quote'](case['source_text'], item.quote) is not None
                                for item in observations
                            )
                            result['feedback'] = feedback.model_dump()
                        except (ValueError, TypeError) as error:
                            result['schema_valid'] = False
                            result['validation_error_type'] = type(error).__name__
                except Exception as error:
                    # Never serialize requests or headers from exceptions.
                    result['error_type'] = type(error).__name__
                result['elapsed_seconds'] = round(time.perf_counter() - start, 3)
                result['exceeds_app_90s_read_budget'] = result['elapsed_seconds'] > 90
                report['results'].append(result)
                save()
                print(
                    json.dumps(
                        {
                            k: result.get(k)
                            for k in [
                                'case_id',
                                'repetition',
                                'effort',
                                'elapsed_seconds',
                                'http_status',
                                'schema_valid',
                                'error_type',
                            ]
                        },
                        ensure_ascii=False,
                    ),
                    flush=True,
                )

        await asyncio.gather(*(one(*job) for job in jobs))
    report['completed_at'] = dt.datetime.now(dt.UTC).isoformat()
    save()


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config-db', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--concurrency', type=int, default=4)
    parser.add_argument(
        '--retry-from', help='Replay one application-format correction for each invalid reading in a completed report.'
    )
    asyncio.run(run(parser.parse_args()))
