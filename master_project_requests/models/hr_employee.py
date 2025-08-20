from odoo import models, fields, api


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    # Maximum workload capacity (hours per day)
    daily_capacity = fields.Float(
        string='Daily Capacity (hours)',
        default=8.0,store =True
    )

    # Current workload (computed field)
    current_workload = fields.Float(
        string='Current Workload (hours)',
        compute='_compute_current_workload',store =True
    )

    assigned_requests = fields.One2many('getmo.request.request', 'assigned_to_id', 'Assigned Requests')

    @api.depends('assigned_requests')
    @api.onchange('assigned_requests')
    def _compute_current_workload(self):
        for employee in self:
            # Filter in Python instead of search, for efficiency with the One2many
            active_requests = employee.assigned_requests.filtered(
                lambda r: r.stage_id.stage_type not in ['done', 'refused']
            )
            employee.current_workload = sum(request.estimated_duration for request in active_requests)


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
