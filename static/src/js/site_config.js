/* Pure-Vanilla JS for /site-config page */
(function () {
    "use strict";

    const qs = (sel, ctx = document) => ctx.querySelector(sel);
    const qsa = (sel, ctx = document) => [...ctx.querySelectorAll(sel)];

    /* ----------  AUTOCOMPLETE  ---------- */
    const searchInput = qs('#site_search');
    const hiddenInput = qs('#site_id');
    const acBox        = document.createElement('div');
    acBox.className   = 'autocomplete-items';
    searchInput.parentNode.appendChild(acBox);

    let currentFocus = -1;

    searchInput.addEventListener('input', debounce(handleSearch, 250));

    function handleSearch(e) {
        const val = e.target.value.trim();
        clearAc();
        if (val.length < 2) return;

        fetch(`/site-config/search_site?term=${encodeURIComponent(val)}`)
            .then(r => r.json())
            .then(list => renderAc(list))
            .catch(console.error);
    }

    function renderAc(list) {
        acBox.innerHTML = '';
        list.forEach(item => {
            const div = document.createElement('div');
            div.className = 'ac-item';
            div.textContent = item.label;
            div.dataset.id = item.id;
            div.addEventListener('click', () => selectItem(item));
            acBox.appendChild(div);
        });
    }

    function selectItem(item) {
        searchInput.value = item.label;
        hiddenInput.value = item.id;
        searchInput.setAttribute('readonly', true);
        clearAc();
    }

    function clearAc() {
        acBox.innerHTML = '';
        currentFocus = -1;
    }

    /* ----------  CONFIG LINES  ---------- */
    const configSelect = qs('#config_select');
    const placeholder  = qs('#lines_placeholder');
    const tbody        = qs('#lines_tbody');

    configSelect.addEventListener('change', () => {
        const cfgId = configSelect.value;
        if (!cfgId) {
            placeholder.classList.add('d-none');
            return;
        }

        fetch(`/site-config/lines/${cfgId}`)
            .then(r => r.json())
            .then(rows => {
                tbody.innerHTML = '';
                rows.forEach(r => {
                    const tr = document.createElement('tr');
                    ['category', 'customer_code', 'supplier_code',
                     'description', 'uom', 'cost_type', 'qty',
                     'unit_price'].forEach(k => {
                        const td = document.createElement('td');
                        td.textContent = r[k] ?? '';
                        tr.appendChild(td);
                    });
                    tbody.appendChild(tr);
                });
                placeholder.classList.remove('d-none');
            })
            .catch(console.error);
    });

    /* ----------  UTILS  ---------- */
    function debounce(fn, wait) {
        let t;
        return (...args) => {
            clearTimeout(t);
            t = setTimeout(() => fn(...args), wait);
        };
    }

    /* ----------  PROCEED BUTTON REDIRECT TO /basket  ---------- */
    const proceedBtn = qs('#btn_proceed');

    proceedBtn.addEventListener('click', () => {
        const siteId   = hiddenInput.value;            // from site search
        const configId = configSelect.value;           // from config dropdown

        if (!siteId) {
            alert('Please select a Site.');
            return;
        }
        if (!configId) {
            alert('Please select a Configuration Version.');
            return;
        }
        window.location.href = `/create-cboq?site_id=${siteId}&config_id=${configId}`;
    });
    /* ----------  SHOW SUMMARY BUTTON REDIRECT TO /basket/summary  ---------- */
    const summaryBtn = qs('#btn_summary');

    summaryBtn.addEventListener('click', () => {
        const siteId   = hiddenInput.value;
        const configId = configSelect.value;

        if (!siteId) {
            alert('Please select a Site.');
            return;
        }
        if (!configId) {
            alert('Please select a Configuration Version.');
            return;
        }

        window.location.href = `/cboq-summary/${siteId}?config_version_id=${configId}`;
    });


    const summarysitelevel = qs('#btn_site_level_summary');

    summarysitelevel.addEventListener('click', () => {
        const siteId   = hiddenInput.value;

        if (!siteId) {
            alert('Please select a Site.');
            return;
        }
        window.location.href = `/cboq-summary/${siteId}`;
    });

})();