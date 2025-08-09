from odoo import models, fields, api, _
from odoo.exceptions import UserError
from faker import Faker
import random


class GenerateRequestsWizard(models.TransientModel):
    _name = 'generate.requests.wizard'
    _description = 'Wizard to generate fake requests'

    category_id = fields.Many2one(
        'getmo.request.category',
        string='Category',
        required=True
    )
    type_id = fields.Many2one(
        'getmo.request.type',
        string='Type',
        required=True,
        domain="[('category_ids', 'in', category_id)]"
    )
    count = fields.Integer(
        string='Number of Requests to Generate',
        default=100,
        required=True
    )
    date_range = fields.Selection([
        ('30', 'Last 30 days'),
        ('60', 'Last 60 days'),
        ('90', 'Last 90 days'),
        ('180', 'Last 180 days'),
        ('365', 'Last 365 days'),
    ], string='Date Range', default='30', required=True)
    priority_distribution = fields.Selection([
        ('normal', 'Mostly Normal (80%)'),
        ('mixed', 'Mixed Priorities'),
        ('high', 'More High Priority (30%)'),
    ], string='Priority Distribution', default='normal')
    stage_distribution = fields.Boolean(
        string='Vary Stages',
        default=True,
        help="If checked, will create requests in different stages"
    )

    @api.onchange('category_id')
    def _onchange_category_id(self):
        if self.category_id and self.category_id not in self.type_id.category_ids:
            self.type_id = False

    def action_generate_requests(self):
        self.ensure_one()

        if self.count <= 0:
            raise UserError(_("Please enter a positive number of requests to generate."))

        if self.count > 10000:
            raise UserError(_("For performance reasons, please generate no more than 10,000 requests at a time."))

        # Initialize Faker
        fake = Faker()
        Faker.seed(0)  # For consistent results

        # Get all employees for random assignment
        employees = self.env['hr.employee'].search([('child_ids', '=', False)])
        if not employees:
            raise UserError(_("No employees found in the system. Please create some employees first."))

        # Get all stages
        stages = self.env['getmo.request.type.stage'].search([])
        if not stages:
            raise UserError(_("No stages found for request types. Please configure stages first."))

        # Prepare priorities based on distribution
        priorities = ['0', '1', '2', '3']
        if self.priority_distribution == 'normal':
            priority_weights = [0.8, 0.1, 0.07, 0.03]  # 80% normal
        elif self.priority_distribution == 'high':
            priority_weights = [0.5, 0.2, 0.2, 0.1]  # 50% normal, 20% high/very high
        else:  # mixed
            priority_weights = [0.25, 0.25, 0.25, 0.25]  # equal distribution

        # Calculate date range
        days = int(self.date_range)
        date_end = fields.Datetime.now()

        batch_size = 100  # Create records in batches for better performance
        batches = (self.count + batch_size - 1) // batch_size

        for batch in range(batches):
            current_batch_size = min(batch_size, self.count - batch * batch_size)
            request_vals = []

            for i in range(current_batch_size):
                # Random date within range
                random_days = random.randint(0, days)
                random_hours = random.randint(0, 23)
                random_minutes = random.randint(0, 59)
                date_request = fields.Datetime.subtract(
                    date_end,
                    days=random_days,
                    hours=random_hours,
                    minutes=random_minutes
                )

                # Random employee (excluding the admin user's employee if needed)
                employee = random.choice(employees)

                # Random stage if enabled
                if self.stage_distribution:
                    stage = random.choice(stages)
                    # For done stages, ensure we have a result text
                    result_text = fake.paragraph() if stage.stage_type == 'done' else False
                    # For assigned/in_progress/done stages, assign someone
                    assigned_to = random.choice(employees) if stage.stage_type in ['assigned', 'in_progress',
                                                                                   'done'] else False
                    date_assigned = date_request if assigned_to and stage.stage_type in ['assigned', 'in_progress',
                                                                                         'done'] else False
                    date_closed = fields.Datetime.add(date_request, days=random.randint(1,
                                                                                        30)) if stage.stage_type == 'done' else False
                else:
                    stage = stages.filtered(lambda s: s.stage_type == 'draft')
                    result_text = False
                    assigned_to = False
                    date_assigned = False
                    date_closed = False

                # Random priority
                priority = random.choices(priorities, weights=priority_weights, k=1)[0]

                request_vals.append({
                    'name': self.type_id.sequence_id.next_by_id() if self.type_id.sequence_id else f"REQ-{batch * batch_size + i + 1}",
                    'request_text': f"<p>{fake.paragraph()}</p><p>{fake.paragraph()}</p>",
                    'type_id': self.type_id.id,
                    'category_id': self.category_id.id,
                    'stage_id': stage.id,
                    'priority': priority,
                    'employee_id': employee.id,
                    'assigned_to_id': assigned_to.id if assigned_to else False,
                    'date_request': date_request,
                    'date_assigned': date_assigned,
                    'date_closed': date_closed,
                    'result_text': f"<p>{result_text}</p>" if result_text else False,
                })

            # Create the batch
            self.env['getmo.request.request'].create(request_vals)

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Success'),
                'message': _('Successfully generated %s requests.', self.count),
                'sticky': False,
                'next': {'type': 'ir.actions.act_window_close'},
            }
        }