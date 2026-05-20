"""Health and self-introspection endpoints (class R, but token-free for /health)."""
from __future__ import annotations

from datetime import datetime, timezone

from flask import jsonify

from app.utils.agent_auth import (
    SCOPE_R, agent_required, current_token, current_user_id,
)

from . import agent_v1_bp
from ._helpers import envelope


@agent_v1_bp.route("/health", methods=["GET"])
def health():
    """Public liveness probe. Does NOT require a token.

    Useful for health checks from monitoring tools and from agent SDKs that
    want to confirm the gateway is reachable before issuing real calls.

    ---
    tags:
      - Agent V1
    responses:
      200:
        description: Service is healthy
        content:
          application/json:
            schema:
              type: object
              properties:
                service:
                  type: string
                  example: quantdinger-agent-gateway
                version:
                  type: string
                  example: v1
                status:
                  type: string
                  example: ok
                timestamp:
                  type: string
                  format: date-time
    """
    return jsonify({
        "service": "quantdinger-agent-gateway",
        "version": "v1",
        "status": "ok",
        # SafeJSONProvider serializes datetimes as UTC ISO (with Z).
        "timestamp": datetime.now(timezone.utc),
    }), 200


@agent_v1_bp.route("/whoami", methods=["GET"])
@agent_required(SCOPE_R)
def whoami():
    """Return the calling token's identity and granted capabilities.

    Lets agents self-discover scopes / market allowlists without guessing.
    Secrets (token hash, etc.) are never returned.

    Requires agent token with R scope.

    ---
    tags:
      - Agent V1
    responses:
      200:
        description: Token identity and capabilities
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/AgentResponseEnvelope'
      401:
        description: Agent token required
      500:
        $ref: '#/components/responses/ServerError'
    """
    token = current_token()
    return envelope({
        "user_id": current_user_id(),
        "agent_name": token.get("name"),
        "scopes": (token.get("scopes") or "R").split(","),
        "markets": (token.get("markets") or "*").split(","),
        "instruments": (token.get("instruments") or "*").split(","),
        "paper_only": bool(token.get("paper_only", True)),
        "rate_limit_per_min": int(token.get("rate_limit_per_min") or 60),
    })
