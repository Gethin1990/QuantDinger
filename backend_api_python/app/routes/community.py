"""
Community APIs - 指标社区接口

提供指标市场、购买、评论等功能的 REST API。
"""

from flask import Blueprint, jsonify, request, g

from app.utils.auth import login_required
from app.utils.logger import get_logger
from app.services.community_service import get_community_service

logger = get_logger(__name__)

community_bp = Blueprint("community", __name__)


# ==========================================
# 指标市场
# ==========================================

@community_bp.route("/indicators", methods=["GET"])
@login_required
def get_market_indicators():
    """
    Get market indicators list with filtering and sorting.

    ---
    tags:
      - Community
    security:
      - BearerAuth: []
    parameters:
      - name: page
        in: query
        required: false
        schema:
          type: integer
          default: 1
        description: "Page number"
      - name: page_size
        in: query
        required: false
        schema:
          type: integer
          default: 12
        description: "Page size (max 50)"
      - name: keyword
        in: query
        required: false
        schema:
          type: string
        description: "Search keyword"
      - name: pricing_type
        in: query
        required: false
        schema:
          type: string
          enum:
            - free
            - paid
        description: "Filter by pricing type (empty for all)"
      - name: sort_by
        in: query
        required: false
        schema:
          type: string
          enum:
            - score
            - newest
            - hot
            - price_asc
            - price_desc
            - rating
          default: score
        description: "Sort order"
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
        page = int(request.args.get('page', 1))
        page_size = int(request.args.get('page_size', 12))
        keyword = request.args.get('keyword', '').strip()
        pricing_type = request.args.get('pricing_type', '').strip() or None
        sort_by = request.args.get('sort_by', 'score').strip()
        
        # 限制每页数量
        page_size = min(max(page_size, 1), 50)
        
        # 多语言：前端在 request.js 自动带 X-App-Lang + Accept-Language。
        # 优先用 X-App-Lang（前端 UI 语言），fallback 到 Accept-Language 第一个值。
        accept_lang = (
            request.headers.get('X-App-Lang')
            or request.headers.get('Accept-Language', '').split(',')[0].strip()
            or 'en-US'
        )

        service = get_community_service()
        result = service.get_market_indicators(
            page=page,
            page_size=page_size,
            keyword=keyword if keyword else None,
            pricing_type=pricing_type,
            sort_by=sort_by,
            user_id=g.user_id,
            accept_language=accept_lang,
        )
        
        return jsonify({'code': 1, 'msg': 'success', 'data': result})
        
    except Exception as e:
        logger.error(f"get_market_indicators failed: {e}")
        return jsonify({'code': 0, 'msg': str(e), 'data': None}), 500


@community_bp.route("/indicators/<int:indicator_id>", methods=["GET"])
@login_required
def get_indicator_detail(indicator_id: int):
    """
    Get indicator detail by ID.

    ---
    tags:
      - Community
    security:
      - BearerAuth: []
    parameters:
      - name: indicator_id
        in: path
        required: true
        schema:
          type: integer
        description: "Indicator ID"
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
        description: Indicator not found
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/ResponseEnvelope'
      500:
        $ref: '#/components/responses/ServerError'
    """
    try:
        accept_lang = (
            request.headers.get('X-App-Lang')
            or request.headers.get('Accept-Language', '').split(',')[0].strip()
            or 'en-US'
        )
        service = get_community_service()
        result = service.get_indicator_detail(
            indicator_id,
            user_id=g.user_id,
            accept_language=accept_lang,
        )
        
        if not result:
            return jsonify({'code': 0, 'msg': 'indicator_not_found', 'data': None}), 404
        
        return jsonify({'code': 1, 'msg': 'success', 'data': result})
        
    except Exception as e:
        logger.error(f"get_indicator_detail failed: {e}")
        return jsonify({'code': 0, 'msg': str(e), 'data': None}), 500


# ==========================================
# 购买功能
# ==========================================

@community_bp.route("/indicators/<int:indicator_id>/purchase", methods=["POST"])
@login_required
def purchase_indicator(indicator_id: int):
    """
    Purchase an indicator from the marketplace.

    ---
    tags:
      - Community
    security:
      - BearerAuth: []
    parameters:
      - name: indicator_id
        in: path
        required: true
        schema:
          type: integer
        description: "Indicator ID to purchase"
    responses:
      200:
        description: Purchase successful
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/ResponseEnvelope'
      400:
        description: Insufficient credits or already purchased
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
        service = get_community_service()
        success, message, data = service.purchase_indicator(
            buyer_id=g.user_id,
            indicator_id=indicator_id
        )
        
        if success:
            return jsonify({'code': 1, 'msg': message, 'data': data})
        else:
            return jsonify({'code': 0, 'msg': message, 'data': data}), 400
            
    except Exception as e:
        logger.error(f"purchase_indicator failed: {e}")
        return jsonify({'code': 0, 'msg': str(e), 'data': None}), 500


