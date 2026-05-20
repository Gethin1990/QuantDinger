"""
健康检查路由
"""
from flask import Blueprint, jsonify
from datetime import datetime, timezone

health_bp = Blueprint('health', __name__)


@health_bp.route('/', methods=['GET'])
def index():
    """
    API homepage - returns basic service info.

    ---
    tags:
      - Health
    responses:
      200:
        description: Success
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/ResponseEnvelope'
    """
    return jsonify({
        'name': 'QuantDinger Python API',
        'version': '2.0.0',
        'status': 'running',
        # SafeJSONProvider serializes datetimes as UTC ISO (with Z).
        'timestamp': datetime.now(timezone.utc)
    })


@health_bp.route('/health', methods=['GET'])
def health_check():
    """
    Health check endpoint.

    ---
    tags:
      - Health
    responses:
      200:
        description: Success
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/ResponseEnvelope'
    """
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now(timezone.utc)
    })


@health_bp.route('/api/health', methods=['GET'])
def api_health_check():
    """
    Health check alias for container probes and reverse proxy health checks.

    ---
    tags:
      - Health
    responses:
      200:
        description: Success
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/ResponseEnvelope'
    """
    return health_check()
