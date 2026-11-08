"""Identical global filters for trial and formal calls, without personal valves."""

import copy
import json

from fastapi import HTTPException
from starlette.responses import StreamingResponse

from open_webui.env import ENABLE_PLUGINS
from open_webui.routers.pipelines import (
    get_sorted_filters,
    process_pipeline_inlet_filter,
    process_pipeline_outlet_filter,
)
from open_webui.services.education.revision_reading import revision_model_view
from open_webui.utils.filter import FilterContext, get_filter_functions, get_function_module, process_filter_functions


class TeachingFilterContext(FilterContext):
    async def get_user_valves(self, filter_id, user_id, UserValves):
        # A teacher's private plugin preferences are not a simulated student's.
        return UserValves()


async def prepare(request, user, payload):
    model = revision_model_view(request.app.state.MODELS[payload['model']])
    model['info']['params'] = copy.deepcopy(request.state.teaching_binding['binding']['params'])
    student_view = user.model_copy(update={'role': 'user', 'name': '学生', 'email': '', 'settings': None, 'info': {}})
    context = TeachingFilterContext()
    request.state.filter_context = context
    functions = await get_filter_functions(request, model, []) if ENABLE_PLUGINS else []
    extra = {
        '__user__': {'id': user.id, 'role': 'user'},
        '__request__': request,
        '__model__': model,
        '__metadata__': {'education': True},
        '__event_emitter__': None,
        '__event_call__': None,
    }
    metadata = payload.get('metadata', {})
    payload = copy.deepcopy(payload)
    payload['metadata'] = {'retry_transient': True}
    payload = await process_pipeline_inlet_filter(request, payload, student_view, request.app.state.MODELS)
    payload, _ = await process_filter_functions(request, context, functions, 'inlet', payload, extra)
    config = request.state.teaching_binding
    if payload.get('model') != config['ai']['model_id'] or payload.get('tools'):
        raise HTTPException(409, 'A global filter changed the teaching model or tool scope')
    has_outlet = bool(get_sorted_filters(model['id'], request.app.state.MODELS))
    for function in functions:
        module = await get_function_module(request, function.id, function=function)
        has_outlet = has_outlet or callable(getattr(module, 'outlet', None))
    request.state.teaching_filters = (student_view, context, functions, extra, copy.deepcopy(payload), has_outlet)
    payload['metadata'] = metadata
    return payload


async def finish(request, response):  # noqa: C901 -- streaming and one-shot share one filter boundary
    state = getattr(request.state, 'teaching_filters', None)
    if state is None:
        return response
    user, context, functions, extra, payload, has_outlet = state
    evidence = request.state.teaching_evidence

    async def outlet(text):
        body = {'model': payload['model'], 'messages': [*payload['messages'], {'role': 'assistant', 'content': text}]}
        body = await process_pipeline_outlet_filter(request, body, user, request.app.state.MODELS)
        body, _ = await process_filter_functions(request, context, functions, 'outlet', body, extra)
        return body['messages'][-1]['content']

    if isinstance(response, dict):
        evidence.setdefault('provider_responses', []).append(copy.deepcopy(response))
        if has_outlet and response.get('choices'):
            response = copy.deepcopy(response)
            response['choices'][0]['message']['content'] = await outlet(
                response['choices'][0]['message'].get('content') or ''
            )
        return response
    if not isinstance(response, StreamingResponse):
        return response

    async def filtered_stream():  # noqa: C901 -- raw capture, filters and completion validation share one stream
        pending, raw, reply = '', [], ''
        final_event = {}
        completed = False
        try:
            async for chunk in response.body_iterator:
                decoded = chunk.decode() if isinstance(chunk, bytes) else chunk
                raw.append(decoded)
                pending += decoded
                while '\n' in pending:
                    line, pending = pending.split('\n', 1)
                    if not line.startswith('data:'):
                        continue
                    if line[5:].strip() == '[DONE]':
                        completed = True
                        continue
                    event = json.loads(line[5:])
                    if event.get('error'):
                        raise ValueError('Teaching model generation failed')
                    completed = completed or any(choice.get('finish_reason') for choice in event.get('choices', []))
                    event, _ = await process_filter_functions(request, context, functions, 'stream', event, extra)
                    if not event:
                        continue
                    final_event = event
                    reply += ((event.get('choices') or [{}])[0].get('delta') or {}).get('content') or ''
                    if not has_outlet:
                        yield 'data: ' + json.dumps(event, ensure_ascii=False) + '\n\n'
            if not completed:
                raise ValueError('Teaching model stream was interrupted')
            if not reply.strip():
                raise ValueError('Teaching model returned no visible reply')
        finally:
            evidence.setdefault('provider_streams', []).append(''.join(raw))
        if has_outlet:
            # An outlet may replace the whole answer. Both adapters buffer in that
            # case so an unfiltered answer is never briefly shown to the student.
            text = await outlet(reply)
            yield (
                'data: '
                + json.dumps(
                    {
                        'id': final_event.get('id'),
                        'choices': [{'index': 0, 'delta': {'content': text}, 'finish_reason': 'stop'}],
                        'usage': final_event.get('usage'),
                    },
                    ensure_ascii=False,
                )
                + '\n\n'
            )
        yield 'data: [DONE]\n\n'

    return StreamingResponse(
        filtered_stream(),
        headers=dict(response.headers),
        status_code=response.status_code,
        media_type=response.media_type,
        background=response.background,
    )
