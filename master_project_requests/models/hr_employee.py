from odoo import models, fields, api


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    # Maximum workload capacity (hours per day)
    daily_capacity = fields.Float(
        string='Daily Capacity (hours)',
        default=8.0
    )

    # Current workload (computed field)
    current_workload = fields.Float(
        string='Current Workload (hours)',
        compute='_compute_current_workload'
    )

    def _compute_current_workload(self):
        for employee in self:
            requests = self.env['getmo.request.request'].search([
                ('assigned_to_id', '=', employee.id),
                ('stage_id.stage_type', 'not in', ['done', 'refused'])
            ])
            employee.current_workload = sum(
                request.estimated_duration for request in requests
            )


class HrEmployeePublic(models.Model):
    _inherit = 'hr.employee.public'

    daily_capacity = fields.Float(
        string='Daily Capacity (hours)',
        related='employee_id.daily_capacity',
        readonly=True
    )

    current_workload = fields.Float(
        string='Current Workload (hours)',
        related='employee_id.current_workload',
        readonly=True
    )
