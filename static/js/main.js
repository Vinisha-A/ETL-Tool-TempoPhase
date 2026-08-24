/**
 * HDFC Data Quality Tool — Main JavaScript
 * Handles dynamic UI interactions, AJAX calls, and form logic
 */

window.isRestoringDraft = false;

// ─── CSRF Token Helper ──────────────────────────────────────────────────────
function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let cookie of cookies) {
            cookie = cookie.trim();
            if (cookie.startsWith(name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}

const csrftoken = getCookie('csrftoken');

function fetchWithCSRF(url, options = {}) {
    return fetch(url, {
        ...options,
        headers: {
            'X-CSRFToken': csrftoken,
            'Content-Type': 'application/json',
            ...options.headers,
        },
    });
}

// ─── Toast Notifications ────────────────────────────────────────────────────
function showToast(message, type = 'info', duration = 4000) {
    let container = document.querySelector('.toast-container');
    if (!container) {
        container = document.createElement('div');
        container.className = 'toast-container';
        document.body.appendChild(container);
    }

    const icons = {
        success: '✓',
        error: '✕',
        warning: '⚠',
        info: 'ℹ',
    };

    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.innerHTML = `<span>${icons[type] || 'ℹ'}</span> <span>${message}</span>`;
    container.appendChild(toast);

    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateX(100%)';
        toast.style.transition = 'all 0.3s ease';
        setTimeout(() => toast.remove(), 300);
    }, duration);
}

// ─── Sidebar Toggle ─────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', function () {
    const sidebarToggle = document.getElementById('sidebar-toggle');
    const sidebar = document.getElementById('sidebar');

    if (sidebarToggle && sidebar) {
        sidebarToggle.addEventListener('click', () => {
            sidebar.classList.toggle('open');
        });

        // Close sidebar on outside click (mobile)
        document.addEventListener('click', (e) => {
            if (window.innerWidth <= 1024 &&
                sidebar.classList.contains('open') &&
                !sidebar.contains(e.target) &&
                !sidebarToggle.contains(e.target)) {
                sidebar.classList.remove('open');
            }
        });
    }

    // ─── Tab System ─────────────────────────────────────────────────────────
    document.querySelectorAll('.tab-item').forEach(tab => {
        tab.addEventListener('click', () => {
            const tabGroup = tab.closest('.tab-bar') || tab.parentElement;
            const contentContainer = tabGroup.parentElement;
            const targetId = tab.dataset.tab;

            // Deactivate all tabs
            tabGroup.querySelectorAll('.tab-item').forEach(t => t.classList.remove('active'));
            contentContainer.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));

            // Activate selected
            tab.classList.add('active');
            const targetContent = document.getElementById(targetId);
            if (targetContent) targetContent.classList.add('active');
        });
    });

    // ─── Modal System ───────────────────────────────────────────────────────
    document.querySelectorAll('[data-modal]').forEach(trigger => {
        trigger.addEventListener('click', () => {
            const modal = document.getElementById(trigger.dataset.modal);
            if (modal) modal.classList.add('active');
        });
    });

    document.querySelectorAll('.modal-overlay').forEach(overlay => {
        overlay.addEventListener('click', (e) => {
            if (e.target === overlay) overlay.classList.remove('active');
        });
    });

    document.querySelectorAll('.modal-close').forEach(btn => {
        btn.addEventListener('click', () => {
            btn.closest('.modal-overlay').classList.remove('active');
        });
    });

    // ─── Login: Dynamic Forgot Password ─────────────────────────────────────
    const usernameInput = document.getElementById('login-username');
    const forgotPasswordLink = document.getElementById('forgot-password-link');

    if (usernameInput && forgotPasswordLink) {
        usernameInput.addEventListener('input', () => {
            const username = usernameInput.value.trim();
            if (username === 'admin') {
                forgotPasswordLink.classList.remove('hidden');
            } else {
                forgotPasswordLink.classList.add('hidden');
            }
        });
    }

    // Initialize dynamic selects if on mapping/dashboard page
    initConnectionSelects();
});

// ─── Connection-based Dynamic Selects ───────────────────────────────────────
function updateTablePreviewLink(prefix) {
    const connSelect = document.getElementById(`${prefix}-connection`);
    const catalogSelect = document.getElementById(`${prefix}-catalog`);
    const schemaSelect = document.getElementById(`${prefix}-schema`);
    const tableSelect = document.getElementById(`${prefix}-table`);
    const previewWrapper = document.getElementById(`${prefix}-table-preview-wrapper`);
    const previewBtn = document.getElementById(`${prefix}-table-preview-btn`);

    if (!connSelect || !tableSelect || !previewWrapper || !previewBtn) return;

    const connId = connSelect.value;
    const table = tableSelect.value;
    const schema = schemaSelect ? schemaSelect.value : '';
    const catalog = catalogSelect ? catalogSelect.value : '';

    // Count how many tables are available in the dropdown (excluding the empty/placeholder select option)
    let tablesCount = 0;
    if (tableSelect && tableSelect.options) {
        for (let i = 0; i < tableSelect.options.length; i++) {
            if (tableSelect.options[i].value !== "") {
                tablesCount++;
            }
        }
    }

    if (connId && table && tablesCount >= 1) {
        previewBtn.href = `/connections/preview/${prefix}/?connection_id=${connId}&schema=${encodeURIComponent(schema)}&table=${encodeURIComponent(table)}&catalog=${encodeURIComponent(catalog)}`;
        previewWrapper.style.display = 'block';
    } else {
        previewWrapper.style.display = 'none';
        previewBtn.href = '#';
    }
}

function initConnectionSelects() {
    // Source connection change
    const sourceConn = document.getElementById('source-connection');
    if (sourceConn) {
        sourceConn.addEventListener('change', () => {
            handleConnectionChange(sourceConn, 'source');
        });
        if (sourceConn.value) {
            updateSchemaTableLabels(sourceConn, 'source');
            if (!window.isRestoringDraft) {
                handleConnectionChange(sourceConn, 'source');
            }
        }
    }

    // Target connection change
    const targetConn = document.getElementById('target-connection');
    if (targetConn) {
        targetConn.addEventListener('change', () => {
            handleConnectionChange(targetConn, 'target');
        });
        if (targetConn.value) {
            updateSchemaTableLabels(targetConn, 'target');
            if (!window.isRestoringDraft) {
                handleConnectionChange(targetConn, 'target');
            }
        }
    }

    // Catalog change listeners
    const sourceCatalog = document.getElementById('source-catalog');
    if (sourceCatalog) {
        sourceCatalog.addEventListener('change', () => {
            const connId = document.getElementById('source-connection').value;
            const catalog = sourceCatalog.value;
            if (connId && catalog) {
                loadSchemas(connId, 'source', catalog);
            } else {
                clearSelect('source-schema');
                clearSelect('source-table');
                clearColumnList('source');
            }
        });
    }

    const targetCatalog = document.getElementById('target-catalog');
    if (targetCatalog) {
        targetCatalog.addEventListener('change', () => {
            const connId = document.getElementById('target-connection').value;
            const catalog = targetCatalog.value;
            if (connId && catalog) {
                loadSchemas(connId, 'target', catalog);
            } else {
                clearSelect('target-schema');
                clearSelect('target-table');
                clearColumnList('target');
            }
        });
    }

    // Schema change listeners
    const sourceSchema = document.getElementById('source-schema');
    if (sourceSchema) {
        sourceSchema.addEventListener('change', () => {
            const connId = document.getElementById('source-connection').value;
            const catalog = document.getElementById('source-catalog') ? document.getElementById('source-catalog').value : '';
            const schema = sourceSchema.value;
            if (connId && schema) {
                loadTables(connId, schema, 'source', catalog);
            }
        });
    }

    const targetSchema = document.getElementById('target-schema');
    if (targetSchema) {
        targetSchema.addEventListener('change', () => {
            const connId = document.getElementById('target-connection').value;
            const catalog = document.getElementById('target-catalog') ? document.getElementById('target-catalog').value : '';
            const schema = targetSchema.value;
            if (connId && schema) {
                loadTables(connId, schema, 'target', catalog);
            }
        });
    }

    // Table change listeners
    const sourceTable = document.getElementById('source-table');
    if (sourceTable) {
        sourceTable.addEventListener('change', () => {
            const connId = document.getElementById('source-connection').value;
            const catalog = document.getElementById('source-catalog') ? document.getElementById('source-catalog').value : '';
            const schema = document.getElementById('source-schema').value;
            const table = sourceTable.value;
            if (connId && table) {
                loadColumns(connId, schema, table, 'source', catalog);
                updateTablePreviewLink('source');
            } else {
                checkTableSelections();
                updateTablePreviewLink('source');
            }
        });
    }

    const targetTable = document.getElementById('target-table');
    if (targetTable) {
        targetTable.addEventListener('change', () => {
            const connId = document.getElementById('target-connection').value;
            const catalog = document.getElementById('target-catalog') ? document.getElementById('target-catalog').value : '';
            const schema = document.getElementById('target-schema').value;
            const table = targetTable.value;
            if (connId && table) {
                loadColumns(connId, schema, table, 'target', catalog);
                updateTablePreviewLink('target');
            } else {
                checkTableSelections();
                updateTablePreviewLink('target');
            }
        });
    }

    const sourceColSelect = document.getElementById('source-column-select');
    if (sourceColSelect) {
        sourceColSelect.addEventListener('change', handleColumnSelectionChange);
    }
    const targetColSelect = document.getElementById('target-column-select');
    if (targetColSelect) {
        targetColSelect.addEventListener('change', handleColumnSelectionChange);
    }

    const modeRadios = document.querySelectorAll('input[name="column_selection_mode"]');
    if (modeRadios.length > 0) {
        modeRadios.forEach(radio => {
            radio.addEventListener('change', handleColumnModeChange);
        });
        checkTableSelections();
        handleColumnModeChange();
    }
}

// Connection types that use the catalog → schema → table → columns hierarchy
// Only Databricks and Lakehouse require a catalog selection; all others go straight to schema.
const DB_TYPES_WITH_CATALOG = ['databricks', 'lakehouse'];

function updateSchemaTableLabels(selectEl, prefix) {
    const labelSchema = document.getElementById(`label-${prefix}-schema`);
    const labelTable = document.getElementById(`label-${prefix}-table`);
    if (!labelSchema || !labelTable) return;

    const selectedOpt = selectEl.selectedOptions[0];
    const connType = selectedOpt ? selectedOpt.getAttribute('data-type') : '';

    if (connType === 'azure_blob') {
        labelSchema.textContent = 'Folder';
        labelTable.textContent = 'File *';
    } else {
        labelSchema.textContent = 'Schema';
        labelTable.textContent = 'Table *';
    }
}

async function handleConnectionChange(selectEl, prefix) {
    const connId = selectEl.value;
    const catalogGroup = document.getElementById(`${prefix}-catalog-group`);
    const catalogSelect = document.getElementById(`${prefix}-catalog`);

    // Reset all downstream fields
    if (catalogGroup) catalogGroup.style.display = 'none';
    if (catalogSelect) catalogSelect.innerHTML = '<option value="">-- Select --</option>';
    clearSelect(`${prefix}-schema`);
    clearSelect(`${prefix}-table`);
    clearColumnList(prefix);

    updateSchemaTableLabels(selectEl, prefix);

    if (!connId) return;

    const selectedOpt = selectEl.selectedOptions[0];
    const connType = selectedOpt ? selectedOpt.getAttribute('data-type') : '';

    // For all database types: show catalog first (strict hierarchy)
    if (DB_TYPES_WITH_CATALOG.includes(connType)) {
        if (catalogGroup) catalogGroup.style.display = 'block';
        await loadCatalogs(connId, prefix);
    } else {
        // File connections — go straight to schemas/tables
        await loadSchemas(connId, prefix);
    }
}

function loadCatalogs(connId, prefix) {
    const select = document.getElementById(`${prefix}-catalog`);
    const catalogGroup = document.getElementById(`${prefix}-catalog-group`);
    if (!select) return Promise.resolve();

    if (catalogGroup) catalogGroup.style.display = 'block';
    select.innerHTML = '<option value="">Loading...</option>';
    clearSelect(`${prefix}-schema`);
    clearSelect(`${prefix}-table`);
    clearColumnList(prefix);

    return fetch(`/connections/api/catalogs/?connection_id=${connId}`)
        .then(r => r.json())
        .then(data => {
            select.innerHTML = '<option value="">-- Select Catalog --</option>';
            if (data.catalogs && data.catalogs.length > 0) {
                data.catalogs.forEach(catalog => {
                    const opt = document.createElement('option');
                    opt.value = catalog;
                    opt.textContent = catalog;
                    select.appendChild(opt);
                });
                // Auto-select if there is only one catalog (e.g. Oracle service name)
                if (data.catalogs.length === 1) {
                    select.value = data.catalogs[0];
                    return loadSchemas(connId, prefix, data.catalogs[0]);
                }
                // For draft restore, caller sets the value manually
            }
        })
        .catch(err => {
            select.innerHTML = '<option value="">Error loading catalogs</option>';
            showToast('Failed to load catalogs', 'error');
        });
}

