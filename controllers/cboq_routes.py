from odoo import http
from odoo.http import request
from io import BytesIO
import xlsxwriter
import json


class CboqRoutes(http.Controller):

    @http.route('/site-config', auth='user', website=True)
    def site_config_page(self, **kw):
        configs = request.env['cboq.config.version'].search([])
        return request.render('BOQ.site_config_template',
                              {'config_versions': configs})


    @http.route('/site-config/search_site', type='http', auth='user', csrf=False)
    def search_site(self, term, **kw):
        domain = ['|', ('site_id', 'ilike', term),
                       ('site_name', 'ilike', term)]
        sites = request.env['boq.sitelist'].search(domain, limit=20)
        payload = [
            {"label": f"{s.site_id}_{s.site_name}",
             "value": f"{s.site_id}_{s.site_name}",
             "id":    s.id}
            for s in sites
        ]
        return json.dumps(payload)

    
    @http.route('/site-config/lines/<int:config_id>', type='http', auth='user')
    def get_lines(self, config_id):
        lines = request.env['cboq.config.line'].search(
            [('config_version_id', '=', config_id)])
        return json.dumps([{
            'category':  l.category,
            'customer_code': l.customer_code,
            'supplier_code': l.supplier_code,
            'description':   l.description,
            'uom':           l.uom,
            'cost_type':     l.cost_type,
            'qty':           l.qty,
            'unit_price':    l.unit_price,
        } for l in lines])


    @http.route('/create-cboq', auth='user', website=True)
    def create_cboq_page(self, **kw):
        site_id = int(kw.get('site_id', 0))
        config_id = int(kw.get('config_id', 0))

        draft_cboq = request.env['cboq'].search([
            ('site_id', '=', site_id),
            ('config_version_id', '=', config_id),
            ('status', '=', 'draft')
        ], limit=1)


        approved_main_cboq = request.env['cboq'].search([
            ('site_id', '=', site_id),
            ('config_version_id', '=', config_id),
            ('is_main', '=', True),
            ('status', 'in', ['approved', 'submitted']),
        ], limit=1)

        is_main = not bool(approved_main_cboq)
        parent_id = approved_main_cboq.id if approved_main_cboq else None

        # Fetch SOR and Config items
        sor_items = request.env['cboq.sor'].search([])
        config_items = request.env['cboq.config.line'].search([('config_version_id', '=', config_id)])

        # Prepare draft data if available
        draft_data = {
            'sor_lines': [],
            'config_lines': []
        }
        if draft_cboq:
            for line in draft_cboq.line_ids:
                if line.item_id:
                    draft_data['sor_lines'].append({
                        'item_id': line.item_id.id,
                        'qty': line.qty,
                        'unit_price': line.unit_price
                    })
                elif line.config_line_id:
                    draft_data['config_lines'].append({
                        'config_line_id': line.config_line_id.id,
                        'qty': line.qty,
                        'unit_price': line.unit_price
                    })

        return request.render('BOQ.create_cboq_template', {
            'site_id': site_id,
            'config_id': config_id,
            'site_name': request.env['boq.sitelist'].browse(site_id).display_name,
            'config_name': request.env['cboq.config.version'].browse(config_id).config_versioned,
            'sor_items': sor_items,
            'config_items': config_items,
            'draft_data': draft_data,
            'is_main': is_main,
            'parent_id': parent_id
        })



    @http.route('/create-cboq/save-draft', type='http',auth='user', methods=['POST'], csrf=False)
    def save_cboq_draft(self, **kw):
        data = json.loads(request.httprequest.data)
        site_id           = int(data['site_id'])
        config_version_id = int(data['config_version_id'])
        lines             = data['lines']
        is_main = data.get('is_main', True)
        if isinstance(is_main, str):
            is_main = is_main.lower() in ['true', '1']
        parent_id = int(data.get('parent_id') or 0)
        print("************")
        print(is_main)
        print(parent_id)
        print("************")

        site = request.env['boq.sitelist'].sudo().browse(site_id)
        parent_cboq = None
        if not is_main:
            parent_cboq = request.env['cboq'].browse(parent_id)
            if parent_cboq.status != 'approved':
                return json.dumps({'status': 'error', 'message': 'Unapproved main CBOQ.'})


        master_boq = request.env['boq.master'].search([('site_id', '=', site.site_id)], limit=1)
        if not master_boq:
            master_boq = request.env['boq.master'].sudo().create({'site_id': site.site_id})
            request.env.cr.commit()
            print(master_boq)

        print('master boq done')
        domain = [('site_id', '=', site_id), ('config_version_id', '=', config_version_id), ('status', '=', 'draft')]
        if is_main:
            domain += [('is_main', '=', True)]
        else:
            domain += [('parent_cboq_id', '=', parent_id)]

        draft = request.env['cboq'].search(domain, limit=1)
        print(draft)


        # existing = request.env['cboq'].search([
        #     ('site_id', '=', site_id),
        #     ('config_version_id', '=', config_version_id)
        # ])

        # draft = existing.filtered(lambda r: r.status == 'draft')[:1]
        if is_main:
            approved_main = request.env['cboq'].search([
                ('site_id', '=', site_id),
                ('config_version_id', '=', config_version_id),
                ('is_main', '=', True),
                ('status', '=', 'approved')
            ], limit=1)
            if approved_main:
                return json.dumps({'status': 'error', 'message': 'Main CBOQ already approved for this site/config.'})


        if draft:
            draft.line_ids.unlink()
            cboq = draft
        else:
            cboq = request.env['cboq'].create({
                'master_boq_id': master_boq.id,
                'site_id': site_id,
                'config_version_id': config_version_id,
                'status': 'draft',
                'is_main': is_main,
                'parent_cboq_id': parent_id if not is_main else False,
            })

        total_amount = 0.0
        for l in lines:
            total_price = l['qty'] * l['unit_price']
            total_amount += total_price
            request.env['cboq.line'].create({
                'cboq_id': cboq.id,
                'source_type': l['source'],
                'item_id': l['source'] == 'item' and l['id'] or False,
                'config_line_id': l['source'] == 'config' and l['id'] or False,
                'qty': l['qty'],
                'unit_price': l['unit_price'],
                'total_price': total_price,
            })

        cboq.write({'total_amount': total_amount})
        return json.dumps({'status': 'success', 'cboq_id': cboq.id, 'site_id': site_id, 'config_version_id': config_version_id})


    @http.route('/cboq-summary/delete/<int:cboq_id>', type='http', auth='user', methods=['POST'], csrf=False)
    def delete_cboq_draft(self, cboq_id):
        cboq = request.env['cboq'].browse(cboq_id)
        if cboq and cboq.status == 'draft':
            cboq.unlink()  # Deletes the CBOQ and its lines
        return request.redirect(request.httprequest.referrer)

    @http.route('/cboq-summary/submit/<int:cboq_id>', type='http', auth='user', methods=['POST'], csrf=False)
    def submit_cboq(self, cboq_id):
        cboq = request.env['cboq'].browse(cboq_id)
        if cboq:
            cboq.write({'status': 'submitted'})
        return request.redirect(request.httprequest.referrer)


    @http.route('/cboq-summary/<int:site_id>', auth='user')
    def cboq_summary(self, site_id, **kw):
        site = request.env['boq.sitelist'].browse(site_id)
        if not site.exists():
            return request.not_found()

        config_version_id = int(kw.get('config_version_id', 0))
        domain = [('site_id', '=', site_id)]
        if config_version_id:
            domain.append(('config_version_id', '=', config_version_id))

        cboqs = request.env['cboq'].search(domain, order='main_version desc, create_date desc')

        # Calculate total price by category for each CBOQ
        cboq_data = []
        for cboq in cboqs:
            category_totals = {}
            for line in cboq.line_ids:
                category = line.category
                if category not in category_totals:
                    category_totals[category] = 0
                category_totals[category] += line.total_price
            cboq_data.append({
                'cboq': cboq,
                'category_totals': category_totals
            })

        return request.render('BOQ.cboq_summary_template', {
            'site': site,
            'cboq_data': cboq_data,
        })


    @http.route('/cboq-summary/export/<int:cboq_id>', type='http', auth='user', methods=['GET'])
    def export_cboq_excel(self, cboq_id):
        cboq = request.env['cboq'].browse(cboq_id)
        if not cboq.exists() or cboq.status not in ('submitted', 'approved'):
            return request.not_found()

        # ---------- build workbook ----------
        from io import BytesIO
        import xlsxwriter

        output = BytesIO()
        wb   = xlsxwriter.Workbook(output, {'in_memory': True})
        ws   = wb.add_worksheet('CBOQ')

        header_fmt = wb.add_format({'bold': True, 'bg_color': '#D9E1F2'})
        money_fmt  = wb.add_format({'num_format': '#,##0.00'})

        row = 0

        # ---- site header ----
        hdr = [
            ('CBOQ #', cboq.name),
            ('Site', cboq.site_id.site_name),
            ('Config Version', cboq.config_version_id.config_versioned),
            ('Status', cboq.status),
            ('Total Amount', cboq.total_amount),
        ]
        for label, val in hdr:
            ws.write(row, 0, label, header_fmt)
            ws.write(row, 1, val, money_fmt if isinstance(val, float) else None)
            row += 1
        row += 1   # blank row

        # ---- category totals (manual aggregation) ----
        totals = {}
        for line in cboq.line_ids:
            cat = line.category or 'N/A'
            totals[cat] = totals.get(cat, 0.0) + line.total_price

        ws.write(row, 0, 'Category Name', header_fmt)
        ws.write(row, 1, 'Amount', header_fmt)
        row += 1
        for cat, amt in totals.items():
            ws.write(row, 0, cat)
            ws.write(row, 1, amt, money_fmt)
            row += 1
        # ws.write(row, 0, 'Category Total')
        # ws.write(row, 1, sum(totals.values()), money_fmt)
        row += 1   # blank row

        # ---- full line items ----
        cols = ['Type', 'Category', 'Description', 'Qty', 'Unit Price', 'Total']
        for col, name in enumerate(cols):
            ws.write(row, col, name, header_fmt)
        row += 1

        for line in cboq.line_ids:
            ws.write(row, 0, dict(line._fields['source_type'].selection).get(line.source_type) or '')
            ws.write(row, 1, line.category or '')
            ws.write(row, 2, line.description or '')
            ws.write(row, 3, line.qty)
            ws.write(row, 4, line.unit_price, money_fmt)
            ws.write(row, 5, line.total_price, money_fmt)
            row += 1

        wb.close()
        output.seek(0)

        filename = f"{cboq.name}.xlsx"
        return request.make_response(
            output.read(),
            headers=[
                ('Content-Type', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
                ('Content-Disposition', f'attachment; filename="{filename}"')
            ]
        )