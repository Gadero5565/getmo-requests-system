from odoo import http, fields
from odoo.http import request
from datetime import datetime, timedelta
from odoo.exceptions import AccessError
import pytz
import logging
_logger = logging.getLogger(__name__)


class RequestDashboardController(http.Controller):
    @http.route('/api/technician/specialist/dashboard', type='json', auth='public', methods=['POST'], cors='*')
    def combined_manager_dashboard(self, **kwargs):
        user = request.env.user
        is_technician = user.has_group('master_project_requests.group_request_technician_specialist')

        # Get current employee (for both manager/technician)
        employee = request.env['hr.employee'].sudo().search([('user_id', '=', user.id)], limit=1)
        if not employee:
            return self._error_response("Employee profile not found", 400)

        # TECHNICIAN-SPECIFIC DATA
        if is_technician:
            return {
                "manager": self._get_manager_info(employee),
                "statistics": self._get_technician_statistics(employee),
                "assignments": self._get_technician_assignments(employee),
                "attention_requests": self._get_technician_attention_requests(employee),
                "performance": self._get_technician_performance(employee),
                "is_technician": True  # Flag for frontend
            }
        else:
            return is_technician

    def _get_manager_info(self, employee):
        return {
            "id": employee.id,
            "name": employee.name,
            "department": employee.department_id.name if employee.department_id else None,
            'image': self.process_image_url(employee.id),
        }

    def process_image_url(self, emp_id):
        web_base_url = request.env['ir.config_parameter'].sudo().get_param('web.base.url')
        return f'{web_base_url}/web/image/hr.employee/{emp_id or 0}/image_1920'

    def _get_technician_statistics(self, employee):
        Request = request.env['getmo.request.request'].sudo()
        assigned_domain = [('assigned_to_id', '=', employee.id)]

        total_requests = Request.search_count(assigned_domain)

        stages = request.env['getmo.request.type.stage'].sudo().search([])
        by_stage = {
            stage.stage_type: {
                "count": Request.search_count(assigned_domain + [('stage_id', '=', stage.id)]),
                "name": stage.name
            } for stage in stages
        }

        # Add category and type breakdowns
        def get_breakdown(model, field):
            records = request.env[model].sudo().search([])
            return [{
                "id": r.id,
                "name": r.name,
                "count": Request.search_count(assigned_domain + [(field, '=', r.id)])
            } for r in records]

        return {
            "total_requests": total_requests,
            "by_stage": by_stage,
            "by_category": get_breakdown('getmo.request.category', 'category_id'),
            "by_type": get_breakdown('getmo.request.type', 'type_id'),
        }

    def _get_technician_assignments(self, employee):
        Request = request.env['getmo.request.request'].sudo()
        assigned_requests = Request.search([('assigned_to_id', '=', employee.id)])

        # Add these fields to match template expectations
        return {
            "assigned_count": len(assigned_requests),
            "unassigned_in_types": 0,  # Not applicable to technicians
            "late_requests_count": 0,  # Not applicable to technicians
            "assigned_to_me": len(assigned_requests),
            "recently_assigned": [{
                "id": r.id,
                "name": r.name,
                "type": r.type_id.name,
                "date_assigned": r.date_assigned.strftime("%Y-%m-%d %H:%M") if r.date_assigned else "",
            } for r in assigned_requests.sorted('date_assigned', reverse=True)[:5]]
        }

    def _get_technician_attention_requests(self, employee):
        Request = request.env['getmo.request.request'].sudo()
        attention_requests = Request.search([
            ('assigned_to_id', '=', employee.id),
            ('stage_id.stage_type', 'in', ['draft', 'assigned', 'in_progress'])
        ], order='date_request desc', limit=10)

        return [{
            "id": r.id,
            "name": r.name,
            "employee": r.employee_id.name,
            "type": r.type_id.name,
            "stage": r.stage_id.name,
            "days_open": (datetime.now() - r.date_request).days if r.date_request else 0,
            "assigned_to": r.assigned_to_id.name if r.assigned_to_id else "Unassigned",
            "priority": r.priority,
        } for r in attention_requests]

    def _get_technician_performance(self, employee):
        Request = request.env['getmo.request.request'].sudo()

        # Get all requests assigned to the technician
        assigned_requests = Request.search([('assigned_to_id', '=', employee.id)])

        # Get completed requests
        completed_requests = assigned_requests.filtered(lambda r: r.date_closed)

        # Calculate Resolution Rate (Completion Rate)
        resolution_rate = round(
            (len(completed_requests) / len(assigned_requests) * 100) if assigned_requests else 0
        )

        # Calculate Average Time to Complete (in days)
        avg_completion_time = 0
        if completed_requests:
            total_seconds = sum(
                (r.date_closed - r.date_assigned).total_seconds()
                for r in completed_requests
                if r.date_assigned and r.date_closed
            )
            avg_completion_time = round(total_seconds / len(completed_requests) / 86400, 1)  # Convert to days

        # Calculate Average Time to Assign (in days)
        avg_assign_time = 0
        if assigned_requests:
            total_assign_seconds = sum(
                (r.date_assigned - r.create_date).total_seconds()
                for r in assigned_requests
                if r.date_assigned
            )
            avg_assign_time = round(total_assign_seconds / len(assigned_requests) / 86400, 1)  # Convert to days

        return {
            "resolution_rate": resolution_rate,
            "average_time_to_complete": avg_completion_time,
            "average_time_to_assign": avg_assign_time
        }

    @http.route('/api/users/dashboard', type='json', auth='user', methods=['POST'], cors='*')
    def combined_user_dashboard(self, **kwargs):
        """
        User Dashboard API
        Returns:
            - User profile info
            - User-specific request statistics
            - Attention-needed requests
        """
        user_id = request.env.user.id
        employee = request.env['hr.employee'].sudo().search([('user_id', '=', user_id)], limit=1)
        if not employee:
            return self._error_response("User profile not found", 400)

        # Get dashboard components specific to user
        user_info = self._get_user_info(employee)
        statistics = self._get_user_statistics(employee)
        attention_requests = self._get_user_attention_requests(employee)

        return {
            "user": user_info,
            "statistics": statistics,
            "attention_requests": attention_requests,
        }

    def _get_user_info(self, employee):
        return {
            "id": employee.id,
            "name": employee.name,
            "department": employee.department_id.name if employee.department_id else None,
            'image': self.process_image_url(employee.id),
        }

    def _get_user_statistics(self, employee):
        Request = request.env['getmo.request.request'].sudo()
        user_domain = [('employee_id', '=', employee.id)]

        # User-specific counts
        total_requests = Request.search_count(user_domain)

        # Stage breakdown
        stages = request.env['getmo.request.type.stage'].sudo().search([])
        by_stage = {
            stage.stage_type: {
                "count": Request.search_count(user_domain + [('stage_id', '=', stage.id)]),
                "name": stage.name
            } for stage in stages
        }

        return {
            "total_requests": total_requests,
            "by_stage": by_stage,
            "by_category": self._get_user_breakdown('getmo.request.category', 'category_id', employee),
            "by_type": self._get_user_breakdown('getmo.request.type', 'type_id', employee),
        }

    def _get_user_breakdown(self, model, field, employee):
        records = request.env[model].sudo().search([])
        Request = request.env['getmo.request.request'].sudo()
        user_domain = [('employee_id', '=', employee.id)]

        return [{
            "id": r.id,
            "name": r.name,
            "count": Request.search_count(user_domain + [(field, '=', r.id)])
        } for r in records]

    def _get_user_attention_requests(self, employee):
        Request = request.env['getmo.request.request'].sudo()
        attention_requests = Request.search([
            ('employee_id', '=', employee.id),
            ('stage_id.stage_type', 'in', ['draft', 'assigned', 'in_progress'])
        ], order='date_request desc', limit=10)

        return [{
            "id": r.id,
            "name": r.name,
            "type": r.type_id.name,
            "stage": r.stage_id.name,
            "days_open": (datetime.now() - r.date_request).days,
            "status": self._get_request_status(r),
            "priority": r.priority,
        } for r in attention_requests]

    def _get_request_status(self, request):
        if request.stage_id.stage_type in ['draft', 'assigned']:
            if request.assigned_to_id:
                return f"Assigned to {request.assigned_to_id.name}"
            else:
                return f"Request Not Assigned"
        elif request.stage_id.stage_type == 'in_progress':
            return "In Progress"
        return "Completed"

    # New
    @http.route('/request/dashboard/data', type='json', auth='user', methods=['POST'], cors='*')
    def get_dashboard_data(self, **kwargs):

        # Security check - only allow manager access
        if not request.env.user.has_group(
                'master_project_requests.group_request_manager') or not request.env.user.has_group(
                'master_project_requests.group_request_service_admin'):
            return {'is_admin': False}
        else:
            # Helper function remains the same
            def prepare_data(records, fields):
                return [{
                    **{field: getattr(rec, field) for field in fields},
                    'id': rec.id
                } for rec in records]

            # Get current date in user's timezone
            today_date = fields.Date.context_today(request.env.user)
            today_start = fields.Datetime.start_of(today_date, 'day')
            today_end = fields.Datetime.end_of(today_date, 'day')

            # Calculate date ranges relative to user's timezone
            yesterday_date = today_date - timedelta(days=1)
            yesterday_start = fields.Datetime.start_of(yesterday_date, 'day')
            yesterday_end = fields.Datetime.end_of(yesterday_date, 'day')

            week_ago_date = today_date - timedelta(days=7)
            week_ago_start = fields.Datetime.start_of(week_ago_date, 'day')

            month_ago_date = today_date - timedelta(days=30)
            month_ago_start = fields.Datetime.start_of(month_ago_date, 'day')

            # Last week boundaries (14-7 days ago)
            last_week_start_date = today_date - timedelta(days=14)
            last_week_end_date = today_date - timedelta(days=8)  # 7 days before today
            last_week_start = fields.Datetime.start_of(last_week_start_date, 'day')
            last_week_end = fields.Datetime.end_of(last_week_end_date, 'day')

            request_env = request.env['getmo.request.request'].sudo()

            # 1. System Overview Metrics
            total_requests = request_env.search_count([])
            open_requests = request_env.search_count([('stage_id.stage_type', 'not in', ['done', 'refused'])])
            unassigned_requests = request_env.search_count([('stage_id.stage_type', '=', 'draft')])

            requests_past_due = request_env.search_count([
                ('is_past_due', '!=', False)
            ])

            requests_created_today = request_env.search_count([
                ('create_date', '>=', today_start),
                ('create_date', '<=', today_end)
            ])

            requests_completed_week = request_env.search_count([
                ('stage_id.stage_type', '=', 'done'),
                ('date_closed', '>=', week_ago_start),
                ('date_closed', '<=', today_end)  # Completed in last 7 days
            ])

            # Historical data
            requests_created_yesterday = request_env.search_count([
                ('create_date', '>=', yesterday_start),
                ('create_date', '<=', yesterday_end)
            ])

            requests_completed_last_week = request_env.search_count([
                ('stage_id.stage_type', '=', 'done'),
                ('date_closed', '>=', last_week_start),
                ('date_closed', '<=', last_week_end)
            ])

            avg_daily_requests = request_env.search_count([
                ('create_date', '>=', month_ago_start),
                ('create_date', '<=', today_end)
            ]) / 30.0  # 30-day average

            # Unassigned requests delta
            prev_unassigned = request_env.search_count([
                ('stage_id.stage_type', '=', 'draft'),
                ('create_date', '<=', yesterday_end)  # Counted until yesterday
            ])

            # Open requests trend
            prev_open_requests = request_env.search_count([
                ('create_date', '<=', yesterday_end),
                '|',
                ('date_closed', '>', yesterday_end),
                ('date_closed', '=', False),
                ('stage_id.stage_type', 'not in', ['done', 'refused'])
            ])

            # Total requests trend (7 days ago)
            seven_days_ago_date = today_date - timedelta(days=7)
            seven_days_ago_start = fields.Datetime.start_of(seven_days_ago_date, 'day')
            prev_total_requests = request_env.search_count([
                ('create_date', '<', seven_days_ago_start)
            ])

            metrics = {
                'total_requests': total_requests,
                'open_requests': open_requests,
                'unassigned_requests': unassigned_requests,
                'requests_past_due': requests_past_due,
                'requests_created_today': requests_created_today,
                'requests_completed_week': requests_completed_week,

                'trends': {
                    'total_requests': {
                        'percentage': ((
                                                   total_requests - prev_total_requests) / prev_total_requests * 100) if prev_total_requests > 0 else 0,
                        'direction': 'up' if total_requests >= prev_total_requests else 'down',
                        'comparison': 'last week'
                    },
                    'open_requests': {
                        'percentage': ((
                                                   open_requests - prev_open_requests) / prev_open_requests * 100) if prev_open_requests > 0 else 0,
                        'direction': 'up' if open_requests >= prev_open_requests else 'down',
                        'comparison': 'yesterday'
                    },
                    'created_today': {
                        'percentage': ((
                                                   requests_created_today - requests_created_yesterday) / requests_created_yesterday * 100) if requests_created_yesterday > 0 else 0,
                        'direction': 'up' if requests_created_today >= requests_created_yesterday else 'down',
                        'comparison': 'yesterday'
                    },
                    'completed_week': {
                        'percentage': ((
                                                   requests_completed_week - requests_completed_last_week) / requests_completed_last_week * 100) if requests_completed_last_week > 0 else 0,
                        'direction': 'up' if requests_completed_week >= requests_completed_last_week else 'down',
                        'comparison': 'last week'
                    },
                    'unassigned_requests': {
                        'new_today': unassigned_requests - prev_unassigned,
                        'direction': 'up' if unassigned_requests >= prev_unassigned else 'down',
                        'comparison': 'yesterday'
                    }
                }
            }

            # 2. Request Distribution
            distribution = {
                'by_stage': request_env.read_group(
                    [('stage_id', '!=', False)],
                    ['stage_id'],
                    ['stage_id']
                ),
                'by_category': request_env.read_group(
                    [('category_id', '!=', False)],
                    ['category_id'],
                    ['category_id']
                ),
                'by_kind': request_env.read_group(
                    [('genre_id', '!=', False)],
                    ['genre_id'],
                    ['genre_id']
                ),
                'by_priority': request_env.read_group(
                    [],
                    ['priority'],
                    ['priority']
                ),
            }

            # 3. Performance Metrics
            done_requests = request_env.search([
                ('stage_id.stage_type', '=', 'done'),
                ('date_request', '!=', False),
                ('date_closed', '!=', False)
            ])

            resolution_times = [
                (r.date_closed - r.date_request).total_seconds() / 3600
                for r in done_requests
            ]

            # Inside your get_dashboard_data method
            performance = {
                'avg_resolution_time': sum(resolution_times) / len(resolution_times) if resolution_times else 0,
                'max_resolution_time': max(resolution_times) if resolution_times else 0,
                # Convert hours to rounded minutes
                'avg_resolution_time_minutes': round(
                    (sum(resolution_times) / len(resolution_times)) * 60) if resolution_times else 0,
                'max_resolution_time_minutes': round(max(resolution_times) * 60) if resolution_times else 0,
            }

            employee_performance_data = request_env.read_group(
                [('assigned_to_id', '!=', False), ('stage_id.stage_type', '=', 'done')],
                ['assigned_to_id', 'request_count:count(id)'],
                ['assigned_to_id'],
                orderby='request_count desc',
                limit=5
            )

            employee_ids = [e['assigned_to_id'][0] for e in employee_performance_data]
            all_requests_data = request_env.read_group(
                [('assigned_to_id', 'in', employee_ids)],
                ['assigned_to_id'],
                ['assigned_to_id']
            )
            total_requests_map = {e['assigned_to_id'][0]: e['assigned_to_id_count'] for e in all_requests_data}

            # Calculate performance metrics
            processed_performance = []
            for entry in employee_performance_data:
                employee_id = entry['assigned_to_id'][0]
                completed = entry['request_count']
                total = total_requests_map.get(employee_id, 1)  # Avoid division by zero

                # 1. Calculate completion rate
                completion_rate = round((completed / total) * 100, 1)

                # 2. Calculate performance rating (1-5 scale)
                rating = min(5.0, max(1.0,
                                      (completion_rate / 20) +  # 100% = 5 points
                                      (min(completed, 10) / 2)  # Max 5 points for volume
                                      ))

                image_url = self.process_image_url(employee_id)
                processed_performance.append({
                    'employee_id': employee_id,
                    'employee_name': entry['assigned_to_id'][1],
                    'request_count': entry['request_count'],
                    'completion_rate': completion_rate,
                    'rating': rating,
                    'image_url': image_url
                })

            performance['employee_performance'] = processed_performance

            category_data = request_env.read_group(
                [('category_id', '!=', False)],
                ['category_id'],
                ['category_id'],
                orderby='category_id desc'
            )

            sorted_category_data = sorted(category_data, key=lambda x: x['category_id_count'], reverse=True)

            # 4. Operational Data
            operational = {
                'pending_assignments': prepare_data(
                    request_env.search([
                        ('stage_id.stage_type', '=', 'draft'),
                        ('category_id.category_manager_id.user_id', '=', request.env.user.id)
                    ], limit=10),
                    ['name', 'date_request', 'type_id', 'priority']
                ),
                'recently_completed': [
                    {
                        'id': rec.id,
                        'name': rec.name,
                        'date_request': rec.date_request,
                        'date_closed': rec.date_closed,
                        'assigned_to_id': rec.assigned_to_id.id,
                        'assigned_to_name': rec.assigned_to_id.name,
                    }
                    for rec in request_env.search([
                        ('stage_id.stage_type', '=', 'done')
                    ], order='date_closed desc', limit=10)
                ],
                'overdue_requests': prepare_data(
                    request_env.search([
                        ('stage_id.stage_type', 'not in', ['done', 'refused']),
                        ('date_closed', '<', fields.Datetime.now())
                    ], limit=10),
                    ['name', 'date_request', 'date_closed', 'assigned_to_id']
                ),
                'category_workload': sorted_category_data,
            }
            # 5. Configuration Overview
            config_overview = {
                'request_types': [
                                {
                                    'id': type.id,
                                    'name': type.name,
                                    'request_count': type.request_count,
                                    'responsible_employees': [
                                        {
                                            'id': emp.id,
                                            'name': emp.name,
                                            'image_url': self.process_image_url(emp.id)
                                        }
                                        for emp in type.responsible_employees_ids
                                    ]
                                }
                                for type in request.env['getmo.request.type'].sudo().search([])
                            ],
                'categories': prepare_data(
                    request.env['getmo.request.category'].sudo().search([]),
                    ['name', 'request_count', 'category_manager_id']
                ),
                'kinds': prepare_data(
                    request.env['getmo.request.genre'].sudo().search([]),
                    ['name', 'request_count']
                ),
                'stages': prepare_data(
                    request.env['getmo.request.type.stage'].sudo().search([]),
                    ['name', 'stage_type', 'sequence']
                ),
            }

            # Compile final dashboard data
            dashboard_data = {
                'metrics': metrics,
                'distribution': distribution,
                'performance': performance,
                'operational': operational,
                'config_overview': config_overview,
                'last_updated': self.convert_time_zone(fields.Datetime.now()),
                'is_admin': True,
            }

            return dashboard_data

    def convert_time_zone(self, date):
        user_tz = request.env.user.tz or 'UTC'
        dt = fields.Datetime.from_string(date)
        dt_tz = dt.astimezone(pytz.timezone(user_tz))
        return fields.Datetime.to_string(dt_tz)