function loadSchemas(connId, prefix, catalog = '') {
    const select = document.getElementById(`${prefix}-schema`);
    if (!select) return Promise.resolve();

    select.innerHTML = '<option value="">Loading...</option>';
    clearSelect(`${prefix}-table`);
    clearColumnList(prefix);

    let url = `/connections/api/schemas/?connection_id=${connId}`;
    if (catalog) {
        url += `&catalog=${encodeURIComponent(catalog)}`;
    }

    return fetch(url)
        .then(r => r.json())
        .then(data => {
            if (data.is_file) {
                // File-based connections — auto-load tables
                select.innerHTML = '<option value="file">File</option>';
                return loadTables(connId, 'file', prefix);
            }
            select.innerHTML = '<option value="">-- Select Schema --</option>';
            if (data.schemas && data.schemas.length > 0) {
                data.schemas.forEach(schema => {
                    const opt = document.createElement('option');
                    opt.value = schema;
                    opt.textContent = schema;
                    select.appendChild(opt);
                });
                // Strict hierarchy: user must pick schema manually — no auto-cascade
                // Exception: when restoring drafts the caller sets the value
            }
        })
        .catch(err => {
            select.innerHTML = '<option value="">Error loading schemas</option>';
            showToast('Failed to load schemas', 'error');
        });
}

function loadTables(connId, schema, prefix, catalog = '') {
    const select = document.getElementById(`${prefix}-table`);
    if (!select) return Promise.resolve();

    select.innerHTML = '<option value="">Loading...</option>';
    clearColumnList(prefix);

    let url = `/connections/api/tables/?connection_id=${connId}&schema=${encodeURIComponent(schema)}`;
    if (catalog) {
        url += `&catalog=${encodeURIComponent(catalog)}`;
    }

    return fetch(url)
        .then(r => r.json())
        .then(data => {
            select.innerHTML = '<option value="">-- Select Table --</option>';
            if (data.tables && data.tables.length > 0) {
                data.tables.forEach(table => {
                    const opt = document.createElement('option');
                    opt.value = table;
                    opt.textContent = table;
                    select.appendChild(opt);
                });
            }
            // Strict hierarchy: user must select table explicitly — no auto-cascade to columns
            if (!window.isRestoringDraft) {
                select.value = '';
            }
            updateTablePreviewLink(prefix);
        })
        .catch(err => {
            select.innerHTML = '<option value="">Error loading tables</option>';
            showToast('Failed to load tables', 'error');
            updateTablePreviewLink(prefix);
        });
}

function loadColumns(connId, schema, table, prefix, catalog = '') {
    const select = document.getElementById(`${prefix}-column-select`);
    if (!select) return Promise.resolve();

    select.innerHTML = '<option value="">Loading...</option>';

    let url = `/connections/api/columns/?connection_id=${connId}&schema=${encodeURIComponent(schema)}&table=${encodeURIComponent(table)}`;
    if (catalog) {
        url += `&catalog=${encodeURIComponent(catalog)}`;
    }

    return fetch(url)
        .then(r => r.json())
        .then(data => {
            select.innerHTML = '<option value="">Select Column</option>';
            if (data.columns && data.columns.length > 0) {
                if (prefix === 'source') {
                    window.sourceColumnsList = data.columns;
                } else if (prefix === 'target') {
                    window.targetColumnsList = data.columns;
                }
                data.columns.forEach(col => {
                    const opt = document.createElement('option');
                    opt.value = col.name;
                    opt.dataset.datatype = col.type;
                    opt.textContent = `${col.name} (${col.type})`;
                    select.appendChild(opt);
                });

                // Populate separate Date Column dropdown based on prefix (source or target)
                const dateFilterSelect = document.getElementById(`${prefix}-date-column`);
                if (dateFilterSelect) {
                    dateFilterSelect.innerHTML = '<option value="">-- Select Date Column --</option>';
                    data.columns.forEach(col => {
                        if (isDateDatatype(col.type, col.name)) {
                            const opt = document.createElement('option');
                            opt.value = col.name;
                            opt.textContent = `${col.name} (${col.type})`;
                            dateFilterSelect.appendChild(opt);
                        }
                    });
                }

                // Populate checklists for Multiple Columns Mode
                const checklistContainer = document.getElementById(`${prefix}-columns-checkboxes-list`);
                if (checklistContainer) {
                    checklistContainer.innerHTML = '';
                    
                    // Add Search Input if not exists
                    let searchInput = document.getElementById(`${prefix}-columns-search-input`);
                    if (!searchInput) {
                        searchInput = document.createElement('input');
                        searchInput.type = 'text';
                        searchInput.id = `${prefix}-columns-search-input`;
                        searchInput.placeholder = `Search ${prefix} columns...`;
                        searchInput.className = 'form-control form-control-sm';
                        searchInput.style.marginBottom = '8px';
                        searchInput.style.padding = '6px 10px';
                        searchInput.style.fontSize = '0.85rem';
                        searchInput.style.borderRadius = 'var(--radius-sm)';
                        searchInput.style.border = '1px solid var(--border-medium)';
                        searchInput.style.backgroundColor = 'var(--bg-input)';
                        searchInput.style.color = 'var(--text-primary)';
                        
                        // Insert search input right before the checklist container
                        checklistContainer.parentNode.insertBefore(searchInput, checklistContainer);
                        
                        // Add filter event listener
                        searchInput.addEventListener('input', function() {
                            const query = this.value.toLowerCase();
                            const items = checklistContainer.querySelectorAll(`.${prefix}-column-list-item`);
                            items.forEach(item => {
                                const colName = item.querySelector('input').value.toLowerCase();
                                if (colName.includes(query)) {
                                    item.style.display = 'flex';
                                } else {
                                    item.style.display = 'none';
                                }
                            });
                        });
                    }
                    
                    // Make sure search input is visible and reset
                    searchInput.style.display = 'block';
                    searchInput.value = '';

                    data.columns.forEach(col => {
                        const div = document.createElement('div');
                        div.className = `${prefix}-column-list-item`;
                        div.style.display = 'flex';
                        div.style.justifyContent = 'space-between';
                        div.style.alignItems = 'center';
                        div.style.padding = '6px 8px';
                        div.style.borderBottom = '1px solid var(--border-light)';
                        
                        let extraHtml = '';
                        if (prefix === 'source') {
                            const sCat = categorizeDatatype(col.type, col.name);
                            const ops = OP_LISTS[sCat] || OP_LISTS.VARCHAR;
                            extraHtml = `
                                <div class="custom-multiselect op-dropdown-wrapper" style="width: 140px; margin-left: 12px; display: none; position: relative;">
                                    <div class="multiselect-select-box" onclick="toggleOpsDropdown(this)" style="padding: 4px 8px; font-size: 0.75rem; min-height: 28px; line-height: 20px;">
                                        <span class="multi-ops-count-span">Choose Validation</span>
                                    </div>
                                    <div class="multiselect-checkboxes" style="display: none; padding: 6px; position: absolute; z-index: 1000; background: var(--bg-card); border: 1px solid var(--border-medium); border-radius: var(--radius-sm); box-shadow: var(--shadow-md); width: 180px; right: 0;">
                            `;
                            ops.forEach(op => {
                                extraHtml += `
                                        <label style="display: flex; align-items: center; gap: 6px; cursor: pointer; padding: 2px 4px; font-size: 0.75rem; margin: 0; font-weight: 500; width: 100%;">
                                            <input type="checkbox" value="${op.value}" class="multi-op-cb" checked> ${op.label}
                                        </label>
                                `;
                            });
                            extraHtml += `
                                    </div>
                                </div>
                            `;
                        }

                        div.innerHTML = `
                            <label style="display: flex; align-items: center; gap: 8px; cursor: pointer; margin: 0; font-size: 0.85rem; font-weight: 500; flex: 1;">
                                <input type="checkbox" class="${prefix}-col-cb" value="${col.name}" data-datatype="${col.type}">
                                <span>${col.name} <span style="font-size: 0.75rem; color: var(--text-muted);">(${col.type})</span></span>
                            </label>
                            ${extraHtml}
                        `;
                        
                        const cb = div.querySelector(`.${prefix}-col-cb`);
                        cb.addEventListener('change', () => {
                            if (prefix === 'source') {
                                const wrapper = div.querySelector('.op-dropdown-wrapper');
                                if (cb.checked) {
                                    wrapper.style.display = 'block';
                                    // Auto-check target column with the same name if exists
                                    const tgtCb = document.querySelector(`.target-col-cb[value="${cb.value}"]`);
                                    if (tgtCb) {
                                        tgtCb.checked = true;
                                    }
                                } else {
                                    wrapper.style.display = 'none';
                                }
                            }
                            handleColumnSelectionChange();
                        });

                        if (prefix === 'source') {
                            const checkboxes = div.querySelectorAll('.multi-op-cb');
                            checkboxes.forEach(opCb => {
                                opCb.addEventListener('change', () => {
                                    updateListItemOpsCount(div);
                                    handleColumnSelectionChange();
                                });
                            });
                            updateListItemOpsCount(div);
                        }

                        checklistContainer.appendChild(div);
                    });
                }
            } else {
                select.innerHTML = '<option value="">No columns found</option>';
            }
            if (typeof checkTableSelections === 'function') {
                checkTableSelections();
            }
            if (typeof handleColumnSelectionChange === 'function') {
                handleColumnSelectionChange();
            }
        })
        .catch(err => {
            select.innerHTML = '<option value="">Error loading columns</option>';
            showToast('Failed to load columns', 'error');
        });
}
function clearSelect(id) {
    const select = document.getElementById(id);
    if (select) {
        select.innerHTML = '<option value="">-- Select --</option>';
    }
}

function clearColumnList(prefix) {
    const select = document.getElementById(`${prefix}-column-select`);
    if (select) {
        select.innerHTML = '<option value="">Select a table to view columns</option>';
    }
    const dateFilterSelect = document.getElementById(`${prefix}-date-column`);
    if (dateFilterSelect) {
        dateFilterSelect.innerHTML = '<option value="">-- Select Date Column --</option>';
    }
    const checklist = document.getElementById(`${prefix}-columns-checkboxes-list`);
    if (checklist) {
        checklist.innerHTML = '';
    }
    const manualTableBody = document.getElementById('manual-mappings-table-body');
    if (manualTableBody) {
        manualTableBody.innerHTML = '';
    }
    const searchInput = document.getElementById(`${prefix}-columns-search-input`);
    if (searchInput) {
        searchInput.style.display = 'none';
        searchInput.value = '';
    }
    if (typeof checkTableSelections === 'function') {
        checkTableSelections();
    }
}

// ─── Validation Progress Polling ────────────────────────────────────────────
function pollValidationProgress(runId) {
    const progressBar = document.getElementById(`progress-fill-${runId}`);
    const progressValue = document.getElementById(`progress-value-${runId}`);
    const statusBadge = document.getElementById(`status-badge-${runId}`);
    const passedVal = document.getElementById(`passed-checks-${runId}`);
    const failedVal = document.getElementById(`failed-checks-${runId}`);
    const totalVal = document.getElementById(`total-checks-${runId}`);

    if (!progressBar) return;

    const poll = setInterval(() => {
        fetch(`/validations/api/progress/${runId}/`)
            .then(r => r.json())
            .then(data => {
                if (progressBar) {
                    progressBar.style.width = `${data.progress}%`;
                }
                if (progressValue) {
                    progressValue.textContent = `${data.progress}%`;
                }
                if (passedVal) {
                    passedVal.textContent = data.passed;
                }
                if (failedVal) {
                    failedVal.textContent = data.failed;
                }
                if (totalVal) {
                    totalVal.textContent = data.total;
                }
                if (statusBadge) {
                    statusBadge.className = `badge badge-dot ${data.status === 'completed' ? 'badge-success' : data.status === 'failed' ? 'badge-danger' : 'badge-warning'}`;
                    statusBadge.textContent = data.status.charAt(0).toUpperCase() + data.status.slice(1);
                }
                if (data.status === 'completed' || data.status === 'failed') {
                    clearInterval(poll);
                    if (data.status === 'completed') {
                        showToast('Validation completed successfully!', 'success');
                    } else {
                        showToast('Validation failed. Check logs for details.', 'error');
                    }
                    // Reload to show updated results
                    setTimeout(() => location.reload(), 1500);
                }
            })
            .catch(() => clearInterval(poll));
    }, 3000);
}


// ─── Manual Trigger ETL ──────────────────────────────────────────────
function closeETLValidationModal() {
    const modal = document.getElementById('etl-validation-modal');
    if (modal) {
        modal.classList.remove('active');
        setTimeout(() => modal.remove(), 300);
    }
}

