"""
Billing APIs - 会员套餐与 USDT 支付

- 套餐金额/积分从系统设置（.env）读取
- 会员开通仅通过 USDT 链上支付确认后触发（见 usdt_payment_service）
"""

from flask import Blueprint, jsonify, request, g

from app.utils.auth import login_required
from app.utils.logger import get_logger
from app.services.billing_service import get_billing_service
from app.services.usdt_payment_service import get_usdt_payment_service

logger = get_logger(__name__)

billing_bp = Blueprint("billing", __name__)


@billing_bp.route("/plans", methods=["GET"])
@login_required
def get_membership_plans():
    """
    Get membership plan configuration and current user's billing snapshot.

    ---
    tags:
      - Billing
    security:
      - BearerAuth: []
    responses:
      200:
        description: Success
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/ResponseEnvelope'
      401:
        $ref: '#/components/responses/Unauthorized'
      500:
        $ref: '#/components/responses/ServerError'
    """
    try:
        user_id = getattr(g, "user_id", None)
        svc = get_billing_service()
        plans = svc.get_membership_plans()
        billing_info = svc.get_user_billing_info(user_id) if user_id else {}
        return jsonify({"code": 1, "msg": "success", "data": {"plans": plans, "billing": billing_info}})
    except Exception as e:
        logger.error(f"get_membership_plans failed: {e}", exc_info=True)
        return jsonify({"code": 0, "msg": str(e), "data": None}), 500


@billing_bp.route("/purchase", methods=["POST"])
@login_required
def purchase_membership():
    """
    Legacy mock checkout (disabled). Use POST /billing/usdt/create and pay on-chain.

    ---
    tags:
      - Billing
    security:
      - BearerAuth: []
    responses:
      403:
        description: Mock purchase disabled
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/ResponseEnvelope'
      401:
        $ref: '#/components/responses/Unauthorized'
    """
    return jsonify(
        {
            "code": 0,
            "msg": "mock_purchase_disabled",
            "data": {"hint": "Use USDT: POST /api/billing/usdt/create then pay to the assigned address."},
        }
    ), 403


# =========================
# USDT Pay (方案B)
# =========================


@billing_bp.route("/usdt/chains", methods=["GET"])
@login_required
def usdt_list_chains():
    """
    List USDT chains that are enabled and have a receiving address configured.

    ---
    tags:
      - Billing
    security:
      - BearerAuth: []
    responses:
      200:
        description: Success
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/ResponseEnvelope'
      401:
        $ref: '#/components/responses/Unauthorized'
      500:
        $ref: '#/components/responses/ServerError'
    """
    try:
        chains = get_usdt_payment_service().list_chains()
        return jsonify({"code": 1, "msg": "success", "data": {"chains": chains}})
    except Exception as e:
        logger.error(f"usdt_list_chains failed: {e}", exc_info=True)
        return jsonify({"code": 0, "msg": str(e), "data": None}), 500


@billing_bp.route("/usdt/create", methods=["POST"])
@login_required
def usdt_create_order():
    """
    Create a USDT membership order.

    ---
    tags:
      - Billing
    security:
      - BearerAuth: []
    requestBody:
      required: true
      content:
        application/json:
          schema:
            type: object
            required:
              - plan
            properties:
              plan:
                type: string
                enum:
                  - monthly
                  - yearly
                  - lifetime
                description: Membership plan to purchase
              chain:
                type: string
                enum:
                  - TRC20
                  - BEP20
                  - ERC20
                  - SOL
                description: USDT chain (defaults to first enabled chain)
    responses:
      200:
        description: Order created successfully
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/ResponseEnvelope'
      400:
        description: Missing plan or invalid input
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/ResponseEnvelope'
      401:
        $ref: '#/components/responses/Unauthorized'
      500:
        $ref: '#/components/responses/ServerError'
    """
    try:
        user_id = getattr(g, "user_id", None)
        data = request.get_json() or {}
        plan = (data.get("plan") or "").strip().lower()
        chain = (data.get("chain") or "").strip().upper() or None
        if not plan:
            return jsonify({"code": 0, "msg": "missing_plan", "data": None}), 400

        ok, msg, out = get_usdt_payment_service().create_order(user_id, plan, chain=chain)
        if ok:
            return jsonify({"code": 1, "msg": "success", "data": out})
        return jsonify({"code": 0, "msg": msg, "data": out}), 400
    except Exception as e:
        logger.error(f"usdt_create_order failed: {e}", exc_info=True)
        return jsonify({"code": 0, "msg": str(e), "data": None}), 500


@billing_bp.route("/usdt/order/<int:order_id>", methods=["GET"])
@login_required
def usdt_get_order(order_id: int):
    """
    Get my USDT order; refresh chain status by default.

    ---
    tags:
      - Billing
    security:
      - BearerAuth: []
    parameters:
      - name: order_id
        in: path
        required: true
        schema:
          type: integer
        description: USDT order ID
      - name: refresh
        in: query
        required: false
        schema:
          type: string
          default: "1"
        description: Whether to refresh on-chain status (1/true/yes)
    responses:
      200:
        description: Success
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/ResponseEnvelope'
      401:
        $ref: '#/components/responses/Unauthorized'
      404:
        description: Order not found
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/ResponseEnvelope'
      500:
        $ref: '#/components/responses/ServerError'
    """
    try:
        user_id = getattr(g, "user_id", None)
        refresh = str(request.args.get("refresh", "1")).lower() in ("1", "true", "yes")
        ok, msg, out = get_usdt_payment_service().get_order(user_id, order_id, refresh=refresh)
        if ok:
            return jsonify({"code": 1, "msg": "success", "data": out})
        return jsonify({"code": 0, "msg": msg, "data": out}), 404
    except Exception as e:
        logger.error(f"usdt_get_order failed: {e}", exc_info=True)
        return jsonify({"code": 0, "msg": str(e), "data": None}), 500

