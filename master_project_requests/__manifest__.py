# -*- coding: utf-8 -*-
{
    'name': "master_project_requests",

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
    'category': 'Uncategorized',
    'version': '0.1',

    # any module necessary for this one to work correctly
    'depends': ['base', 'bus', 'hr', 'web', 'mail'],

    # always loaded
    'data': [
        'data/data.xml',
        'data/knapsack_cron.xml',

        'security/security_groups.xml',
        'security/ir.model.access.csv',

        'views/request_category_view.xml',
        'views/request_genre_view.xml',
        'views/request_type_stage_view.xml',
        'views/request_type_view.xml',
        'views/request_request_view.xml',
        'views/hr_employee_inherit.xml',
        'views/knapsack_assignment_log_view.xml',
        'views/menus_views.xml',

        'report/employee_request_report.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'master_project_requests/static/src/css/request_form.scss',
            'master_project_requests/static/src/js/services/*.js',
        ]
    }
}