function triggerETL(mappingId) {
    // 1. Create and Append Modal Dynamically
    let modalHTML = `
    <div id="etl-validation-modal" class="modal-overlay">
        <div class="modal" style="padding: 28px; max-width: 600px; width: 90%; position: relative;">
            <div class="modal-header" style="padding: 0 0 16px; border-bottom: 1px solid var(--border-light); display: flex; justify-content: space-between; align-items: center;">
                <h3 style="font-size: var(--font-size-lg); font-weight: 700; color: var(--text-primary); margin: 0; display: flex; align-items: center; gap: 8px;">
                    <i class="fas fa-check-circle" style="color: var(--primary);"></i> Pre-Run Validation Checks
                </h3>
                <button type="button" class="modal-close" onclick="closeETLValidationModal()" style="border: none; background: var(--bg-hover); color: var(--text-secondary); width: 32px; height: 32px; border-radius: var(--radius-md); cursor: pointer; display: flex; align-items: center; justify-content: center; font-size: 1.2rem;">&times;</button>
            </div>
            <div class="modal-body" style="padding: 20px 0 0;">
                <div id="validation-checks-loading" style="text-align: center; padding: 24px;">
                    <i class="fas fa-spinner fa-spin" style="font-size: 2rem; color: var(--primary); margin-bottom: 12px; display: block; margin-left: auto; margin-right: auto;"></i>
                    <p style="color: var(--text-secondary); margin: 0; font-size: 0.9rem;">Running checks on connection, tables, columns, and datatypes...</p>
                </div>
                <div id="validation-checks-list" style="display: none; flex-direction: column; gap: 12px; max-height: 280px; overflow-y: auto; padding-right: 8px;">
                    <!-- Populated dynamically -->
                </div>
                <div id="validation-warning-message" style="display: none; margin-top: 20px; padding: 16px; background: #FFFBEB; border-left: 4px solid #D97706; border-radius: var(--radius-md); color: #78350F; font-size: 0.9rem;">
                    <div style="display: flex; gap: 8px; align-items: flex-start;">
                        <i class="fas fa-exclamation-triangle" style="margin-top: 2px;"></i>
                        <div>
                            <strong>Full Load Warning:</strong> Full Load will clear the existing target data and load the selected source dataset. Do you want to continue?
                        </div>
                    </div>
                </div>
                <div id="validation-error-message" style="display: none; margin-top: 20px; padding: 16px; background: #FEF2F2; border-left: 4px solid #DC2626; border-radius: var(--radius-md); color: #991B1B; font-size: 0.9rem;">
                    <div style="display: flex; gap: 8px; align-items: flex-start;">
                        <i class="fas fa-times-circle" style="margin-top: 2px;"></i>
                        <div>
                            <strong>Critical Errors Detected:</strong> Please fix the errors in connection or schema mapping before triggering the ETL load.
                        </div>
                    </div>
                </div>
            </div>
            <div class="modal-footer" style="padding: 16px 0 0; border-top: 1px solid var(--border-light); display: flex; justify-content: flex-end; gap: 12px; margin-top: 20px; margin-bottom: 0;">
                <button type="button" class="btn btn-secondary" onclick="closeETLValidationModal()" style="height: 38px; padding: 0 18px; border-radius: var(--radius-sm); background: #fff; border: 1px solid var(--border-medium); color: var(--text-secondary); font-weight: 500; cursor: pointer;">Cancel</button>
                <button type="button" id="confirm-etl-run-btn" class="btn btn-primary" style="height: 38px; padding: 0 18px; border-radius: var(--radius-sm); background: var(--primary); color: white; border: none; font-weight: 500; cursor: pointer; display: none;">Confirm & Run</button>
            </div>
        </div>
    </div>
    `;

    document.body.insertAdjacentHTML('beforeend', modalHTML);
    const modalElement = document.getElementById('etl-validation-modal');
    setTimeout(() => modalElement.classList.add('active'), 50);

    // 2. Fetch and run checks
    fetch(`/validations/api/validate/${mappingId}/`)
        .then(r => r.json())
        .then(data => {
            document.getElementById('validation-checks-loading').style.display = 'none';
            const listContainer = document.getElementById('validation-checks-list');
            listContainer.style.display = 'flex';

            let listHTML = '';
            data.validations.forEach(check => {
                let iconClass = 'fa-check-circle text-success';
                let bgStyle = 'background: #F0FDF4; border: 1px solid #DCFCE7; color: #166534;';
                if (check.status === 'error') {
                    iconClass = 'fa-times-circle text-danger';
                    bgStyle = 'background: #FEF2F2; border: 1px solid #FEE2E2; color: #991B1B;';
                } else if (check.status === 'warning') {
                    iconClass = 'fa-exclamation-triangle text-warning';
                    bgStyle = 'background: #FFFBEB; border: 1px solid #FEF3C7; color: #78350F;';
                }

                listHTML += `
                <div style="padding: 10px 14px; border-radius: var(--radius-md); font-size: 0.85rem; display: flex; align-items: flex-start; gap: 10px; ${bgStyle}">
                    <i class="fas ${iconClass}" style="margin-top: 3px; font-size: 1rem;"></i>
                    <div style="flex-grow: 1;">
                        <strong style="display: block; font-weight: 600; margin-bottom: 2px;">${check.name}</strong>
                        <span style="font-size: 0.8rem; line-height: 1.2;">${check.message}</span>
                    </div>
                </div>
                `;
            });
            listContainer.innerHTML = listHTML;

            // Show appropriate warning or error box
            if (data.success) {
                document.getElementById('validation-warning-message').style.display = 'block';
                const runBtn = document.getElementById('confirm-etl-run-btn');
                runBtn.style.display = 'block';
                runBtn.onclick = () => executeETLLoad(mappingId);
            } else {
                document.getElementById('validation-error-message').style.display = 'block';
            }
        })
        .catch(err => {
            console.error(err);
            showToast('Failed to execute pre-run validations.', 'error');
            closeETLValidationModal();
        });
}

function executeETLLoad(mappingId) {
    closeETLValidationModal();
    showToast('Triggering ETL Run...', 'info');

    // First fetch if any parameter-based rules are active
    fetch(`/validations/api/mapping/${mappingId}/rules-metadata/`)
        .then(r => r.json())
        .then(meta => {
            let parameters = {};
            if (meta.requires_parameters) {
                for (const rule of meta.rules) {
                    let promptMsg = `Enter input parameter for column "${rule.column}" (${rule.operation_display}):`;
                    let userInput = prompt(promptMsg);
                    if (userInput === null) {
                        showToast('ETL run cancelled.', 'warning');
                        return;
                    }
                    parameters[`${rule.column}:${rule.operation}`] = userInput;
                }
            }

            // Trigger execution
            fetchWithCSRF(`/validations/api/trigger/${mappingId}/`, {
                method: 'POST',
                body: JSON.stringify({ parameters: parameters })
            })
            .then(r => r.json())
            .then(data => {
                if (data.success) {
                    showToast('ETL Run triggered successfully!', 'success');
                    if (data.run_id) {
                        pollValidationProgress(data.run_id);
                    }
                    setTimeout(() => location.reload(), 1000);
                } else {
                    showToast(data.error || 'Failed to trigger ETL run', 'error');
                }
            })
            .catch(() => showToast('Network error', 'error'));
        })
        .catch(() => showToast('Failed to check pipeline metadata', 'error'));
}

// ─── Trigger Workflow ───────────────────────────────────────────────────────
function triggerWorkflow(workflowId) {
    if (!confirm('Manually trigger this workflow now?')) return;

    fetchWithCSRF(`/workflows/api/trigger/${workflowId}/`, { method: 'POST' })
        .then(r => r.json())
        .then(data => {
            if (data.success) {
                showToast('Workflow triggered!', 'success');
                setTimeout(() => location.reload(), 1000);
            } else {
                showToast(data.error || 'Failed to trigger workflow', 'error');
            }
        })
        .catch(() => showToast('Network error', 'error'));
}

// ─── Toggle Workflow Active State ───────────────────────────────────────────
function toggleWorkflow(workflowId, isActive) {
    fetchWithCSRF(`/workflows/api/toggle/${workflowId}/`, {
        method: 'POST',
        body: JSON.stringify({ is_active: isActive }),
    })
        .then(r => r.json())
        .then(data => {
            if (data.success) {
                showToast(`Workflow ${isActive ? 'activated' : 'deactivated'}`, 'success');
            }
        })
        .catch(() => showToast('Failed to update workflow', 'error'));
}

// ─── Test Connection ────────────────────────────────────────────────────────
function testConnection(connId) {
    const btn = event ? event.target : null;
    let originalText = '';
    if (btn) {
        originalText = btn.textContent;
        btn.textContent = 'Testing...';
        btn.disabled = true;
    }

    fetch(`/connections/api/test/${connId}/`)
        .then(r => r.json())
        .then(data => {
            const statusCol = document.getElementById(`conn-status-${connId}`);
            if (data.success) {
                showToast('Connection successful!', 'success');
                if (statusCol) {
                    statusCol.className = 'badge badge-success badge-dot';
                    statusCol.textContent = 'Connected';
                }
            } else {
                showToast(`Connection failed: ${data.message || data.error || 'Unknown error'}`, 'error');
                if (statusCol) {
                    statusCol.className = 'badge badge-danger badge-dot';
                    statusCol.textContent = 'Failed';
                }
            }
        })
        .catch(() => showToast('Network error', 'error'))
        .finally(() => {
            if (btn) {
                btn.textContent = originalText;
                btn.disabled = false;
            }
        });
}

// ─── Delete Confirmation ────────────────────────────────────────────────────
function confirmDelete(url, itemName) {
    if (confirm(`Are you sure you want to delete "${itemName}"? This action cannot be undone.`)) {
        fetchWithCSRF(url, { method: 'DELETE' })
            .then(r => {
                if (r.ok) {
                    showToast(`"${itemName}" deleted successfully`, 'success');
                    setTimeout(() => location.reload(), 500);
                } else {
                    showToast('Failed to delete', 'error');
                }
            })
            .catch(() => showToast('Network error', 'error'));
    }
}

// ─── Export Report ──────────────────────────────────────────────────────────
function exportReport(runId, format) {
    window.location.href = `/validations/export/${runId}/?format=${format}`;
}

// ─── Date Filter Toggle ────────────────────────────────────────────────────
function toggleDateFilter(type) {
    const rangeFields = document.getElementById('date-range-fields');
    const specificField = document.getElementById('date-specific-field');

    if (rangeFields && specificField) {
        if (type === 'range') {
            rangeFields.style.display = 'flex';
            specificField.style.display = 'none';
        } else if (type === 'specific') {
            rangeFields.style.display = 'none';
            specificField.style.display = 'flex';
        } else {
            rangeFields.style.display = 'none';
            specificField.style.display = 'none';
        }
    }
}

// ─── Form Validation Helper ─────────────────────────────────────────────────
function validateForm(formId) {
    const form = document.getElementById(formId);
    if (!form) return true;

    let isValid = true;
    form.querySelectorAll('[required]').forEach(field => {
        if (!field.value.trim()) {
            field.style.borderColor = 'var(--danger)';
            isValid = false;
        } else {
            field.style.borderColor = '';
        }
    });

    if (!isValid) {
        showToast('Please fill in all required fields', 'warning');
    }
    return isValid;
}

// ─── Auto-dismiss alerts ────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.alert[data-auto-dismiss]').forEach(alert => {
        const delay = parseInt(alert.dataset.autoDismiss) || 5000;
        setTimeout(() => {
            alert.style.opacity = '0';
            alert.style.transform = 'translateY(-10px)';
            alert.style.transition = 'all 0.3s ease';
            setTimeout(() => alert.remove(), 300);
        }, delay);
    });
});

// ─── Form Draft Manager ──────────────────────────────────────────────────────
function saveFormDraft(formId, pageKey) {
    const jsonInput = document.getElementById('column-mappings-json');
    if (jsonInput && typeof getColumnMappingsJSON === 'function') {
        jsonInput.value = getColumnMappingsJSON();
    }
    const data = serializeForm(formId);
    return fetchWithCSRF('/dashboard/api/drafts/save/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ page_key: pageKey, data: data })
    })
    .then(r => r.json())
    .then(res => {
        if (res.success) {
            showToast('Progress saved as draft', 'success');
            return true;
        } else {
            showToast('Failed to save draft: ' + (res.error || 'Unknown error'), 'error');
            return false;
        }
    })
    .catch(() => {
        showToast('Error saving draft', 'error');
        return false;
    });
}

function discardFormDraft(formId, pageKey, onDiscardCallback) {
    if (!confirm('Are you sure you want to discard this draft? This will clear your unsaved progress.')) {
        return;
    }
    fetchWithCSRF('/dashboard/api/drafts/cancel/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ page_key: pageKey })
    })
    .then(r => r.json())
    .then(res => {
        if (res.success) {
            showToast('Draft discarded', 'info');
            // Hide the draft banner
            const banner = document.getElementById(`draft-banner-${pageKey}`);
            if (banner) banner.style.display = 'none';
            
            // Clear form
            if (onDiscardCallback) {
                onDiscardCallback();
            } else {
                const form = document.getElementById(formId);
                if (form) form.reset();
            }
        }
    })
    .catch(() => showToast('Error discarding draft', 'error'));
}

function serializeForm(formId) {
    const form = document.getElementById(formId);
    if (!form) return {};
    const data = {};
    form.querySelectorAll('input, select, textarea').forEach(el => {
        const name = el.name;
        if (!name || name === 'csrfmiddlewaretoken') return;

        if (el.type === 'checkbox') {
            if (!data[name]) {
                data[name] = [];
            }
            if (el.checked) {
                data[name].push(el.value);
            }
        } else if (el.type === 'radio') {
            if (el.checked) {
                data[name] = el.value;
            }
        } else {
            data[name] = el.value;
        }
    });
    return data;
}

function deserializeForm(formId, data) {
    const form = document.getElementById(formId);
    if (!form || !data) return;

    form.querySelectorAll('input, select, textarea').forEach(el => {
        const name = el.name;
        if (!name || !(name in data)) return;

        const val = data[name];
        if (el.type === 'checkbox') {
            el.checked = Array.isArray(val) ? val.includes(el.value) : (el.value === val);
            el.dispatchEvent(new Event('change'));
        } else if (el.type === 'radio') {
            el.checked = (el.value === val);
            el.dispatchEvent(new Event('change'));
        } else {
            el.value = val;
            el.dispatchEvent(new Event('change'));
        }
    });
}

