from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
import re

class SboqSOR(models.Model):
    _name = 'sboq.sor'
    _description = 'SBOQ SOR'

    item_code = fields.Char(required=True)
    description = fields.Text()
    cost_type = fields.Char()           
    uom = fields.Char()
    qty = fields.Float(string='Quantity', default=1)
    unit_price  = fields.Float(string='Unit Price', default=0.0)
    total_price = fields.Float(compute='_compute_total', store=True)
    subcon = fields.Char()    
    category = fields.Char()
    vendor_id = fields.Many2one(
        'boq.vendor',
        string='Vendor',
    )


    @api.depends('qty', 'unit_price')
    def _compute_total(self):
        for rec in self:
            rec.total_price = rec.qty * rec.unit_price

class SboqNonSor(models.Model):
    _name = 'sboq.non.sor'
    _description = 'SBOQ NON SOR'
    category_id = fields.Many2one('sboq.category')
    subcategory_id = fields.Many2one('sboq.subcategory', string='Sub-Category')
    description = fields.Text()
    cost_type = fields.Char()              
    uom = fields.Char()
    qty = fields.Float(string='Quantity', default=1)
    unit_price  = fields.Float(string='Unit Price', default=0.0)
    total_price = fields.Float(compute='_compute_total', store=True)


class Sboq(models.Model):
    _name = 'sboq'
    _description = 'SBOQ Version Node (tree)'

    master_boq_id = fields.Many2one('boq.master', ondelete='cascade')
    name = fields.Char(string='SBOQ #', readonly=True, copy=False)
    site_id = fields.Many2one('boq.sitelist', required=True)
    cboq_id = fields.Many2one('cboq', string='Source CBOQ', required=False)
    is_main = fields.Boolean(string='Is Base SBOQ', default=False)
    parent_sboq_id = fields.Many2one('sboq', string='Main SBOQ (if variation)',domain="[('is_main', '=', True), ('site_id', '=', site_id), ('vendor_id', '=', vendor_id)]")
    variation_ids = fields.One2many('sboq', 'parent_sboq_id', string='Variation SBOQs')

    # version = fields.Integer(default=1, readonly=True, help="Human-friendly 1,2,3…")
    
    main_version = fields.Integer(string='Main Version', default=1, readonly=True)
    variation_index = fields.Integer(string='Variation #', default=0, readonly=True)
    version_label = fields.Char(string="Version Label", compute='_compute_version_label', store=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('submitted', 'Submitted SD10'),
        ('resubmitted', 'Resubmitted'),
        ('rejected', 'Rejected'),
        ('approved', 'Approved'),
    ], default='draft', tracking=True)
    rejection_type = fields.Selection([('minor', 'Minor'), ('major', 'Major')])
    rejection_note = fields.Text()

    reviewed_by_id = fields.Many2one('res.users', string='Nokia PM')
    reviewed_date  = fields.Datetime()
    approval_note  = fields.Text()

    total_amount = fields.Monetary(compute='_compute_total', store=True)
    currency_id = fields.Many2one('res.currency', default=lambda self: self.env.company.currency_id)
    line_ids = fields.One2many('sboq.line', 'sboq_id', string='Delta Lines')
    is_resubmitted = fields.Boolean(string='Is Resubmitted', default=False, help="True if this SBOQ is a resubmission")
    is_pending_review = fields.Boolean(
        compute='_compute_is_pending_review',
        string='Pending Review',
        store=True,
        help='Indicates if this SBOQ is awaiting review (submitted or resubmitted)'
    )

    @api.depends('main_version', 'variation_index')
    def _compute_version_label(self):
        for sboq in self:
            if sboq.variation_index:
                sboq.version_label = f"V{sboq.main_version}.{sboq.variation_index}"
            else:
                sboq.version_label = f"V{sboq.main_version}"

    @api.model
    def create(self, vals):
        is_main = vals.get('is_main', True)
        site_id = vals.get('site_id')
        state = vals.get('state')
        create_uid = self.env.uid

        if state == 'rejected':
            rejection_type = vals.get('rejection_type')
            main_version = vals.get('main_version')
            variation_index = vals.get('variation_index')
            parent_id = vals.get('parent_sboq_id')
            if rejection_type == 'major':
                max_main_version = self.env['sboq'].search([
                    ('site_id', '=', site_id),
                    ('create_uid', '=', create_uid)
                ]).mapped('main_version')
                print(max_main_version)
                max_main_version = max(max_main_version or [0])
                vals['main_version'] = max_main_version + 1
                vals['variation_index'] = 0
                vals['parent_sboq_id'] = False
                vals['is_main'] = True

            else:
                vals['main_version'] = main_version
                vals['variation_index'] = variation_index+1
                vals['is_main'] = False

            vals['state'] = 'resubmitted'
            vals.pop('rejection_type', None)

            site = self.env['boq.sitelist'].browse(site_id)
            site_id_part = site.site_id if site else 'NoSiteID'
            site_name_part = site.site_name if site else 'NoSiteName'
            print("from model")
            print(vals['is_main'])
            print(vals.get('parent_sboq_id'))
            print("Done from end")

            if vals['is_main']:
                version_str = f"V{vals['main_version']}"
            else:
                version_str = f"V{vals['main_version']}.{vals['variation_index']}"

            vals['name'] = f"{site_id_part}_{site_name_part}_{version_str}"
            return super().create(vals)

        elif state == "approved":
            main_version = vals.get('main_version')
            variation_index = vals.get('variation_index')
            parent_id = vals.get('parent_sboq_id')
            if rejection_type == 'major':
                vals['main_version'] = main_version
                vals['variation_index'] = variation_index+1
                vals['is_main'] = False

            vals['state'] = 'resubmitted'
            vals.pop('rejection_type', None)

            site = self.env['boq.sitelist'].browse(site_id)
            site_id_part = site.site_id if site else 'NoSiteID'
            site_name_part = site.site_name if site else 'NoSiteName'

            if vals['is_main']:
                version_str = f"V{vals['main_version']}"
            else:
                version_str = f"V{vals['main_version']}.{vals['variation_index']}"

            vals['name'] = f"{site_id_part}_{site_name_part}_{version_str}"
            return super().create(vals)
            
        else:
            # Default versioning
            main_version = 1
            variation_index = 0

            if is_main:
                # Get max main_version for this site + config
                existing_main = self.search([
                    ('site_id', '=', site_id),
                    ('create_uid', '=', self.env.uid),
                    ('is_main', '=', True)
                ])
                if existing_main:
                    main_version = max(existing_main.mapped('main_version') or [0]) + 1
            else:
                parent_id = vals.get('parent_sboq_id')
                parent = self.env['sboq'].browse(parent_id)
                main_version = parent.main_version
                # Get next variation index under same main_version
                variations = self.search([
                    ('parent_sboq_id', '=', parent_id)
                ])
                variation_index = max(variations.mapped('variation_index') or [0]) + 1

            # Set version values
            vals['main_version'] = main_version
            vals['variation_index'] = variation_index

            # Generate name like "SiteID_SiteName_V1" or "V1.1"
            site = self.env['boq.sitelist'].browse(site_id)
            site_id_part = site.site_id if site else 'NoSiteID'
            site_name_part = site.site_name if site else 'NoSiteName'

            if is_main or not vals.get('parent_sboq_id'):
                version_str = f"V{main_version}"
            else:
                version_str = f"V{main_version}.{variation_index}"

            vals['name'] = f"{site_id_part}_{site_name_part}_{version_str}"
            return super().create(vals)


    @api.depends('state')
    def _compute_is_pending_review(self):
        for rec in self:
            rec.is_pending_review = rec.state in ['submitted', 'resubmitted']

    @api.depends('line_ids.total_price')
    def _compute_total(self):
        for rec in self:
            rec.total_amount = sum(rec.line_ids.mapped('total_price'))

    def action_approve(self, approval_note):
        """
        Approve the SBOQ with a note.
        Call this from a wizard or button with the note as input.
        """
        # if not self.env.user.has_group('your_module.group_nokia_user'):  # Replace 'your_module' with your actual module name
        #     raise ValidationError(_("Only Nokia users can approve SBOQs."))
        
        if not self.is_pending_review:
            raise ValidationError(_("Only pending reviews can be approved."))
        
        self.write({
            'state': 'approved',
            'approval_note': approval_note or '',
            'reviewed_by_id': self.env.user.id,
            'reviewed_date': fields.Datetime.now(),
        })
        # self.message_post(body=_("SBOQ approved by %s with note: %s") % (self.env.user.name, approval_note))

    def action_reject(self, rejection_type, rejection_note):
        """
        Reject the SBOQ with type and note.
        Call this from a wizard or button with inputs.
        """
        # if not self.env.user.has_group('your_module.group_nokia_user'):  # Replace 'your_module' with your actual module name
        #     raise ValidationError(_("Only Nokia users can reject SBOQs."))
        
        if not self.is_pending_review:
            raise ValidationError(_("Only pending reviews can be rejected."))
        
        self.write({
            'state': 'rejected',
            'rejection_type': rejection_type,
            'rejection_note': rejection_note or '',
            'reviewed_by_id': self.env.user.id,
            'reviewed_date': fields.Datetime.now(),
        })
        # self.message_post(body=_("SBOQ rejected by %s (%s) with note: %s") % (self.env.user.name, rejection_type, rejection_note))



