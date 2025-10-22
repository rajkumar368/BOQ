from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class BoqVendor(models.Model):
    _name = 'boq.vendor'
    _description = 'Vendor List'

    code = fields.Char(string='Short Code', required=True)
    name = fields.Char(string='Vendor Name', required=True)


class ResUsers(models.Model):
    _inherit = 'res.users'

    user_type = fields.Selection([
        ('nokia', 'Nokia'),
        ('external', 'External')
    ], string='User Type', default='external')

    vendor_id = fields.Many2one('boq.vendor', string='Vendor')
