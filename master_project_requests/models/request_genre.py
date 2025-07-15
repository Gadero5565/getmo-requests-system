from odoo import models, fields, api
import re


class RequestGenre(models.Model):
    _name = 'getmo.request.genre'
    _description = 'Request Genre'

    name = fields.Char(string='Genre')
    code = fields.Char()

    description = fields.Text(translate=True)
    help_html = fields.Html(translate=True)
    request_type_ids = fields.One2many(
        'getmo.request.type', 'genre_id', string='Request Types')
    request_type_count = fields.Integer(
        compute='_compute_request_type_count', store=True, compute_sudo=True)
    request_ids = fields.One2many(
        'getmo.request.request', 'genre_id', string='Requests')
    request_count = fields.Integer(
        compute='_compute_request_count', store=True, compute_sudo=True)

    sequence = fields.Integer(index=True, default=5)

    @api.depends('request_type_ids')
    def _compute_request_type_count(self):
        for rec in self:
            rec.request_type_count = self.env['getmo.request.type'].search_count([('genre_id', '=', rec.id)])

    @api.depends('request_ids')
    def _compute_request_count(self):
        for rec in self:
            rec.request_count = self.env['getmo.request.request'].search_count([('genre_id', '=', rec.id)])

    @api.model
    def create(self, vals):
        # Generate code from name
        if 'name' in vals and not vals.get('code'):
            # Remove special characters and replace spaces with hyphens
            code = re.sub(r'[^a-zA-Z0-9]+', '-', vals['name']).lower()
            code = re.sub(r'-+', '-', code).strip('-')
            vals['code'] = code
        return super(RequestGenre, self).create(vals)

    def write(self, vals):
        if 'name' in vals and not vals.get('code'):
            # Similar logic for write if name changes
            for rec in self:
                code = re.sub(r'[^a-zA-Z0-9]+', '-', vals['name']).lower()
                code = re.sub(r'-+', '-', code).strip('-')
                vals['code'] = code
        return super(RequestGenre, self).write(vals)
