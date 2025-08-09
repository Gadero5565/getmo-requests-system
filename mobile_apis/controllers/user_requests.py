from odoo import http
from odoo.http import request, Response
import json
import logging
from .common import *

_logger = logging.getLogger(__name__)

sec_token_param = 'mobile_apis.sec_token_for_online_requests'


class RequestAPI(http.Controller):

    @http.route('/api/user/requests', type='json', auth='public', methods=['POST'], )
    def get_user_requests(self, **post):
        try:
            # Extract user ID from payload
            user_id = int(post.get('user_id'))

            # Find employee linked to user
            employee = request.env['hr.employee'].sudo().search([
                ('user_id', '=', user_id)
            ], limit=1)

            if not employee:
                return error_template(error_string="Employee not found for user")

            sec_token = request.env['ir.config_parameter'].sudo().get_param(sec_token_param)

            if post['sec_token'] != sec_token:
                return invalid_sec_token()

            # Fetch requests where user is requester OR assigned technician
            requests = request.env['getmo.request.request'].sudo().search([
                '|',
                ('employee_id', '=', employee.id),
                ('assigned_to_id', '=', employee.id)
            ])

            # Prepare response data
            request_data = []
            for req in requests:
                request_data.append({
                    'id': req.id,
                    'name': req.name,
                    'request_summary': self._html_to_text(req.request_text)[:100],
                    'type': req.type_id.name,
                    'category': req.category_id.name,
                    'stage': req.stage_id.name,
                    'stage_type': req.stage_id.stage_type,
                    'priority': dict(req._fields['priority'].selection).get(req.priority),
                    'date_request': req.date_request.isoformat() if req.date_request else None,
                    'date_assigned': req.date_assigned.isoformat() if req.date_assigned else None,
                    'date_closed': req.date_closed.isoformat() if req.date_closed else None,
                    'is_past_due': req.is_past_due,
                    'assigned_to': req.assigned_to_id.name if req.assigned_to_id else None,
                    'status': 'assigned' if req.assigned_to_id else 'unassigned',
                    'attachments_count': len(req.requests_attachments)
                })

            return success_template(request_data)

        except Exception as e:
            _logger.error("API Error: %s", str(e))
            return error_template(e)

    def _html_to_text(self, html_content):
        """Convert HTML to plain text for mobile display"""
        if not html_content:
            return ""
        return html_content.replace('<p>', ' ').replace('</p>', ' ').strip()