"""SQL aggregates keep diagnostics independent of chat contents and message retention."""

from sqlalchemy import case, func, select

from open_webui.models.model_calls import ModelCall as Call
from open_webui.models.model_calls import ModelCallAttempt as Attempt


def count_if(condition):
    return func.sum(case((condition, 1), else_=0))


async def model_health_summary(db, start, end):
    window = (Call.started_at >= start, Call.started_at <= end)
    rows = (
        (
            await db.execute(
                select(
                    Call.model_id,
                    func.count().label('calls'),
                    count_if(Call.outcome == 'success').label('successes'),
                    count_if(Call.outcome == 'failed').label('failures'),
                    count_if(Call.outcome == 'cancelled').label('cancelled'),
                    count_if(Call.fallback_used).label('fallback_calls'),
                    count_if(Call.fallback_used & (Call.outcome == 'success')).label('fallback_successes'),
                    func.avg(case((Call.outcome == 'success', Call.duration_ms))).label('average_duration_ms'),
                    func.count(func.distinct(case((Call.outcome == 'failed', Call.user_id)))).label('affected_users'),
                    func.max(case((Call.outcome == 'failed', Call.started_at))).label('last_failure_at'),
                )
                .where(*window)
                .group_by(Call.model_id)
            )
        )
        .mappings()
        .all()
    )
    models = {r['model_id']: dict(r, routes=[]) for r in rows}
    routes = (
        (
            await db.execute(
                select(
                    Call.model_id.label('requested_model'),
                    Attempt.model_id,
                    Attempt.route,
                    func.count().label('attempts'),
                    count_if(Attempt.outcome == 'failed').label('failures'),
                    count_if(Attempt.outcome == 'cancelled').label('cancelled'),
                    func.max(case((Attempt.outcome == 'failed', Attempt.started_at))).label('last_failure_at'),
                )
                .join(Call, Call.id == Attempt.call_id)
                .where(*window)
                .group_by(Call.model_id, Attempt.model_id, Attempt.route)
            )
        )
        .mappings()
        .all()
    )
    for row in routes:
        route = dict(row)
        models[route.pop('requested_model')]['routes'].append(route)
    reasons = (
        (
            await db.execute(
                select(Call.model_id, Attempt.reason, func.count().label('count'))
                .join(Call, Call.id == Attempt.call_id)
                .where(*window, Attempt.outcome == 'failed')
                .group_by(Call.model_id, Attempt.reason)
            )
        )
        .mappings()
        .all()
    )
    for model in models.values():
        completed = model['successes'] + model['failures']
        model['failure_rate'] = model['failures'] / completed if completed else None
        model['attempts'] = sum(r['attempts'] for r in model['routes'])
        model['attempt_failures'] = sum(r['failures'] for r in model['routes'])
        attempts = sum(r['attempts'] - r['cancelled'] for r in model['routes'])
        model['attempt_failure_rate'] = model['attempt_failures'] / attempts if attempts else None
        model['reasons'] = {}
    for row in reasons:
        models[row['model_id']]['reasons'][row['reason']] = row['count']
    return sorted(models.values(), key=lambda m: (-m['failures'], -m['attempt_failures'], m['model_id']))


async def model_health_failures(db, start, end, model_id, offset, limit):
    conditions = [Call.started_at >= start, Call.started_at <= end, Attempt.outcome == 'failed']
    if model_id is not None:
        conditions.append(Call.model_id == model_id)
    source = select(Attempt).join(Call, Call.id == Attempt.call_id).where(*conditions)
    total = await db.scalar(select(func.count()).select_from(source.subquery()))
    rows = (
        (
            await db.execute(
                select(
                    Attempt.id,
                    Attempt.call_id,
                    Attempt.model_id,
                    Attempt.route,
                    Attempt.started_at,
                    Attempt.duration_ms,
                    Attempt.reason,
                    Attempt.http_status,
                    Attempt.fallback,
                    Call.model_id.label('requested_model'),
                    Call.outcome.label('final_outcome'),
                )
                .join(Call, Call.id == Attempt.call_id)
                .where(*conditions)
                .order_by(Attempt.started_at.desc(), Attempt.id)
                .offset(offset)
                .limit(limit)
            )
        )
        .mappings()
        .all()
    )
    return {'items': [dict(row) for row in rows], 'total': total}