async function restoreMappingDraft(data) {
    window.isRestoringDraft = true;
    try {
        // 1. Restore simple text / description fields safely
        const nameInput = document.querySelector('[name="name"]');
        if (nameInput) nameInput.value = data['name'] || '';
        const descInput = document.querySelector('[name="description"]');
        if (descInput) descInput.value = data['description'] || '';

        // Helper: restore a single side (source or target) of the connection cascade
        async function restoreConnSide(prefix, data) {
            console.log(`[restoreConnSide] Starting restoration for side: ${prefix}`);
            try {
                const connVal = data[`${prefix}_connection`];
                if (!connVal) {
                    console.log(`[restoreConnSide] No connection value found for side: ${prefix}`);
                    return;
                }
                const connSelect = document.getElementById(`${prefix}-connection`);
                if (!connSelect) {
                    console.warn(`[restoreConnSide] Connection select element not found for side: ${prefix}`);
                    return;
                }
                
                // Fallback: if connection option is not found in select dropdown (e.g. inactive)
                let connOptExists = Array.from(connSelect.options).some(o => o.value === String(connVal));
                if (!connOptExists) {
                    const opt = document.createElement('option');
                    opt.value = String(connVal);
                    opt.textContent = `Connection #${connVal} (Inactive/Saved)`;
                    const connTypeVal = data[`${prefix}_connection_type`] || '';
                    if (connTypeVal) {
                        opt.setAttribute('data-type', connTypeVal);
                    }
                    connSelect.appendChild(opt);
                }
                connSelect.value = String(connVal);

                const selectedOpt = connSelect.selectedOptions[0];
                const connType = selectedOpt ? selectedOpt.getAttribute('data-type') : '';
                const catalogVal = data[`${prefix}_catalog`];
                const schemaVal = data[`${prefix}_schema`];
                const tableVal = data[`${prefix}_table`];

                console.log(`[restoreConnSide] Side: ${prefix}, Connection ID: ${connVal}, Type: ${connType}, Catalog: ${catalogVal}, Schema: ${schemaVal}, Table: ${tableVal}`);

                if (DB_TYPES_WITH_CATALOG.includes(connType)) {
                    // Show catalog group and load catalogs
                    const catalogGroup = document.getElementById(`${prefix}-catalog-group`);
                    if (catalogGroup) catalogGroup.style.display = 'block';
                    
                    console.log(`[restoreConnSide] Side: ${prefix}, loading catalogs...`);
                    try {
                        await loadCatalogs(connVal, prefix);
                    } catch (e) {
                        console.error(`[restoreConnSide] Side: ${prefix}, loadCatalogs failed:`, e);
                    }

                    const catalogSelect = document.getElementById(`${prefix}-catalog`);
                    if (catalogSelect) {
                        // Fallback: if catalog option is not found in select dropdown (e.g. db offline/changed)
                        let catOptExists = Array.from(catalogSelect.options).some(o => o.value === String(catalogVal));
                        if (!catOptExists && catalogVal) {
                            const opt = document.createElement('option');
                            opt.value = String(catalogVal);
                            opt.textContent = String(catalogVal);
                            catalogSelect.appendChild(opt);
                        }
                        catalogSelect.value = String(catalogVal);
                    }
                    
                    console.log(`[restoreConnSide] Side: ${prefix}, loading schemas...`);
                    try {
                        // Load schemas regardless of catalogVal selection presence
                        await loadSchemas(connVal, prefix, catalogVal || '');
                    } catch (e) {
                        console.error(`[restoreConnSide] Side: ${prefix}, loadSchemas failed:`, e);
                    }

                    const schemaSelect = document.getElementById(`${prefix}-schema`);
                    if (schemaSelect) {
                        // Fallback: if schema option is not found in select dropdown
                        let schOptExists = Array.from(schemaSelect.options).some(o => o.value === String(schemaVal));
                        if (!schOptExists && schemaVal) {
                            const opt = document.createElement('option');
                            opt.value = String(schemaVal);
                            opt.textContent = String(schemaVal);
                            schemaSelect.appendChild(opt);
                        }
                        schemaSelect.value = schemaVal ? String(schemaVal) : '';
                    }

                    console.log(`[restoreConnSide] Side: ${prefix}, loading tables...`);
                    try {
                        await loadTables(connVal, schemaVal || '', prefix, catalogVal || '');
                    } catch (e) {
                        console.error(`[restoreConnSide] Side: ${prefix}, loadTables failed:`, e);
                    }

                    const tableSelect = document.getElementById(`${prefix}-table`);
                    if (tableSelect) {
                        // Fallback: if table option is not found in select dropdown
                        let tblOptExists = Array.from(tableSelect.options).some(o => o.value === String(tableVal));
                        if (!tblOptExists && tableVal) {
                            const opt = document.createElement('option');
                            opt.value = String(tableVal);
                            opt.textContent = String(tableVal);
                            tableSelect.appendChild(opt);
                        }
                        tableSelect.value = String(tableVal || '');
                    }

                    if (tableVal) {
                        console.log(`[restoreConnSide] Side: ${prefix}, loading columns...`);
                        try {
                            await loadColumns(connVal, schemaVal || '', tableVal, prefix, catalogVal || '');
                        } catch (e) {
                            console.error(`[restoreConnSide] Side: ${prefix}, loadColumns failed:`, e);
                        }
                        updateTablePreviewLink(prefix);
                    }
                } else {
                    // File connections or other DB connections without catalog
                    console.log(`[restoreConnSide] Side: ${prefix}, loading schemas (no catalog)...`);
                    try {
                        await loadSchemas(connVal, prefix);
                    } catch (e) {
                        console.error(`[restoreConnSide] Side: ${prefix}, loadSchemas failed:`, e);
                    }

                    const schemaSelect = document.getElementById(`${prefix}-schema`);
                    if (schemaSelect) {
                        // Fallback: if schema option is not found in select dropdown
                        let schOptExists = Array.from(schemaSelect.options).some(o => o.value === String(schemaVal));
                        if (!schOptExists && schemaVal) {
                            const opt = document.createElement('option');
                            opt.value = String(schemaVal);
                            opt.textContent = String(schemaVal);
                            schemaSelect.appendChild(opt);
                        }
                        schemaSelect.value = schemaVal ? String(schemaVal) : '';
                    }

                    console.log(`[restoreConnSide] Side: ${prefix}, loading tables (no catalog)...`);
                    try {
                        await loadTables(connVal, schemaVal || '', prefix);
                    } catch (e) {
                        console.error(`[restoreConnSide] Side: ${prefix}, loadTables failed:`, e);
                    }

                    const tableSelect = document.getElementById(`${prefix}-table`);
                    if (tableSelect) {
                        // Fallback: if table option is not found in select dropdown
                        let tblOptExists = Array.from(tableSelect.options).some(o => o.value === String(tableVal));
                        if (!tblOptExists && tableVal) {
                            const opt = document.createElement('option');
                            opt.value = String(tableVal);
                            opt.textContent = String(tableVal);
                            tableSelect.appendChild(opt);
                        }
                        tableSelect.value = String(tableVal || '');
                    }

                    if (tableVal) {
                        console.log(`[restoreConnSide] Side: ${prefix}, loading columns (no catalog)...`);
                        try {
                            await loadColumns(connVal, schemaVal || '', tableVal, prefix);
                        } catch (e) {
                            console.error(`[restoreConnSide] Side: ${prefix}, loadColumns failed:`, e);
                        }
                        updateTablePreviewLink(prefix);
                    }
                }
                console.log(`[restoreConnSide] Successfully finished restoration for side: ${prefix}`);
            } catch (err) {
                console.error(`[restoreConnSide] Critical error in restoreConnSide for side: ${prefix}:`, err);
            }
        }

        // 2. Restore Source Connection cascade
        try {
            console.log("Starting source side restoration...");
            await restoreConnSide('source', data);
        } catch (e) {
            console.error("Uncaught exception in source side restoration:", e);
        }

        // 3. Restore Target Connection cascade
        try {
            console.log("Starting target side restoration...");
            await restoreConnSide('target', data);
        } catch (e) {
            console.error("Uncaught exception in target side restoration:", e);
        }

        // 4. Restore Column Selection Mode and choices
        let mode = 'single';
        if (data['column_selection_mode']) {
            mode = data['column_selection_mode'];
        } else if (data['source_columns'] === '__all__' || data['target_columns'] === '__all__') {
            mode = 'all';
        } else if (Array.isArray(data['source_columns']) && data['source_columns'].length > 1) {
            mode = 'multiple';
        }
        
        const modeRadio = document.querySelector(`input[name="column_selection_mode"][value="${mode}"]`);
        if (modeRadio) {
            modeRadio.checked = true;
        }
        handleColumnModeChange(); // Initialize the mode UI

        const currentMode = getColumnSelectionMode();
        if (currentMode === 'single') {
            const sourceColVal = data['source_columns'];
            const sourceColSelect = document.getElementById('source-column-select');
            if (sourceColVal && sourceColSelect) {
                const sVal = Array.isArray(sourceColVal) ? sourceColVal[0] : sourceColVal;
                // Fallback: if column option is not found in select dropdown
                let sColOptExists = Array.from(sourceColSelect.options).some(o => o.value === String(sVal));
                if (!sColOptExists && sVal) {
                    const opt = document.createElement('option');
                    opt.value = String(sVal);
                    opt.textContent = String(sVal);
                    sourceColSelect.appendChild(opt);
                }
                sourceColSelect.value = sVal;
                renderSingleColumnOps('source');
            }

            const targetColVal = data['target_columns'];
            const targetColSelect = document.getElementById('target-column-select');
            if (targetColVal && targetColSelect) {
                const tVal = Array.isArray(targetColVal) ? targetColVal[0] : targetColVal;
                // Fallback: if column option is not found in select dropdown
                let tColOptExists = Array.from(targetColSelect.options).some(o => o.value === String(tVal));
                if (!tColOptExists && tVal) {
                    const opt = document.createElement('option');
                    opt.value = String(tVal);
                    opt.textContent = String(tVal);
                    targetColSelect.appendChild(opt);
                }
                targetColSelect.value = tVal;
                renderSingleColumnOps('target');
            }

            // Restore single operations
            const sOps = data['source_single_operations'] || data['operations'] || [];
            const tOps = data['target_single_operations'] || data['operations'] || [];
            const sOpsArr = Array.isArray(sOps) ? sOps : [sOps];
            const tOpsArr = Array.isArray(tOps) ? tOps : [tOps];

            setTimeout(() => {
                document.querySelectorAll('.source-single-op-cb').forEach(cb => {
                    cb.checked = sOpsArr.includes(cb.value);
                });
                updateSingleOpsCount('source');

                document.querySelectorAll('.target-single-op-cb').forEach(cb => {
                    cb.checked = tOpsArr.includes(cb.value);
                });
                updateSingleOpsCount('target');
            }, 100);
        } else if (currentMode === 'multiple') {
            const mappingsJSON = data['column_mappings_json'];
            if (mappingsJSON) {
                try {
                    const mappings = JSON.parse(mappingsJSON);
                    
                    // Populate source & target checklists and the operations inside row
                    setTimeout(() => {
                        mappings.forEach(m => {
                            const srcCbs = document.querySelectorAll('.source-col-cb');
                            const srcCb = Array.from(srcCbs).find(c => c.value === m.source_column);
                            if (srcCb) {
                                srcCb.checked = true;
                                const row = srcCb.closest('.source-column-list-item');
                                const wrapper = row.querySelector('.op-dropdown-wrapper');
                                if (wrapper) wrapper.style.display = 'block';
                                
                                const opCbs = row.querySelectorAll('.multi-op-cb');
                                opCbs.forEach(cb => {
                                    cb.checked = m.operations.includes(cb.value);
                                });
                                updateListItemOpsCount(row);
                            }

                            const tgtCbs = document.querySelectorAll('.target-col-cb');
                            const tgtCb = Array.from(tgtCbs).find(c => c.value === m.target_column);
                            if (tgtCb) {
                                tgtCb.checked = true;
                            }
                        });
                        handleColumnSelectionChange();
                    }, 200);
                } catch (e) {
                    console.error("Failed to parse draft column mappings JSON", e);
                }
            }
        } else if (currentMode === 'manual') {
            const mappingsJSON = data['column_mappings_json'];
            if (mappingsJSON) {
                try {
                    const mappings = JSON.parse(mappingsJSON);
                    const tableBody = document.getElementById('manual-mappings-table-body');
                    if (tableBody) {
                        tableBody.innerHTML = '';
                    }
                    setTimeout(() => {
                        mappings.forEach(m => {
                            addManualMappingRow(m);
                        });
                    }, 200);
                } catch (e) {
                    console.error("Failed to parse draft column mappings JSON", e);
                }
            }
        } else if (currentMode === 'all') {
            const mappingsJSON = data['column_mappings_json'];
            if (mappingsJSON) {
                try {
                    const mappings = JSON.parse(mappingsJSON);
                    if (mappings.length > 0 && mappings[0].operations) {
                        const ops = mappings[0].operations;
                        setTimeout(() => {
                            document.querySelectorAll('.all-op-cb').forEach(cb => {
                                cb.checked = ops.includes(cb.value);
                            });
                            const selectAllRadio = document.getElementById('all-ops-select-all');
                            const deselectAllRadio = document.getElementById('all-ops-deselect-all');
                            if (selectAllRadio && deselectAllRadio) {
                                selectAllRadio.checked = (ops.length === 19);
                                deselectAllRadio.checked = (ops.length === 0);
                            }
                        }, 200);
                    }
                } catch (e) {
                    console.error("Failed to parse draft column mappings JSON", e);
                }
            }
        }

        // 6. Restore new separate Date Filter inputs
        const filterTypes = ['source', 'target'];
        filterTypes.forEach(prefix => {
            const dateColumn = data[`${prefix}_date_column`] || '';
            const filterType = data[`${prefix}_date_filter_type`] || 'none';
            const dateSingle = data[`${prefix}_date_single`] || '';
            const filterStart = data[`${prefix}_date_filter_start`] || '';
            const filterEnd = data[`${prefix}_date_filter_end`] || '';

            const dateColSelect = document.getElementById(`${prefix}-date-column`);
            if (dateColSelect) {
                dateColSelect.value = dateColumn;
            }

            const radioBtn = document.querySelector(`input[name="${prefix}_date_filter_type"][value="${filterType}"]`);
            if (radioBtn) {
                radioBtn.checked = true;
                toggleDateFilterInputs(prefix, filterType);
            }

            const includeTimestampCb = document.getElementById(`${prefix}-include-timestamp`);
            if (includeTimestampCb) {
                const isTimestamp = dateSingle.includes('T') || filterStart.includes('T') || dateSingle.includes(':') || filterStart.includes(':');
                includeTimestampCb.checked = isTimestamp;
                toggleTimeFormat(prefix);
            }

            const singleOpSelect = document.getElementById(`${prefix}-date-operator`);
            if (singleOpSelect) {
                singleOpSelect.value = data[`${prefix}_date_operator`] || '=';
            }

            const singleInput = document.getElementById(`${prefix}-date-single`);
            if (singleInput) {
                singleInput.value = dateSingle;
            }

            const startInput = document.getElementById(`${prefix}-date-filter-start`);
            if (startInput) {
                startInput.value = filterStart;
            }

            const startOpSelect = document.getElementById(`${prefix}-date-range-operator-start`);
            if (startOpSelect) {
                startOpSelect.value = data[`${prefix}_date_range_operator_start`] || '>=';
            }

            const endOpSelect = document.getElementById(`${prefix}-date-range-operator-end`);
            if (endOpSelect) {
                endOpSelect.value = data[`${prefix}_date_range_operator_end`] || '<=';
            }

            const endInput = document.getElementById(`${prefix}-date-filter-end`);
            if (endInput) {
                endInput.value = filterEnd;
            }
        });

        // 7. Fallback to old single Date Filter inputs if present
        if (data['date_filter_column']) {
            const dateFilterColSelect = document.getElementById('date-filter-column');
            if (dateFilterColSelect) {
                dateFilterColSelect.value = data['date_filter_column'];
                dateFilterColSelect.dispatchEvent(new Event('change'));
            }
        }
        const dateStartInput = document.getElementById('date-filter-start');
        if (dateStartInput && data['date_filter_start']) {
            dateStartInput.value = data['date_filter_start'];
        }
        const dateEndInput = document.getElementById('date-filter-end');
        if (dateEndInput && data['date_filter_end']) {
            dateEndInput.value = data['date_filter_end'];
        }
    } finally {
        window.isRestoringDraft = false;
    }
}

