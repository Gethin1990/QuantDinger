"""Job polling endpoints — read job status/result for the calling tenant.

Two flavors:
  * `GET /jobs/{id}` — single snapshot (cheap).
  * `GET /jobs/{id}/stream` — Server-Sent Events for "edge of the result"
    consumers (LLMs that want to react to partial results, dashboards, etc.).
"""
from __future__ import annotations

import json
import time

from app.utils.agent_auth import SCOPE_R, agent_required, current_user_id
from app.utils.agent_jobs import get_job, list_jobs, stream_progress
from flask import Response, request

from . import agent_v1_bp
from ._helpers import clip_int, envelope, error


@agent_v1_bp.route("/jobs", methods=["GET"])
@agent_required(SCOPE_R)
def list_user_jobs():
    """List recent jobs for this tenant (newest first).

    Requires agent token with R scope.

    ---
    tags:
      - Agent V1
    parameters:
      - name: kind
        in: query
        required: false
        schema:
          type: string
        description: Filter by job kind (e.g. backtest, experiment_pipeline, structured_tune, ai_optimize)
      - name: limit
        in: query
        required: false
        schema:
          type: integer
          minimum: 1
          maximum: 200
          default: 50
        description: Maximum number of jobs to return
    responses:
      200:
        description: List of jobs
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/AgentResponseEnvelope'
      401:
        description: Agent token required
      500:
        $ref: '#/components/responses/ServerError'
    """
    kind = (request.args.get("kind") or "").strip() or None
    limit = clip_int(request.args.get("limit"), default=50, lo=1, hi=200)
    rows = list_jobs(user_id=current_user_id(), kind=kind, limit=limit)
    return envelope(rows)


@agent_v1_bp.route("/jobs/<job_id>", methods=["GET"])
@agent_required(SCOPE_R)
def get_user_job(job_id: str):
    """Fetch a single job (tenant-scoped).

    Requires agent token with R scope.

    ---
    tags:
      - Agent V1
    parameters:
      - name: job_id
        in: path
        required: true
        schema:
          type: string
        description: Job ID
    responses:
      200:
        description: Job details
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/AgentResponseEnvelope'
      401:
        description: Agent token required
      404:
        description: Job not found
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/AgentErrorResponse'
      500:
        $ref: '#/components/responses/ServerError'
    """
    row = get_job(job_id, user_id=current_user_id())
    if not row:
        return error(404, "Job not found", http=404)
    return envelope(row)


def _sse_frame(event: str, data) -> bytes:
    payload = json.dumps(data, default=str, ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n".encode("utf-8")


@agent_v1_bp.route("/jobs/<job_id>/stream", methods=["GET"])
@agent_required(SCOPE_R)
def stream_user_job(job_id: str):
    """SSE stream for a job's progress.

    Frames:
      ``event: progress``  every partial update emitted by the runner.
      ``event: result``    once when the job ends (`status`, `result`, `error`).
      ``event: ping``      ~every 15s while idle, to keep proxies from
                           dropping the connection.

    Reconnection: clients can pass `?since=<seq>` (or the standard SSE
    ``Last-Event-ID`` header) to resume from a given sequence number.
    Snapshots never wait for a long-poll if the job already finished —
    the final `result` frame is emitted immediately and the stream closes.

    Requires agent token with R scope.

    ---
    tags:
      - Agent V1
    parameters:
      - name: job_id
        in: path
        required: true
        schema:
          type: string
        description: Job ID to stream
      - name: since
        in: query
        required: false
        schema:
          type: integer
        description: Sequence number to resume from (or use Last-Event-ID header)
    responses:
      200:
        description: SSE event stream
        content:
          text/event-stream:
            schema:
              type: string
              description: |
                Server-Sent Events stream with the following event types:
                - `snapshot`: Current job state (sent immediately on connect)
                - `progress`: Partial updates from the runner
                - `result`: Final job result (status, result, error)
                - `ping`: Keepalive every ~15s
      401:
        description: Agent token required
      404:
        description: Job not found
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/AgentErrorResponse'
    """
    user_id = current_user_id()
    row = get_job(job_id, user_id=user_id)
    if not row:
        return error(404, "Job not found", http=404)

    try:
        since_seq = int(request.args.get("since") or request.headers.get("Last-Event-ID") or 0)
    except Exception:
        since_seq = 0

    def _gen():
        # Surface the current snapshot first so the client always has a
        # baseline (status, partial result, etc.) even if no live events arrive.
        yield _sse_frame("snapshot", row)

        # If the job already ended before the client connected, just emit the
        # final result and close — no point holding the connection open.
        if row.get("status") in ("succeeded", "failed", "cancelled"):
            yield _sse_frame("result", {
                "job_id": row["job_id"],
                "status": row["status"],
                "result": row.get("result"),
                "error": row.get("error"),
            })
            return

        last_ping = time.monotonic()
        for rec in stream_progress(job_id, since_seq=since_seq):
            yield _sse_frame("progress", rec)
            now = time.monotonic()
            if now - last_ping > 15.0:
                yield _sse_frame("ping", {"ts": now})
                last_ping = now
            if rec.get("terminal"):
                break

        # Re-fetch the row after termination so result/error are accurate.
        final = get_job(job_id, user_id=user_id) or row
        yield _sse_frame("result", {
            "job_id": final.get("job_id", job_id),
            "status": final.get("status"),
            "result": final.get("result"),
            "error": final.get("error"),
        })

    return Response(
        _gen(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
