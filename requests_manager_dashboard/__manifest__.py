# -*- coding: utf-8 -*-
{
    'name': "requests_manager_dashboard",

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
    'depends': ['base', 'master_project_requests'],

    'data': [
        'views/views.xml',
    ],
    "assets": {
        'web.assets_backend': [
            '/requests_manager_dashboard/static/src/libs/Chart.min.js',
            '/requests_manager_dashboard/static/src/libs/high.charts.min.js',
            '/requests_manager_dashboard/static/src/libs/high.charts.min.css',

            '/requests_manager_dashboard/static/src/components/**/*.js',
            '/requests_manager_dashboard/static/src/components/**/*.xml',
            '/requests_manager_dashboard/static/src/components/**/*.css',
        ],
    },
}