function setupFormDraftManager(formId, pageKey, options = {}) {
    const form = document.getElementById(formId);
    if (!form) return;

    fetch(`/dashboard/api/drafts/get/?page_key=${pageKey}`)
        .then(r => r.json())
        .then(res => {
            if (res.success && res.data) {
                const draftData = res.data;
                
                // Show Banner
                const banner = document.getElementById(`draft-banner-${pageKey}`);
                if (banner) {
                    banner.style.display = 'block';
                    
                    // Hook up Resume Button
                    const resumeBtn = document.getElementById(`resume-draft-btn-${pageKey}`);
                    if (resumeBtn) {
                        resumeBtn.onclick = () => {
                            if (options.onRestore) {
                                options.onRestore(draftData);
                            } else {
                                deserializeForm(formId, draftData);
                            }
                            showToast('Draft restored successfully', 'success');
                        };
                    }

                    // Hook up Discard Button
                    const discardBtn = document.getElementById(`discard-draft-btn-${pageKey}`);
                    if (discardBtn) {
                        discardBtn.onclick = () => {
                            discardFormDraft(formId, pageKey, options.onDiscard);
                        };
                    }
                }

                // Restore automatically as requested by "Draft restored automatically"
                if (options.onRestore) {
                    options.onRestore(draftData);
                } else {
                    deserializeForm(formId, draftData);
                }
            }
        })
        .catch(err => console.error('Error loading draft', err));
}

// ─── New Dynamic Validation Rules & Date Filter Utilities ───────────────────
const OP_LISTS = {
    VARCHAR: [
        { value: 'null_check', label: 'Null Check' },
        { value: 'length_sum_check', label: 'Length Check' },
        { value: 'sum_length', label: 'Sum Length' },
        { value: 'duplicate_check', label: 'Duplicate Check' },
        { value: 'pattern_match', label: 'Pattern Match' },
        { value: 'count', label: 'Count' },
        { value: 'row_count', label: 'Row Count Match' },
        { value: 'unique_check', label: 'Unique Check' },
        { value: 'distinct_count', label: 'Distinct Count' },
        { value: 'data_type_check', label: 'Data Type Check' }
    ],
    INTEGER: [
        { value: 'null_check', label: 'Null Check' },
        { value: 'sum', label: 'Sum' },
        { value: 'avg', label: 'Average' },
        { value: 'min', label: 'Min' },
        { value: 'max', label: 'Max' },
        { value: 'duplicate_check', label: 'Duplicate Check' },
        { value: 'count', label: 'Count' },
        { value: 'row_count', label: 'Row Count Match' },
        { value: 'unique_check', label: 'Unique Check' },
        { value: 'distinct_count', label: 'Distinct Count' },
        { value: 'data_type_check', label: 'Data Type Check' },
        { value: 'std_dev', label: 'Standard Deviation' },
        { value: 'variance', label: 'Variance' },
        { value: 'median', label: 'Median' },
        { value: 'mode', label: 'Mode' }
    ],
    DATE: [
        { value: 'null_check', label: 'Null Check' },
        { value: 'min_date', label: 'Min Date' },
        { value: 'max_date', label: 'Max Date' },
        { value: 'duplicate_check', label: 'Duplicate Check' },
        { value: 'count', label: 'Count' },
        { value: 'row_count', label: 'Row Count Match' },
        { value: 'unique_check', label: 'Unique Check' },
        { value: 'distinct_count', label: 'Distinct Count' }
    ],
    BOOLEAN: [
        { value: 'null_check', label: 'Null Check' },
        { value: 'duplicate_check', label: 'Duplicate Check' },
        { value: 'count', label: 'Count' },
        { value: 'row_count', label: 'Row Count Match' },
        { value: 'unique_check', label: 'Unique Check' },
        { value: 'distinct_count', label: 'Distinct Count' }
    ]
};

function updateListItemOpsCount(div) {
    const checked = div.querySelectorAll('.multi-op-cb:checked');
    const span = div.querySelector('.multi-ops-count-span');
    if (span) {
        if (checked.length === 0) {
            span.textContent = 'Choose Validation';
        } else {
            span.textContent = `${checked.length} Op(s)`;
        }
    }
}

function isDateDatatype(typeStr, nameStr = '') {
    const t = (typeStr || '').toLowerCase();
    const n = (nameStr || '').toLowerCase();
    return t.includes('date') || t.includes('time') || t.includes('timestamp') || t.includes('datetime') ||
           n.includes('date') || n.includes('time') || n.includes('timestamp') || n.includes('datetime') ||
           n.endsWith('_at') || n.endsWith('_on') || n === 'at' || n.includes('dt');
}

function categorizeDatatype(typeStr, nameStr = '') {
    const t = (typeStr || '').toUpperCase();
    const n = (nameStr || '').toUpperCase();
    if (t.includes('INT') || t.includes('BIGINT') || t.includes('SMALLINT') || t.includes('TINYINT') || t.includes('NUMERIC') || t.includes('DECIMAL') || t.includes('FLOAT') || t.includes('DOUBLE') || t.includes('REAL') || t.includes('NUMBER')) {
        return 'INTEGER';
    } else if (t.includes('DATE') || t.includes('TIME') || t.includes('TIMESTAMP') || n.includes('DATE') || n.includes('TIME') || n.includes('TIMESTAMP') || n.includes('DATETIME')) {
        return 'DATE';
    } else if (t.includes('BOOL') || t.includes('BOOLEAN')) {
        return 'BOOLEAN';
    }
    return 'VARCHAR';
}

function getColumnSelectionMode() {
    return document.querySelector('input[name="column_selection_mode"]:checked')?.value || 'single';
}

function renderSingleColumnOps(prefix) {
    const select = document.getElementById(`${prefix}-column-select`);
    const container = document.getElementById(`${prefix}-single-ops-container`);
    if (!select || !container) return;

    const col = select.value;
    if (!col) {
        container.innerHTML = '';
        container.style.display = 'none';
        return;
    }

    const opt = Array.from(select.options).find(o => o.value === col);
    const type = opt ? opt.dataset.datatype : 'unknown';
    const cat = categorizeDatatype(type, col);
    const ops = OP_LISTS[cat] || OP_LISTS.VARCHAR;

    let html = `
        <div class="form-group mb-0">
            <label style="font-size: 0.85rem; font-weight: 600; margin-bottom: 6px; display: block;">Validation Operations *</label>
            <div class="custom-multiselect" id="${prefix}-single-ops-multiselect" style="position: relative;">
                <div class="multiselect-select-box" onclick="toggleOpsDropdown(this)" style="padding: 6px 12px; font-size: 0.85rem;">
                    <span id="${prefix}-single-ops-selected-count">Select Operations</span>
                </div>
                <div class="multiselect-checkboxes" style="display: none; padding: 8px; position: absolute; z-index: 1000; background: var(--bg-card); border: 1px solid var(--border-medium); border-radius: var(--radius-sm); box-shadow: var(--shadow-md); width: 100%;">
    `;

    ops.forEach(op => {
        html += `
            <label style="display: flex; align-items: center; gap: 8px; cursor: pointer; padding: 4px 8px; font-size: 0.85rem; margin: 0; font-weight: 500;">
                <input type="checkbox" name="${prefix}_single_operations" value="${op.value}" class="${prefix}-single-op-cb" checked onchange="updateSingleOpsCount('${prefix}')"> ${op.label}
            </label>
        `;
    });

    html += `
                </div>
            </div>
        </div>
    `;
    container.innerHTML = html;
    container.style.display = 'block';
    updateSingleOpsCount(prefix);
}

function checkTableSelections() {
    const sourceTable = document.getElementById('source-table')?.value;
    const targetTable = document.getElementById('target-table')?.value;
    
    const sourceSection = document.getElementById('source-column-section');
    const targetSection = document.getElementById('target-column-section');
    const columnSelectionSection = document.getElementById('column-selection-section');
    const validationOpsSection = document.getElementById('validation-operations-section');
    
    if (sourceTable && targetTable) {
        if (sourceSection) sourceSection.style.display = 'block';
        if (targetSection) targetSection.style.display = 'block';
        if (columnSelectionSection) columnSelectionSection.style.display = 'block';
        
        const mode = getColumnSelectionMode();
        if (validationOpsSection) {
            if (mode === 'single') {
                validationOpsSection.style.display = 'none';
            } else {
                validationOpsSection.style.display = 'block';
            }
        }
    } else {
        if (sourceSection) sourceSection.style.display = 'none';
        if (targetSection) targetSection.style.display = 'none';
        if (columnSelectionSection) columnSelectionSection.style.display = 'none';
        if (validationOpsSection) validationOpsSection.style.display = 'none';
    }
}

