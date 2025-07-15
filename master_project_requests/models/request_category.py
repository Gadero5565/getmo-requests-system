import re

from odoo import models, fields, api


class RequestCategory(models.Model):
    _name = 'getmo.request.category'
    _description = 'Request Category'

    name = fields.Char()
    code = fields.Char()
    description = fields.Text(translate=True)
    help_html = fields.Html(translate=True)
    request_ids = fields.One2many(
        'getmo.request.request', 'category_id', 'Requests', readonly=True)
    request_count = fields.Integer(
        'All Requests', compute='_compute_request_count', store=True, compute_sudo=True)
    request_type_ids = fields.Many2many(
        'getmo.request.type',
        'request_type_category_rel', 'category_id', 'type_id',
        string="Request types")
    request_type_count = fields.Integer(
        compute='_compute_request_type_count', store=True, compute_sudo=True)
    sequence = fields.Integer(index=True, default=5)
    category_manager_id = fields.Many2one('hr.employee', 'Manager', required=True,
                                          help="This field defines who can assign requests to responsible employees and follow them")

    @api.depends('request_ids')
    def _compute_request_count(self):
        for rec in self:
            rec.request_count = self.env['getmo.request.request'].search_count([('category_id', '=', rec.id)])

    @api.depends('request_type_ids')
    def _compute_request_type_count(self):
        for rec in self:
            rec.request_type_count = self.env['getmo.request.type'].search_count([('category_ids', 'in', rec.id)])

    @api.model
    def create(self, vals):
        # Generate code from name
        if 'name' in vals and not vals.get('code'):
            # Remove special characters and replace spaces with hyphens
            code = re.sub(r'[^a-zA-Z0-9]+', '-', vals['name']).lower()
            code = re.sub(r'-+', '-', code).strip('-')
            vals['code'] = code
        return super(RequestCategory, self).create(vals)

    def write(self, vals):
        if 'name' in vals and not vals.get('code'):
            # Similar logic for write if name changes
            for rec in self:
                code = re.sub(r'[^a-zA-Z0-9]+', '-', vals['name']).lower()
                code = re.sub(r'-+', '-', code).strip('-')
                vals['code'] = code
        return super(RequestCategory, self).write(vals)