@community_bp.route("/indicators/<int:indicator_id>/sync", methods=["POST"])
@login_required
def sync_purchased_indicator(indicator_id: int):
    """
    Sync the latest code of a purchased indicator.

    ---
    tags:
      - Community
    security:
      - BearerAuth: []
    parameters:
      - name: indicator_id
        in: path
        required: true
        schema:
          type: integer
        description: "Indicator ID to sync"
    responses:
      200:
        description: Sync successful
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/ResponseEnvelope'
      401:
        $ref: '#/components/responses/Unauthorized'
      403:
        description: Not purchased
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/ResponseEnvelope'
      404:
        description: Indicator not found, unpublished, or local copy missing
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/ResponseEnvelope'
      500:
        $ref: '#/components/responses/ServerError'
    """
    try:
        service = get_community_service()
        success, message, data = service.sync_purchased_indicator(
            buyer_id=g.user_id,
            indicator_id=indicator_id
        )

        if success:
            return jsonify({'code': 1, 'msg': message, 'data': data})
        else:
            # 不同失败场景给到可区分的 http 状态，便于前端处理
            status = 400
            if message in ('indicator_not_found', 'indicator_unpublished', 'local_copy_not_found'):
                status = 404
            elif message == 'not_purchased':
                status = 403
            return jsonify({'code': 0, 'msg': message, 'data': data}), status

    except Exception as e:
        logger.error(f"sync_purchased_indicator failed: {e}")
        return jsonify({'code': 0, 'msg': str(e), 'data': None}), 500


@community_bp.route("/my-purchases", methods=["GET"])
@login_required
def get_my_purchases():
    """
    Get the current user's purchased indicators list.

    ---
    tags:
      - Community
    security:
      - BearerAuth: []
    parameters:
      - name: page
        in: query
        required: false
        schema:
          type: integer
          default: 1
        description: "Page number"
      - name: page_size
        in: query
        required: false
        schema:
          type: integer
          default: 20
        description: "Page size (max 50)"
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
        page = int(request.args.get('page', 1))
        page_size = int(request.args.get('page_size', 20))
        page_size = min(max(page_size, 1), 50)
        
        service = get_community_service()
        result = service.get_my_purchases(
            user_id=g.user_id,
            page=page,
            page_size=page_size
        )
        
        return jsonify({'code': 1, 'msg': 'success', 'data': result})
        
    except Exception as e:
        logger.error(f"get_my_purchases failed: {e}")
        return jsonify({'code': 0, 'msg': str(e), 'data': None}), 500


# ==========================================
# 作者后台 (Author Dashboard)
#
# 普通用户上传指标到市场后，需要一个轻量的「我的发布 / 销量 / 收入 / 评分」
# 概览页。这三个端点都按 g.user_id 过滤，不会泄露其它作者数据。
# 实现细节见 services/community_service.py 的同名方法。
# ==========================================

@community_bp.route("/author/summary", methods=["GET"])
@login_required
def get_author_summary():
    """
    Get author dashboard summary (publish count, sales, revenue, ratings).

    ---
    tags:
      - Community
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
        service = get_community_service()
        result = service.get_author_summary(user_id=g.user_id)
        return jsonify({'code': 1, 'msg': 'success', 'data': result})
    except Exception as e:
        logger.error(f"get_author_summary failed: {e}")
        return jsonify({'code': 0, 'msg': str(e), 'data': None}), 500


