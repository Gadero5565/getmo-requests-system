from odoo import http
from odoo.http import request, Response
import logging
from .common import *

_logger = logging.getLogger(__name__)

sec_token_param = 'mobile_apis.sec_token_for_online_requests'


class RequestAPI(http.Controller):

    @http.route('/api/user/requests', type='json', auth='public', methods=['POST'], )
    def get_user_requests(self, **post):
        try:

            required_fields = [
                'user_id',
                'sec_token',
            ]

            # Validate inputs
            if not all(post.get(field) for field in required_fields):
                missing = ', '.join([field for field in required_fields if not post.get(field)])
                return bad_params_template(missing)

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
                    'request_text': convert_to_plain_text(req.request_text),
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
            _logger.error("API </api/user/requests> Error: %s", str(e))
            return error_template(e)

    @http.route('/api/request/create', type='json', auth='public', methods=['POST'])
    def create_request(self, **post):
        required_fields = [
            'user_id',
            'sec_token',
            'category_id',
            'type_id',
            'request_text',
        ]

        # Validate inputs
        if not all(post.get(field) for field in required_fields):
            missing = ', '.join([field for field in required_fields if not post.get(field)])
            return bad_params_template(missing)

        user_id = check_int_str_val(int(post.get('user_id')))
        category_id = check_int_str_val(int(post['category_id']))
        type_id = check_int_str_val(int(post['type_id']))

        employee = request.env['hr.employee'].sudo().search([('user_id', '=', user_id)], limit=1)
        if not employee:
            return error_template(error_string="Employee not found for user")

        sec_token = request.env['ir.config_parameter'].sudo().get_param(sec_token_param)

        if post['sec_token'] != sec_token:
            return invalid_sec_token()

        # Validate category-type relationship
        category = request.env['getmo.request.category'].sudo().browse(category_id)
        if not category.exists():
            return error_template(error_string="Category not found")

        # Check if the provided type_id is linked to the category
        if not request.env['getmo.request.type'].sudo().search_count([
            ('id', '=', type_id),
            ('category_ids', 'in', category_id)
        ]):
            return error_template(error_string="Invalid Type for the selected Category")

        try:
            # Core request data
            request_vals = {
                'category_id': category_id,
                'type_id': type_id,
                'employee_id': employee.id,
                'request_text': post['request_text'],
                'priority': post.get('priority', '0')
            }

            # Create request
            new_request = request.env['getmo.request.request'].sudo().create(request_vals)
            data = {
                'success': True,
                'request_id': new_request.id,
                'request_code': new_request.name
            }
            return success_template(data)
        except Exception as e:
            _logger.error("API </api/request/create> Error: %s", str(e))
            return error_template(e)

    @http.route('/api/request/categories_with_types', type='json', auth='public', methods=['POST'])
    def get_categories_with_types(self, **post):
        try:
            # Security token validation
            sec_token = request.env['ir.config_parameter'].sudo().get_param(sec_token_param)
            if post.get('sec_token') != sec_token:
                return invalid_sec_token()

            # Fetch all categories with their types
            categories = request.env['getmo.request.category'].sudo().search([])
            Request = request.env['getmo.request.request'].sudo()
            result = []

            for category in categories:
                # Get types for this category
                types = category.request_type_ids.read(['id', 'name'])
                result.append({
                    "id": category.id,
                    "name": category.name,
                    "types": types,
                    "request_count": Request.search_count([('category_id', '=', category.id)])
                })

            return success_template({"categories": result})

        except Exception as e:
            _logger.error("API </api/request/categories_with_types> Error: %s", str(e))
            return error_template(e)
