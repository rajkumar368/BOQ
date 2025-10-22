(function () {
    "use strict";

    const $ = sel => document.querySelector(sel);
    const $$ = sel => Array.from(document.querySelectorAll(sel));

    let non_sor_categories = [];
    let non_sor_subcategories = [];

    document.addEventListener('DOMContentLoaded', () => {
        // Load categories and subcategories from JSON script tags
        const categoriesData = JSON.parse(document.querySelector('#non_sor_categories_data')?.textContent || '[]');
        const subcategoriesData = JSON.parse(document.querySelector('#non_sor_subcategories_data')?.textContent || '[]');

        non_sor_categories = categoriesData.map(cat => ({ id: cat.id, name: cat.name }));
        non_sor_subcategories = subcategoriesData.map(subcat => ({
            id: subcat.id,
            name: subcat.name,
            category_id: subcat.category_id
        }));

        // Prevent native form submit
        document.addEventListener('submit', e => e.preventDefault(), { capture: true });

        // Tab switching logic
        const tabs = $$('.nav-link');
        const tabPanes = $$('.tab-pane');

        tabs.forEach(tab => {
            tab.addEventListener('click', e => {
                e.preventDefault();
                tabs.forEach(t => t.classList.remove('active'));
                tabPanes.forEach(p => p.classList.remove('active'));

                tab.classList.add('active');
                const target = document.querySelector(tab.getAttribute('data-target'));
                if (target) target.classList.add('active');

                if (tab.getAttribute('data-target') === '#tab-config') {
                    const catFilter = $('#filter-category');
                    const descFilter = $('#filter-description');
                    if (catFilter) catFilter.value = '';
                    if (descFilter) descFilter.value = '';
                }

                updateTotals();
            });
        });

        tabs[0]?.click(); // Activate first tab initially

        // Filter inputs event handlers
        const catFilter = $('#filter-category');
        const descFilter = $('#filter-description');

        [catFilter, descFilter].forEach(el =>
            el.addEventListener('input', updateTotals)
        );

        // Inputs inside SOR rows
        $$('#tab-sor input').forEach(inp =>
            inp.addEventListener('input', updateTotals)
        );

        // Inputs inside Non-SOR rows
        $('#tab-config').addEventListener('input', e => {
            if (e.target.matches('input, select')) updateTotals();
        });

        // Add Non-SOR Item button
        $('#add-nonsor')?.addEventListener('click', () => {
            addNonSorRow();
            updateTotals();
        });

        // Delegate remove button clicks in non-sor tbody
        $('#non_sor_tbody')?.addEventListener('click', e => {
            if (e.target.classList.contains('btn-remove')) {
                const row = e.target.closest('tr');
                const nonSorId = row.dataset.id ? parseInt(row.dataset.id, 10) : null;

                if (nonSorId) {
                    fetch('/sboq-create/delete-non-sor', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ sboq_non_sor_id: nonSorId }),
                        credentials: 'same-origin'
                    })
                    .then(r => r.json())
                    .then(res => {
                        if (res.error) {
                            alert(res.error);
                        } else {
                            row.remove();
                            updateTotals();
                        }
                    })
                    .catch(err => {
                        console.error('Delete Non-SOR error:', err);
                        alert(`Error while deleting: ${err.message}`);
                    });
                } else {
                    row.remove();
                    updateTotals();
                }
            }
        });

        // Delegate category change event to update subcategories dynamically
        $('#non_sor_tbody')?.addEventListener('change', e => {
            if (e.target.classList.contains('category-select')) {
                console.log('Category changed:', e.target.value);
                const tr = e.target.closest('tr');
                updateSubcategoryOptions(tr);
            }
        });

        // On page load, initialize subcategories dropdowns
        $$('#non_sor_tbody tr').forEach(tr => updateSubcategoryOptions(tr));

        updateTotals();

    });

    function updateSubcategoryOptions(row) {
        const catSelect = row.querySelector('.category-select');
        const subcatSelect = row.querySelector('.subcategory-select');
        const selectedCatId = catSelect.value;
        const currentSubcatId = subcatSelect.value;

        // Clear current options except the default
        subcatSelect.innerHTML = '<option value="">Select Subcategory</option>';

        if (!selectedCatId) return;

        // Filter subcategories for the selected category
        const filteredSubcats = non_sor_subcategories.filter(s => s.category_id === selectedCatId);

        filteredSubcats.forEach(subcat => {
            const option = document.createElement('option');
            option.value = subcat.id;
            option.textContent = subcat.name;
            if (subcat.id === currentSubcatId) option.selected = true;
            subcatSelect.appendChild(option);
        });
    }

    function addNonSorRow() {
        const tbody = $('#non_sor_tbody');
        const template = document.querySelector('#non_sor_row_template');
        if (!tbody || !template) {
            console.error('Table body or template not found');
            return;
        }

        // Clone template content
        const clone = template.content.cloneNode(true);
        const newRow = clone.querySelector('tr');

        // Populate category dropdown
        const catSelect = newRow.querySelector('.category-select');
        catSelect.innerHTML = '<option value="">Select Category</option>';
        non_sor_categories.forEach(cat => {
            const option = document.createElement('option');
            option.value = cat.id;
            option.textContent = cat.name;
            catSelect.appendChild(option);
        });

        // Subcategory starts empty
        const subcatSelect = newRow.querySelector('.subcategory-select');
        subcatSelect.innerHTML = '<option value="">Select Subcategory</option>';

        // Set default qty and price inputs
        newRow.querySelector('.qty-input').value = '1';
        newRow.querySelector('.price-input').value = '0.00';

        // Append new row
        tbody.appendChild(newRow);

        // Attach event listener to the new category select
        catSelect.addEventListener('change', () => updateSubcategoryOptions(newRow));

        // Update totals
        updateTotals();
    }

    function updateTotals() {
        const catFilter = ($('#filter-category').value || '').toLowerCase();
        const descFilter = ($('#filter-description').value || '').toLowerCase();

        let sorTotal = 0;
        let nonSorTotal = 0;

        // SOR tab total
        $$('#tab-sor .sor-row').forEach(tr => {
            const catText = tr.children[1].textContent.toLowerCase();
            const descText = tr.children[2].textContent.toLowerCase();
            const visible = (!catFilter || catText.includes(catFilter)) && (!descFilter || descText.includes(descFilter));
            tr.style.display = visible ? '' : 'none';

            if (visible && tr.querySelector('.select-sor').checked) {
                const qty = parseFloat(tr.querySelector('.qty').value) || 0;
                const price = parseFloat(tr.querySelector('.price').value) || 0;
                const costType = tr.children[3].textContent.replace(/\s+/g, '');
                let lineTotal = qty * price;
                if (['CostPlus', 'FIM', 'Passthrough', 'Passthrough+x%'].includes(costType)) {lineTotal *= 1.10;}
                sorTotal += lineTotal;
            }
        });

        // Non-SOR tab total
        $$('#tab-config .non-sor-row').forEach(tr => {
            const catSelect = tr.querySelector('.category-select');
            const descInput = tr.querySelector('.description-input');

            const catText = catSelect.selectedOptions[0]?.textContent.toLowerCase() || '';
            const descText = descInput.value.toLowerCase();

            const visible = (!catFilter || catText.includes(catFilter)) && (!descFilter || descText.includes(descFilter));
            tr.style.display = visible ? '' : 'none';

            if (visible) {
                const qty = parseFloat(tr.querySelector('.qty-input').value) || 0;
                const price = parseFloat(tr.querySelector('.price-input').value) || 0;
                nonSorTotal += qty * price;
            }
        });

        $('#total-sor-price').textContent = sorTotal.toFixed(2);
        $('#total-config-price').textContent = nonSorTotal.toFixed(2);
    }

    // Save draft logic
    $('#btn-save-draft')?.addEventListener('click', function once(ev) {
        ev.preventDefault();

        const catFilter = $('#filter-category');
        const descFilter = $('#filter-description');
        if (catFilter) catFilter.value = '';
        if (descFilter) descFilter.value = '';
        // Collect checked + visible SOR rows
        const sorRows = $$('#tab-sor .sor-row')
            .filter(tr => tr.querySelector('.select-sor').checked)
            .map(tr => ({
                source_type: 'sor',
                sboq_sor_id: parseInt(tr.dataset.id, 10),
                qty: parseFloat(tr.querySelector('.qty').value) || 0,
                unit_price: parseFloat(tr.querySelector('.price').value) || 0
            }));

        // Collect all visible Non-SOR rows
        const nonSorRows = $$('#tab-config .non-sor-row')
            .filter(tr => true)
            .map(tr => ({
                source_type: 'non_sor',
                sboq_non_sor_id: tr.dataset.id ? parseInt(tr.dataset.id, 10) : null,
                category_id: tr.querySelector('.category-select').value || null,
                subcategory_id: tr.querySelector('.subcategory-select').value || null,
                description: tr.querySelector('.description-input').value || '',
                qty: parseFloat(tr.querySelector('.qty-input').value) || 0,
                unit_price: parseFloat(tr.querySelector('.price-input').value) || 0
            }));

        const sboqStatusElement = $('#sboq_status-id');
        const sboqIdElement = $('#sboq-id');
        const sboqStatus = sboqStatusElement ? sboqStatusElement.value : 'draft'; // Default to 'draft' if no status
        const sboqId = sboqIdElement ? sboqIdElement.value : 0; // Default to 'draft' if no status
        const fetchUrl = (sboqStatus === 'rejected' || sboqStatus === 'approved') ? `/create-sboq/resubmitted/${sboqId}` : '/create-sboq/save-draft';

        fetch(fetchUrl, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                site_id: parseInt($('#site-id').value, 10),
                is_main: $('#is-main').value === 'True',
                parent_id: parseInt($('#parent-id').value, 10) || null,
                lines: [...sorRows, ...nonSorRows]
            }),
            credentials: 'same-origin'
        })
        .then(r => r.json())
            .then(res => {
                if (res.result.error) {
                    alert(res.result.error);
                } else {
                    window.location.href = `/sboq-summary/${res.result.site_id}`;
                }
            })
            .catch(err => {
                console.error(err);
                alert('Error while saving: Network or server issue');
            });
    });
})();