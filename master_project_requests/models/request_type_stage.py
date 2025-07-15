import re
from odoo import models, fields, api


class RequestTypeStage(models.Model):
    _name = 'getmo.request.type.stage'
    _description = 'Request Stage per Type'
    _order = 'sequence, id'

    name = fields.Char('Stage', required=True)
    code = fields.Char("Code")
    sequence = fields.Integer('Sequence', default=10)
    stage_type = fields.Selection(
        [('draft', 'Draft'), ('assigned', 'Assigned'), ('in_progress', 'In Progress'), ('done', 'Done'),
         ('refused', 'Refused')], default='draft',
        string="Stage Type")
    fold = fields.Boolean(
        string="Folded in Kanban",
        help="This stage is folded in the kanban view "
             "when there are no records in that stage "
             "to display.",
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if 'name' in vals and not vals.get('code'):
                vals['code'] = self._generate_stage_code(vals['name'])
        return super().create(vals_list)

    def write(self, vals):
        if 'name' in vals and not vals.get('code'):
            vals['code'] = self._generate_stage_code(vals['name'])
        return super().write(vals)

    @api.model
    def _generate_stage_code(self, name):
        """Generate a standardized code from the stage name"""
        if not name:
            return ''

        # Convert to lowercase
        code = name.lower()
        # Replace spaces with hyphens
        code = re.sub(r'\s+', '-', code)
        # Remove all special characters except hyphens and underscores
        code = re.sub(r'[^a-z0-9_-]', '', code)
        # Remove leading/trailing hyphens/underscores
        code = code.strip('-_')
        # Replace multiple hyphens/underscores with single hyphen
        code = re.sub(r'[-_]+', '-', code)

        return code