@community_bp.route("/author/published", methods=["GET"])
@login_required
def get_author_published():
    """
    Get author's published indicators with sales/revenue/rating stats.

    ---
    tags:
      - Community
    security:
      - BearerAuth: []
    parameters:
      - name: page
        in: query
        required: false
        schema:
          type: integer
          default: 1
        description: "Page number"
      - name: page_size
        in: query
        required: false
        schema:
          type: integer
          default: 20
        description: "Page size (max 50)"
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
        page = int(request.args.get('page', 1))
        page_size = int(request.args.get('page_size', 20))
        page_size = min(max(page_size, 1), 50)

        service = get_community_service()
        result = service.get_author_published(
            user_id=g.user_id,
            page=page,
            page_size=page_size,
        )
        return jsonify({'code': 1, 'msg': 'success', 'data': result})
    except Exception as e:
        logger.error(f"get_author_published failed: {e}")
        return jsonify({'code': 0, 'msg': str(e), 'data': None}), 500


@community_bp.route("/author/sales", methods=["GET"])
@login_required
def get_author_sales():
    """
    Get author's sales records with optional indicator filter.

    ---
    tags:
      - Community
    security:
      - BearerAuth: []
    parameters:
      - name: page
        in: query
        required: false
        schema:
          type: integer
          default: 1
        description: "Page number"
      - name: page_size
        in: query
        required: false
        schema:
          type: integer
          default: 20
        description: "Page size (max 100)"
      - name: indicator_id
        in: query
        required: false
        schema:
          type: integer
        description: "Filter by indicator ID"
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
        page = int(request.args.get('page', 1))
        page_size = int(request.args.get('page_size', 20))
        page_size = min(max(page_size, 1), 100)
        indicator_id_raw = request.args.get('indicator_id', '').strip()
        indicator_id = int(indicator_id_raw) if indicator_id_raw else None

        service = get_community_service()
        result = service.get_author_sales(
            user_id=g.user_id,
            page=page,
            page_size=page_size,
            indicator_id=indicator_id,
        )
        return jsonify({'code': 1, 'msg': 'success', 'data': result})
    except Exception as e:
        logger.error(f"get_author_sales failed: {e}")
        return jsonify({'code': 0, 'msg': str(e), 'data': None}), 500


# ==========================================
# 评论功能
# ==========================================

