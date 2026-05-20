"""
Policy / capability discovery routes.

Read-only endpoints that expose backend policy matrices to the frontend so
the UI does not have to hard-code its own copy of broker x market rules.
The frontend fetches these once at app boot and caches them in
sessionStorage; nothing here is per-user, so caching is safe.
"""
from flask import Blueprint, jsonify

from app.services.broker_market_policy import to_dict as broker_market_policy_dict


policy_bp = Blueprint('policy', __name__)


@policy_bp.route('/broker-market', methods=['GET'])
def get_broker_market_policy():
    """
    Return the full broker x market x market_type compatibility matrix.

    ---
    tags:
      - Policy
    responses:
      200:
        description: Success
        content:
          application/json:
            schema:
              type: object
              properties:
                code:
                  type: integer
                  example: 1
                data:
                  type: object
                  properties:
                    broker_markets:
                      type: object
                      description: Map of broker to supported markets and types
                    long_only_brokers:
                      type: array
                      items:
                        type: string
                      description: Brokers that only support long positions
                    bot_type_markets:
                      type: object
                      description: Map of bot type to supported markets
                    live_market_categories:
                      type: array
                      items:
                        type: string
                      description: All market categories available for live trading
      500:
        $ref: '#/components/responses/ServerError'
    """
    return jsonify({"code": 1, "data": broker_market_policy_dict()})
