# -*- coding: utf-8 -*-
{
    'name': "mobile_apis",

    'summary': """
        Short (1 phrase/line) summary of the module's purpose, used as
        subtitle on modules listing or apps.openerp.com""",

    'description': """
        Long description of module's purpose
    """,

    'author': "My Company",
    'website': "https://www.yourcompany.com",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/16.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'category': 'Mixins',
    'version': '1.0.0',

    # any module necessary for this one to work correctly
    'depends': ['base', 'master_project_requests'],

    # always loaded
    'data': [
        'data/token_cron.xml',
        'views/res_config_setting_view.xml'
    ],
}
