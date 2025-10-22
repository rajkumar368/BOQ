from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

class BoqMaster(models.Model):
    _name = 'boq.master'
    _description = 'Master BOQ – Site-level tracker'

    site_id = fields.Char(string='Site', required=True)
    cboq_ids = fields.One2many('cboq', 'master_boq_id', string='CBOQs')
    sboq_ids = fields.One2many('sboq', 'master_boq_id', string='All SBOQs')

    @api.depends('cboq_ids', 'sboq_ids')
    def _compute_counts(self):
        for rec in self:
            rec.cboq_count = len(rec.cboq_ids)
            rec.sboq_count = len(rec.sboq_ids)

class BoqSiteList(models.Model):
    _name = 'boq.sitelist'
    _description = 'Site'

    site_id   = fields.Char(string='Site ID',   required=True)
    site_name = fields.Char(string='Site Name', required=True)
    smp_name  = fields.Char(string='SMP Name',  required=True)
    program   = fields.Char(string='Program',   required=True)
    phase     = fields.Char(string='Phase',     required=True)


class CboqConfigVersion(models.Model):
    _name = 'cboq.config.version'
    _description = '5G Configuration Version'

    config_versioned = fields.Char(string='Config Version', required=True)
    name             = fields.Char(string='Config Name')
    description      = fields.Text(string='Technical Scope')
    line_ids         = fields.One2many('cboq.config.line', 'config_version_id', string='Lines')


class CboqSOR(models.Model):
    """Static catalogue."""
    _name = 'cboq.sor'
    _description = 'CBOQ (SOR)'

    category      = fields.Char()
    customer_code = fields.Char()
    supplier_code = fields.Char()
    description   = fields.Text()
    uom           = fields.Char(string='UoM')
    cost_type     = fields.Char()
    unit_price    = fields.Float(string='Unit Price', default=0.0)
    unit_sales_rate = fields.Float(string='Unit Sales Rate', default=0.0)
    qty = fields.Float(string='Quantity', default=0)
    item_code = fields.Char(string='Internal Item Code')


class CboqConfigLine(models.Model):
    """Static template – NO relation to ItemCode."""
    _name = 'cboq.config.line'
    _description = 'Config Line (Static)'

    config_version_id = fields.Many2one('cboq.config.version', required=True, ondelete='cascade')
    category      = fields.Char()
    customer_code = fields.Char()
    supplier_code = fields.Char()
    description   = fields.Text()
    uom           = fields.Char(string='UoM')
    cost_type     = fields.Char()
    qty       = fields.Float(string='Qty')
    unit_price    = fields.Float(string='Unit Price')


