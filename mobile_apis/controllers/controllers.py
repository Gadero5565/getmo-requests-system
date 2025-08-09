from odoo import http
from odoo.http import request
from .common import *

sec_token_param = 'mobile_apis.sec_token_for_online_requests'


class DashboardController(http.Controller):
    @http.route('/api/user/dashboard', type='json', auth='public', methods=['POST'])
    def get_dashboard_data(self, **kwargs):
        # Get the current user's employee record
        user_id = kwargs['user_id']
        # Verify security token

        sec_token = request.env['ir.config_parameter'].sudo().get_param(sec_token_param)

        if kwargs['sec_token'] != sec_token:
            return invalid_sec_token()

        employee = request.env['hr.employee'].sudo().search([('user_id', '=', user_id)])
        if not employee:
            return {'error': 'No employee record found for the user'}

        # Reference to the request model
        Request = request.env['getmo.request.request'].sudo()

        # Existing dashboard card counts
        draft_count = Request.search_count([
            ('employee_id', '=', employee.id),
            ('stage_id.stage_type', '=', 'draft')
        ])
        in_progress_count = Request.search_count([
            ('employee_id', '=', employee.id),
            ('stage_id.stage_type', 'in', ['in_progress', 'assigned'])
        ])
        done_count = Request.search_count([
            ('employee_id', '=', employee.id),
            ('stage_id.stage_type', '=', 'done')
        ])
        refused_count = Request.search_count([
            ('employee_id', '=', employee.id),
            ('stage_id.stage_type', '=', 'refused')
        ])
        urgent_count = Request.search_count([
            ('employee_id', '=', employee.id),
            ('priority', 'in', ('2', '3')),
            ('stage_id.stage_type', 'not in', ('done', 'refused'))
        ])

        # Format dashboard cards data
        dashboard_cards = [
            {'card_int_val': draft_count, 'card_name': 'Draft'},
            {'card_int_val': in_progress_count, 'card_name': 'In Progress'},
            {'card_int_val': done_count, 'card_name': 'Done'},
            {'card_int_val': refused_count, 'card_name': 'Refused'},
            {'card_int_val': urgent_count, 'card_name': 'Urgent'},
        ]

        # Fetch all request types
        request_types = request.env['getmo.request.type'].sudo().search([])
        types_list = [{'id': t.id, 'name': t.name} for t in request_types]

        # Fetch request counts by category
        categories = request.env['getmo.request.category'].sudo().search([])
        category_counts = [
            {
                'category_id': category.id,
                'category_name': category.name,
                'request_count': Request.search_count([('category_id', '=', category.id), ('employee_id', '=', employee.id)])
            }
            for category in categories
        ]

        # Return the JSON response
        return {
            'dashboard_cards_details': dashboard_cards,
            'requests_types': types_list,
            'category_counts': category_counts,  # New field for category-based counts
        }

    @http.route('/api/get_request_token', type='json', auth='public', methods=['POST'])
    def get_token_for_online_services(self):
        sec_token_for_online_requests = request.env['ir.config_parameter'].sudo().get_param(sec_token_param)
        return sec_token_for_online_requests