@community_bp.route("/indicators/<int:indicator_id>/comments", methods=["GET"])
@login_required
def get_comments(indicator_id: int):
    """
    Get comments for an indicator.

    ---
    tags:
      - Community
    security:
      - BearerAuth: []
    parameters:
      - name: indicator_id
        in: path
        required: true
        schema:
          type: integer
        description: "Indicator ID"
      - name: page
        in: query
        required: false
        schema:
          type: integer
          default: 1
        description: "Page number"
      - name: page_size
        in: query
        required: false
        schema:
          type: integer
          default: 20
        description: "Page size (max 50)"
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
        page = int(request.args.get('page', 1))
        page_size = int(request.args.get('page_size', 20))
        page_size = min(max(page_size, 1), 50)
        
        service = get_community_service()
        result = service.get_comments(
            indicator_id=indicator_id,
            page=page,
            page_size=page_size
        )
        
        return jsonify({'code': 1, 'msg': 'success', 'data': result})
        
    except Exception as e:
        logger.error(f"get_comments failed: {e}")
        return jsonify({'code': 0, 'msg': str(e), 'data': None}), 500


@community_bp.route("/indicators/<int:indicator_id>/comments", methods=["POST"])
@login_required
def add_comment(indicator_id: int):
    """
    Add a comment to an indicator (requires purchase).

    ---
    tags:
      - Community
    security:
      - BearerAuth: []
    parameters:
      - name: indicator_id
        in: path
        required: true
        schema:
          type: integer
        description: "Indicator ID"
    requestBody:
      required: true
      content:
        application/json:
          schema:
            type: object
            properties:
              rating:
                type: integer
                minimum: 1
                maximum: 5
                default: 5
                description: "Star rating (1-5)"
              content:
                type: string
                maxLength: 500
                description: "Comment content (optional, max 500 chars)"
    responses:
      200:
        description: Comment added successfully
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/ResponseEnvelope'
      400:
        description: Already commented or not purchased
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
        data = request.get_json() or {}
        rating = int(data.get('rating', 5))
        content = (data.get('content') or '').strip()
        
        service = get_community_service()
        success, message, result = service.add_comment(
            user_id=g.user_id,
            indicator_id=indicator_id,
            rating=rating,
            content=content
        )
        
        if success:
            return jsonify({'code': 1, 'msg': message, 'data': result})
        else:
            return jsonify({'code': 0, 'msg': message, 'data': result}), 400
            
    except Exception as e:
        logger.error(f"add_comment failed: {e}")
        return jsonify({'code': 0, 'msg': str(e), 'data': None}), 500


@community_bp.route("/indicators/<int:indicator_id>/comments/<int:comment_id>", methods=["PUT"])
@login_required
def update_comment(indicator_id: int, comment_id: int):
    """
    Update an existing comment (own comments only).

    ---
    tags:
      - Community
    security:
      - BearerAuth: []
    parameters:
      - name: indicator_id
        in: path
        required: true
        schema:
          type: integer
        description: "Indicator ID"
      - name: comment_id
        in: path
        required: true
        schema:
          type: integer
        description: "Comment ID"
    requestBody:
      required: true
      content:
        application/json:
          schema:
            type: object
            properties:
              rating:
                type: integer
                minimum: 1
                maximum: 5
                default: 5
                description: "Star rating (1-5)"
              content:
                type: string
                maxLength: 500
                description: "Comment content (max 500 chars)"
    responses:
      200:
        description: Comment updated successfully
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/ResponseEnvelope'
      400:
        description: Update failed
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
        data = request.get_json() or {}
        rating = int(data.get('rating', 5))
        content = (data.get('content') or '').strip()
        
        service = get_community_service()
        success, message, result = service.update_comment(
            user_id=g.user_id,
            comment_id=comment_id,
            indicator_id=indicator_id,
            rating=rating,
            content=content
        )
        
        if success:
            return jsonify({'code': 1, 'msg': message, 'data': result})
        else:
            return jsonify({'code': 0, 'msg': message, 'data': result}), 400
            
    except Exception as e:
        logger.error(f"update_comment failed: {e}")
        return jsonify({'code': 0, 'msg': str(e), 'data': None}), 500


@community_bp.route("/indicators/<int:indicator_id>/my-comment", methods=["GET"])
@login_required
def get_my_comment(indicator_id: int):
    """
    Get the current user's comment on an indicator (for editing).

    ---
    tags:
      - Community
    security:
      - BearerAuth: []
    parameters:
      - name: indicator_id
        in: path
        required: true
        schema:
          type: integer
        description: "Indicator ID"
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
        service = get_community_service()
        result = service.get_user_comment(
            user_id=g.user_id,
            indicator_id=indicator_id
        )
        
        return jsonify({'code': 1, 'msg': 'success', 'data': result})
        
    except Exception as e:
        logger.error(f"get_my_comment failed: {e}")
        return jsonify({'code': 0, 'msg': str(e), 'data': None}), 500


# ==========================================
# 实盘表现
# ==========================================

