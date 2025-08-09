from odoo import http, _
from odoo.http import request
import logging
import base64
from .common import *
import rsa


_logger = logging.getLogger(__name__)

private_key_str = """-----BEGIN RSA PRIVATE KEY-----
MIIEpAIBAAKCAQEAw1ix08k7aIoY+SYNZ4Ip53eTlZC+w7RBTW1pO64+K3YtFdrFWxl3w+RD/EesEmzT6AgWvPbW5fACPUWFh+v3SRlli9qmSLdM1jUeTWZWkeKDGimI561oNFUiu7Wdw3BqjcHxSny/GcD8Cw2Mm0XxoziSyrmJgBN24/q4jKyIAEywTC5JbiofgcV+Vd3HZpJXnBzoXmS1gVxQY3k2yT2GzvdfyZBfrOQLACj6zaPlIBrYJ81SWoWEXf4HLzNLOBXUyAUz6nlwJvPTOrkgQ3O+5tel8LWWMARduCNu1/xmIzZy1U6yQE9iEaGkRI36dWYL4sUXVyl8gc3jzt/9RIk51QIDAQABAoIBADKLmRu5Jm+SyApzn6VIR0p2pM/e75VY50q/BCsmlzyMq/bLMCS1zsj3n+W/r9TmpuATc7q6TfmaJCIxgm8cjdQyx5Ur4rnPAAkvHmOdlsnRp+WVmLCFrIBaBQ433JXs2Q1MAQCqjZH+3tiHTXoB25fFtCnTXzIuFyW/QpBXtisJOIMMWNZwjf/ZWP+n184jczditLRLB/mXsasojRCDqab0l82wt7l6qIESS9+Iu74TqyF+cYIb6KjZxnvi8NVLeoEpdIR4zo7wDy5dLyBfBF7hNCbkJAq5XfbFzcFrlhj5jqMPNJmNd0Q0xHYMag8bvXf1SmcKUk7XCafsMzGF9uMCgYEA95aPlwx8eQLykkKANDQniaJHd2WR5ew5JAJeJca4hvU3S1Ok0fA9cNBVfVRU/vBo1PM90Xurjc0mxuDaAPbdLryixuKwVJAM+kNXkagObN+IPsb3HyqhTvHR/nSh2sHpmLK8Ho0RCInHsXp9fnf0Yrug7vEEPRcSCLzqg3By/acCgYEAyfvAzTn52eiAjr+mYPahhjeE/YdPEQ/ikExUXLILOl7iGopOxvE/vfow6JQ5SMUN+Fky5LvGmvS2j+SH0mg54ctn5UxdR7SaOwzEdG3Btx3g330iDOjJskiRNsqULtCHhAHkENjHuUFhTTpifLyo/Q59/+PSLmDFvIulnQH0lCMCgYEAy74XnbqFt+OIEHovHEaK/sUPQJ7R6D5za0GTjkywz0Z94TwM10J2nR6kK0W5yC24Zv1gMsItk7xuG50vaTm9HFfZMAeeCYidVVkTd+avMELm0JpVBE3FfrybDWWXR/jpLWJwUkfN65PORCvDl85IyvMSZW7rCQayLYShC9b+meMCgYBvC/E5I5nA+vnLAYT4pD+zqcx9EqoeqEwYp05uVBimM8o9azLaX4J68RV4mR1Ra709f9TiOnZ7dPT18V/XByRjhlANmcljBeERe/h6RmmNQmkCliplTIqvcQQdSozjnBQVOHDp7jUIHfDf46yIBbUmw5P0Xo2Mn/m2qlQYGR4dXwKBgQDifuunIrTk4sXJiWtsbTqXmWDTQ4wTXTCtB/hk3FCdpkYkMY4oix02PaEcS2al9j4hi07e/OlSMNb4Ht51KbIGfMPhtvGn1KOchj2IL6QGgS00kvz+Q2/hD6hjFOjdZMxDDyJ5LukBlPgIrpMPbr6sTkTcQVQ1oItmULzwGlNzzw==
-----END RSA PRIVATE KEY-----"""
sec_token_param = 'mobile_apis.sec_token_for_online_requests'

class UserLogin(http.Controller):
    @http.route('/api/user/login', csrf=False, auth='none', type='json', methods=['POST'], cors='*')
    def api_login(self, **kw):
        username = kw.get('username')
        password = kw.get('password')
        if not username:
            return bad_params_template("user name", {})
        elif not password:
            return bad_params_template("password", {})
        try:
            private_key = rsa.PrivateKey.load_pkcs1(private_key_str)
            encrypted_message = base64.b64decode(password)
            decrypted_message = rsa.decrypt(encrypted_message, private_key)
            uid = request.session.authenticate(request.session.db, username, decrypted_message)
            if not uid:
                return auth_failed_template({})

            user = request.env['res.users'].sudo().search([('id', '=', uid)], limit=1)
            if not user:
                return auth_failed_template({})
            sec_token_for_online_requests = request.env['ir.config_parameter'].sudo().get_param(sec_token_param)
            data = {
                "user_id": user.id,
                "sec_token_for_online_requests": sec_token_for_online_requests,
            }

            return success_template(data)
        except Exception as EX:
            return error_template(str(EX))