function handleColumnModeChange() {
    const mode = getColumnSelectionMode();

    const sourceSelect = document.getElementById('source-column-select');
    const targetSelect = document.getElementById('target-column-select');
    
    const sourceSingleWrapper = document.getElementById('source-single-column-wrapper');
    const sourceMultiWrapper = document.getElementById('source-multiple-columns-wrapper');
    const targetSingleWrapper = document.getElementById('target-single-column-wrapper');
    const targetMultiWrapper = document.getElementById('target-multiple-columns-wrapper');
    const targetMultiMessage = document.getElementById('target-multiple-message');
    const manualMappingWrapper = document.getElementById('manual-mapping-wrapper');

    const sourceSingleOps = document.getElementById('source-single-ops-container');
    const targetSingleOps = document.getElementById('target-single-ops-container');

    const validationOpsSection = document.getElementById('validation-operations-section');

    if (mode === 'all') {
        if (sourceSingleWrapper) sourceSingleWrapper.style.display = 'none';
        if (sourceMultiWrapper) sourceMultiWrapper.style.display = 'none';
        if (targetSingleWrapper) targetSingleWrapper.style.display = 'none';
        if (targetMultiWrapper) targetMultiWrapper.style.display = 'none';
        if (targetMultiMessage) targetMultiMessage.style.display = 'none';
        if (manualMappingWrapper) manualMappingWrapper.style.display = 'none';
        if (sourceSingleOps) sourceSingleOps.style.display = 'none';
        if (targetSingleOps) targetSingleOps.style.display = 'none';
        
        if (sourceSelect) {
            sourceSelect.removeAttribute('multiple');
            sourceSelect.value = '__all__';
        }
        if (targetSelect) {
            targetSelect.removeAttribute('multiple');
            targetSelect.value = '__all__';
        }
        if (validationOpsSection) validationOpsSection.style.display = 'block';
    } else if (mode === 'single') {
        if (sourceSingleWrapper) sourceSingleWrapper.style.display = 'block';
        if (sourceMultiWrapper) sourceMultiWrapper.style.display = 'none';
        if (targetSingleWrapper) targetSingleWrapper.style.display = 'block';
        if (targetMultiWrapper) targetMultiWrapper.style.display = 'none';
        if (targetMultiMessage) targetMultiMessage.style.display = 'none';
        
        if (sourceSelect && sourceSelect.value === '__all__') sourceSelect.value = '';
        if (targetSelect && targetSelect.value === '__all__') targetSelect.value = '';
        
        if (validationOpsSection) validationOpsSection.style.display = 'none';
    } else if (mode === 'multiple') {
        if (sourceSingleWrapper) sourceSingleWrapper.style.display = 'none';
        if (sourceMultiWrapper) sourceMultiWrapper.style.display = 'block';
        if (targetSingleWrapper) targetSingleWrapper.style.display = 'none';
        if (targetMultiWrapper) targetMultiWrapper.style.display = 'block';
        if (targetMultiMessage) targetMultiMessage.style.display = 'block';
        if (sourceSingleOps) sourceSingleOps.style.display = 'none';
        if (targetSingleOps) targetSingleOps.style.display = 'none';
        
        if (validationOpsSection) validationOpsSection.style.display = 'block';
    } else if (mode === 'manual') {
        if (sourceSingleWrapper) sourceSingleWrapper.style.display = 'none';
        if (sourceMultiWrapper) sourceMultiWrapper.style.display = 'none';
        if (targetSingleWrapper) targetSingleWrapper.style.display = 'none';
        if (targetMultiWrapper) targetMultiWrapper.style.display = 'none';
        if (targetMultiMessage) targetMultiMessage.style.display = 'none';
        if (manualMappingWrapper) manualMappingWrapper.style.display = 'block';
        if (sourceSingleOps) sourceSingleOps.style.display = 'none';
        if (targetSingleOps) targetSingleOps.style.display = 'none';
        
        if (validationOpsSection) validationOpsSection.style.display = 'none';

        const tableBody = document.getElementById('manual-mappings-table-body');
        if (tableBody && tableBody.children.length === 0) {
            addManualMappingRow();
        }
    }

    handleColumnSelectionChange();
}

function handleColumnSelectionChange() {
    const mode = getColumnSelectionMode();
    if (mode === 'manual') return;

    const sourceSelect = document.getElementById('source-column-select');
    const targetSelect = document.getElementById('target-column-select');
    if (!sourceSelect || !targetSelect) return;

    const container = document.getElementById('validation-operations-container');
    if (!container) return;

    // Case 1: All Columns
    if (mode === 'all') {
        const allOps = [
            { value: 'null_check', label: 'Null Check' },
            { value: 'duplicate_check', label: 'Duplicate Check' },
            { value: 'length_sum_check', label: 'Length Check' },
            { value: 'sum_length', label: 'Sum Length' },
            { value: 'sum', label: 'Sum' },
            { value: 'avg', label: 'Average' },
            { value: 'min', label: 'Min' },
            { value: 'max', label: 'Max' },
            { value: 'min_date', label: 'Min Date' },
            { value: 'max_date', label: 'Max Date' },
            { value: 'count', label: 'Count' },
            { value: 'row_count', label: 'Row Count Match' },
            { value: 'unique_check', label: 'Unique Check' },
            { value: 'distinct_count', label: 'Distinct Count' },
            { value: 'data_type_check', label: 'Data Type Check' },
            { value: 'pattern_match', label: 'Pattern Match' },
            { value: 'std_dev', label: 'Standard Deviation' },
            { value: 'variance', label: 'Variance' },
            { value: 'median', label: 'Median' },
            { value: 'mode', label: 'Mode' }
        ];

        let html = `
            <div class="form-group mb-16">
                <label style="font-size: 0.9rem; font-weight: 600; margin-bottom: 12px; display: block; color: var(--text-primary);">Choose Validation Operations</label>
                
                <!-- Bulk Select/Deselect All Radio Buttons -->
                <div style="display: flex; gap: 20px; align-items: center; margin-bottom: 16px; padding-bottom: 12px; border-bottom: 1px dashed var(--border-medium);">
                    <label class="d-flex align-center gap-6" style="font-weight: 600; cursor: pointer; font-size: 0.85rem; color: var(--text-primary);">
                        <input type="radio" name="bulk_select_all_operations" id="all-ops-select-all" value="all" checked> Select All
                    </label>
                    <label class="d-flex align-center gap-6" style="font-weight: 600; cursor: pointer; font-size: 0.85rem; color: var(--text-primary);">
                        <input type="radio" name="bulk_select_all_operations" id="all-ops-deselect-all" value="none"> Deselect All
                    </label>
                </div>

                <!-- Grid of Operations -->
                <div id="all-ops-grid" style="display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 12px; margin-bottom: 16px;">
        `;

        allOps.forEach(op => {
            html += `
                <label class="d-flex align-center gap-8" style="cursor: pointer; padding: 8px 12px; background: var(--bg-card); border: 1.5px solid var(--border-light); border-radius: var(--radius-md); font-size: 0.85rem; font-weight: 500; color: var(--text-primary);">
                    <input type="checkbox" name="all_operations" value="${op.value}" class="all-op-cb" checked style="margin: 0;">
                    <span>${op.label}</span>
                </label>
            `;
        });

        html += `
                </div>
            </div>
            <div class="alert alert-info d-flex align-center gap-12" style="background: var(--primary-light); color: var(--primary); border: 1px solid var(--primary-medium); padding: 10px 14px; border-radius: var(--radius-md); font-size: 0.85rem;">
                <i class="fas fa-info-circle" style="font-size: 1.1rem;"></i>
                <div>
                    <strong>Disclaimer:</strong> Operations will be executed in the background based on the datatypes of the columns. Unsupported operations for a datatype (e.g. Sum on String) are bypassed automatically.
                </div>
            </div>
        `;
        container.innerHTML = html;

        // Add change listeners to the bulk radio buttons
        const selectAllRadio = document.getElementById('all-ops-select-all');
        const deselectAllRadio = document.getElementById('all-ops-deselect-all');
        const checkboxes = container.querySelectorAll('.all-op-cb');

        selectAllRadio.addEventListener('change', () => {
            if (selectAllRadio.checked) {
                checkboxes.forEach(cb => cb.checked = true);
            }
        });

        deselectAllRadio.addEventListener('change', () => {
            if (deselectAllRadio.checked) {
                checkboxes.forEach(cb => cb.checked = false);
            }
        });

        // If any checkbox is clicked, clear the bulk radios
        checkboxes.forEach(cb => {
            cb.addEventListener('change', () => {
                selectAllRadio.checked = false;
                deselectAllRadio.checked = false;
            });
        });

        // Hide single ops container
        const sourceSingleOps = document.getElementById('source-single-ops-container');
        const targetSingleOps = document.getElementById('target-single-ops-container');
        if (sourceSingleOps) sourceSingleOps.style.display = 'none';
        if (targetSingleOps) targetSingleOps.style.display = 'none';
        return;
    }

    // Case 2: Single Column
    if (mode === 'single') {
        container.innerHTML = '';
        
        renderSingleColumnOps('source');
        renderSingleColumnOps('target');
        return;
    }

    // Case 3: Multiple Columns
    if (mode === 'multiple') {
        const checkedSource = Array.from(document.querySelectorAll('.source-col-cb:checked'));
        const checkedTarget = Array.from(document.querySelectorAll('.target-col-cb:checked'));

        if (checkedSource.length === 0) {
            container.innerHTML = '<div class="alert alert-info" style="padding: 10px 14px; font-size: 0.85rem; margin-bottom: 0;">Please select source columns to configure validations.</div>';
            return;
        }

        let summaryHtml = `
            <div style="margin-top: 12px; background: var(--bg-body); border: 1.5px solid var(--border-light); border-radius: var(--radius-md); padding: 12px;">
                <h4 style="font-size: 0.85rem; font-weight: 600; margin-top: 0; margin-bottom: 8px; color: var(--text-primary); border-bottom: 1px dashed var(--border-medium); padding-bottom: 4px;">
                    <i class="fas fa-link text-primary"></i> Active Column Mappings Summary
                </h4>
                <div style="display: flex; flex-direction: column; gap: 8px;">
        `;

        let activeCount = 0;
        checkedSource.forEach((srcCb) => {
            const sCol = srcCb.value;
            let tCb = checkedTarget.find(tgt => tgt.value.toLowerCase() === sCol.toLowerCase());
            if (!tCb) {
                const srcIdx = checkedSource.indexOf(srcCb);
                if (checkedTarget[srcIdx]) {
                    tCb = checkedTarget[srcIdx];
                }
            }

            if (tCb) {
                activeCount++;
                const tCol = tCb.value;
                const row = srcCb.closest('.source-column-list-item');
                const checkedOps = Array.from(row.querySelectorAll('.multi-op-cb:checked')).map(cb => {
                    const labelText = cb.closest('label').textContent.trim();
                    return labelText;
                });
                
                summaryHtml += `
                    <div style="display: flex; justify-content: space-between; align-items: center; font-size: 0.8rem; background: var(--bg-card); padding: 6px 10px; border-radius: var(--radius-sm); border: 1px solid var(--border-light);">
                        <div>
                            <span style="font-weight: 600; color: var(--primary);">${sCol}</span>
                            <span style="margin: 0 6px; color: var(--text-muted); font-size: 0.75rem;"><i class="fas fa-arrow-right"></i></span>
                            <span style="font-weight: 600; color: var(--success);">${tCol}</span>
                        </div>
                        <div style="font-size: 0.75rem; color: var(--text-muted);">
                            ${checkedOps.length > 0 ? checkedOps.join(', ') : '<span style="color: var(--danger);">No operations</span>'}
                        </div>
                    </div>
                `;
            }
        });

        if (activeCount === 0) {
            summaryHtml += `
                <div style="font-size: 0.8rem; color: var(--text-muted); font-style: italic;">
                    No columns paired. Please select checked columns in the target panel.
                </div>
            `;
        }

        summaryHtml += `
                </div>
            </div>
        `;
        
        container.innerHTML = summaryHtml;
    }
}

function updateSingleOpsCount(prefix) {
    if (prefix) {
        const checked = document.querySelectorAll(`.${prefix}-single-op-cb:checked`);
        const span = document.querySelector(`#${prefix}-single-ops-selected-count`);
        if (span) {
            if (checked.length === 0) {
                span.textContent = 'Select Operations';
            } else {
                span.textContent = `${checked.length} Operation(s) Selected`;
            }
        }
    } else {
        const checked = document.querySelectorAll('.single-op-cb:checked');
        const span = document.querySelector('#single-ops-selected-count');
        if (span) {
            if (checked.length === 0) {
                span.textContent = 'Select Operations';
            } else {
                span.textContent = `${checked.length} Operation(s) Selected`;
            }
        }
    }
}

function updateAllOpsCount() {
    const checked = document.querySelectorAll('.all-op-cb:checked');
    const span = document.querySelector('#all-ops-selected-count');
    if (span) {
        if (checked.length === 0) {
            span.textContent = 'Select Operations';
        } else {
            span.textContent = `${checked.length} Operation(s) Selected`;
        }
    }
}

window.updateAllOpsCount = updateAllOpsCount;

