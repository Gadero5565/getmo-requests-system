from odoo import models, fields, api


class AlgorithmLog(models.Model):
    _name = 'getmo.algorithm.log'
    _description = 'Algorithm Log'

    name = fields.Char(default='Algorithm Log', readonly=True)
    timestamp = fields.Datetime(default=fields.Datetime.now, readonly=True)
    steps = fields.Text(string='Algorithm Steps', readonly=True)
    mermaid_flow = fields.Text(string='Mermaid Flowchart', readonly=True)
