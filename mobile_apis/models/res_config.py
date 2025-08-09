# -*- coding: utf-8 -*-
import secrets
from datetime import datetime, timedelta
from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    sec_token_for_online_requests = fields.Char(
        string="Security Token for Online Services",
        config_parameter='mobile_apis.sec_token_for_online_requests'
    )

    def generate_new_token(self):
        """Generate new token and record update time"""
        token = secrets.token_urlsafe(32)  # 44-char URL-safe token
        self.env['ir.config_parameter'].set_param(
            'mobile_apis.sec_token_for_online_requests',
            token
        )
        return token

    @api.model
    def _cron_rotate_token(self):
        """Cron job to rotate token every 7 days"""
        self.sudo().generate_new_token()