class SboqCategory(models.Model):
    _name = 'sboq.category'
    _description = 'Category (parent)'

    name = fields.Char(required=True)

class SboqSubCategory(models.Model):
    _name = 'sboq.subcategory'
    _description = 'Sub-Category (user extendable)'

    name = fields.Char(required=True)
    category_id = fields.Many2one('sboq.category', required=True)
    _sql_constraints = [('uniq_per_cat', 'unique(name,category_id)', 'Duplicate sub-category.')]


class SboqLine(models.Model):
    _name = 'sboq.line'
    _description = 'SBOQ Delta Line (stores only changes)'

    sboq_id = fields.Many2one('sboq', required=True, ondelete='cascade')
    source_type = fields.Selection([('sor','SOR'),('non_sor','Non-SOR')], required=True)
    sboq_sor_id  = fields.Many2one('sboq.sor', ondelete='restrict')
    sboq_non_sor_id = fields.Many2one('sboq.non.sor', ondelete='restrict')
    description   = fields.Text(compute='_compute_item_field', store=True)
    cost_type     = fields.Char(compute='_compute_item_field', store=True)
    uom           = fields.Char(compute='_compute_item_field', store=True)
    qty        = fields.Float(string='Qty', default=1)
    unit_price = fields.Float(string='Unit Price')
    markup = fields.Float(default=1.0)
    total_price = fields.Float(string='Total', compute='_compute_total', store=True)

    @api.depends('source_type', 'sboq_sor_id', 'sboq_non_sor_id')
    def _compute_item_field(self):
        for rec in self:
            src = None
            if rec.source_type == 'sor' and rec.sboq_sor_id:
                src = rec.sboq_sor_id
            elif rec.source_type == 'non_sor' and rec.sboq_non_sor_id:
                src = rec.sboq_non_sor_id

            if src:
                rec.description = src.description or ''
                rec.uom = src.uom or ''
                rec.cost_type = src.cost_type or ''
            else:
                rec.description = ''
                rec.uom = ''
                rec.cost_type = ''

    @api.depends('qty', 'markup', 'unit_price', 'sboq_sor_id.cost_type')
    def _compute_total(self):
        for rec in self:
            if rec.source_type == 'sor' and rec.sboq_sor_id:
                cost_type = re.sub(r'\s+', '', rec.sboq_sor_id.cost_type or 'NA')
                rec.markup = 1.10 if cost_type in ['CostPlus', 'FIM', 'Passthrough', 'Passthrough+x%'] else 1.0
            else:
                rec.markup = 1.0
            rec.total_price = rec.qty * rec.unit_price * rec.markup

    
