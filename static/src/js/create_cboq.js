(function () {
    "use strict";

    const $  = sel => document.querySelector(sel);
    const $$ = sel => Array.from(document.querySelectorAll(sel));

    /* ----------  TAB SWITCHING  ---------- */
    document.addEventListener('DOMContentLoaded', () => {
        document.addEventListener('submit', e => e.preventDefault(), {capture: true});

        const tabs  = $$('.nav-link');
        const panes = $$('.tab-pane');

        tabs.forEach(tab => {
            tab.addEventListener('click', e => {
                e.preventDefault();
                tabs.forEach(t => t.classList.remove('active'));
                panes.forEach(p => p.classList.remove('active'));
                tab.classList.add('active');
                const target = document.getElementById(
                    tab.getAttribute('data-target').slice(1)
                );
                if (target) target.classList.add('active');
                
                if (tab.getAttribute('data-target') === '#tab-config') {
                const catFilter = $('#filter-category');
                const descFilter = $('#filter-description');
                if (catFilter) catFilter.value = '';
                if (descFilter) descFilter.value = '';
                }
                updateTotals();               // recalc after every tab change
            });
        });
        tabs[0]?.click();

        /* ----------  FILTERS & TOTALS  ---------- */
        const catFilter  = $('#filter-category');
        const descFilter = $('#filter-description');

        [catFilter, descFilter].forEach(el =>
            el.addEventListener('input', updateTotals)
        );

        /* inputs inside rows */
        $$('#tab-sor input, #tab-config input').forEach(inp =>
            inp.addEventListener('input', updateTotals)
        );

        updateTotals();   // initial run
    });

    /* ----------  TOTAL CALCULATION  ---------- */
    function updateTotals() {
        const cat = ($('#filter-category').value  || '').toLowerCase();
        const dsc = ($('#filter-description').value || '').toLowerCase();

        let sorTotal    = 0;
        let configTotal = 0;

        /* ----- SOR tab ----- */
        $$('#tab-sor .sor-row').forEach(tr => {
            const showCat = !cat || tr.children[1].textContent.toLowerCase().includes(cat);
            const showDsc = !dsc || tr.children[2].textContent.toLowerCase().includes(dsc);
            const checked = tr.querySelector('.select-sor').checked;
            const visible = showCat && showDsc;

            tr.style.display = (visible ? '' : 'none');

            if (visible && checked) {
                const qty = parseFloat(tr.querySelector('.qty').value)   || 0;
                const up  = parseFloat(tr.querySelector('.price').value) || 0;
                sorTotal += qty * up;
            }
        });

        /* ----- Config tab ----- */
        $$('#tab-config .config-row').forEach(tr => {
            const showCat = !cat || tr.children[0].textContent.toLowerCase().includes(cat);
            const showDsc = !dsc || tr.children[1].textContent.toLowerCase().includes(dsc);
            const visible = showCat && showDsc;

            tr.style.display = (visible ? '' : 'none');

            if (visible) {
                const qty = parseFloat(tr.querySelector('.qty').value)   || 0;
                const up  = parseFloat(tr.querySelector('.price').value) || 0;
                configTotal += qty * up;
            }
        });

        $('#total-sor-price').textContent    = sorTotal.toFixed(2);
        $('#total-config-price').textContent = configTotal.toFixed(2);
    }

    /* ----------  SAVE DRAFT – prevents double click  ---------- */
    $('#btn-save-draft')?.addEventListener('click', function once(ev) {
        ev.preventDefault();
        // ev.stopPropagation();
        // this.disabled = true;
        // this.removeEventListener('click', once);
        const catFilter = $('#filter-category');
        const descFilter = $('#filter-description');
        if (catFilter) catFilter.value = '';
        if (descFilter) descFilter.value = '';

        /* collect only CHECKED + VISIBLE SOR rows */
        const sorRows = $$('#tab-sor .sor-row')
            .filter(tr => tr.style.display !== 'none' && tr.querySelector('.select-sor').checked)
            .map(tr => ({
                source     : 'item',
                id         : parseInt(tr.dataset.id, 10),
                qty        : parseFloat(tr.querySelector('.qty').value)   || 0,
                unit_price : parseFloat(tr.querySelector('.price').value) || 0
            }));

        /* all config lines (always) */
        const cfgRows = $$('.config-row').map(tr => ({
            source     : 'config',
            id         : parseInt(tr.dataset.id, 10),
            qty        : parseFloat(tr.querySelector('.qty').value)   || 0,
            unit_price : parseFloat(tr.querySelector('.price').value) || 0
        }));

        fetch('/create-cboq/save-draft', {
            method : 'POST',
            headers: { 'Content-Type': 'application/json' },
            body   : JSON.stringify({
                site_id          : parseInt($('#site-id').value, 10),
                config_version_id: parseInt($('#config-id').value, 10),
                is_main          : $('#is-main').value === 'True',
                parent_id        : parseInt($('#parent-id').value, 10) || null,
                lines            : [...sorRows, ...cfgRows]
            }),
            credentials: 'same-origin'
        })
        .then(r => r.json())
        .then(res => {
            if (res.status === 'error') {
                alert(res.message || 'An unknown error occurred.');
                this.disabled = false;
                return;
            }

            // If status is not error, proceed
            window.location.href = `/cboq-summary/${res.site_id}?config_version_id=${res.config_version_id}`;
        })
        .catch(err => {
            console.error(err);
            alert('Error while saving');
            this.disabled = false;
        });
    });
})();