function getColumnMappingsJSON() {
    const mode = getColumnSelectionMode();

    if (mode === 'all') {
        const checkedOps = Array.from(document.querySelectorAll('.all-op-cb:checked')).map(cb => cb.value);
        return JSON.stringify([{
            source_column: '__all__',
            source_datatype: 'unknown',
            target_column: '__all__',
            target_datatype: 'unknown',
            operations: checkedOps
        }]);
    }

    const sourceSelect = document.getElementById('source-column-select');
    const targetSelect = document.getElementById('target-column-select');
    if (!sourceSelect || !targetSelect) return '[]';

    let mappings = [];

    if (mode === 'single') {
        const sCol = sourceSelect.value;
        const tCol = targetSelect.value;
        if (!sCol || !tCol) return '[]';

        const sOpt = Array.from(sourceSelect.options).find(o => o.value === sCol);
        const tOpt = Array.from(targetSelect.options).find(o => o.value === tCol);
        const sType = sOpt ? sOpt.dataset.datatype : 'unknown';
        const tType = tOpt ? tOpt.dataset.datatype : 'unknown';

        const sourceOps = Array.from(document.querySelectorAll('.source-single-op-cb:checked')).map(cb => cb.value);
        const targetOps = Array.from(document.querySelectorAll('.target-single-op-cb:checked')).map(cb => cb.value);
        const unionOps = Array.from(new Set([...sourceOps, ...targetOps]));

        mappings.push({
            source_column: sCol,
            source_datatype: sType,
            target_column: tCol,
            target_datatype: tType,
            operations: unionOps
        });
    } else if (mode === 'multiple') {
        const checkedSource = Array.from(document.querySelectorAll('.source-col-cb:checked'));
        const checkedTarget = Array.from(document.querySelectorAll('.target-col-cb:checked'));

        checkedSource.forEach((srcCb) => {
            const sCol = srcCb.value;
            const sType = srcCb.dataset.datatype || 'unknown';

            let tCb = checkedTarget.find(tgt => tgt.value.toLowerCase() === sCol.toLowerCase());
            if (!tCb) {
                const srcIdx = checkedSource.indexOf(srcCb);
                if (checkedTarget[srcIdx]) {
                    tCb = checkedTarget[srcIdx];
                }
            }

            if (tCb) {
                const tCol = tCb.value;
                const tType = tCb.dataset.datatype || 'unknown';

                const row = srcCb.closest('.source-column-list-item');
                const checkedOps = Array.from(row.querySelectorAll('.multi-op-cb:checked')).map(cb => cb.value);

                mappings.push({
                    source_column: sCol,
                    source_datatype: sType,
                    target_column: tCol,
                    target_datatype: tType,
                    operations: checkedOps
                });
            }
        });
    } else if (mode === 'manual') {
        let mappings = [];
        let hasIncomplete = false;
        const rows = document.querySelectorAll('.manual-mapping-row');
        rows.forEach(row => {
            const sCol = row.querySelector('.manual-source-col').value;
            const tCol = row.querySelector('.manual-target-col').value;
            if (sCol && tCol) {
                const sOpt = row.querySelector(`.manual-source-col option[value="${sCol}"]`);
                const tOpt = row.querySelector(`.manual-target-col option[value="${tCol}"]`);
                const sType = sOpt ? sOpt.dataset.datatype : 'unknown';
                const tType = tOpt ? tOpt.dataset.datatype : 'unknown';
                const checkedOps = Array.from(row.querySelectorAll('.row-op-cb:checked')).map(cb => cb.value);
                mappings.push({
                    source_column: sCol,
                    source_datatype: sType,
                    target_column: tCol,
                    target_datatype: tType,
                    operations: checkedOps
                });
            } else if (sCol || tCol) {
                hasIncomplete = true;
            }
        });
        if (hasIncomplete) {
            showToast('Please select both source and target columns for all manual mapping rows, or remove incomplete rows.', 'warning');
            return '[]';
        }
        return JSON.stringify(mappings);
    }

    return JSON.stringify(mappings);
}

function validateDateFilters() {
    const sourceCol = document.getElementById('source-date-column').value;
    if (sourceCol) {
        const sourceFilterType = document.querySelector('input[name="source_date_filter_type"]:checked')?.value || 'range';
        const sourceStart = document.getElementById('source-date-filter-start').value;
        const sourceEnd = document.getElementById('source-date-filter-end').value;

        if (sourceFilterType === 'range') {
            if (sourceStart && sourceEnd && new Date(sourceStart) > new Date(sourceEnd)) {
                showToast('Source From Date cannot be greater than To Date.', 'warning');
                return false;
            }
        }
    }

    const targetCol = document.getElementById('target-date-column').value;
    if (targetCol) {
        const targetFilterType = document.querySelector('input[name="target_date_filter_type"]:checked')?.value || 'range';
        const targetStart = document.getElementById('target-date-filter-start').value;
        const targetEnd = document.getElementById('target-date-filter-end').value;

        if (targetFilterType === 'range') {
            if (targetStart && targetEnd && new Date(targetStart) > new Date(targetEnd)) {
                showToast('Target From Date cannot be greater than To Date.', 'warning');
                return false;
            }
        }
    }

    return true;
}


function toggleDateFilterInputs(prefix, type) {
    const singleWrapper = document.getElementById(`${prefix}-single-date-wrapper`);
    const rangeWrapper = document.getElementById(`${prefix}-range-date-wrapper`);
    if (singleWrapper && rangeWrapper) {
        if (type === 'specific') {
            singleWrapper.style.display = 'block';
            rangeWrapper.style.display = 'none';
        } else if (type === 'range') {
            singleWrapper.style.display = 'none';
            rangeWrapper.style.display = 'flex';
        } else {
            singleWrapper.style.display = 'none';
            rangeWrapper.style.display = 'none';
        }
    }
}

function toggleTimeFormat(prefix) {
    const includeTimestamp = document.getElementById(`${prefix}-include-timestamp`).checked;
    const dateSingle = document.getElementById(`${prefix}-date-single`);
    const dateStart = document.getElementById(`${prefix}-date-filter-start`);
    const dateEnd = document.getElementById(`${prefix}-date-filter-end`);
    
    const inputType = includeTimestamp ? 'datetime-local' : 'date';
    if (dateSingle) dateSingle.type = inputType;
    if (dateStart) dateStart.type = inputType;
    if (dateEnd) dateEnd.type = inputType;
}

function toggleDateValueType(prefix, valType) {
    const calWrapper = document.getElementById(`${prefix}-calendar-picker-wrapper`);
    const relWrapper = document.getElementById(`${prefix}-relative-input-wrapper`);
    if (calWrapper && relWrapper) {
        if (valType === 'relative') {
            calWrapper.style.display = 'none';
            relWrapper.style.display = 'block';
        } else {
            calWrapper.style.display = 'block';
            relWrapper.style.display = 'none';
        }
    }
}

function toggleMultiselectDropdown(prefix) {
    const container = document.getElementById(`${prefix}-columns-multiselect`);
    if (container) {
        const checkboxes = container.querySelector('.multiselect-checkboxes');
        const isOpen = container.classList.contains('open');
        
        // Close all first
        document.querySelectorAll('.custom-multiselect').forEach(el => {
            el.classList.remove('open');
            const cb = el.querySelector('.multiselect-checkboxes');
            if (cb) cb.style.display = 'none';
        });

        if (!isOpen) {
            container.classList.add('open');
            if (checkboxes) checkboxes.style.display = 'block';
        }
    }
}

function toggleOpsDropdown(selectBox) {
    const container = selectBox.closest('.custom-multiselect');
    if (container) {
        const checkboxes = container.querySelector('.multiselect-checkboxes');
        const isOpen = container.classList.contains('open');
        
        // Close all first
        document.querySelectorAll('.custom-multiselect').forEach(el => {
            el.classList.remove('open');
            const cb = el.querySelector('.multiselect-checkboxes');
            if (cb) cb.style.display = 'none';
        });

        if (!isOpen) {
            container.classList.add('open');
            if (checkboxes) checkboxes.style.display = 'block';
        }
    }
}

// Global click listener to close multiselects on clicking outside
document.addEventListener('click', function(e) {
    if (!e.target.closest('.custom-multiselect')) {
        document.querySelectorAll('.custom-multiselect').forEach(container => {
            container.classList.remove('open');
            const cb = container.querySelector('.multiselect-checkboxes');
            if (cb) cb.style.display = 'none';
        });
    }
});

// Setup date column listeners to automatically select date range
document.addEventListener('DOMContentLoaded', () => {
    ['source', 'target'].forEach(prefix => {
        const dateColSelect = document.getElementById(`${prefix}-date-column`);
        if (dateColSelect) {
            dateColSelect.addEventListener('change', () => {
                const val = dateColSelect.value;
                const rangeRadio = document.querySelector(`input[name="${prefix}_date_filter_type"][value="range"]`);
                
                if (val) {
                    // Auto-select range if no filter type is currently checked
                    const currentType = document.querySelector(`input[name="${prefix}_date_filter_type"]:checked`)?.value;
                    if (!currentType && rangeRadio) {
                        rangeRadio.checked = true;
                        toggleDateFilterInputs(prefix, 'range');
                    }
                } else {
                    // Hide both single and range inputs when column is cleared
                    const singleWrapper = document.getElementById(`${prefix}-single-date-wrapper`);
                    const rangeWrapper = document.getElementById(`${prefix}-range-date-wrapper`);
                    if (singleWrapper) singleWrapper.style.display = 'none';
                    if (rangeWrapper) rangeWrapper.style.display = 'none';
                }
            });
        }
    });
});

window.isDateDatatype = isDateDatatype;
window.categorizeDatatype = categorizeDatatype;
window.handleColumnSelectionChange = handleColumnSelectionChange;
window.handleColumnModeChange = handleColumnModeChange;
window.checkTableSelections = checkTableSelections;
window.getColumnMappingsJSON = getColumnMappingsJSON;
window.validateDateFilters = validateDateFilters;
window.toggleDateFilterInputs = toggleDateFilterInputs;
window.toggleDateValueType = toggleDateValueType;
window.toggleMultiselectDropdown = toggleMultiselectDropdown;
window.toggleOpsDropdown = toggleOpsDropdown;
window.updateSingleOpsCount = updateSingleOpsCount;

window.getColumnSelectionMode = getColumnSelectionMode;
window.renderSingleColumnOps = renderSingleColumnOps;

window.sourceColumnsList = [];
window.targetColumnsList = [];

function addManualMappingRow(initialData = null) {
    const tableBody = document.getElementById('manual-mappings-table-body');
    if (!tableBody) return;

    const rowId = 'manual-row-' + Date.now() + '-' + Math.floor(Math.random() * 1000);
    const row = document.createElement('tr');
    row.id = rowId;
    row.className = 'manual-mapping-row';

    // Build source column options
    let sourceOptions = '<option value="">-- Select Source Column --</option>';
    (window.sourceColumnsList || []).forEach(col => {
        const selected = (initialData && initialData.source_column === col.name) ? 'selected' : '';
        sourceOptions += `<option value="${col.name}" data-datatype="${col.type}" ${selected}>${col.name} (${col.type})</option>`;
    });

    // Build target column options
    let targetOptions = '<option value="">-- Select Target Column --</option>';
    (window.targetColumnsList || []).forEach(col => {
        const selected = (initialData && initialData.target_column === col.name) ? 'selected' : '';
        targetOptions += `<option value="${col.name}" data-datatype="${col.type}" ${selected}>${col.name} (${col.type})</option>`;
    });

    row.innerHTML = `
        <td style="padding: 8px; border: none;">
            <select class="form-control manual-source-col" style="font-size: 0.85rem; padding: 6px 10px;">
                ${sourceOptions}
            </select>
        </td>
        <td style="padding: 8px; text-align: center; vertical-align: middle; color: var(--text-muted); border: none;">
            <i class="fas fa-arrow-right" style="margin-top: 8px;"></i>
        </td>
        <td style="padding: 8px; border: none;">
            <select class="form-control manual-target-col" style="font-size: 0.85rem; padding: 6px 10px;">
                ${targetOptions}
            </select>
        </td>
        <td style="padding: 8px; position: relative; border: none;">
            <div class="custom-multiselect row-op-dropdown-wrapper" style="width: 100%; position: relative;">
                <div class="multiselect-select-box" onclick="toggleOpsDropdown(this)" style="padding: 6px 12px; font-size: 0.85rem; min-height: 34px; line-height: 20px;">
                    <span class="row-ops-count-span">Choose Validation</span>
                </div>
                <div class="multiselect-checkboxes" style="display: none; padding: 8px; position: absolute; z-index: 1000; background: var(--bg-card); border: 1px solid var(--border-medium); border-radius: var(--radius-sm); box-shadow: var(--shadow-md); width: 220px; right: 0;">
                    <!-- Checkboxes populated based on selected source datatype -->
                </div>
            </div>
        </td>
        <td style="padding: 8px; text-align: center; vertical-align: middle; border: none;">
            <button type="button" class="btn btn-xs btn-outline btn-danger remove-manual-row-btn" style="padding: 6px 10px; border-radius: var(--radius-sm);">
                <i class="fas fa-trash-alt"></i>
            </button>
        </td>
    `;

    const sourceSelect = row.querySelector('.manual-source-col');
    const targetSelect = row.querySelector('.manual-target-col');
    const opsContainer = row.querySelector('.multiselect-checkboxes');
    const opsSpan = row.querySelector('.row-ops-count-span');
    const removeBtn = row.querySelector('.remove-manual-row-btn');

    function updateOpsForSelectedSource() {
        const sCol = sourceSelect.value;
        if (!sCol) {
            opsContainer.innerHTML = '<span style="font-size: 0.75rem; color: var(--text-muted); padding: 4px 8px; display: block;">Select a source column first</span>';
            opsSpan.textContent = 'Choose Validation';
            return;
        }

        const selectedOpt = sourceSelect.selectedOptions[0];
        const type = selectedOpt ? selectedOpt.dataset.datatype : 'unknown';
        const cat = categorizeDatatype(type, sCol);
        const ops = OP_LISTS[cat] || OP_LISTS.VARCHAR;

        let html = '';
        ops.forEach(op => {
            const isChecked = (initialData && initialData.operations) ? initialData.operations.includes(op.value) : false;
            html += `
                <label style="display: flex; align-items: center; gap: 8px; cursor: pointer; padding: 4px 8px; font-size: 0.8rem; margin: 0; font-weight: 500; width: 100%;">
                    <input type="checkbox" value="${op.value}" class="row-op-cb" ${isChecked ? 'checked' : ''} style="margin:0;">
                    <span>${op.label}</span>
                </label>
            `;
        });
        opsContainer.innerHTML = html;

        row.querySelectorAll('.row-op-cb').forEach(cb => {
            cb.addEventListener('change', () => {
                updateRowOpsCount();
                handleColumnSelectionChange();
            });
        });
        updateRowOpsCount();
    }

    function updateRowOpsCount() {
        const checked = row.querySelectorAll('.row-op-cb:checked');
        if (checked.length === 0) {
            opsSpan.textContent = 'Choose Validation';
        } else {
            opsSpan.textContent = `${checked.length} Op(s)`;
        }
    }

    sourceSelect.addEventListener('change', () => {
        updateOpsForSelectedSource();
        if (sourceSelect.value && !targetSelect.value) {
            const matchOpt = Array.from(targetSelect.options).find(o => o.value.toLowerCase() === sourceSelect.value.toLowerCase());
            if (matchOpt) {
                targetSelect.value = matchOpt.value;
            }
        }
        handleColumnSelectionChange();
    });

    targetSelect.addEventListener('change', () => {
        handleColumnSelectionChange();
    });

    removeBtn.addEventListener('click', () => {
        row.remove();
        handleColumnSelectionChange();
    });

    tableBody.appendChild(row);
    updateOpsForSelectedSource();
}

