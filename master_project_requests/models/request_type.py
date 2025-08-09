import re
from odoo import models, fields, api,_
from odoo.exceptions import ValidationError


class RequestType(models.Model):
    _name = 'getmo.request.type'
    _description = 'Request Type'

    name = fields.Char(copy=False, required=True)
    code = fields.Char(copy=False, readonly=True)
    description = fields.Text(translate=True)
    help_html = fields.Html(translate=True)
    genre_id = fields.Many2one('getmo.request.genre', index=True)
    sequence_id = fields.Many2one(
        'ir.sequence', 'Sequence', ondelete='restrict', readonly=True,
        help="Use this sequence to generate names for requests for this type")
    category_ids = fields.Many2many(
        'getmo.request.category',
        'request_type_category_rel', 'type_id', 'category_id',
        'Categories', required=False, index=True)
    estimated_duration = fields.Float(
        string='Estimated Duration (hours)',
        default=1.0,
        required=True
    )
    request_ids = fields.One2many(
        'getmo.request.request', 'type_id', 'Requests', readonly=True, copy=False)
    request_count = fields.Integer(
        'All Requests', compute='_compute_request_count', store=True, compute_sudo=True)
    responsible_employees_ids = fields.Many2many('hr.employee', 'hr_employee_request_type_rel',
                                                 string="Employees Responsible For Request Type")
    attachment_setting_state = fields.Selection(
        [('no_attachments', 'No Attachments'), ('single_attachment', 'Single Attachment'),
         ('multiple_attachments', 'Multiple Attachments')], default='no_attachments', string="Attachments State",
        help="This field will determine if service need attachment for workflow.")
    report_needed = fields.Boolean("Is Report Needed ?",
                                   help="This flag will determine if the service will result as report.")
    result_type = fields.Selection([('text', 'Text'), ('attachment', 'Attachment')], default='text',
                                   string="Result Type")
    expected_completion_days = fields.Integer(
        string='Expected Completion Time (days)',
        default=1,
        required=True,
        help="Expected number of days to complete requests of this type"
    )

    @api.depends('request_ids')
    def _compute_request_count(self):
        for rec in self:
            rec.request_count = self.env['getmo.request.request'].search_count([('type_id', '=', rec.id)])

    @api.model
    def create(self, vals):
        # Generate code from name
        if 'name' in vals and not vals.get('code'):
            # Remove special characters and replace spaces with hyphens
            code = re.sub(r'[^a-zA-Z0-9]+', '-', vals['name']).lower()
            code = re.sub(r'-+', '-', code).strip('-')
            vals['code'] = code

            # Create sequence for this request type
            sequence = self.env['ir.sequence'].create({
                'name': f"Request Sequence - {vals['name']}",
                'code': f"request.{code}",
                'prefix': f"{code}-",
                'padding': 4,
                'number_next': 1,
            })
            vals['sequence_id'] = sequence.id

        return super(RequestType, self).create(vals)

    def write(self, vals):
        if 'name' in vals and not vals.get('code'):
            # Similar logic for write if name changes
            for rec in self:
                code = re.sub(r'[^a-zA-Z0-9]+', '-', vals['name']).lower()
                code = re.sub(r'-+', '-', code).strip('-')
                vals['code'] = code

                if rec.sequence_id:
                    # Update existing sequence
                    rec.sequence_id.write({
                        'name': f"Request Sequence - {vals['name']}",
                        'code': f"request.{code}",
                        'prefix': f"{code}-",
                    })
        return super(RequestType, self).write(vals)

    @api.constrains('expected_completion_days')
    def _check_expected_completion_days(self):
        for rec in self:
            if rec.expected_completion_days < 1:
                raise ValidationError(_("Expected completion days must be at least 1."))

    @api.onchange('responsible_employees_ids')
    def _onchange_responsible_employees_ids(self):
        for rec in self:
            if rec.responsible_employees_ids:
                for line in rec.responsible_employees_ids:
                    if line.user_id and not line.user_id.has_group(
                            'master_project_requests.group_request_technician_specialist'):
                        raise ValidationError(
                            "Employee Must Have Group (Requests Technician/Specialist) Before assigning him to A Request Type!.")