@community_bp.route("/indicators/<int:indicator_id>/performance", methods=["GET"])
@login_required
def get_indicator_performance(indicator_id: int):
    """
    Get live performance statistics for an indicator.

    ---
    tags:
      - Community
    security:
      - BearerAuth: []
    parameters:
      - name: indicator_id
        in: path
        required: true
        schema:
          type: integer
        description: "Indicator ID"
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
        service = get_community_service()
        result = service.get_indicator_performance(indicator_id)
        
        return jsonify({'code': 1, 'msg': 'success', 'data': result})
        
    except Exception as e:
        logger.error(f"get_indicator_performance failed: {e}")
        return jsonify({'code': 0, 'msg': str(e), 'data': None}), 500


# ==========================================
# 管理员审核功能
# ==========================================

def _is_admin():
    """检查当前用户是否是管理员"""
    role = getattr(g, 'user_role', None)
    return role == 'admin'


@community_bp.route("/admin/pending-indicators", methods=["GET"])
@login_required
def get_pending_indicators():
    """
    Get indicators pending review (admin only).

    ---
    tags:
      - Community
    security:
      - BearerAuth: []
    parameters:
      - name: page
        in: query
        required: false
        schema:
          type: integer
          default: 1
        description: "Page number"
      - name: page_size
        in: query
        required: false
        schema:
          type: integer
          default: 20
        description: "Page size (max 100)"
      - name: review_status
        in: query
        required: false
        schema:
          type: string
          enum:
            - pending
            - approved
            - rejected
            - all
          default: pending
        description: "Filter by review status"
    responses:
      200:
        description: Success
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/ResponseEnvelope'
      401:
        $ref: '#/components/responses/Unauthorized'
      403:
        description: Admin role required
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/ResponseEnvelope'
      500:
        $ref: '#/components/responses/ServerError'
    """
    try:
        if not _is_admin():
            return jsonify({'code': 0, 'msg': 'admin_required', 'data': None}), 403
        
        page = int(request.args.get('page', 1))
        page_size = int(request.args.get('page_size', 20))
        review_status = request.args.get('review_status', 'pending').strip() or 'pending'
        page_size = min(max(page_size, 1), 100)
        
        service = get_community_service()
        result = service.get_pending_indicators(
            page=page,
            page_size=page_size,
            review_status=review_status
        )
        
        return jsonify({'code': 1, 'msg': 'success', 'data': result})
        
    except Exception as e:
        logger.error(f"get_pending_indicators failed: {e}")
        return jsonify({'code': 0, 'msg': str(e), 'data': None}), 500


@community_bp.route("/admin/review-stats", methods=["GET"])
@login_required
def get_review_stats():
    """
    Get review statistics (admin only).

    ---
    tags:
      - Community
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
      403:
        description: Admin role required
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/ResponseEnvelope'
      500:
        $ref: '#/components/responses/ServerError'
    """
    try:
        if not _is_admin():
            return jsonify({'code': 0, 'msg': 'admin_required', 'data': None}), 403
        
        service = get_community_service()
        result = service.get_review_stats()
        
        return jsonify({'code': 1, 'msg': 'success', 'data': result})
        
    except Exception as e:
        logger.error(f"get_review_stats failed: {e}")
        return jsonify({'code': 0, 'msg': str(e), 'data': None}), 500


@community_bp.route("/admin/indicators/<int:indicator_id>/review", methods=["POST"])
@login_required
def review_indicator(indicator_id: int):
    """
    Review an indicator (admin only).

    ---
    tags:
      - Community
    security:
      - BearerAuth: []
    parameters:
      - name: indicator_id
        in: path
        required: true
        schema:
          type: integer
        description: "Indicator ID to review"
    requestBody:
      required: true
      content:
        application/json:
          schema:
            type: object
            required:
              - action
            properties:
              action:
                type: string
                enum:
                  - approve
                  - reject
                description: "Review action"
              note:
                type: string
                description: "Review note (optional)"
    responses:
      200:
        description: Review completed
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/ResponseEnvelope'
      400:
        description: Invalid action
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/ResponseEnvelope'
      401:
        $ref: '#/components/responses/Unauthorized'
      403:
        description: Admin role required
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/ResponseEnvelope'
      500:
        $ref: '#/components/responses/ServerError'
    """
    try:
        if not _is_admin():
            return jsonify({'code': 0, 'msg': 'admin_required', 'data': None}), 403
        
        data = request.get_json() or {}
        action = data.get('action', '').strip()
        note = data.get('note', '').strip()
        
        if action not in ('approve', 'reject'):
            return jsonify({'code': 0, 'msg': 'invalid_action', 'data': None}), 400
        
        service = get_community_service()
        success, message = service.review_indicator(
            admin_id=g.user_id,
            indicator_id=indicator_id,
            action=action,
            note=note
        )
        
        if success:
            return jsonify({'code': 1, 'msg': message, 'data': None})
        else:
            return jsonify({'code': 0, 'msg': message, 'data': None}), 400
            
    except Exception as e:
        logger.error(f"review_indicator failed: {e}")
        return jsonify({'code': 0, 'msg': str(e), 'data': None}), 500


@community_bp.route("/admin/indicators/<int:indicator_id>/unpublish", methods=["POST"])
@login_required
def unpublish_indicator(indicator_id: int):
    """
    Unpublish an indicator (admin only).

    ---
    tags:
      - Community
    security:
      - BearerAuth: []
    parameters:
      - name: indicator_id
        in: path
        required: true
        schema:
          type: integer
        description: "Indicator ID to unpublish"
    requestBody:
      required: false
      content:
        application/json:
          schema:
            type: object
            properties:
              note:
                type: string
                description: "Reason for unpublishing (optional)"
    responses:
      200:
        description: Unpublished successfully
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/ResponseEnvelope'
      400:
        description: Unpublish failed
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/ResponseEnvelope'
      401:
        $ref: '#/components/responses/Unauthorized'
      403:
        description: Admin role required
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/ResponseEnvelope'
      500:
        $ref: '#/components/responses/ServerError'
    """
    try:
        if not _is_admin():
            return jsonify({'code': 0, 'msg': 'admin_required', 'data': None}), 403
        
        data = request.get_json() or {}
        note = data.get('note', '').strip()
        
        service = get_community_service()
        success, message = service.unpublish_indicator(
            admin_id=g.user_id,
            indicator_id=indicator_id,
            note=note
        )
        
        if success:
            return jsonify({'code': 1, 'msg': message, 'data': None})
        else:
            return jsonify({'code': 0, 'msg': message, 'data': None}), 400
            
    except Exception as e:
        logger.error(f"unpublish_indicator failed: {e}")
        return jsonify({'code': 0, 'msg': str(e), 'data': None}), 500


@community_bp.route("/admin/indicators/<int:indicator_id>", methods=["DELETE"])
@login_required
def admin_delete_indicator(indicator_id: int):
    """
    Delete an indicator (admin only).

    ---
    tags:
      - Community
    security:
      - BearerAuth: []
    parameters:
      - name: indicator_id
        in: path
        required: true
        schema:
          type: integer
        description: "Indicator ID to delete"
    responses:
      200:
        description: Deleted successfully
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/ResponseEnvelope'
      400:
        description: Delete failed
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/ResponseEnvelope'
      401:
        $ref: '#/components/responses/Unauthorized'
      403:
        description: Admin role required
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/ResponseEnvelope'
      500:
        $ref: '#/components/responses/ServerError'
    """
    try:
        if not _is_admin():
            return jsonify({'code': 0, 'msg': 'admin_required', 'data': None}), 403
        
        service = get_community_service()
        success, message = service.admin_delete_indicator(
            admin_id=g.user_id,
            indicator_id=indicator_id
        )
        
        if success:
            return jsonify({'code': 1, 'msg': message, 'data': None})
        else:
            return jsonify({'code': 0, 'msg': message, 'data': None}), 400
            
    except Exception as e:
        logger.error(f"admin_delete_indicator failed: {e}")
        return jsonify({'code': 0, 'msg': str(e), 'data': None}), 500