window.addManualMappingRow = addManualMappingRow;


// ─── Dynamic Notifications Center ───────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    const notifBtn = document.getElementById('notifications-btn');
    const notifDropdown = document.getElementById('notifications-dropdown');
    const notifList = document.getElementById('notifications-list');
    const notifBadge = document.getElementById('notifications-badge');
    const clearNotifBtn = document.getElementById('clear-notifications-btn');

    if (!notifBtn || !notifDropdown) return;

    // Load notifications from API
    function loadNotifications() {
        fetch('/dashboard/api/notifications/')
            .then(r => r.json())
            .then(data => {
                if (data.success) {
                    // Update badge dot visibility
                    if (data.unread_count > 0) {
                        notifBadge.style.display = 'block';
                    } else {
                        notifBadge.style.display = 'none';
                    }

                    // Populate list
                    if (data.notifications && data.notifications.length > 0) {
                        notifList.innerHTML = '';
                        data.notifications.forEach(n => {
                            const item = document.createElement('div');
                            item.className = `notification-item ${n.is_read ? 'read' : 'unread'}`;
                            item.style.padding = '12px 16px';
                            item.style.borderBottom = '1px solid var(--border-light)';
                            item.style.background = n.is_read ? 'transparent' : 'rgba(30, 66, 159, 0.04)';
                            item.style.cursor = 'default';
                            item.style.transition = 'background 0.2s';
                            
                            const levelIcons = {
                                success: '<i class="fas fa-check-circle" style="color: var(--success); margin-right: 8px;"></i>',
                                error: '<i class="fas fa-exclamation-circle" style="color: var(--danger); margin-right: 8px;"></i>',
                                warning: '<i class="fas fa-exclamation-triangle" style="color: var(--warning); margin-right: 8px;"></i>',
                                info: '<i class="fas fa-info-circle" style="color: var(--info); margin-right: 8px;"></i>',
                            };
                            
                            const icon = levelIcons[n.level] || levelIcons.info;

                            item.innerHTML = `
                                <div style="display: flex; align-items: flex-start; gap: 4px;">
                                    ${icon}
                                    <div style="flex: 1;">
                                        <div style="font-weight: 600; font-size: 0.8rem; color: var(--text-main); margin-bottom: 2px;">${n.title}</div>
                                        <div style="font-size: 0.75rem; color: var(--text-secondary); line-height: 1.3; white-space: pre-wrap;">${n.message}</div>
                                        <div style="font-size: 0.65rem; color: var(--text-muted); margin-top: 4px;">${n.created_at}</div>
                                    </div>
                                </div>
                            `;
                            notifList.appendChild(item);
                        });
                    } else {
                        notifList.innerHTML = `
                            <div style="padding: 16px; text-align: center; color: var(--text-muted); font-size: 0.85rem;">
                                No new notifications
                            </div>
                        `;
                    }
                }
            })
            .catch(err => console.error('Error loading notifications:', err));
    }

    // Toggle dropdown
    notifBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        const isVisible = notifDropdown.style.display === 'block';
        notifDropdown.style.display = isVisible ? 'none' : 'block';
        if (!isVisible) {
            loadNotifications();
        }
    });

    // Close dropdown on outside click
    document.addEventListener('click', (e) => {
        if (!notifDropdown.contains(e.target) && e.target !== notifBtn && !notifBtn.contains(e.target)) {
            notifDropdown.style.display = 'none';
        }
    });

    // Clear notifications
    if (clearNotifBtn) {
        clearNotifBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            fetchWithCSRF('/dashboard/api/notifications/clear/', { method: 'POST' })
                .then(r => r.json())
                .then(data => {
                    if (data.success) {
                        showToast('All notifications cleared', 'success');
                        loadNotifications();
                    }
                })
                .catch(err => console.error('Error clearing notifications:', err));
        });
    }

    // Scan for and dynamically update any running validations on current page
    const runningBadges = document.querySelectorAll('[id^="status-badge-"]');
    runningBadges.forEach(badge => {
        const text = badge.textContent.trim().toLowerCase();
        if (text === 'running' || text === 'pending' || text === 'in progress' || badge.classList.contains('badge-warning')) {
            const runId = badge.id.split('-').pop();
            pollValidationProgress(runId);
        }
    });

    // Initial load and poll every 15 seconds
    loadNotifications();
    setInterval(loadNotifications, 15000);
});

// ─── Table Preview Modal System (In-page Popup with Backdrop Blur) ───────────
function showTablePreviewModal(url, title) {
    let modalOverlay = document.getElementById('table-preview-modal');
    if (!modalOverlay) {
        modalOverlay = document.createElement('div');
        modalOverlay.id = 'table-preview-modal';
        modalOverlay.className = 'preview-modal-overlay';
        modalOverlay.innerHTML = `
            <div class="preview-modal-content">
                <div class="preview-modal-header">
                    <h3>${title}</h3>
                    <button type="button" class="preview-modal-close-btn">&times;</button>
                </div>
                <div class="preview-modal-body" id="table-preview-modal-body">
                    <div style="display: flex; justify-content: center; align-items: center; height: 200px;">
                        <i class="fas fa-spinner fa-spin" style="font-size: 2rem; color: var(--primary);"></i>
                        <span style="margin-left: 12px; font-weight: 500;">Loading preview data...</span>
                    </div>
                </div>
            </div>
        `;
        document.body.appendChild(modalOverlay);
    } else {
        modalOverlay.querySelector('.preview-modal-header h3').textContent = title;
        modalOverlay.querySelector('#table-preview-modal-body').innerHTML = `
            <div style="display: flex; justify-content: center; align-items: center; height: 200px;">
                <i class="fas fa-spinner fa-spin" style="font-size: 2rem; color: var(--primary);"></i>
                <span style="margin-left: 12px; font-weight: 500;">Loading preview data...</span>
            </div>
        `;
    }

    let modalStyle = document.getElementById('table-preview-modal-style');
    if (!modalStyle) {
        modalStyle = document.createElement('style');
        modalStyle.id = 'table-preview-modal-style';
        modalStyle.textContent = `
            .preview-modal-overlay {
                position: fixed;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                background: rgba(15, 23, 42, 0.6);
                backdrop-filter: blur(8px);
                -webkit-backdrop-filter: blur(8px);
                z-index: 9999;
                display: flex;
                justify-content: center;
                align-items: center;
                opacity: 0;
                transition: opacity 0.25s ease;
                pointer-events: none;
            }
            .preview-modal-overlay.active {
                opacity: 1;
                pointer-events: auto;
            }
            .preview-modal-content {
                background: var(--bg-card, #ffffff);
                border-radius: var(--radius-lg, 12px);
                box-shadow: var(--shadow-xl), 0 20px 25px -5px rgba(0, 0, 0, 0.1);
                border: 1px solid var(--border-light, #e2e8f0);
                width: 90%;
                max-width: 1100px;
                max-height: 85%;
                display: flex;
                flex-direction: column;
                transform: translateY(20px) scale(0.98);
                transition: transform 0.25s cubic-bezier(0.34, 1.56, 0.64, 1);
            }
            .preview-modal-overlay.active .preview-modal-content {
                transform: translateY(0) scale(1);
            }
            .preview-modal-header {
                padding: 16px 24px;
                border-bottom: 1px solid var(--border-light, #e2e8f0);
                display: flex;
                justify-content: space-between;
                align-items: center;
                background: var(--bg-body, #f8fafc);
                border-top-left-radius: var(--radius-lg, 12px);
                border-top-right-radius: var(--radius-lg, 12px);
            }
            .preview-modal-header h3 {
                margin: 0;
                font-size: 1.15rem;
                font-weight: 600;
                color: var(--text-primary, #0f172a);
            }
            .preview-modal-body {
                padding: 24px;
                overflow: auto;
                flex: 1;
                background: var(--bg-card, #ffffff);
                border-bottom-left-radius: var(--radius-lg, 12px);
                border-bottom-right-radius: var(--radius-lg, 12px);
            }
            .preview-modal-close-btn {
                background: none;
                border: none;
                font-size: 1.75rem;
                color: var(--text-muted, #94a3b8);
                cursor: pointer;
                padding: 0 4px;
                display: flex;
                align-items: center;
                justify-content: center;
                transition: color 0.2s, transform 0.2s;
                outline: none;
                line-height: 1;
            }
            .preview-modal-close-btn:hover {
                color: var(--danger, #ef4444);
                transform: scale(1.15);
            }
            .preview-modal-body .card {
                border: none !important;
                box-shadow: none !important;
                margin: 0 !important;
                background: transparent !important;
            }
            .preview-modal-body .card-header {
                display: none !important;
            }
            .preview-modal-body .card-body {
                padding: 0 !important;
            }
        `;
        document.head.appendChild(modalStyle);
    }

    setTimeout(() => {
        modalOverlay.classList.add('active');
    }, 10);

    fetch(url)
        .then(response => {
            return response.text().then(text => {
                return { ok: response.ok, status: response.status, text: text };
            });
        })
        .then(res => {
            const parser = new DOMParser();
            const doc = parser.parseFromString(res.text, 'text/html');
            const card = doc.querySelector('.main-content .card') || doc.querySelector('.card');
            
            if (card) {
                const body = document.getElementById('table-preview-modal-body');
                body.innerHTML = '';
                body.appendChild(card);
            } else {
                if (!res.ok) {
                    throw new Error(`Failed to load table preview (HTTP ${res.status})`);
                }
                throw new Error('Could not parse table preview content');
            }
        })
        .catch(error => {
            console.error("Table preview fetch failed:", error);
            const body = document.getElementById('table-preview-modal-body');
            body.innerHTML = `
                <div class="alert alert-danger" style="margin: 20px 0; padding: 16px 20px; border-radius: var(--radius-md); font-weight: 500;">
                    <i class="fas fa-exclamation-triangle" style="margin-right: 8px; font-size: 1.1rem;"></i> 
                    ${error.message || 'An error occurred while loading preview data.'}
                </div>
            `;
        });
}

function closeTablePreviewModal() {
    const modalOverlay = document.getElementById('table-preview-modal');
    if (modalOverlay) {
        modalOverlay.classList.remove('active');
        // Reset the body content to a spinner so previous content is cleared
        const body = document.getElementById('table-preview-modal-body');
        if (body) {
            body.innerHTML = `
                <div style="display: flex; justify-content: center; align-items: center; height: 200px;">
                    <i class="fas fa-spinner fa-spin" style="font-size: 2rem; color: var(--primary);"></i>
                    <span style="margin-left: 12px; font-weight: 500;">Loading preview data...</span>
                </div>
            `;
        }
    }
}

// Intercept table preview button clicks to show modal popup
document.addEventListener('click', function(e) {
    const previewBtn = e.target.closest('#source-table-preview-btn, #target-table-preview-btn');
    if (previewBtn) {
        e.preventDefault();
        const url = previewBtn.getAttribute('href');
        if (url && url !== '#') {
            const title = previewBtn.id.includes('source') ? 'Source Table Preview' : 'Target Table Preview';
            showTablePreviewModal(url, title);
        }
    }
});

// Intercept close button clicks to safely close without form submission or background loss
document.addEventListener('click', function(e) {
    const closeBtn = e.target.closest('.preview-modal-close-btn');
    if (closeBtn) {
        e.preventDefault();
        e.stopPropagation();
        closeTablePreviewModal();
    }
});

// Close modal on backdrop click
document.addEventListener('click', function(e) {
    const modalOverlay = document.getElementById('table-preview-modal');
    if (modalOverlay && e.target === modalOverlay) {
        e.preventDefault();
        e.stopPropagation();
        closeTablePreviewModal();
    }
});

// Close modal on Escape key press
document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') {
        closeTablePreviewModal();
    }
});

// Intercept form submissions inside the table preview modal to prevent page reload and handle paging/filtering inline
document.addEventListener('submit', function(e) {
    const modalOverlay = document.getElementById('table-preview-modal');
    if (modalOverlay && modalOverlay.contains(e.target)) {
        e.preventDefault();
        const form = e.target;
        const formData = new FormData(form);
        const params = new URLSearchParams();
        for (const [key, val] of formData.entries()) {
            params.append(key, val);
        }
        
        // Find if this is source or target based on modal title
        const titleEl = modalOverlay.querySelector('.preview-modal-header h3');
        const title = titleEl ? titleEl.textContent : 'Table Preview';
        const prefix = title.toLowerCase().includes('source') ? 'source' : 'target';
        
        const url = `/connections/preview/${prefix}/?${params.toString()}`;
        showTablePreviewModal(url, title);
    }
});

