from odoo import http, fields
from odoo.http import request
from datetime import datetime, timedelta
from odoo.exceptions import AccessError
import json
import logging
_logger = logging.getLogger(__name__)


class RequestDashboardController(http.Controller):

    # Before Using SQL Queries For Speed
    @http.route('/api/managers/dashboard', type='json', auth='user', methods=['POST'], cors='*')
    def combined_manager_dashboard(self, **kwargs):
        """
        Unified Manager Dashboard API
        Returns:
            - Manager profile info
            - Comprehensive request statistics (global + manager-specific)
            - Assignment metrics
            - Attention-needed requests
            - Performance metrics (avg. times, top performers)
        """
        # Validate manager
        user_id = request.env.user.id
        employee = request.env['hr.employee'].sudo().search([('user_id', '=', user_id)], limit=1)
        if not employee:
            return self._error_response("Manager profile not found", 400)

        # Get all dashboard components
        manager_info = self._get_manager_info(employee)
        statistics = self._get_combined_statistics(employee)
        assignments = self._get_assignment_data(employee)
        attention_requests = self._get_attention_requests(employee)
        performance = self._get_performance_metrics()

        return {
            "manager": manager_info,
            "statistics": statistics,
            "assignments": assignments,
            "attention_requests": attention_requests,
            "performance": performance
        }

    def _error_response(self, message, status=400):
        return request.make_response(
            json.dumps({"error": message}),
            headers=[('Content-Type', 'application/json')],
            status=status
        )

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

    def _get_combined_statistics(self, employee):
        """Combine global statistics with manager-specific metrics"""
        Request = request.env['request.request'].sudo()

        # Global counts
        total_requests = Request.search_count([])

        # Stage breakdown (with names)
        stages = request.env['request.type.stage'].sudo().search([])
        by_stage = {
            stage.stage_type: {
                "count": Request.search_count([('stage_id', '=', stage.id)]),
                "name": stage.name
            } for stage in stages
        }

        # Category/Kind/Type breakdowns
        def get_breakdown(model, field):
            records = request.env[model].sudo().search([])
            return [{
                "id": r.id,
                "name": r.name,
                "count": Request.search_count([(field, '=', r.id)])
            } for r in records]

        return {
            "total_requests": total_requests,
            "by_stage": by_stage,
            "by_category": get_breakdown('request.category', 'category_id'),
            "by_kind": get_breakdown('request.kind', 'kind_id'),
            "by_type": get_breakdown('request.type', 'type_id'),
            "manager_specific": {
                "assigned_to_me": Request.search_count(['|', ('assigned_to_id', '=', employee.id), ('assigned_to_id.parent_id', '=', employee.id),]),
                "created_by_me": Request.search_count([('employee_id', '=', employee.id)])
            }
        }

    def _get_assignment_data(self, employee):
        """Manager's assignment metrics"""
        Request = request.env['request.request'].sudo()

        # Assigned to current manager
        assigned_requests = Request.search(['|', ('assigned_to_id', '=', employee.id), ('assigned_to_id.parent_id', '=', employee.id),])

        # Requests needing assignment in manager's types
        responsible_types = request.env['request.type'].sudo().search(['|', ('responsible_employees_ids', 'in', employee.id), ('responsible_employees_ids', 'in', employee.child_ids.ids)])
        unassigned_requests = Request.search([
            ('type_id', 'in', responsible_types.ids),
            ('assigned_to_id', '=', False),
            ('stage_id.stage_type', '=', 'draft')
        ])
        # Late requests
        late_requests = Request.search(['|',
            ('assigned_to_id', '=', employee.id),('assigned_to_id.parent_id', '=', employee.id),
            ('stage_id.stage_type', '=', 'in_progress'),
            ('date_assigned', '<', datetime.now() - timedelta(days=3))
        ])

        return {
            "assigned_count": len(assigned_requests),
            "unassigned_in_types": len(unassigned_requests),
            "late_requests_count": len(late_requests),
            "recently_assigned": [
                {
                    "id": r.id,
                    "name": r.name,
                    "type": r.type_id.name,
                    "date_assigned": r.date_assigned,
                } for r in assigned_requests.filtered(lambda r: r.date_assigned)
                           .sorted('date_assigned', reverse=True)[:5]
            ]
        }

    def _get_attention_requests(self, employee):
        """Requests needing immediate action"""
        Request = request.env['request.request'].sudo()
        attention_requests = Request.search(
            ['|', '|', ('assigned_to_id', '=', employee.id), ('assigned_to_id.parent_id', '=', employee.id),
             ('type_id.responsible_employees_ids', 'in', employee.id),
             ('stage_id.stage_type', 'in', ['draft', 'assigned', 'in_progress'])], order='date_request desc', limit=10)

        return [{
            "id": r.id,
            "name": r.name,
            "employee": r.employee_id.name,
            "type": r.type_id.name,
            "stage": r.stage_id.name,
            "days_open": (datetime.now() - r.date_request).days,
            "assigned_to": r.assigned_to_id.name if r.assigned_to_id else "Unassigned",
            "priority": r.priority,
            # "sla_deadline": r.sla_deadline  # Additional metric
        } for r in attention_requests]

    def _get_performance_metrics(self):
        """Global performance indicators"""
        Request = request.env['request.request'].sudo()

        # Time metrics
        assigned_requests = Request.search([('date_assigned', '!=', False)])
        completed_requests = Request.search([('date_closed', '!=', False)])

        avg_assign = self._calc_avg_time(
            assigned_requests,
            lambda r: (r.date_assigned - r.date_request).total_seconds() / 86400
        )

        avg_complete = self._calc_avg_time(
            [r for r in completed_requests if r.date_assigned],
            lambda r: (r.date_closed - r.date_assigned).total_seconds() / 86400
        )

        # Top performers
        top_employees = Request.read_group(
            [('assigned_to_id', '!=', False)],
            ['assigned_to_id'],
            ['assigned_to_id'],
            orderby='assigned_to_id desc',
            limit=5
        )
        sorted_top_employees = sorted(top_employees, key=lambda x: x['assigned_to_id_count'], reverse=True)

        return {
            "average_time_to_assign": round(avg_assign, 2),
            "average_time_to_complete": round(avg_complete, 2),
            "resolution_rate": self._calc_resolution_rate(),
            "top_performers": self.perform_top_performers(sorted_top_employees)
        }

    def perform_top_performers(self, top_employees):
        return [
            {
                'id': group['assigned_to_id'][0],
                'name': group['assigned_to_id'][1],
                'image':self.process_image_url(group['assigned_to_id'][0]),
                'requests_handled': self._get_requests_for_performer(group['assigned_to_id'][0])
            } for group in top_employees
        ]

    def _get_requests_for_performer(self, emp_id):
        requests = request.env['request.request'].sudo().search_count([('assigned_to_id', '=', emp_id)])
        return requests

    def _calc_avg_time(self, records, time_func):
        """Helper to calculate average times"""
        if not records:
            return 0
        return sum(time_func(r) for r in records) / len(records)

    def _calc_resolution_rate(self):
        """Calculate % of resolved requests"""
        total = request.env['request.request'].sudo().search_count([])
        resolved = request.env['request.request'].sudo().search_count([
            ('stage_id.stage_type', 'in', ['done', 'refused'])
        ])
        return round(resolved / total * 100, 2) if total else 0

    def _get_sla_status(self, request):
        """Additional SLA metric (example implementation)"""
        if request.sla_deadline:
            if datetime.now() > request.sla_deadline:
                return "breached"
            elif (request.sla_deadline - datetime.now()).days < 1:
                return "at_risk"
        return "within_sla"

    # After Using SQL Queries For Speed
    # @http.route('/api/managers/dashboard', type='json', auth='user', methods=['POST'], cors='*')
    # def combined_manager_dashboard(self, **kwargs):
    #     user_id = request.env.user.id
    #     employee = request.env['hr.employee'].sudo().search([('user_id', '=', user_id)], limit=1)
    #     if not employee:
    #         return self._error_response("Manager profile not found", 400)
    #
    #     manager_info = self._get_manager_info(employee)
    #     statistics = self._get_combined_statistics(employee)
    #     assignments = self._get_assignment_data(employee)
    #     attention_requests = self._get_attention_requests(employee)
    #     performance = self._get_performance_metrics()
    #
    #     return {
    #         "manager": manager_info,
    #         "statistics": statistics,
    #         "assignments": assignments,
    #         "attention_requests": attention_requests,
    #         "performance": performance
    #     }
    #
    # def _error_response(self, message, status=400):
    #     return request.make_response(
    #         json.dumps({"error": message}),
    #         headers=[('Content-Type', 'application/json')],
    #         status=status
    #     )
    #
    # def _get_manager_info(self, employee):
    #     return {
    #         "id": employee.id,
    #         "name": employee.name,
    #         "department": employee.department_id.name if employee.department_id else None,
    #         'image': self.process_image_url(employee.id),
    #     }
    #
    # def process_image_url(self, emp_id):
    #     web_base_url = request.env['ir.config_parameter'].sudo().get_param('web.base.url')
    #     return f'{web_base_url}/web/image/hr.employee/{emp_id or 0}/image_1920'
    #
    # def _get_combined_statistics(self, employee):
    #     """Fully SQL-optimized statistics calculation"""
    #     cr = request.env.cr
    #
    #     # 1. Total requests count
    #     cr.execute("SELECT COUNT(*) FROM request_request")
    #     total_requests = cr.fetchone()[0] or 0
    #
    #     # 2. Stage breakdown
    #     cr.execute("""
    #         SELECT s.id, s.stage_type, s.name, COUNT(r.id) as count
    #         FROM request_type_stage s
    #         LEFT JOIN request_request r ON r.stage_id = s.id
    #         GROUP BY s.id, s.stage_type, s.name
    #     """)
    #     by_stage = {}
    #     for stage_id, stage_type, stage_name, count in cr.fetchall():
    #         if stage_type not in by_stage:
    #             by_stage[stage_type] = {
    #                 "count": count,
    #                 "name": stage_name
    #             }
    #         else:
    #             by_stage[stage_type]["count"] += count
    #
    #     # 3. Category breakdown
    #     def get_sql_breakdown(model, field):
    #         cr.execute(f"""
    #             SELECT rel.id, rel.name, COUNT(r.id) as count
    #             FROM {model} rel
    #             LEFT JOIN request_request r ON r.{field} = rel.id
    #             GROUP BY rel.id, rel.name
    #             ORDER BY rel.id
    #         """)
    #         return [{
    #             "id": row[0],
    #             "name": row[1],
    #             "count": row[2]
    #         } for row in cr.fetchall()]
    #
    #     # 4. Manager-specific counts
    #     cr.execute("""
    #         SELECT COUNT(*)
    #         FROM request_request
    #         WHERE assigned_to_id = %s OR assigned_to_id IN (
    #             SELECT id FROM hr_employee WHERE parent_id = %s
    #         )
    #     """, (employee.id, employee.id))
    #     assigned_to_me = cr.fetchone()[0] or 0
    #
    #     cr.execute("""
    #         SELECT COUNT(*) FROM request_request WHERE employee_id = %s
    #     """, (employee.id,))
    #     created_by_me = cr.fetchone()[0] or 0
    #
    #     return {
    #         "total_requests": total_requests,
    #         "by_stage": by_stage,
    #         "by_category": get_sql_breakdown('request_category', 'category_id'),
    #         "by_kind": get_sql_breakdown('request_kind', 'kind_id'),
    #         "by_type": get_sql_breakdown('request_type', 'type_id'),
    #         "manager_specific": {
    #             "assigned_to_me": assigned_to_me,
    #             "created_by_me": created_by_me
    #         }
    #     }
    #
    # def _get_assignment_data(self, employee):
    #     """SQL-optimized assignment metrics"""
    #     cr = request.env.cr
    #
    #     # 1. Get responsible type IDs
    #     cr.execute("""
    #         SELECT id FROM request_type
    #         WHERE id IN (
    #             SELECT request_type_id FROM hr_employee_request_type_rel
    #             WHERE hr_employee_id IN %s
    #         )
    #     """, [tuple([employee.id] + employee.child_ids.ids)])
    #     type_ids = [r[0] for r in cr.fetchall()] if cr.rowcount else []
    #
    #     # 2. Assigned count
    #     cr.execute("""
    #         SELECT COUNT(*)
    #         FROM request_request
    #         WHERE assigned_to_id = %s OR assigned_to_id IN (
    #             SELECT id FROM hr_employee WHERE parent_id = %s
    #         )
    #     """, (employee.id, employee.id))
    #     assigned_count = cr.fetchone()[0] or 0
    #
    #     # 3. Unassigned count
    #     unassigned_count = 0
    #     if type_ids:
    #         cr.execute("""
    #             SELECT COUNT(*)
    #             FROM request_request r
    #             JOIN request_type_stage s ON r.stage_id = s.id
    #             WHERE r.type_id IN %s
    #             AND r.assigned_to_id IS NULL
    #             AND s.stage_type = 'draft'
    #         """, (tuple(type_ids),))
    #         unassigned_count = cr.fetchone()[0] or 0
    #
    #     # 4. Late requests count
    #     late_date = fields.Datetime.to_string(datetime.now() - timedelta(days=3))
    #     cr.execute("""
    #         SELECT COUNT(*)
    #         FROM request_request r
    #         JOIN request_type_stage s ON r.stage_id = s.id
    #         WHERE (r.assigned_to_id = %s OR r.assigned_to_id IN (
    #             SELECT id FROM hr_employee WHERE parent_id = %s
    #         ))
    #         AND s.stage_type = 'in_progress'
    #         AND r.date_assigned < %s
    #     """, (employee.id, employee.id, late_date))
    #     late_count = cr.fetchone()[0] or 0
    #
    #     # 5. Recently assigned requests
    #     cr.execute("""
    #         SELECT r.id, r.name, t.name as type_name, r.date_assigned
    #         FROM request_request r
    #         JOIN request_type t ON r.type_id = t.id
    #         WHERE (r.assigned_to_id = %s OR r.assigned_to_id IN (
    #             SELECT id FROM hr_employee WHERE parent_id = %s
    #         ))
    #         AND r.date_assigned IS NOT NULL
    #         ORDER BY r.date_assigned DESC
    #         LIMIT 5
    #     """, (employee.id, employee.id))
    #     recently_assigned = [{
    #         "id": row[0],
    #         "name": row[1],
    #         "type": row[2],
    #         "date_assigned": row[3]
    #     } for row in cr.fetchall()]
    #
    #     return {
    #         "assigned_count": assigned_count,
    #         "unassigned_in_types": unassigned_count,
    #         "late_requests_count": late_count,
    #         "recently_assigned": recently_assigned
    #     }
    #
    # def _get_attention_requests(self, employee):
    #     """Optimized attention requests with direct fields"""
    #     domain = [
    #         '|', '|',
    #         ('assigned_to_id', '=', employee.id),
    #         ('assigned_to_id.parent_id', '=', employee.id),
    #         ('type_id.responsible_employees_ids', 'in', employee.id),
    #         ('stage_id.stage_type', 'in', ['draft', 'assigned', 'in_progress'])
    #     ]
    #
    #     requests = request.env['request.request'].sudo().search(
    #         domain,
    #         order='date_request DESC',
    #         limit=10
    #     )
    #
    #     return [{
    #         "id": r.id,
    #         "name": r.name,
    #         "employee": r.employee_id.name,
    #         "type": r.type_id.name,
    #         "stage": r.stage_id.name,
    #         "days_open": (datetime.now() - r.date_request).days if r.date_request else 0,
    #         "assigned_to": r.assigned_to_id.name if r.assigned_to_id else "Unassigned",
    #         "priority": r.priority,
    #     } for r in requests]
    #
    # def _get_performance_metrics(self):
    #     """Optimized performance with raw SQL and batched reads"""
    #     cr = request.env.cr
    #
    #     # Average time to assign with corrected parenthesis
    #     cr.execute("""SELECT
    #                       AVG(EXTRACT(EPOCH FROM (date_assigned - date_request)) / 86400)
    #                   FROM request_request
    #                   WHERE date_assigned IS NOT NULL""")
    #     avg_assign = cr.fetchone()[0] or 0
    #
    #     # Average time to complete with corrected parenthesis
    #     cr.execute("""SELECT
    #                       AVG(EXTRACT(EPOCH FROM (date_closed - date_assigned)) / 86400)
    #                   FROM request_request
    #                   WHERE date_closed IS NOT NULL AND date_assigned IS NOT NULL""")
    #     avg_complete = cr.fetchone()[0] or 0
    #
    #     # Resolution rate with single query
    #     cr.execute("""SELECT
    #                       COUNT(*) FILTER (WHERE stage_type IN ('done', 'refused'))::float / COUNT(*)
    #                   FROM request_request r
    #                   JOIN request_type_stage s ON r.stage_id = s.id""")
    #     resolution_rate = (cr.fetchone()[0] or 0) * 100
    #
    #     # Top performers - Fixed implementation
    #     try:
    #         # First get the top 5 assigned_to_ids with most requests
    #         cr.execute("""
    #             SELECT assigned_to_id, COUNT(*) as request_count
    #             FROM request_request
    #             WHERE assigned_to_id IS NOT NULL
    #             GROUP BY assigned_to_id
    #             ORDER BY request_count DESC
    #             LIMIT 5
    #         """)
    #         top_performer_data = cr.fetchall()
    #
    #         top_performers = []
    #         for emp_id, count in top_performer_data:
    #             if not emp_id:
    #                 continue
    #
    #             employee = request.env['hr.employee'].sudo().browse(emp_id)
    #             top_performers.append({
    #                 'id': emp_id,
    #                 'name': employee.name,
    #                 'image': self.process_image_url(emp_id),
    #                 'requests_handled': count
    #             })
    #     except Exception as e:
    #         _logger.error("Error calculating top performers: %s", str(e))
    #         top_performers = []
    #
    #     return {
    #         "average_time_to_assign": round(avg_assign, 2),
    #         "average_time_to_complete": round(avg_complete, 2),
    #         "resolution_rate": round(resolution_rate, 2),
    #         "top_performers": top_performers
    #     }


    # New
    @http.route('/request/dashboard/data', type='json', auth='user', methods=['POST'], cors='*')
    def get_dashboard_data(self, **kwargs):

        # Security check - only allow manager access
        # if not request.env.user.has_group('master_project_requests.group_request_manager') or not request.env.user.has_group('master_project_requests.group_request_service_admin'):
            # return request.make_response(json.dumps({'error': 'Access denied'}),
            #                              [('Content-Type', 'application/json')])

        # Helper function to convert ORM data to JSON-serializable format
        def prepare_data(records, fields):
            return [{
                **{field: getattr(rec, field) for field in fields},
                'id': rec.id
            } for rec in records]

        # 1. System Overview Metrics
        # Calculate date ranges
        today = datetime.now()
        yesterday = today - timedelta(days=1)
        week_ago = today - timedelta(days=7)
        month_ago = today - timedelta(days=30)
        last_week_start = week_ago - timedelta(days=7)
        yesterday_end = datetime.now().replace(hour=23, minute=59, second=59) - timedelta(days=1)
        request_env = request.env['request.request'].sudo()

        # Current period metrics
        total_requests = request_env.search_count([])
        open_requests = request_env.search_count([('stage_id.stage_type', 'not in', ['done', 'refused'])])
        unassigned_requests = request_env.search_count([('stage_id.stage_type', '=', 'draft')])
        requests_past_due = request_env.search_count([
            ('stage_id.stage_type', 'not in', ['done', 'refused']),  # Only open requests
            ('date_closed', '<', today)  # Deadline passed
        ])
        requests_created_today = request_env.search_count([('create_date', '>=', today)])
        requests_completed_week = request_env.search_count([
            ('stage_id.stage_type', '=', 'done'),
            ('date_closed', '>=', week_ago)
        ])

        # Historical data for trends
        # For created today vs yesterday
        requests_created_yesterday = request_env.search_count([
            ('create_date', '>=', yesterday),
            ('create_date', '<', today)
        ])

        # For weekly completion rate
        requests_completed_last_week = request_env.search_count([
            ('stage_id.stage_type', '=', 'done'),
            ('date_closed', '>=', last_week_start),
            ('date_closed', '<', week_ago)
        ])

        # For average daily requests
        avg_daily_requests = request_env.search_count([
            ('create_date', '>=', month_ago),
            ('create_date', '<', today)
        ]) / 30  # 30-day average

        # For unassigned requests delta
        prev_unassigned = request_env.search_count([
            ('stage_id.stage_type', '=', 'draft'),
            ('create_date', '<', today)
        ])

        # For open requests trend
        prev_open_requests = request_env.search_count([
            ('create_date', '<=', yesterday_end),  # Created before end of yesterday
            '|',
            ('date_closed', '>', yesterday_end),  # Closed AFTER yesterday
            ('date_closed', '=', False),  # OR still not closed
            ('stage_id.stage_type', 'not in', ['done', 'refused'])
        ])

        prev_total_requests = request_env.search_count([
            ('create_date', '<', last_week_start)
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
                    'percentage': ((total_requests - prev_total_requests) / prev_total_requests * 100) if prev_total_requests > 0 else 0,
                    'direction': 'up' if total_requests >= prev_total_requests else 'down',
                    'comparison': 'last week'
                },
                'open_requests': {
                    'percentage': ((open_requests - prev_open_requests) / prev_open_requests * 100) if prev_open_requests > 0 else 0,
                    'direction': 'up' if open_requests >= prev_open_requests else 'down',
                    'comparison': 'yesterday'
                },
                'created_today': {
                    'percentage': ((requests_created_today - requests_created_yesterday) / requests_created_yesterday * 100) if requests_created_yesterday > 0 else 0,
                    'direction': 'up' if requests_created_today >= requests_created_yesterday else 'down',
                    'comparison': 'yesterday'
                },
                'completed_week': {
                    'percentage': ((requests_completed_week - requests_completed_last_week) / requests_completed_last_week * 100) if requests_completed_last_week > 0 else 0,
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
                [('kind_id', '!=', False)],
                ['kind_id'],
                ['kind_id']
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

        performance = {
            'avg_resolution_time': sum(resolution_times) / len(resolution_times) if resolution_times else 0,
            'max_resolution_time': max(resolution_times) if resolution_times else 0,
        }

        employee_performance_data = request_env.read_group(
            [('assigned_to_id', '!=', False), ('stage_id.stage_type', '=', 'done')],
            ['assigned_to_id', 'request_count:count(id)'],
            ['assigned_to_id'],
            orderby='request_count desc',
            limit=5
        )

        processed_performance = []
        for entry in employee_performance_data:
            employee_id = entry['assigned_to_id'][0] if entry['assigned_to_id'] else None
            image_url = self.process_image_url(employee_id)
            processed_performance.append({
                'employee_id': employee_id,
                'employee_name': entry['assigned_to_id'][1],
                'request_count': entry['request_count'],
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
            'recently_completed': prepare_data(
                request_env.search([
                    ('stage_id.stage_type', '=', 'done')
                ], order='date_closed desc', limit=10),
                ['name', 'date_request', 'date_closed', 'assigned_to_id']
            ),
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
            'request_types': prepare_data(
                request.env['request.type'].sudo().search([]),
                ['name', 'request_count', 'responsible_employees_ids']
            ),
            'categories': prepare_data(
                request.env['request.category'].sudo().search([]),
                ['name', 'request_count', 'category_manager_id']
            ),
            'kinds': prepare_data(
                request.env['request.kind'].sudo().search([]),
                ['name', 'request_count']
            ),
            'stages': prepare_data(
                request.env['request.type.stage'].sudo().search([]),
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
            'last_updated': fields.Datetime.now()
        }

        return dashboard_data
