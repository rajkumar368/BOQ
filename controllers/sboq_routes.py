from odoo import http
from odoo.http import request
import json
import logging
from io import BytesIO
import xlsxwriter
from odoo.addons.portal.controllers.portal import CustomerPortal, pager as portal_pager


class SboqRoutes(http.Controller):

    @http.route('/sboq-site', auth='user', website=True)
    def site_config_page(self, **kw):
        return request.render('BOQ.site_selection_template')

    @http.route('/site-config/search_site', type='json', auth='user')
    def search_site(self, term='', offset=0, limit=20, **kw):
        domain = ['|', ('site_id', 'ilike', term), ('site_name', 'ilike', term)] if term else []
        sites = request.env['boq.sitelist'].search(domain, offset=offset, limit=limit)
        return [{'label': f"{s.site_id}_{s.site_name}", 'value': f"{s.site_id}_{s.site_name}", 'id': s.id} for s in sites]
    
    @http.route('/sboq-create/<int:site_id>', auth='user', website=True)
    def sboq_create_page(self, site_id, **kw):
        site = request.env['boq.sitelist'].browse(site_id)
        if not site.exists():
            return request.redirect('/sboq-site')
        
        sboq_status = kw.get('status', 'draft')
        print(kw)
        sboq_id = int(kw.get('sboq_id', 0))
        rejection_type = kw.get('rejection_type', 'NA')
        is_main = False
        parent_id = None

        if sboq_status == 'rejected':
            sboq_obj = request.env['sboq'].search([
                ('id', '=', sboq_id),
                ('site_id', '=', site_id),
                ('state', '=', sboq_status),
                ('rejection_type', '=', rejection_type),
                ('create_uid', '=', request.env.uid)
            ], limit=1)

            if rejection_type == 'major':
                is_main = True
            else:
                is_main = False
                parent_id = sboq_obj.parent_sboq_id.id if sboq_obj.parent_sboq_id else sboq_id

        elif sboq_status == 'approved':
            sboq_obj = request.env['sboq'].search([
                ('id', '=', sboq_id),
                ('site_id', '=', site_id),
                ('state', '=', sboq_status),
                ('create_uid', '=', request.env.uid)
            ], limit=1)
            is_main = False
            parent_id = sboq_obj.parent_sboq_id.id if sboq_obj.parent_sboq_id else sboq_id

        else:
            sboq_obj = request.env['sboq'].search([
                ('site_id', '=', site_id),
                ('state', '=', sboq_status),
                ('create_uid', '=', request.env.uid)
            ], limit=1)

            is_main = True

        current_vendor = request.env.user.vendor_id
        sor_items = request.env['sboq.sor'].search([('vendor_id', '=', current_vendor.id)])
        # sor_items = request.env['sboq.sor'].search([])

        sboq_lines = request.env['sboq.line'].sudo().search([('sboq_id.site_id', '=', site_id), ('source_type', '=', 'non_sor'), ('sboq_id.state', '=', sboq_status)])
        non_sor_ids = sboq_lines.mapped('sboq_non_sor_id').ids
        non_sor_items = request.env['sboq.non.sor'].sudo().search([('id', 'in', non_sor_ids)])

        non_sor_categories = request.env['sboq.category'].search([])
        non_sor_subcategories = request.env['sboq.subcategory'].search([])

        data = {
            'sor_lines': [],
            'non_sor_lines': []
        }
        if sboq_obj:
            for line in sboq_obj.line_ids:
                if line.sboq_sor_id:
                    data['sor_lines'].append({
                        'item_id': line.sboq_sor_id.id,
                        'qty': line.qty,
                        'unit_price': line.unit_price
                    })
                elif line.sboq_non_sor_id:
                    data['non_sor_lines'].append({
                        'non_sor_line_id': line.sboq_non_sor_id.id,
                        'qty': line.qty,
                        'unit_price': line.unit_price
                    })

        return request.render('BOQ.create_sboq_template', {
            'site_id': site_id,
            'site_name': request.env['boq.sitelist'].browse(site_id).display_name,
            'sor_items': sor_items,
            'non_sor_items': non_sor_items,
            'draft_data': data,
            'sboq_status': sboq_status,
            'rejection_type': rejection_type,
            'non_sor_categories': non_sor_categories,
            'non_sor_subcategories': non_sor_subcategories,
            'is_main': is_main,
            'parent_id': parent_id,
            'sboq_id':sboq_id
        })
    
    
    @http.route('/create-sboq/save-draft', type='json', auth='user', methods=['POST'], csrf=False)
    def save_sboq_draft(self, **kw):
        data = json.loads(request.httprequest.data)
        site_id = int(data['site_id'])
        lines = data['lines']
        is_main = data.get('is_main', True)

        if isinstance(is_main, str):
            is_main = is_main.lower() in ['true', '1']
            
        parent_id = int(data.get('parent_id') or 0)
        print("************")
        print(is_main)
        print(parent_id)
        print("************")
        
        site = request.env['boq.sitelist'].sudo().browse(site_id)
        if not site.exists():
            return {'error': 'Site not found.'}

        # parent_sboq = None
        # if not is_main:
        #     parent_sboq = request.env['sboq'].browse(parent_id)
        #     if parent_sboq.state != 'approved':
        #         return json.dumps({'status': 'error', 'message': 'Unapproved main SBOQ.'})

        
        master_boq = request.env['boq.master'].search([('site_id', '=', site.site_id)], limit=1)
        if not master_boq:
            master_boq = request.env['boq.master'].sudo().create({'site_id': site.site_id})
            request.env.cr.commit()
            print(master_boq)

        domain = [('site_id', '=', site_id), ('state', '=', 'draft'), ('create_uid', '=', request.env.uid)]
        # if is_main:
        #     domain += [('is_main', '=', True)]
        # else:
        #     domain += [('parent_sboq_id', '=', parent_id)]

        draft = request.env['sboq'].search(domain, limit=1)
        print(draft)


        # existing = request.env['sboq'].search([('site_id', '=', site_id)])
        # draft = existing.filtered(lambda r: r.state == 'draft')[:1]

        if draft:
            draft.line_ids.unlink()
            sboq = draft
        else:
            # max_version = max(existing.mapped('version') or [0])
            try:
                sboq = request.env['sboq'].create({
                    'master_boq_id': master_boq.id,
                    'site_id': site_id,
                    'state': 'draft',
                    'is_main': is_main,
                    'parent_sboq_id': parent_id if not is_main else False
                })
            except Exception as e:
                return {'error': 'Failed to create SBOQ'}

        # Create lines
        total_amount = 0.0
        for line in lines:
            total_price = line['qty'] * line['unit_price']
            total_amount += total_price
            vals = {
                'sboq_id': sboq.id,
                'source_type': line['source_type'],
                'qty': line['qty'],
                'unit_price': line['unit_price'],
                'total_price': total_price,
            }
            if line['source_type'] == 'sor':
                vals['sboq_sor_id'] = line['sboq_sor_id']
            else:
                non_sor_vals = {
                    'category_id': int(line.get('category_id', 0)),
                    'subcategory_id': int(line.get('subcategory_id', 0)),
                    'description': line.get('description', ''),
                    'qty': line['qty'],
                    'unit_price': line['unit_price'],
                }

                if line.get('sboq_non_sor_id'):
                    non_sor = request.env['sboq.non.sor'].sudo().browse(line['sboq_non_sor_id'])
                    if non_sor.exists():
                        non_sor.write(non_sor_vals)
                    else:
                        non_sor = request.env['sboq.non.sor'].sudo().create(non_sor_vals)
                else:
                    non_sor = request.env['sboq.non.sor'].sudo().create(non_sor_vals)
                vals['sboq_non_sor_id'] = non_sor.id
            try:
                request.env['sboq.line'].create(vals)
            except:
                return {'error': 'Failed to save SBOQ Lines'}

        sboq.write({'total_amount': total_amount})
        return {'status': 'success', 'sboq_id': sboq.id, 'site_id': site_id}


    @http.route('/create-sboq/resubmitted/<int:sboq_id>', type='json', auth='user', methods=['POST'], csrf=False)
    def save_rejected_sboq(self,sboq_id, **kw):
        data = json.loads(request.httprequest.data)
        site_id = int(data['site_id'])
        lines = data['lines']
        # is_main = data.get('is_main', True)

        # if isinstance(is_main, str):
        #     is_main = is_main.lower() in ['true', '1']
            
        # parent_id = int(data.get('parent_id') or 0)
        # print("************")
        # print(is_main)
        # print(parent_id)
        # print("************")


        master_boq = request.env['boq.master'].search([('site_id', '=', site_id)], limit=1)
        # cboq_obj = request.env['cboq'].search([
        #     ('master_boq_id', '=', master_boq.id),
        #     ('status', '=', 'approved')  
        # ], limit=1)

        # sboq = request.env['sboq'].search([('site_id', '=', site_id),('state', '=', 'rejected'),('create_uid', '=', request.env.uid)], limit=1)
        old_sboq = request.env['sboq'].search([('id', '=', sboq_id),('create_uid', '=', request.env.uid)], limit=1)
        # sboq.line_ids.unlink()

        if old_sboq.state == "approved":
            parent_sboq_id =  old_sboq.parent_sboq_id.id if old_sboq.parent_sboq_id else old_sboq.id
        else:
            parent_sboq_id =  old_sboq.parent_sboq_id.id if old_sboq.parent_sboq_id else False


        sboq = request.env['sboq'].create({
            'master_boq_id': old_sboq.master_boq_id.id,
            'site_id': old_sboq.site_id.id,
            'cboq_id': old_sboq.cboq_id.id if old_sboq.cboq_id else False,
            'is_main':  True if old_sboq.rejection_type == 'major' else False,
            'parent_sboq_id': parent_sboq_id,
            'main_version':old_sboq.main_version,
            'variation_index':old_sboq.variation_index,
            'state': old_sboq.state,
            'rejection_type':old_sboq.rejection_type
        })

        # Create lines
        total_amount = 0.0
        for line in lines:
            total_price = line['qty'] * line['unit_price']
            total_amount += total_price
            vals = {
                'sboq_id': sboq.id,
                'source_type': line['source_type'],
                'qty': line['qty'],
                'unit_price': line['unit_price'],
                'total_price': total_price,
            }
            if line['source_type'] == 'sor':
                vals['sboq_sor_id'] = line['sboq_sor_id']
            else:
                non_sor_vals = {
                    'category_id': int(line.get('category_id', 0)),
                    'subcategory_id': int(line.get('subcategory_id', 0)),
                    'description': line.get('description', ''),
                    'qty': line['qty'],
                    'unit_price': line['unit_price'],
                }

                if line.get('sboq_non_sor_id'):
                    non_sor = request.env['sboq.non.sor'].sudo().browse(line['sboq_non_sor_id'])
                    if non_sor.exists():
                        non_sor.write(non_sor_vals)
                    else:
                        non_sor = request.env['sboq.non.sor'].sudo().create(non_sor_vals)
                else:
                    non_sor = request.env['sboq.non.sor'].sudo().create(non_sor_vals)
                vals['sboq_non_sor_id'] = non_sor.id
            try:
                request.env['sboq.line'].create(vals)
            except:
                return {'error': 'Failed to save SBOQ Lines'}

        old_sboq.write({'is_resubmitted': True})
        sboq.write({'total_amount': total_amount})
        sboq.write({'state': 'resubmitted'})
        return {'status': 'success', 'sboq_id': sboq.id, 'site_id': site_id}



    @http.route('/sboq-summary/submit/<int:sboq_id>', type='http', auth='user', methods=['POST'], csrf=False)
    def submit_cboq(self, sboq_id):
        sboq = request.env['sboq'].browse(sboq_id)
        if sboq:
            if sboq.state == 'draft':
                sboq.write({'state': 'submitted'})
            else:
                sboq.write({'state': 'resubmitted'})
        return request.redirect(request.httprequest.referrer)

    @http.route('/sboq-summary/delete/<int:sboq_id>', type='http', auth='user', methods=['POST'], csrf=False)
    def delete_cboq_draft(self, sboq_id):
        sboq = request.env['sboq'].browse(sboq_id)
        if sboq and sboq.state == 'draft':
            non_sor_ids = sboq.line_ids.filtered(lambda line: line.source_type == 'non_sor').mapped('sboq_non_sor_id').ids
            
            lines_to_delete = request.env['sboq.line'].search([('sboq_non_sor_id', 'in', non_sor_ids)])
            if lines_to_delete:
                lines_to_delete.unlink()
           
            if non_sor_ids:
                request.env['sboq.non.sor'].browse(non_sor_ids).unlink()
                
            sboq.unlink() 
        return request.redirect(request.httprequest.referrer)

    @http.route('/sboq-create/delete-non-sor', type='json', auth='user', methods=['POST'], csrf=False)
    def delete_non_sor(self, **kw):
        try:
            data = json.loads(request.httprequest.data.decode('utf-8'))
            non_sor_id = data.get('sboq_non_sor_id')

            if not non_sor_id:
                return {'error': 'Non-SOR ID is required'}

            non_sor = request.env['sboq.non.sor'].sudo().browse(int(non_sor_id))
            if not non_sor.exists():
                return {'error': 'Non-SOR record not found'}

            linked_lines = request.env['sboq.line'].sudo().search([('sboq_non_sor_id', '=', non_sor_id)])
            if linked_lines:
                linked_lines.unlink()
            non_sor.unlink()
            return {'status': 'success'}

        except Exception as e:
            return {'error': f'Failed to delete Non-SOR record: {str(e)}'}


    @http.route('/sboq-summary/<int:site_id>', auth='user')
    def sboq_summary(self, site_id, **kw):
        site = request.env['boq.sitelist'].browse(site_id)
        if not site.exists():
            return request.not_found()

        # config_version_id = int(kw.get('config_version_id', 0))
        domain = [('site_id', '=', site_id), ('create_uid', '=', request.env.uid)]
        # if config_version_id:
            # domain.append(('config_version_id', '=', config_version_id))

        sboqs = request.env['sboq'].search(domain, order='create_date desc')
        sboq_data = []
        for sboq in sboqs:
            sboq_data.append({'sboq': sboq})
        return request.render('BOQ.sboq_summary_template', {
            'site': site,
            'sboq_data': sboq_data,
        })


    @http.route('/sboq-summary/export/<int:sboq_id>', type='http', auth='user')
    def export_sboq_excel(self, sboq_id):
        sboq = request.env['sboq'].browse(sboq_id)
        if not sboq.exists() or sboq.state != 'approved':
            return request.not_found()

        # ---------- build workbook ----------
        from io import BytesIO
        import xlsxwriter

        output = BytesIO()
        wb   = xlsxwriter.Workbook(output, {'in_memory': True})
        ws   = wb.add_worksheet('SBOQ')

        header_fmt = wb.add_format({'bold': True, 'bg_color': '#D9E1F2'})
        money_fmt  = wb.add_format({'num_format': '#,##0.00'})

        row = 0

        # ---- site header ----
        hdr = [
            ('SBOQ #', sboq.name),
            ('Site', f"{sboq.site_id.site_id}_{sboq.site_id.site_name}"),
            # ('Config Version', cboq.config_version_id.config_versioned),
            ('Status', sboq.state),
            ('Total Amount', sboq.total_amount),
        ]
        for label, val in hdr:
            ws.write(row, 0, label, header_fmt)
            ws.write(row, 1, val, money_fmt if isinstance(val, float) else None)
            row += 1
        row += 1  

        cols = ['Item Type', 'Category', 'Description', 'Cost Type', 'Qty', 'Unit Price', 'Total']
        for col, name in enumerate(cols):
            ws.write(row, col, name, header_fmt)
        row += 1

        for line in sboq.line_ids:
            ws.write(row, 0, dict(line._fields['source_type'].selection).get(line.source_type) or '')
            cat = ''
            if line.source_type == "sor":
                cat = line.sboq_sor_id.category
            else:
                cat = line.sboq_non_sor_id.category_id.name
            ws.write(row, 1, cat or '')
            ws.write(row, 2, line.description or '')
            ws.write(row, 3, line.cost_type or '')
            ws.write(row, 4, line.qty)
            ws.write(row, 5, line.unit_price, money_fmt)
            ws.write(row, 6, line.total_price, money_fmt)
            row += 1

        wb.close()
        output.seek(0)

        filename = f"{sboq.site_id.site_id}_{sboq.site_id.site_name}_export.xlsx"
        return request.make_response(
            output.read(),
            headers=[
                ('Content-Type', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
                ('Content-Disposition', f'attachment; filename="{filename}"')
            ]
        )

    @http.route(['/my/pending_sboqs'], type='http', auth='user', website=True)
    def portal_pending_sboqs(self, **kw):
        items_per_page = 10
        domain = [('is_pending_review', '=', True)]
        sboq_obj = request.env['sboq'].sudo().search(domain, order='create_date desc')
        
        # Pagination
        url = "/my/pending_sboqs"
        page = int(kw.get('page', 1))
        total_records = len(sboq_obj)

        # Generate pagination dictionary
        pagination = portal_pager(
            url=url,
            total=total_records,
            page=page,
            step=items_per_page,
        ) if total_records > 0 else {
            'page_count': 1,
            'offset': 0,
            'page': page,
            'url': url,
            'url_args': {},
        }

        # Calculate offset and limit manually
        offset = (page - 1) * items_per_page
        limit = items_per_page

        # Slice the recordset for the current page
        sboqs_paginated = sboq_obj[offset:offset + limit] if total_records > 0 else sboq_obj
        values = {
            'sboqs': sboqs_paginated,
            'page_name': 'pending_sboqs',
            'pagination': pagination,
        }
        return request.render('BOQ.pending_review', values)

    @http.route(['/my/sboq/<int:sboq_id>'], type='http', auth='user', website=True)
    def portal_sboq_detail(self, sboq_id, **kw):
        sboq = request.env['sboq'].sudo().browse(sboq_id)
        if not sboq.exists():
            return request.redirect('/my/pending_sboqs')

        cboqs = request.env['cboq'].sudo().search([
            ('site_id', '=', sboq.site_id.id),
            ('status', '=', 'approved')
        ])

        values = {
            'sboq': sboq,
            'cboq': sboq.cboq_id,
            'cboq_options': cboqs,
            'page_name': 'sboq_detail',
        }
        return request.render('BOQ.pending_review_detail_template', values)


    @http.route(['/my/sboq/<int:sboq_id>/link-cboq'], type='http', auth='user', website=True, methods=['POST'])
    def portal_link_cboq(self, sboq_id, **post):
        cboq_id = int(post.get('cboq_id', 0))
        sboq = request.env['sboq'].sudo().browse(sboq_id)
        cboq = request.env['cboq'].sudo().browse(cboq_id)

        if sboq.exists() and cboq.exists():
            sboq.write({'cboq_id': cboq.id})
        return request.redirect(f'/my/sboq/{sboq_id}')

    @http.route(['/my/sboq/<int:sboq_id>/approve'], type='http', auth='user', website=True, methods=['POST'])
    def portal_approve_sboq(self, sboq_id, approval_note, **kw):
        sboq = request.env['sboq'].sudo().browse(sboq_id)
        if sboq.exists():
            sboq.action_approve(approval_note)
            return request.redirect('/my/pending_sboqs')
        return request.redirect('/my')

    @http.route(['/my/sboq/<int:sboq_id>/reject'], type='http', auth='user', website=True, methods=['POST'])
    def portal_reject_sboq(self, sboq_id, rejection_type, rejection_note, **kw):
        sboq = request.env['sboq'].sudo().browse(sboq_id)
        if sboq.exists():
            sboq.action_reject(rejection_type, rejection_note)
            return request.redirect('/my/pending_sboqs')
        return request.redirect('/my')
