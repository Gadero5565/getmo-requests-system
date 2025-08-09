from odoo import http
from odoo.http import request, Response
import logging
from .common import *

_logger = logging.getLogger(__name__)

sec_token_param = 'mobile_apis.sec_token_for_online_requests'


class EmployeeAPI(http.Controller):

    @http.route('/api/user/profile', type='json', auth='public', methods=['POST'])
    def get_employee_profile(self, **post):
        try:
            # Extract and validate user_id
            user_id = post.get('user_id')
            if not user_id:
                return error_template("Missing 'user_id' in request")

            # Find employee linked to user
            employee = request.env['hr.employee'].sudo().search([
                ('user_id', '=', int(user_id))
            ], limit=1)

            if not employee:
                return error_template("Employee not found")

            sec_token = request.env['ir.config_parameter'].sudo().get_param(sec_token_param)

            if post['sec_token'] != sec_token:
                return invalid_sec_token()

            # Prepare profile data
            profile_data = {
                'employee_id': employee.id,
                'name': employee.name,
                'job_title': employee.job_title or '',
                'department': employee.department_id.name if employee.department_id else '',
                'work_phone': employee.work_phone or '',
                'work_email': employee.work_email or '',
                'marital': employee.marital or '',
                'country': employee.country_id.name or '',
                'identification_id': employee.identification_id or '',
                'passport_id': employee.passport_id or '',
                'gender': employee.gender or '',
                'birthday': employee.birthday or '',
                'visa_no': employee.visa_no or '',
                'certificate': employee.certificate or '',
                'study_field': employee.study_field or '',
                'image_url': process_image_url(record_id=employee.id, model_name='hr.employee'),
                'manager': employee.parent_id.name if employee.parent_id else '',
            }

            return success_template(profile_data)
        except Exception as e:
            _logger.error("Employee Profile API Error: %s", str(e))
            return error_template(str(e))
