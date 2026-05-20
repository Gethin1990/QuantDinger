"""Strategies CRUD (read = R, create/update = W).

Reuses StrategyService so behavior matches the human UI exactly. We only
expose a curated subset of fields to keep the agent contract stable.
"""
from __future__ import annotations

from typing import Any

from app.services.strategy import StrategyService
from app.utils.agent_auth import (
    SCOPE_R, SCOPE_W, agent_required, current_user_id,
)
from app.utils.logger import get_logger
from flask import request

from . import agent_v1_bp
from ._helpers import clip_int, envelope, error, get_json_or_400

logger = get_logger(__name__)
_strategy_service = StrategyService()


_PUBLIC_FIELDS = (
    "id", "strategy_name", "strategy_type", "market_category",
    "symbol", "timeframe", "status", "initial_capital", "leverage",
    "market_type", "strategy_mode", "execution_mode",
    "created_at", "updated_at",
)


def _project(row: dict | None) -> dict | None:
    if not row:
        return None
    return {k: row.get(k) for k in _PUBLIC_FIELDS if k in row}


@agent_v1_bp.route("/strategies", methods=["GET"])
@agent_required(SCOPE_R)
def list_strategies():
    """List the calling tenant's strategies (compact projection).

    Requires agent token with R scope.

    ---
    tags:
      - Agent V1
    parameters:
      - name: limit
        in: query
        required: false
        schema:
          type: integer
          minimum: 1
          maximum: 200
          default: 50
        description: Maximum number of strategies to return
    responses:
      200:
        description: List of strategies
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/AgentResponseEnvelope'
      401:
        description: Agent token required
      500:
        $ref: '#/components/responses/ServerError'
    """
    try:
        rows = _strategy_service.list_strategies(user_id=current_user_id()) or []
    except Exception as exc:
        logger.error(f"agent_v1/strategies list failed: {exc}", exc_info=True)
        return error(500, "list_strategies failed", details=str(exc), http=500)

    limit = clip_int(request.args.get("limit"), default=50, lo=1, hi=200)
    return envelope([_project(r) for r in rows[:limit]])


@agent_v1_bp.route("/strategies/<int:strategy_id>", methods=["GET"])
@agent_required(SCOPE_R)
def get_strategy(strategy_id: int):
    """Tenant-scoped strategy lookup.

    Requires agent token with R scope.

    ---
    tags:
      - Agent V1
    parameters:
      - name: strategy_id
        in: path
        required: true
        schema:
          type: integer
        description: Strategy ID
    responses:
      200:
        description: Strategy details
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/AgentResponseEnvelope'
      401:
        description: Agent token required
      404:
        description: Strategy not found
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/AgentErrorResponse'
      500:
        $ref: '#/components/responses/ServerError'
    """
    try:
        row = _strategy_service.get_strategy(strategy_id, user_id=current_user_id())
    except Exception as exc:
        logger.error(f"agent_v1/strategies get failed: {exc}", exc_info=True)
        return error(500, "get_strategy failed", details=str(exc), http=500)
    if not row:
        return error(404, "Strategy not found", http=404)
    return envelope(row)


@agent_v1_bp.route("/strategies", methods=["POST"])
@agent_required(SCOPE_W)
def create_strategy():
    """Create a strategy on behalf of the calling tenant.

    Request body mirrors `StrategyService.create_strategy` payload, minus
    `user_id` (always overridden to the token's tenant for safety).

    Requires agent token with W scope.

    ---
    tags:
      - Agent V1
    requestBody:
      required: true
      content:
        application/json:
          schema:
            type: object
            required:
              - strategy_name
            properties:
              strategy_name:
                type: string
                description: Name of the strategy
              strategy_type:
                type: string
              market_category:
                type: string
              symbol:
                type: string
              timeframe:
                type: string
              initial_capital:
                type: number
              leverage:
                type: integer
              market_type:
                type: string
              strategy_mode:
                type: string
              execution_mode:
                type: string
    responses:
      200:
        description: Strategy created
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/AgentResponseEnvelope'
      400:
        description: Invalid input
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/AgentErrorResponse'
      401:
        description: Agent token required
      500:
        $ref: '#/components/responses/ServerError'
    """
    body, err = get_json_or_400()
    if err:
        return err

    name = (body.get("strategy_name") or "").strip()
    if not name:
        return error(400, "strategy_name is required")

    payload: dict[str, Any] = dict(body)
    payload["user_id"] = current_user_id()
    payload.setdefault("status", "stopped")  # never auto-start from agent path

    try:
        new_id = _strategy_service.create_strategy(payload)
    except ValueError as ve:
        return error(400, str(ve))
    except Exception as exc:
        logger.error(f"agent_v1/strategies create failed: {exc}", exc_info=True)
        return error(500, "create_strategy failed", details=str(exc), http=500)

    row = _strategy_service.get_strategy(int(new_id), user_id=current_user_id())
    return envelope({"strategy_id": int(new_id), "strategy": _project(row)}, message="created")


@agent_v1_bp.route("/strategies/<int:strategy_id>", methods=["PATCH"])
@agent_required(SCOPE_W)
def update_strategy(strategy_id: int):
    """Tenant-scoped patch.  Status changes that flip a strategy to `running`
    are rejected unless the token also has T scope; agents must explicitly
    request live execution scope to start strategies.

    Requires agent token with W scope.

    ---
    tags:
      - Agent V1
    parameters:
      - name: strategy_id
        in: path
        required: true
        schema:
          type: integer
        description: Strategy ID to update
    requestBody:
      required: true
      content:
        application/json:
          schema:
            type: object
            properties:
              strategy_name:
                type: string
              status:
                type: string
                enum: [stopped, running, paused]
                description: Setting to 'running' requires T scope on the token
              initial_capital:
                type: number
              leverage:
                type: integer
    responses:
      200:
        description: Strategy updated
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/AgentResponseEnvelope'
      400:
        description: Invalid input
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/AgentErrorResponse'
      401:
        description: Agent token required
      403:
        description: T scope required to activate strategy
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/AgentErrorResponse'
      404:
        description: Strategy not found or no fields updated
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/AgentErrorResponse'
      500:
        $ref: '#/components/responses/ServerError'
    """
    body, err = get_json_or_400()
    if err:
        return err

    new_status = (body.get("status") or "").strip().lower()
    if new_status == "running":
        from app.utils.agent_auth import current_token, parse_scopes
        if "T" not in parse_scopes(current_token().get("scopes")):
            return error(
                403,
                "Activating a strategy requires T (trading) scope on this token",
                http=403,
            )

    try:
        ok = _strategy_service.update_strategy(strategy_id, body, user_id=current_user_id())
    except Exception as exc:
        logger.error(f"agent_v1/strategies update failed: {exc}", exc_info=True)
        return error(500, "update_strategy failed", details=str(exc), http=500)

    if not ok:
        return error(404, "Strategy not found or no fields updated", http=404)

    row = _strategy_service.get_strategy(strategy_id, user_id=current_user_id())
    return envelope(_project(row), message="updated")
