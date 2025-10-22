from odoo import http, fields
from odoo.http import request
from odoo.exceptions import AccessDenied

class AuthController(http.Controller):

    @http.route('/', auth='public', website=True)
    def boq_home(self, **kw):
        return request.render('BOQ.boq_homepage')

    @http.route('/cboq/login', type='http', auth='public', website=True, methods=['GET', 'POST'])
    def login_cboq(self, **post):
        error = None
        if request.httprequest.method == 'POST':
            username = post.get('username', '').strip()
            password = post.get('password', '').strip()

            if not username or not password:
                error = "Please provide both username and password"

            else:
                nokia_user = request.env['res.users'].sudo().search([
                    ('login', '=', username),
                    ('user_type', '=', 'nokia')
                ], limit=1)

                if not nokia_user:
                    error = "Invalid credentials or user is not a Nokia user"
                else:
                    try:
                        uid = request.session.authenticate(request.session.db, username, password)
                        return request.redirect('/site-config') 
                    except AccessDenied:
                        error = "Invalid credentials"
        return request.render('BOQ.login_template', {'error': error})


    @http.route('/sboq/login', type='http', auth='public', website=True, methods=['GET', 'POST'])
    def login_sboq(self, **post):
        error = None
        if request.httprequest.method == 'POST':
            username = post.get('username', '').strip()
            password = post.get('password', '').strip()

            if not username or not password:
                error = "Please provide both username and password"
            else:
                external_user = request.env['res.users'].sudo().search([
                    ('login', '=', username),
                    ('user_type', '=', 'external')
                ], limit=1)

                if not external_user:
                    error = "Invalid credentials or user is not a Vendor user"
                else:
                    try:
                        uid = request.session.authenticate(request.session.db, username, password)
                        return request.redirect('/sboq-site') 
                    except AccessDenied:
                        error = "Invalid credentials"
        return request.render('BOQ.sboq_login_template', {'error': error})


    @http.route('/logout', type='http', auth='user', website=True)
    def logout_cboq(self, **kwargs):
        request.session.logout()  
        return request.redirect('/cboq/login') 

    
    @http.route('/sboq/logout', type='http', auth='user', website=True)
    def logout_sboq(self, **kwargs):
        request.session.logout()  
        return request.redirect('/sboq/login') 


