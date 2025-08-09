from odoo.http import request

def empty_response():
    return {
        "status": "success",
        "type": "emptyResponse",
        "msg": f"There is no matching data",
        "data": [],
    }

def bad_params_template(param_name,data=[]):
    return {
        "status": "failure",
        "type": "badParams",
        "msg": f"Make sure the {param_name} parameter is sent appropriately.",
        "data": data,
    }

def error_template(error_string):
    return {
        "status": "failure",
        "type": "somethingWentWrong",
        "msg": error_string,
        "data": {},
    }

def success_template(data):
    return {
        "status": "success",
        "type": "calledSuccessfully",
        "msg": 'Operation accomplished successfully',
        "data": data,
    }

def auth_failed_template(data=[]):
    return {
        "status": "failure",
        "type": "authFailure",
        "msg": 'Invalid credentials',
        "data": data,
    }

def invalid_sec_token():
    return {
        "status": "error",
        "type": "unauthorized",
        "msg": "Invalid security token",
        "data": []
    }

def process_image_url(record_id, model_name, image_field=None):
    """Generate proper image URL for any model"""
    web_base_url = request.env['ir.config_parameter'].sudo().get_param('web.base.url')
    if image_field:
        return f'{web_base_url}web/image/{model_name}/{record_id or 0}/{image_field}'
    else:
        return f'{web_base_url}web/image/{model_name}/{record_id or 0}/image_1920'