class Cboq(models.Model):
    """CBOQ header – versioned & status-tracked."""
    _name = 'cboq'
    _description = 'CBOQ (SD4) – Nokia Quote'

    master_boq_id = fields.Many2one('boq.master', ondelete='cascade')
    name = fields.Char(string='CBOQ #', default='New', readonly=True, copy=False)
    site_id = fields.Many2one('boq.sitelist', string='Site', required=True)
    config_version_id = fields.Many2one('cboq.config.version', string='Config Version', required=True)
    is_main = fields.Boolean(string='Is Main CBOQ', default=False)
    parent_cboq_id = fields.Many2one('cboq', string='Main CBOQ (if variation)', domain="[('is_main', '=', True), ('site_id', '=', site_id)]")
    variation_ids = fields.One2many('cboq', 'parent_cboq_id', string='Variations')
    # version = fields.Integer(string='Version', default=1, readonly=True)
    main_version = fields.Integer(string='Main Version', default=1, readonly=True)
    variation_index = fields.Integer(string='Variation #', default=0, readonly=True)
    version_label = fields.Char(string="Version Label", compute='_compute_version_label', store=True)
    status = fields.Selection([
        ('draft',     'Draft'),
        ('submitted', 'SD4 Submitted'),
        ('approved',  'Approved'),
        ('rejected',  'Rejected'),
    ], default='draft', tracking=True)
    line_ids = fields.One2many('cboq.line', 'cboq_id', string='CBOQ Lines')
    total_amount = fields.Float(string='Total')
    total_sor = fields.Float(string='Total SOR', compute='_compute_totals', store=True)
    total_config = fields.Float(string='Total Config', compute='_compute_totals', store=True)

    @api.depends('main_version', 'variation_index')
    def _compute_version_label(self):
        for cboq in self:
            if cboq.variation_index:
                cboq.version_label = f"V{cboq.main_version}.{cboq.variation_index}"
            else:
                cboq.version_label = f"V{cboq.main_version}"

    @api.depends('line_ids.source_type', 'line_ids.total_price')
    def _compute_totals(self):
        for cboq in self:
            total_sor = sum(line.total_price for line in cboq.line_ids if line.source_type == 'item')
            total_config = sum(line.total_price for line in cboq.line_ids if line.source_type == 'config')
            cboq.total_sor = total_sor
            cboq.total_config = total_config

    @api.model
    def create(self, vals):
        is_main = vals.get('is_main', True)
        site_id = vals.get('site_id')
        config_version_id = vals.get('config_version_id')

        # Default versioning
        main_version = 1
        variation_index = 0

        if is_main:
            # Get max main_version for this site + config
            existing_main = self.search([
                ('site_id', '=', site_id),
                ('config_version_id', '=', config_version_id),
                ('is_main', '=', True)
            ])
            if existing_main:
                main_version = max(existing_main.mapped('main_version') or [0]) + 1
        else:
            parent_id = vals.get('parent_cboq_id')
            parent = self.env['cboq'].browse(parent_id)
            main_version = parent.main_version
            # Get next variation index under same main_version
            variations = self.search([
                ('parent_cboq_id', '=', parent_id)
            ])
            variation_index = max(variations.mapped('variation_index') or [0]) + 1

        # Set version values
        vals['main_version'] = main_version
        vals['variation_index'] = variation_index

        # Generate name like "SiteID_SiteName_V1" or "V1.1"
        site = self.env['boq.sitelist'].browse(site_id)
        site_id_part = site.site_id if site else 'NoSiteID'
        site_name_part = site.site_name if site else 'NoSiteName'

        if is_main or not vals.get('parent_cboq_id'):
            version_str = f"V{main_version}"
        else:
            version_str = f"V{main_version}.{variation_index}"

        vals['name'] = f"{site_id_part}_{site_name_part}_{version_str}"

        return super().create(vals)


    # --------------- actions -----------------
    def action_load_config_lines(self):
        """Auto-pull every ConfigLine of the selected ConfigVersion."""
        self.ensure_one()
        self.line_ids.unlink()
        for cfg in self.config_version_id.line_ids:
            self.env['cboq.line'].create({
                'cboq_id': self.id,
                'source_type': 'config',
                'config_line_id': cfg.id,
                'qty': cfg.qty_std,
                'unit_price': cfg.unit_price,
            })


class CboqLine(models.Model):
    """Editable snapshot – can reference ItemCode OR ConfigLine."""
    _name = 'cboq.line'
    _description = 'CBOQ Line'

    cboq_id = fields.Many2one('cboq', required=True, ondelete='cascade')

    # which static row is the source?
    source_type = fields.Selection(
        [('item', 'Item'), ('config', 'Config Line')],
        required=True,
        default='item'
    )
    item_id        = fields.Many2one('cboq.sor', ondelete='restrict')
    config_line_id = fields.Many2one('cboq.config.line', ondelete='restrict')

    # editable overrides
    qty        = fields.Float(string='Qty', default=1)
    unit_price = fields.Float(string='Unit Price')

    # read-only helpers
    category      = fields.Char(compute='_compute_item_field')
    customer_code = fields.Char(compute='_compute_item_field')
    supplier_code = fields.Char(compute='_compute_item_field')
    description   = fields.Text(compute='_compute_item_field')
    uom           = fields.Char(compute='_compute_item_field')
    cost_type     = fields.Char(compute='_compute_item_field')

    total_price = fields.Float(
        string='Total', compute='_compute_total', store=True
    )

    # ---- helpers ----
    @api.constrains('source_type', 'item_id', 'config_line_id')
    def _check_source(self):
        for rec in self:
            if rec.source_type == 'item' and not rec.item_id:
                raise ValidationError(_("Please select an Item."))
            if rec.source_type == 'config' and not rec.config_line_id:
                raise ValidationError(_("Please select a Config Line."))

    @api.depends('source_type', 'item_id', 'config_line_id')
    def _compute_item_field(self):
        for rec in self:
            src = rec.item_id if rec.source_type == 'item' else rec.config_line_id
            rec.category      = src.category
            rec.customer_code = src.customer_code
            rec.supplier_code = src.supplier_code
            rec.description   = src.description
            rec.uom           = src.uom
            rec.cost_type     = src.cost_type

    @api.depends('qty', 'unit_price')
    def _compute_total(self):
        for rec in self:
            rec.total_price = rec.qty * rec.unit_price
