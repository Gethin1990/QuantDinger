"""
AI chat API routes (optional).
Currently kept as a minimal compatibility layer for legacy frontend calls.
"""

from flask import Blueprint, request, jsonify

from app.utils.logger import get_logger

logger = get_logger(__name__)

ai_chat_bp = Blueprint('ai_chat', __name__)


@ai_chat_bp.route('/chat/message', methods=['POST'])
def chat_message():
    """
    Send a chat message (placeholder).

    ---
    tags:
      - AI Chat
    requestBody:
      content:
        application/json:
          schema:
            type: object
            properties:
              message:
                type: string
                description: Chat message text
    responses:
      200:
        description: Success
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/ResponseEnvelope'
      400:
        description: Missing message
      500:
        $ref: '#/components/responses/ServerError'
    """
    data = request.get_json() or {}
    msg = (data.get('message') or '').strip()
    if not msg:
        return jsonify({'code': 0, 'msg': 'Missing message', 'data': None}), 400
    return jsonify({
        'code': 1,
        'msg': 'success',
        'data': {
            'reply': 'Chat API is not implemented yet in local-only mode.',
            'echo': msg
        }
    })


@ai_chat_bp.route('/chat/history', methods=['GET'])
def get_chat_history():
    """
    Get chat history (compatibility stub).

    ---
    tags:
      - AI Chat
    responses:
      200:
        description: Success
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/ResponseEnvelope'
      500:
        $ref: '#/components/responses/ServerError'
    """
    return jsonify({'code': 1, 'msg': 'success', 'data': []})


@ai_chat_bp.route('/chat/history/save', methods=['POST'])
def save_chat_history():
    """
    Save chat history (compatibility stub).

    ---
    tags:
      - AI Chat
    responses:
      200:
        description: Success
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/ResponseEnvelope'
      500:
        $ref: '#/components/responses/ServerError'
    """
    return jsonify({'code': 1, 'msg': 'success', 'data': None})


