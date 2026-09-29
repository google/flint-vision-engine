function getModelFullName(mKey) {
  if (!mKey) return 'Model';
  if (mKey.includes('clip-vit-b-32')) return 'CLIP ViT-B/32 (Fast Baseline)';
  if (mKey.includes('dinov3')) return 'DINOv3 ViT-B/16 (Vision Only)';
  if (mKey.includes('siglip2-naflex')) return 'SigLIP2 NaFlex (Crop Optimized)';
  if (mKey.includes('siglip-base')) return 'SigLIP Base (High Accuracy)';
  if (mKey.includes('mobileclip')) return 'mobileCLIP S0 (Ultra Fast)';
  if (mKey.includes('openclip')) return 'OpenCLIP LAION-2B';
  return mKey;
}

// FLINT Vision Engine UI Application Logic - Modern Two-View Architecture

let appState = {
  activeView: 'index', // 'index' or 'investigate'
  activeModelKey: 'clip-vit-b-32',
  databasesList: [],
  activeDatabase: 'default.sqlite',
  selectedModelKeys: new Set(['clip-vit-b-32', 'siglip-base', 'siglip2-naflex']),
  investigateActiveModel: 'clip-vit-b-32',
  knownMode: 'path',
  unknownMode: 'folder',
  knownImages: [],
  knownTargets: [],
  lastSearchResults: null,
  activeModel: null,
  cropState: {
    imageObj: null,
    startX: 0,
    startY: 0,
    box: null,
  },
  logs: [],
  latestLogId: 0,
  logFilter: 'ALL',
  consoleExpanded: false,
  autoScroll: true,
  investigateEvidenceList: [],
  investigateHiddenIds: new Set(),
  investigateSelectedTargets: new Set(),
  investigateSearchQuery: null,
  investigateTargetsInitialized: false,
  activeCropResults: null,
  activeCropEmbeddings: null,
  semanticMultiModelResults: null,
  activeDetailItem: null,
  pendingDownloadModelKey: null,
  pendingDownloadModelName: null,
};

function cleanInputPath(str) {
  if (!str) return '';
  let p = str.trim();
  while ((p.startsWith('"') && p.endsWith('"')) || (p.startsWith("'") && p.endsWith("'"))) {
    p = p.substring(1, p.length - 1).trim();
  }
  if (p.startsWith('file://')) {
    p = decodeURIComponent(p.substring(7));
    // On Windows, file:///C:/... leaves /C:/... or \C:\...
    if ((p.startsWith('/') || p.startsWith('\\')) && p.length > 2 && p[2] === ':') {
      p = p.substring(1);
    }
  }
  p = p.replace(/\\ /g, ' ').replace(/\"/g, '"').replace(/\'/g, "'");
  return p;
}

// Global DOM Content Loaded
document.addEventListener('DOMContentLoaded', () => {
  // Enforce blank input fields immediately on startup before any scripts or browser autofill
  const ki = document.getElementById('knownPathInput');
  if (ki) ki.value = '';
  const ui = document.getElementById('unknownFolderPath');
  if (ui) ui.value = '';

  initTheme();
  initStatus();
  initLiveConsole();
  initVisualMatcher();
  fetchDatabases();
  initVideoCropListeners();
  initModals();
  initHfTokenModal();
  initAutoSaveListeners();
  restoreSessionState();
});

window.addEventListener('pageshow', () => {
  if (typeof isRestoringSession !== 'undefined' && isRestoringSession) {
    const ki = document.getElementById('knownPathInput');
    if (ki) ki.value = '';
    const ui = document.getElementById('unknownFolderPath');
    if (ui) ui.value = '';
  }
});

// ==========================================
// TOAST NOTIFICATIONS
// ==========================================
function showToast(msg, type = 'info') {
  const container = document.getElementById('toastContainer');
  if (!container) return;
  const toast = document.createElement('div');
  toast.className = 'toast';
  const icon = type === 'error' ? '❌' : type === 'success' ? '✅' : '⚡';
  toast.innerHTML = `<span>${icon}</span><span>${msg}</span>`;
  container.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = '0';
    setTimeout(() => toast.remove(), 300);
  }, 4000);
}

// ==========================================
// THEME
// ==========================================
function initTheme() {
  const btn = document.getElementById('btnToggleTheme');
  const saved = localStorage.getItem('flint_theme') || 'dark';
  if (saved === 'light') {
    document.body.classList.remove('dark-theme');
    document.body.classList.add('light-theme');
    if (btn) btn.innerText = '☀️';
  }

  btn?.addEventListener('click', () => {
    const isDark = document.body.classList.contains('dark-theme');
    if (isDark) {
      document.body.classList.remove('dark-theme');
      document.body.classList.add('light-theme');
      btn.innerText = '☀️';
      localStorage.setItem('flint_theme', 'light');
    } else {
      document.body.classList.remove('light-theme');
      document.body.classList.add('dark-theme');
      btn.innerText = '🌙';
      localStorage.setItem('flint_theme', 'dark');
    }
  });
}


// ==========================================
// SQLITE DATABASE ARCHIVE MANAGER
// ==========================================
async function fetchDatabases(showFeedback = false) {
  try {
    const res = await fetch('/api/databases');
    const data = await res.json();
    if (!data.databases) return;

    appState.databasesList = data.databases;
    appState.activeDatabase = data.active_db || 'default.sqlite';

    const select = document.getElementById('unknownDbSelect');
    if (select) {
      select.innerHTML = data.databases.map(db => `
        <option value="${db.filename}" ${db.is_active ? 'selected' : ''}>
          ${db.filename} (${db.media_count} media, ${db.size_formatted})
        </option>
      `).join('');
    }

    const activeDb = data.databases.find(db => db.is_active) || data.databases[0];
    if (activeDb) {
      updateActiveDbStatsUI(activeDb);
    }

    if (showFeedback) {
      showToast(`Refreshed ${data.databases.length} databases in databases/ folder`, 'success');
    }
  } catch (err) {
    console.error('Failed to fetch databases:', err);
  }
}

function updateActiveDbStatsUI(db) {
  const elMedia = document.getElementById('dbActiveMediaCount');
  const elModels = document.getElementById('dbActiveModelsIndexed');
  const elSize = document.getElementById('dbActiveFileSize');
  const elTopCount = document.getElementById('dbMediaCount');

  if (elMedia) elMedia.innerText = `${db.media_count} Media Indexed`;
  if (elModels) elModels.innerText = db.models_stored && db.models_stored.length > 0 ? `Models: ${db.models_stored.join(', ')}` : 'Models: None';
  if (elSize) elSize.innerText = db.size_formatted;
  if (elTopCount) elTopCount.innerText = `${db.media_count} Media in ${db.filename}`;
}

window.onDatabaseSelectChange = async function(dbFilename) {
  if (!dbFilename) return;
  showToast(`Switching active database to ${dbFilename}...`, 'info');
  try {
    const res = await fetch('/api/databases/set_active', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: dbFilename })
    });
    const data = await res.json();
    if (data.error) throw new Error(data.error);

    appState.activeDatabase = data.filename;
    showToast(`Active database set to: ${data.filename} (${data.stats.total_media} media ready)`, 'success');
    await fetchDatabases();
    fetchStatus();
    saveSessionState();
  } catch (err) {
    showToast(`Failed to switch database: ${err.message}`, 'error');
  }
};

window.openNewDbModal = function() {
  const modal = document.getElementById('newDbModal');
  const input = document.getElementById('newDbNameInput');
  if (input) input.value = '';
  modal?.classList.remove('hidden');
  setTimeout(() => input?.focus(), 50);
};

window.closeNewDbModal = function() {
  document.getElementById('newDbModal')?.classList.add('hidden');
};



// ==========================================
// LOAD SQLITE INVESTIGATION MODAL
// ==========================================

// ==========================================
// COMPUTATION METHOD CONTROLLER (EXACT vs ANN)
// ==========================================
window.setComputationMode = function(mode) {
  appState.computationMethod = mode === 'ann' ? 'ann' : 'exact';

  document.querySelectorAll('.btn-comp-exact').forEach(b => {
    b.classList.toggle('active', appState.computationMethod === 'exact');
  });
  document.querySelectorAll('.btn-comp-ann').forEach(b => {
    b.classList.toggle('active', appState.computationMethod === 'ann');
  });

  const label = appState.computationMethod === 'ann' ? 'ANN (Approximate Nearest Neighbors - IVF Index)' : 'Exact (Brute Force Matrix Multiplication)';
  showToast(`Computation Mode: ${label}`, 'info');

  saveSessionState();

  // If currently investigating, recompute matches with new computation mode!
  if (appState.activeView === 'investigate') {
    if (appState.cropFilterActive && appState.activeCropResults) {
      showToast('Re-running crop search in ' + appState.computationMethod.toUpperCase() + ' mode...', 'info');
    } else if (appState.investigateSearchQuery) {
      runInvestigateSemanticSearch();
    } else if (appState.lastSearchResults) {
      recomputeInvestigation();
    }
  }
};

window.openLoadDbModal = async function() {
  const modal = document.getElementById('loadDbModal');
  const container = document.getElementById('loadDbModalList');
  if (!container) return;

  container.innerHTML = '<div style="padding: 24px; text-align: center; color: var(--text-muted);">Scanning databases/ directory...</div>';
  modal?.classList.remove('hidden');

  try {
    const res = await fetch('/api/databases');
    const data = await res.json();
    const dbs = data.databases || [];

    if (dbs.length === 0) {
      container.innerHTML = `
        <div style="padding: 30px; text-align: center; color: var(--text-muted); background: rgba(255,255,255,0.02); border-radius: 8px;">
          <div style="font-size: 32px; margin-bottom: 8px;">🗄️</div>
          <strong style="color: var(--text-main);">No SQLite Databases Found</strong>
          <p style="margin-top: 6px; font-size: 13px;">Index a target folder or click "Create New Database" to create an SQLite archive.</p>
        </div>
      `;
      return;
    }

    container.innerHTML = dbs.map(db => `
      <div class="db-archive-card ${db.is_active ? 'active-db-card' : ''}" style="display: flex; justify-content: space-between; align-items: center; padding: 14px 18px; background: rgba(255,255,255,0.03); border: 1px solid ${db.is_active ? 'var(--accent-cyan)' : 'var(--border-color)'}; border-radius: 10px;">
        <div style="display: flex; flex-direction: column; gap: 4px; min-width: 0;">
          <div style="display: flex; align-items: center; gap: 8px;">
            <span style="font-size: 18px;">🗄️</span>
            <strong style="font-size: 15px; color: var(--text-main);">${db.filename}</strong>
            ${db.is_active ? '<span class="pill pill-cyan pill-xs">ACTIVE</span>' : ''}
          </div>
          <div style="display: flex; gap: 8px; flex-wrap: wrap; margin-top: 4px;">
            <span class="pill pill-xs" style="background: rgba(0, 242, 254, 0.1); color: var(--accent-cyan); font-weight: 700;">${db.media_count} Media Indexed</span>
            <span class="pill pill-xs">${db.models_stored && db.models_stored.length ? 'Models: ' + db.models_stored.join(', ') : 'No Vectors'}</span>
            <span class="pill pill-xs">${db.size_formatted}</span>
            <span class="pill pill-xs" style="color: var(--text-muted); font-size: 10px;">${db.path}</span>
          </div>
        </div>
        <div style="display: flex; gap: 8px; flex-shrink: 0; margin-left: 16px;">
          ${!db.is_active ? `<button type="button" class="btn btn-secondary-outline btn-xs" onclick="onDatabaseSelectChange('${db.filename}'); openLoadDbModal();">⚡ Set Active</button>` : ''}
          <button type="button" class="btn btn-primary btn-sm" onclick="loadDatabaseByName('${db.filename}')" style="font-weight: 700;">
            <span>🚀</span> Load into Investigation
          </button>
        </div>
      </div>
    `).join('');
  } catch (err) {
    container.innerHTML = `<div style="color: #f87171; padding: 16px;">Failed to scan databases: ${err.message}</div>`;
  }
};

window.closeLoadDbModal = function() {
  document.getElementById('loadDbModal')?.classList.add('hidden');
};

window.loadDatabaseByName = async function(dbFilename) {
  if (!dbFilename) return;
  closeLoadDbModal();
  showToast(`Loading SQLite Investigation: ${dbFilename}...`, 'info');

  const knownPath = document.getElementById('knownPathInput')?.value.trim() || appState.knownPath || '';
  const knownInput = knownPath || (appState.knownImages && appState.knownImages.length ? appState.knownImages.map(img => img.file_path) : (appState.knownTargets && appState.knownTargets.length ? appState.knownTargets.map(t => t.file_path || t.label) : null));

  try {
    const res = await fetch('/api/databases/load_investigation', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: dbFilename,
        known_targets: knownInput,
        search_mode: appState.computationMethod || 'exact',
      })
    });
    const rawData = await res.json();
    if (rawData.error) throw new Error(rawData.error);
    const data = rawData.results || rawData;

    appState.activeDatabase = dbFilename;
    appState.investigateTargetsInitialized = false;
    appState.lastSearchResults = data;
    appState.knownTargets = (data.known_targets && data.known_targets.length > 0) ? data.known_targets : (appState.knownTargets || []);
    appState.investigateEvidenceList = data.matches || [];

    if (appState.knownTargets && appState.knownTargets.length > 0) {
      appState.investigateSelectedTargets = new Set(appState.knownTargets.map((t, idx) => `target_${idx}`));
    }

    const caseBadge = document.getElementById('investigateCaseBadge');
    if (caseBadge) caseBadge.innerText = `📁 ${dbFilename}`;

    showToast(`Loaded ${data.num_matches || (data.matches ? data.matches.length : 0)} media records from ${dbFilename}!`, 'success');
    await fetchDatabases();
    showInvestigateView();
  } catch (err) {
    showToast(`Failed to load database: ${err.message}`, 'error');
  }
};

window.loadSelectedDatabaseToInvestigate = async function() {
  const select = document.getElementById('unknownDbSelect');
  const selectedDb = select ? select.value : (appState.activeDatabase || 'default.sqlite');
  if (!selectedDb) {
    showToast('Please select an SQLite database first', 'error');
    return;
  }
  loadDatabaseByName(selectedDb);
};

window.openSaveDbPromptModal = function(defaultName = '') {
  const modal = document.getElementById('saveDbPromptModal');
  const input = document.getElementById('saveDbPromptNameInput');
  if (input) {
    input.value = defaultName || '';
  }
  modal?.classList.remove('hidden');
  setTimeout(() => input?.focus(), 50);
};

window.closeSaveDbPromptModal = function() {
  document.getElementById('saveDbPromptModal')?.classList.add('hidden');
};

window.confirmSaveDbAndRun = function() {
  const input = document.getElementById('saveDbPromptNameInput');
  const dbName = input ? input.value.trim() : '';
  closeSaveDbPromptModal();
  executeVisualSearch(dbName || null);
};

window.submitCreateNewDatabase = async function() {
  const input = document.getElementById('newDbNameInput');
  const dbName = input ? input.value.trim() : '';
  if (!dbName) {
    showToast('Please enter a name for the database file', 'error');
    input?.focus();
    return;
  }

  showToast(`Creating SQLite database ${dbName}...`, 'info');
  try {
    const res = await fetch('/api/databases/create', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: dbName })
    });
    const data = await res.json();
    if (data.error) throw new Error(data.error);

    closeNewDbModal();
    showToast(`Created & activated database: ${data.filename}`, 'success');
    await fetchDatabases();
    fetchStatus();
    saveSessionState();
  } catch (err) {
    showToast(`Database creation error: ${err.message}`, 'error');
  }
};

// ==========================================
// STATUS
// ==========================================
async function initStatus() {
  document.getElementById('btnRefreshStatus')?.addEventListener('click', fetchStatus);
  await fetchStatus();
  fetchLogs();
  setInterval(fetchLogs, 1500);
}

async function fetchStatus() {
  try {
    const res = await fetch('/api/status');
    const data = await res.json();
    if (data.active_model) {
      const modelName = typeof data.active_model === 'object' ? (data.active_model.display_name || data.active_model.key || 'CLIP ViT-B/32') : data.active_model;
      appState.activeModel = modelName;
      const modelText = document.getElementById('activeModelText');
      if (modelText) modelText.innerText = modelName;
    }
    if (data.device) {
      const devText = document.getElementById('deviceText');
      if (devText) devText.innerText = data.device.toUpperCase();
    }
    if (data.db_stats) {
      const dbCount = document.getElementById('dbMediaCount');
      if (dbCount) dbCount.innerText = `${data.db_stats.total_media || 0} Media in SQLite`;
    }
  } catch (e) {
    console.error('Status fetch error:', e);
  }
}

// ==========================================
// VIEW SWITCHING (INDEX vs INVESTIGATE)
// ==========================================
window.showIndexView = function(shouldSave = true) {
  appState.activeView = 'index';
  document.getElementById('view-index')?.classList.remove('hidden');
  document.getElementById('view-investigate')?.classList.add('hidden');

  document.getElementById('appHeaderTitle').innerText = 'FLINT - INDEX';
  document.getElementById('appHeaderSubtitle').innerText = 'Edge Vision & Similarity Engine';

  document.getElementById('indexStatusPills')?.classList.remove('hidden');
  document.getElementById('indexActionsBar')?.classList.remove('hidden');
  document.getElementById('investigateHeaderPills')?.classList.add('hidden');
  document.getElementById('investigateActionsBar')?.classList.add('hidden');

  if (appState.lastSearchResults && ((appState.lastSearchResults.matches && appState.lastSearchResults.matches.length > 0) || appState.lastSearchResults.num_matches > 0)) {
    document.getElementById('btnResumeInvestigation')?.classList.remove('hidden');
  }

  if (shouldSave && typeof isRestoringSession !== 'undefined' && !isRestoringSession) {
    saveSessionState();
  }
};

window.showInvestigateView = function() {
  appState.activeView = 'investigate';
  document.getElementById('view-index')?.classList.add('hidden');
  document.getElementById('view-investigate')?.classList.remove('hidden');

  document.getElementById('appHeaderTitle').innerText = 'FLINT - INVESTIGATE';
  document.getElementById('appHeaderSubtitle').innerText = 'Studio & Evidence Analysis';

  document.getElementById('indexStatusPills')?.classList.add('hidden');
  document.getElementById('indexActionsBar')?.classList.add('hidden');
  document.getElementById('investigateHeaderPills')?.classList.remove('hidden');
  document.getElementById('investigateActionsBar')?.classList.remove('hidden');

  initInvestigateWorkspace();
  saveSessionState();
};

// ==========================================
// VISUAL MATCHER CONTROLLER
// ==========================================
function initVisualMatcher() {
  renderMatcherModelSelection();

  // Known Mode Toggles
  document.querySelectorAll('[data-known-mode]').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('[data-known-mode]').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      const mode = btn.getAttribute('data-known-mode');
      appState.knownMode = mode;
      document.getElementById('knownPathSection')?.classList.toggle('hidden', mode !== 'path');
      document.getElementById('knownUploadSection')?.classList.toggle('hidden', mode !== 'upload');
      saveSessionState();
    });
  });

  // Unknown Mode Toggles
  document.querySelectorAll('[data-unknown-mode]').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('[data-unknown-mode]').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      const mode = btn.getAttribute('data-unknown-mode');
      appState.unknownMode = mode;
      document.getElementById('unknownFolderSection')?.classList.toggle('hidden', mode !== 'folder');
      document.getElementById('unknownDbSection')?.classList.toggle('hidden', mode !== 'db');
      saveSessionState();
    });
  });

  // Browse buttons
  const knownPicker = document.getElementById('knownFolderPicker');
  document.getElementById('btnBrowseKnownFolder')?.addEventListener('click', () => knownPicker?.click());
  knownPicker?.addEventListener('change', () => {
    if (knownPicker.files && knownPicker.files.length > 0) {
      const path = knownPicker.files[0].path || knownPicker.files[0].webkitRelativePath;
      if (path) {
        const lastSep = Math.max(path.lastIndexOf('/'), path.lastIndexOf('\\'));
        document.getElementById('knownPathInput').value = lastSep !== -1 ? path.substring(0, lastSep) : path;
        handleLoadKnownPath();
      }
    }
  });

  const unknownPicker = document.getElementById('unknownFolderPicker');
  document.getElementById('btnBrowseUnknownFolder')?.addEventListener('click', () => unknownPicker?.click());
  unknownPicker?.addEventListener('change', () => {
    if (unknownPicker.files && unknownPicker.files.length > 0) {
      const path = unknownPicker.files[0].path || unknownPicker.files[0].webkitRelativePath;
      if (path) {
        const lastSep = Math.max(path.lastIndexOf('/'), path.lastIndexOf('\\'));
        document.getElementById('unknownFolderPath').value = lastSep !== -1 ? path.substring(0, lastSep) : path;
      }
    }
  });

  // Video Options toggle & method switch
  document.getElementById('unknownProcessVideos')?.addEventListener('change', (e) => {
    document.getElementById('videoConfigBody')?.classList.toggle('hidden', !e.target.checked);
  });

  const videoMethodSelect = document.getElementById('videoMethodSelect');
  videoMethodSelect?.addEventListener('change', () => {
    const m = videoMethodSelect.value;
    document.getElementById('videoParamSsim')?.classList.toggle('hidden', m !== 'ssim');
    document.getElementById('videoParamInterval')?.classList.toggle('hidden', m !== 'interval');
    document.getElementById('videoParamUniform')?.classList.toggle('hidden', m !== 'uniform');
  });

  document.getElementById('unknownVideoSsim')?.addEventListener('input', (e) => {
    const valEl = document.getElementById('unknownVideoSsimVal');
    if (valEl) valEl.innerText = e.target.value;
  });

  // Similarity Slider
  const simSlider = document.getElementById('simThresholdSlider');
  simSlider?.addEventListener('input', () => {
    const valEl = document.getElementById('simThresholdVal');
    if (valEl) valEl.innerText = simSlider.value === '0' ? '0% (Show All)' : `${simSlider.value}%`;
  });

  // Load known path button
  document.getElementById('btnLoadKnownPath')?.addEventListener('click', handleLoadKnownPath);

  // Clear known targets button
  document.getElementById('btnClearKnownTargets')?.addEventListener('click', () => {
    appState.knownImages = [];
    appState.knownTargets = [];
    renderKnownGallery();
    showToast('Cleared known reference targets', 'info');
  });

  // Dropzone for upload
  const dropZone = document.getElementById('knownDropZone');
  const fileInput = document.getElementById('knownFileInput');
  dropZone?.addEventListener('click', () => fileInput?.click());
  dropZone?.addEventListener('dragover', (e) => { e.preventDefault(); dropZone.classList.add('dragover'); });
  dropZone?.addEventListener('dragleave', () => dropZone.classList.remove('dragover'));
  dropZone?.addEventListener('drop', async (e) => {
    e.preventDefault();
    dropZone.classList.remove('dragover');
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      await uploadKnownFiles(e.dataTransfer.files);
    }
  });
  fileInput?.addEventListener('change', async () => {
    if (fileInput.files && fileInput.files.length > 0) {
      await uploadKnownFiles(fileInput.files);
    }
  });

  // Run Visual Search Button
  document.getElementById('btnRunVisualSearch')?.addEventListener('click', runVisualSearch);
}

async function handleLoadKnownPath() {
  const rawP = document.getElementById('knownPathInput')?.value || '';
  const p = cleanInputPath(rawP);
  if (!p) {
    showToast('Please enter a valid file or folder path', 'error');
    return;
  }
  document.getElementById('knownPathInput').value = p;
  showToast(`Loading reference targets from: ${p}...`, 'info');

  try {
    const res = await fetch(`/api/known_targets?path=${encodeURIComponent(p)}`);
    const data = await res.json();
    if (data.success && data.targets && data.targets.length > 0) {
      appState.knownTargets = data.targets;
      appState.knownImages = data.targets.map(t => ({
        label: t.label,
        file_path: t.file_path,
        thumb_url: `/api/media/preview?path=${encodeURIComponent(t.file_path)}&thumb=1`,
      }));
      renderKnownGallery();
      showToast(`Loaded ${data.targets.length} reference targets!`, 'success');
    } else {
      const fname = p.split(/[\/\\]/).pop();
      appState.knownTargets = [{ label: fname, file_path: p }];
      appState.knownImages = [{
        label: fname,
        file_path: p,
        thumb_url: `/api/media/preview?path=${encodeURIComponent(p)}&thumb=1`,
      }];
      renderKnownGallery();
      showToast(`Loaded reference target: ${fname}`, 'success');
    }
  } catch (err) {
    const fname = p.split(/[\/\\]/).pop();
    appState.knownTargets = [{ label: fname, file_path: p }];
    appState.knownImages = [{
      label: fname,
      file_path: p,
      thumb_url: `/api/media/preview?path=${encodeURIComponent(p)}&thumb=1`,
    }];
    renderKnownGallery();
  }
  saveSessionState();
}

async function uploadKnownFiles(files) {
  const formData = new FormData();
  for (let i = 0; i < files.length; i++) {
    formData.append('files', files[i]);
  }
  showToast(`Uploading ${files.length} reference files...`, 'info');
  try {
    const res = await fetch('/api/upload', { method: 'POST', body: formData });
    const data = await res.json();
    if (data.success && data.files) {
      data.files.forEach(f => {
        appState.knownImages.push({
          label: f.filename,
          file_path: f.path,
          thumb_url: `/api/media/preview?path=${encodeURIComponent(f.path)}&thumb=1`,
        });
        appState.knownTargets.push({
          label: f.filename,
          file_path: f.path,
        });
      });
      renderKnownGallery();
      showToast(`Added ${data.files.length} reference images`, 'success');
    } else {
      showToast(data.error || 'Upload failed', 'error');
    }
  } catch (err) {
    showToast(`Upload error: ${err.message}`, 'error');
  }
}

function renderKnownGallery() {
  const gallery = document.getElementById('knownTargetsGallery');
  const countEl = document.getElementById('knownTargetsCount');
  if (countEl) countEl.innerText = appState.knownImages.length;
  if (!gallery) return;

  if (appState.knownImages.length === 0) {
    gallery.innerHTML = '<div class="empty-gallery">No reference targets loaded. Enter a path above.</div>';
    return;
  }

  gallery.innerHTML = appState.knownImages.map((img, idx) => `
    <div class="target-card">
      <img src="${img.thumb_url}" alt="${img.label}" loading="lazy" onerror="this.src='';this.alt='Preview N/A'" />
      <span class="target-card-label" title="${img.label}">${img.label}</span>
      <button class="target-card-remove" onclick="removeKnownImage(${idx})" title="Remove target">&times;</button>
    </div>
  `).join('');
}

window.removeKnownImage = function(idx) {
  appState.knownImages.splice(idx, 1);
  if (appState.knownTargets && appState.knownTargets.length > idx) {
    appState.knownTargets.splice(idx, 1);
  }
  renderKnownGallery();
  saveSessionState();
};

async function runVisualSearch() {
  const knownPath = document.getElementById('knownPathInput')?.value.trim();
  if (!knownPath && (!appState.knownImages || appState.knownImages.length === 0)) {
    showToast('Please specify known reference images in Step 1', 'error');
    return;
  }

  const isDbMode = appState.unknownMode === 'db';
  const unknownFolder = isDbMode ? null : document.getElementById('unknownFolderPath')?.value.trim();
  if (!isDbMode && !unknownFolder) {
    showToast('Please specify evidence folder path in Step 2, or select Full Database mode', 'error');
    return;
  }

  // If in folder mode, prompt the user if they want to name their SQLite archive
  if (!isDbMode && unknownFolder) {
    const defaultSuggestion = unknownFolder.split(/[\/\\]/).filter(Boolean).pop() || `investigation_${Date.now()}`;
    openSaveDbPromptModal(defaultSuggestion);
    return;
  }

  executeVisualSearch(null);
}

window.executeVisualSearch = async function(saveDbName = null) {
  closeSaveDbPromptModal();

  const knownPath = document.getElementById('knownPathInput')?.value.trim();
  const isDbMode = appState.unknownMode === 'db';
  const unknownFolder = isDbMode ? null : document.getElementById('unknownFolderPath')?.value.trim();

  const simThreshold = parseFloat(document.getElementById('simThresholdSlider')?.value || '0') / 100.0;
  const metric = document.getElementById('metricSelect')?.value || 'auto';
  const aggregation = document.getElementById('aggregationSelect')?.value || 'max';
  const topK = parseInt(document.getElementById('topKSelect')?.value || '0', 10);
  const recursive = document.getElementById('unknownRecursive')?.checked ?? true;
  const autoIndex = document.getElementById('unknownAutoIndex')?.checked ?? true;
  const processVideos = document.getElementById('unknownProcessVideos')?.checked ?? true;
  const videoMethod = document.getElementById('videoMethodSelect')?.value || 'ssim';
  const videoSsim = parseFloat(document.getElementById('unknownVideoSsim')?.value || '0.65');
  const videoInterval = parseFloat(document.getElementById('unknownVideoInterval')?.value || '1.0');
  const videoUniform = parseInt(document.getElementById('unknownVideoUniformCount')?.value || '10', 10);
  const activeModel = appState.activeModelKey || 'clip-vit-b-32';

  const btn = document.getElementById('btnRunVisualSearch');
  if (btn) {
    btn.disabled = true;
    btn.innerText = '⚡ Running Similarity Search...';
  }

  showToast('Executing visual similarity search against evidence...', 'info');

  try {
    const knownInput = knownPath || appState.knownImages.map(img => img.file_path);
    const payload = {
      known_input: knownInput,
      unknown_folder: unknownFolder,
      threshold: simThreshold,
      metric: metric,
      aggregation: aggregation,
      top_k: topK > 0 ? topK : null,
      recursive: recursive,
      auto_index: autoIndex,
      include_videos: processVideos,
      video_method: videoMethod,
      video_ssim_threshold: videoSsim,
      video_interval_seconds: videoInterval,
      video_uniform_count: videoUniform,
      model: activeModel,
      models: Array.from(appState.selectedModelKeys),
      save_database_name: saveDbName,
      search_mode: appState.computationMethod || 'exact',
    };

    const res = await fetch('/api/search/visual', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    const rawData = await res.json();
    if (rawData.error) throw new Error(rawData.error);
    const data = rawData.results || rawData;

    appState.investigateTargetsInitialized = false;
    appState.lastSearchResults = data;
    appState.investigateEvidenceList = data.matches || [];
    showToast(`Search complete! Found ${data.num_matches || (data.matches ? data.matches.length : 0)} matches in ${data.duration_ms || 0}ms`, 'success');

    await fetchDatabases();
    showInvestigateView();
  } catch (err) {
    showToast(`Search error: ${err.message}`, 'error');
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerText = '⚡ Run Visual Similarity Search & Open Investigation';
    }
  }
};

// ==========================================
// VISION FOUNDATION MODEL SELECTION CONTROLLER
// ==========================================

async function renderMatcherModelSelection() {
  const container = document.getElementById('matcherModelGrid');
  if (!container) return;

  try {
    const res = await fetch('/api/models');
    const data = await res.json();
    if (!data.models) return;

    if (!appState.selectedModelKeys || appState.selectedModelKeys.size === 0) {
      appState.selectedModelKeys = new Set(data.models.filter(m => m.downloaded).map(m => m.key));
      if (appState.selectedModelKeys.size === 0) appState.selectedModelKeys.add('clip-vit-b-32');
    }

    container.innerHTML = data.models.map(m => {
      const isSelected = appState.selectedModelKeys.has(m.key);
      const isReady = m.downloaded;
      const isDinov3 = m.key === 'dinov3';

      if (isReady) {
        return `
          <div class="model-click-box ${isSelected ? 'selected' : ''}" onclick="toggleModelSelection('${m.key}')">
            <div class="model-box-top">
              <span class="model-box-name">
                <span class="model-radio-dot">${isSelected ? '☑️' : '☐'}</span>
                <b>${m.display_name}</b>
              </span>
              <span class="model-pill-status pill-ready">✓ Ready</span>
            </div>
            <p class="model-box-desc">${m.description}</p>
          </div>
        `;
      } else if (isDinov3) {
        return `
          <div class="model-click-box not-downloaded" onclick="openHfTokenModal('dinov3', 'DINOv3 ViT-B/16')">
            <div class="model-box-top">
              <span class="model-box-name">
                <span class="model-radio-dot">🔒</span>
                <b>${m.display_name}</b>
              </span>
              <span class="model-pill-status pill-not-installed">🔒 Gated Model</span>
            </div>
            <p class="model-box-desc">${m.description}</p>
            <button class="btn-paste-hf-token" onclick="event.stopPropagation(); openHfTokenModal('dinov3', 'DINOv3 ViT-B/16')">
              🔑 Paste Hugging Face Token
            </button>

            <!-- Hover Popup Tooltip -->
            <div class="model-hover-tooltip" onclick="event.stopPropagation()">
              <div class="tooltip-title">🔑 Meta DINOv3 Access</div>
              <p>Meta requires accepting their license terms on Hugging Face to download weights.</p>
              <button class="btn-download-action" onclick="openHfTokenModal('dinov3', 'DINOv3 ViT-B/16')">
                🔑 Enter Token & Download
              </button>
              <a href="https://huggingface.co/facebook/dinov3-vitb16-pretrain-lvd1689m" target="_blank" style="font-size: 10px; color: var(--accent-cyan); text-decoration: underline; margin-top: 4px; display: inline-block;">
                ↗ Request Access on HuggingFace
              </a>
            </div>
          </div>
        `;
      } else {
        return `
          <div class="model-click-box not-downloaded" onclick="downloadModel('${m.key}', '${m.display_name}')">
            <div class="model-box-top">
              <span class="model-box-name">
                <span class="model-radio-dot">🔒</span>
                <b>${m.display_name}</b>
              </span>
              <span class="model-pill-status pill-not-installed">⬇️ Not Installed</span>
            </div>
            <p class="model-box-desc">${m.description}</p>

            <!-- Hover Download Popup Tooltip -->
            <div class="model-hover-tooltip" onclick="event.stopPropagation()">
              <div class="tooltip-title">⬇️ Download ${m.display_name}</div>
              <p>Model weights not installed locally. Would you like to download this model now?</p>
              <button class="btn-download-action" onclick="downloadModel('${m.key}', '${m.display_name}')">
                ⬇️ Download & Install
              </button>
            </div>
          </div>
        `;
      }
    }).join('');
  } catch (err) {
    console.error('Failed to load matcher models:', err);
  }
}

window.toggleModelSelection = function(modelKey) {
  if (appState.selectedModelKeys.has(modelKey)) {
    if (appState.selectedModelKeys.size > 1) {
      appState.selectedModelKeys.delete(modelKey);
    } else {
      showToast('At least one model must be selected', 'info');
      return;
    }
  } else {
    appState.selectedModelKeys.add(modelKey);
  }
  appState.activeModelKey = Array.from(appState.selectedModelKeys)[0];
  renderMatcherModelSelection();
  saveSessionState();
};

window.selectAllReadyModels = async function() {
  try {
    const res = await fetch('/api/models');
    const data = await res.json();
    if (data.models) {
      data.models.filter(m => m.downloaded).forEach(m => appState.selectedModelKeys.add(m.key));
      renderMatcherModelSelection();
      showToast(`Selected all ${appState.selectedModelKeys.size} ready models!`, 'success');
      saveSessionState();
    }
  } catch (e) {}
};

window.clearSelectedModels = function() {
  appState.selectedModelKeys = new Set(['clip-vit-b-32']);
  renderMatcherModelSelection();
  showToast('Reset selection to default baseline', 'info');
  saveSessionState();
};

window.selectMatcherModel = async function(modelKey) {
  appState.activeModelKey = modelKey;
  showToast(`Activating model: ${modelKey}...`, 'info');
  try {
    const res = await fetch('/api/models/set_active', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ model_key: modelKey, model: modelKey })
    });
    const data = await res.json();
    if (data.success) {
      showToast(`Model ${modelKey} activated!`, 'success');
      fetchStatus();
      renderMatcherModelSelection();
    }
  } catch (e) {
    showToast(`Model switch error: ${e.message}`, 'error');
  }
};

window.downloadModel = async function(modelKey, displayName, token = null) {
  const name = displayName || modelKey;
  const hfToken = token || localStorage.getItem('hf_token') || '';
  showToast(`Downloading weights for ${name}... (Check live console)`, 'info');
  try {
    const res = await fetch('/api/models/download', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ model_key: modelKey, model: modelKey, token: hfToken, hf_token: hfToken })
    });
    const data = await res.json();
    if (data.error) throw new Error(data.error);

    const interval = setInterval(async () => {
      try {
        const sRes = await fetch('/api/models/download_status');
        const sData = await sRes.json();
        if (!sData.is_downloading) {
          clearInterval(interval);
          if (sData.error) {
            showToast(`Download failed: ${sData.error}`, 'error');
          } else {
            showToast(`Model ${name} download complete!`, 'success');
            await selectMatcherModel(modelKey);
            renderMatcherModelSelection();
          }
        }
      } catch (err) {
        clearInterval(interval);
      }
    }, 2000);
  } catch (err) {
    showToast(`Download request error: ${err.message}`, 'error');
  }
};

// ==========================================
// HUGGING FACE TOKEN MODAL CONTROLLER
// ==========================================
window.openHfTokenModal = function(modelKey = 'dinov3', displayName = 'DINOv3 ViT-B/16') {
  appState.pendingDownloadModelKey = modelKey;
  appState.pendingDownloadModelName = displayName;

  const modal = document.getElementById('hfTokenModal');
  const input = document.getElementById('hfTokenModalInput');
  const savedStatus = document.getElementById('hfTokenSavedStatus');

  const savedToken = localStorage.getItem('hf_token') || '';
  if (input) input.value = savedToken;

  if (savedStatus) {
    if (savedToken) {
      savedStatus.innerText = '✓ Token loaded from your local browser storage.';
      savedStatus.style.color = '#4ade80';
    } else {
      savedStatus.innerText = 'Token will be stored securely in your browser localStorage.';
      savedStatus.style.color = 'var(--text-muted)';
    }
  }

  modal?.classList.remove('hidden');
  setTimeout(() => input?.focus(), 50);
};

window.closeHfTokenModal = function() {
  document.getElementById('hfTokenModal')?.classList.add('hidden');
};

function initHfTokenModal() {
  document.getElementById('btnCloseHfTokenModal')?.addEventListener('click', closeHfTokenModal);
  document.getElementById('btnCancelHfTokenModal')?.addEventListener('click', closeHfTokenModal);

  document.getElementById('btnToggleTokenVisibility')?.addEventListener('click', () => {
    const input = document.getElementById('hfTokenModalInput');
    if (input) {
      input.type = input.type === 'password' ? 'text' : 'password';
    }
  });

  document.getElementById('btnSaveHfTokenAndDownload')?.addEventListener('click', () => {
    const input = document.getElementById('hfTokenModalInput');
    const token = input ? input.value.trim() : '';

    if (!token) {
      showToast('Please paste your Hugging Face Access Token', 'error');
      input?.focus();
      return;
    }

    localStorage.setItem('hf_token', token);
    closeHfTokenModal();
    showToast('Hugging Face Token saved locally!', 'success');

    const modelKey = appState.pendingDownloadModelKey || 'dinov3';
    const modelName = appState.pendingDownloadModelName || 'DINOv3 ViT-B/16';
    downloadModel(modelKey, modelName, token);
  });
}

// ==========================================
// INVESTIGATE WORKSPACE CONTROLLER
// ==========================================
function initInvestigateWorkspace() {
  if (!appState.lastSearchResults) return;
  const res = appState.lastSearchResults.results || appState.lastSearchResults;
  
  const modelsResults = res.models_results || {};
  const computedKeys = Object.keys(modelsResults).length > 0 ? Object.keys(modelsResults) : (res.models_computed || [res.model_name || 'clip-vit-b-32']);
  
  appState.investigateActiveModel = appState.investigateActiveModel || computedKeys[0];
  if (!computedKeys.includes(appState.investigateActiveModel)) {
    appState.investigateActiveModel = computedKeys[0];
  }

  // Load matches for the active model
  if (modelsResults[appState.investigateActiveModel] && modelsResults[appState.investigateActiveModel].matches) {
    appState.investigateEvidenceList = modelsResults[appState.investigateActiveModel].matches;
  } else {
    appState.investigateEvidenceList = res.matches || [];
  }

  const folderName = res.unknown_folder ? res.unknown_folder.split(/[\/\\]/).pop() : 'Full Database';
  const caseBadge = document.getElementById('investigateCaseBadge');
  if (caseBadge) caseBadge.innerText = `📁 ${folderName} Investigation (${computedKeys.length} Models Computed)`;

  const studioTitle = document.getElementById('invStudioTitle');
  if (studioTitle) studioTitle.innerText = `${folderName} Studio`;

  // Render computed model tabs directly above the evidence gallery
  const galleryTabsList = document.getElementById('galleryModelTabsList');
  const galleryTabsBar = document.getElementById('galleryModelTabsBar');
  if (galleryTabsBar && galleryTabsList) {
    if (computedKeys.length > 0) {
      galleryTabsBar.classList.remove('hidden');
      galleryTabsList.innerHTML = computedKeys.map(mKey => {
        const isAct = mKey === appState.investigateActiveModel;
        const mInfo = modelsResults[mKey] || {};
        const dName = mInfo.display_name || getModelFullName(mKey);
        const mMetric = (mInfo.metric_used || 'cosine').toUpperCase();
        const count = mInfo.num_matches !== undefined ? mInfo.num_matches : (mInfo.matches ? mInfo.matches.length : (res.matches ? res.matches.length : 0));
        
        return `
          <button type="button" class="gallery-model-tab-btn ${isAct ? 'active' : ''}" onclick="switchInvestigateModel('${mKey}')" title="Distance Metric Formula: ${mMetric}">
            <span class="model-tab-icon">⚡</span>
            <span class="model-tab-name">${dName}</span>
            <span class="model-tab-badge">${count} Matches</span>
          </button>
        `;
      }).join('');
    } else {
      galleryTabsBar.classList.add('hidden');
    }
  }

  // Update Patch Match Control Bar visibility & Title for active model
  const patchBar = document.getElementById('dinov3PatchControlsBar');
  const patchTitle = document.getElementById('modelPatchBarTitle');
  if (patchBar) {
    patchBar.classList.remove('hidden');
  }
  const dName = getModelFullName(appState.investigateActiveModel);
  if (patchTitle) {
    const shortName = dName.split(' ')[0];
    patchTitle.innerText = `${shortName} PATCH SCORING:`;
  }

  // Model initialization complete
  renderInvestigateTargetsTree();
  renderInvestigateSemanticModelOptions();
  applyInvestigateFilters();
}

window.switchInvestigateModel = function(modelKey) {
  if (!appState.lastSearchResults) return;
  appState.investigateActiveModel = modelKey;

  const res = appState.lastSearchResults.results || appState.lastSearchResults;
  const modelsResults = res.models_results || {};

  if (appState.activeCropResults) {
    const cropModels = appState.activeCropResults.models_results || {};
    appState.investigateEvidenceList = (cropModels[modelKey] && cropModels[modelKey].matches) ? cropModels[modelKey].matches : (appState.activeCropResults.matches || []);
  } else if (appState.activeSemanticResults) {
    const semModels = appState.activeSemanticResults.models_results || {};
    appState.investigateEvidenceList = (semModels[modelKey] && semModels[modelKey].matches) ? semModels[modelKey].matches : (appState.activeSemanticResults.matches || []);
  } else {
    appState.investigateEvidenceList = (modelsResults[modelKey] && modelsResults[modelKey].matches) ? modelsResults[modelKey].matches : (res.matches || []);
  }

  // Update active button state in gallery model tabs
  document.querySelectorAll('#galleryModelTabsList .gallery-model-tab-btn').forEach(btn => {
    const onclickStr = btn.getAttribute('onclick') || '';
    btn.classList.toggle('active', onclickStr.includes(`'${modelKey}'`));
  });

  // Update Patch Match Control Bar visibility & Title for active model
  const patchBar = document.getElementById('dinov3PatchControlsBar');
  const patchTitle = document.getElementById('modelPatchBarTitle');
  if (patchBar) {
    patchBar.classList.remove('hidden');
  }
  const dName = getModelFullName(modelKey);
  if (patchTitle) {
    const shortName = dName.split(' ')[0];
    patchTitle.innerText = `${shortName} PATCH SCORING:`;
  }
  showToast(`Active Model: ${dName}`, 'info');

  applyInvestigateFilters();
};

window.toggleTreeFolder = function(headEl) {
  const itemsEl = headEl.nextElementSibling;
  const chevron = headEl.querySelector('.tree-chevron');
  if (itemsEl) {
    itemsEl.classList.toggle('hidden');
    if (chevron) chevron.innerText = itemsEl.classList.contains('hidden') ? '▶' : '▼';
  }
};

window.expandAllTree = function() {
  document.querySelectorAll('.tree-folder-items').forEach(el => el.classList.remove('hidden'));
  document.querySelectorAll('.tree-chevron').forEach(el => el.innerText = '▼');
};

window.collapseAllTree = function() {
  document.querySelectorAll('.tree-folder-items').forEach(el => el.classList.add('hidden'));
  document.querySelectorAll('.tree-chevron').forEach(el => el.innerText = '▶');
};

window.selectAllTree = function() {
  document.querySelectorAll('#invTargetsTreeContainer input[type="checkbox"]').forEach(cb => {
    cb.checked = true;
    cb.indeterminate = false;
  });
  const knownTargets = (appState.lastSearchResults && appState.lastSearchResults.known_targets) || appState.knownTargets || [];
  knownTargets.forEach(t => appState.investigateSelectedTargets.add(t.file_path || t.label));
  updateInvestigateTreeSummary();
  applyInvestigateFilters();
};

window.unselectAllTree = function() {
  document.querySelectorAll('#invTargetsTreeContainer input[type="checkbox"]').forEach(cb => {
    cb.checked = false;
    cb.indeterminate = false;
  });
  appState.investigateSelectedTargets.clear();
  updateInvestigateTreeSummary();
  applyInvestigateFilters();
};

window.toggleInvestigateTargetSelection = function(keyEnc, isChecked) {
  const key = decodeURIComponent(keyEnc);
  if (isChecked) {
    appState.investigateSelectedTargets.add(key);
  } else {
    appState.investigateSelectedTargets.delete(key);
  }
  updateInvestigateTreeSummary();
  applyInvestigateFilters();
};

window.selectFolderTargets = function(folderNameEnc, selectAll) {
  const folderName = decodeURIComponent(folderNameEnc);
  const knownTargets = (appState.lastSearchResults?.known_targets && appState.lastSearchResults.known_targets.length > 0)
    ? appState.lastSearchResults.known_targets
    : ((appState.knownTargets && appState.knownTargets.length > 0) ? appState.knownTargets : []);

  if (!appState.investigateSelectedTargets) {
    appState.investigateSelectedTargets = new Set();
  }

  // Find all items belonging to this folderName
  const folderKeys = [];
  knownTargets.forEach(t => {
    let groupName = t.group_name;
    if (!groupName || groupName === 'default' || groupName === 'Reference') {
      if (t.file_path) {
        const parts = t.file_path.split(/[\/\\]/).filter(Boolean);
        if (parts.length >= 2) {
          const parentFolder = parts[parts.length - 2];
          groupName = (parentFolder && parentFolder !== 'known_files' && parentFolder !== 'test_images') ? parentFolder : 'General';
        } else {
          groupName = 'General';
        }
      } else {
        groupName = 'General';
      }
    }
    if (groupName === folderName) {
      folderKeys.push(t.file_path || t.label);
    }
  });

  folderKeys.forEach(k => {
    if (selectAll) {
      appState.investigateSelectedTargets.add(k);
    } else {
      appState.investigateSelectedTargets.delete(k);
    }
  });

  // Update item checkboxes in DOM for this folder group
  const folderGroupEl = document.querySelector(`.tree-folder-group[data-folder="${folderNameEnc}"]`);
  if (folderGroupEl) {
    folderGroupEl.querySelectorAll('.tree-item-row input[type="checkbox"]').forEach(cb => {
      cb.checked = selectAll;
    });
    const folderCb = folderGroupEl.querySelector('.tree-folder-cb');
    if (folderCb) {
      folderCb.checked = selectAll;
      folderCb.indeterminate = false;
    }
  }

  updateInvestigateTreeSummary();
  applyInvestigateFilters();
};

function updateInvestigateTreeSummary() {
  const total = (appState.lastSearchResults && appState.lastSearchResults.known_targets && appState.lastSearchResults.known_targets.length) || appState.knownTargets.length;
  const count = appState.investigateSelectedTargets ? appState.investigateSelectedTargets.size : 0;
  const el = document.getElementById('invTreeSummaryText');
  if (el) el.innerText = `Selected ${count} of ${total} reference targets`;

  // Synchronize folder-level checkboxes (checked, unchecked, or indeterminate)
  document.querySelectorAll('.tree-folder-group').forEach(groupEl => {
    const itemCbs = groupEl.querySelectorAll('.tree-item-row input[type="checkbox"]');
    const folderCb = groupEl.querySelector('.tree-folder-cb');
    if (folderCb && itemCbs.length > 0) {
      const checkedCount = Array.from(itemCbs).filter(cb => cb.checked).length;
      folderCb.checked = (checkedCount === itemCbs.length);
      folderCb.indeterminate = (checkedCount > 0 && checkedCount < itemCbs.length);
    }
  });
}

window.applyInvestigateFilters = function() {
  const rawList = appState.investigateEvidenceList || [];
  const searchTxt = (document.getElementById('invSearchInput')?.value || '').toLowerCase().trim();
  const matchStatus = document.getElementById('invMatchStatusSelect')?.value || 'all';
  const mediaType = document.querySelector('input[name="inv_media_type"]:checked')?.value || 'all';
  const minScore = parseFloat(document.getElementById('invMinScoreSlider')?.value || '0');
  const sortBy = document.getElementById('invSortSelect')?.value || 'score_desc';

  const selectedTargets = appState.investigateSelectedTargets || new Set();
  const allTargets = (appState.lastSearchResults && appState.lastSearchResults.known_targets) || appState.knownTargets || [];
  const totalTargets = allTargets.length;
  const isSubsetSelected = !appState.activeCropResults && !appState.investigateSearchQuery && totalTargets > 0 && selectedTargets.size > 0 && selectedTargets.size < totalTargets;

  let filtered = [];

  const matchesSelected = (tPath, tLabel) => {
    if (!tPath && !tLabel) return false;
    if (selectedTargets.has(tPath) || selectedTargets.has(tLabel)) return true;
    const tFname = tPath ? tPath.split(/[\/\\]/).pop() : '';
    const tBase = tFname ? tFname.replace(/\.[^/.]+$/, '') : (tLabel ? tLabel.replace(/\.[^/.]+$/, '') : '');
    if (tFname && selectedTargets.has(tFname)) return true;
    if (tBase && selectedTargets.has(tBase)) return true;
    for (const sel of selectedTargets) {
      const selBase = sel.split(/[\/\\]/).pop().replace(/\.[^/.]+$/, '');
      if (sel === tPath || sel === tLabel || sel === tFname || (selBase && (selBase === tBase || sel.includes(tBase) || tPath.includes(selBase)))) {
        return true;
      }
    }
    return false;
  };

  for (const item of rawList) {
    const itemId = item.id || item.file_path;
    if (appState.investigateHiddenIds.has(itemId)) continue;

    const fname = (item.filename || item.file_path.split(/[\/\\]/).pop() || '').toLowerCase();
    const fpath = (item.file_path || '').toLowerCase();
    if (searchTxt && !fname.includes(searchTxt) && !fpath.includes(searchTxt)) {
      continue;
    }

    const isVideo = item.media_type === 'video' || item.keyframes_count > 0;
    if (mediaType === 'images' && isVideo) continue;
    if (mediaType === 'videos' && !isVideo) continue;

    let effectiveScore = item.similarity_pct !== undefined ? item.similarity_pct : (item.score * 100);
    let effectiveTargetLabel = item.best_target_label;
    let effectiveTargetPath = item.best_target_path;

    // Evaluate target selection filtering dynamically
    if (!appState.activeCropResults && !appState.investigateSearchQuery && totalTargets > 0) {
      if (selectedTargets.size === 0) {
        continue;
      }

      if (isSubsetSelected) {
        let isTargetSelected = false;
        let bestSubScore = -999999.0;
        let bestSubTarget = null;
        let bestSubPct = 0.0;

        if (item.all_target_scores && Array.isArray(item.all_target_scores) && item.all_target_scores.length > 0) {
          const matchedTargetScores = [];
          for (let i = 0; i < item.all_target_scores.length; i++) {
            const entry = item.all_target_scores[i];
            const tObj = (typeof entry === 'object' && entry !== null) ? entry : (allTargets[i] || {});
            const tPath = tObj.target_path || tObj.file_path || (allTargets[i] && allTargets[i].file_path) || '';
            const tLabel = tObj.target_label || tObj.label || (allTargets[i] && allTargets[i].label) || '';

            const isEntryMatched = (typeof entry === 'object' && entry !== null)
              ? matchesSelected(tPath, tLabel)
              : Boolean(allTargets[i] && matchesSelected(allTargets[i].file_path, allTargets[i].label));
            if (isEntryMatched) {
              const scoreVal = (typeof entry === 'object' && entry !== null) ? (entry.score ?? 0.0) : (typeof entry === 'number' ? entry : 0.0);
              const pctVal = (typeof entry === 'object' && entry !== null) ? (entry.similarity_pct ?? (scoreVal * 100)) : (scoreVal * 100);
              matchedTargetScores.push({
                file_path: tPath,
                label: tLabel || (allTargets[i] && (allTargets[i].label || allTargets[i].file_path)) || `Target ${i+1}`,
                score: scoreVal,
                similarity_pct: pctVal,
              });
            }
          }

          if (matchedTargetScores.length > 0) {
            isTargetSelected = true;
            if (appState.dinov3PatchMode === 'avg') {
              const avgScore = matchedTargetScores.reduce((acc, t) => acc + t.score, 0) / matchedTargetScores.length;
              const avgPct = matchedTargetScores.reduce((acc, t) => acc + t.similarity_pct, 0) / matchedTargetScores.length;
              effectiveScore = avgPct;
              effectiveTargetLabel = matchedTargetScores.length > 1 ? `Avg of ${matchedTargetScores.length} targets` : matchedTargetScores[0].label;
              effectiveTargetPath = matchedTargetScores[0].file_path;
            } else {
              matchedTargetScores.sort((a, b) => b.score - a.score);
              effectiveScore = matchedTargetScores[0].similarity_pct;
              effectiveTargetLabel = matchedTargetScores[0].label;
              effectiveTargetPath = matchedTargetScores[0].file_path;
            }
          }
        }

        if (!isTargetSelected) {
          const tPath = item.best_target_path || '';
          const tLabel = item.best_target_label || '';
          if (matchesSelected(tPath, tLabel)) {
            isTargetSelected = true;
            effectiveScore = item.similarity_pct !== undefined ? item.similarity_pct : (item.score * 100);
            effectiveTargetLabel = item.best_target_label;
            effectiveTargetPath = item.best_target_path;
          }
        }

        if (!isTargetSelected) {
          continue;
        }
      }
    }

    // Preserve genuine model similarity score for ranking and presentation
    const isDinoModel = (appState.investigateActiveModel || '').toLowerCase().includes('dino');
    let pMax, pAvg;

    if (isDinoModel && item.patch_max_score !== undefined && item.patch_avg_score !== undefined) {
      pMax = item.patch_max_score;
      pAvg = item.patch_avg_score;
      effectiveScore = (appState.dinov3PatchMode === 'avg') ? pAvg : pMax;
    } else {
      pMax = effectiveScore;
      pAvg = effectiveScore;
    }

    item.patch_scoring_mode = appState.dinov3PatchMode || 'max';
    item.current_patch_max = pMax;
    item.current_patch_avg = pAvg;

    if (isDinoModel && effectiveScore < (appState.dinov3PatchThreshold || 0)) {
      continue;
    }

    item.display_score = effectiveScore / 100.0;
    item.display_similarity_pct = Math.round(effectiveScore * 100) / 100;
    item.display_target_label = effectiveTargetLabel;
    item.display_target_path = effectiveTargetPath;

    const isMatched = effectiveScore > 0.0;
    if (matchStatus === 'matched' && !isMatched) continue;
    if (matchStatus === 'unmatched' && isMatched) continue;
    if (effectiveScore < minScore) continue;

    filtered.push(item);
  }

  // Sort filtered list
  if (sortBy === 'score_desc') {
    filtered.sort((a, b) => ((b.display_similarity_pct ?? b.similarity_pct ?? (b.score * 100)) - (a.display_similarity_pct ?? a.similarity_pct ?? (a.score * 100))));
  } else if (sortBy === 'score_asc') {
    filtered.sort((a, b) => ((a.display_similarity_pct ?? a.similarity_pct ?? (a.score * 100)) - (b.display_similarity_pct ?? b.similarity_pct ?? (b.score * 100))));
  } else if (sortBy === 'name_asc') {
    filtered.sort((a, b) => (a.filename || a.file_path).localeCompare(b.filename || b.file_path));
  } else if (sortBy === 'name_desc') {
    filtered.sort((a, b) => (b.filename || b.file_path).localeCompare(a.filename || a.file_path));
  }

  const totalCount = filtered.length;
  const matchedCount = filtered.filter(m => (m.display_similarity_pct ?? m.similarity_pct ?? (m.score * 100)) > 0.0).length;
  const unmatchedCount = totalCount - matchedCount;

  const stTotal = document.getElementById('invStatTotal');
  const stMatched = document.getElementById('invStatMatched');
  const stUnmatched = document.getElementById('invStatUnmatched');

  if (stTotal) stTotal.innerText = totalCount;
  if (stMatched) stMatched.innerText = matchedCount;
  if (stUnmatched) stUnmatched.innerText = unmatchedCount;

  const unhideBtn = document.getElementById('btnUnHideAll');
  if (unhideBtn) {
    unhideBtn.classList.toggle('hidden', appState.investigateHiddenIds.size === 0);
  }

  const dinoBadge = document.getElementById('dinov3PatchCountBadge');
  if (dinoBadge) {
    dinoBadge.innerText = `${filtered.length} Matches (≥ ${appState.dinov3PatchThreshold || 0}%)`;
  }
  
  renderInvestigateGrid(filtered);
};

function isVideoMedia(item) {
  if (!item) return false;
  const fpath = item.file_path || item.video_path || '';
  const ext = fpath.split('.').pop().toLowerCase();
  if (['jpg', 'jpeg', 'png', 'webp', 'bmp', 'tif', 'tiff', 'gif'].includes(ext)) {
    return false;
  }
  if (['mp4', 'mov', 'avi', 'mkv', 'webm', 'm4v', 'flv'].includes(ext)) {
    return true;
  }
  return item.media_type === 'video' || (item.keyframes_count && item.keyframes_count > 0);
}

function renderInvestigateGrid(items) {
  appState.investigateRenderedList = items || [];
  const grid = document.getElementById('investigateResultsGrid');
  const emptyState = document.getElementById('invEmptyState');
  if (!grid) return;

  if (items.length === 0) {
    grid.innerHTML = '';
    emptyState?.classList.remove('hidden');
    return;
  }

  emptyState?.classList.add('hidden');

  grid.innerHTML = items.map((item, idx) => {
    const isVideo = isVideoMedia(item);
    const fpath = item.file_path || '';
    const fname = item.filename || fpath.split(/[\/\\]/).pop() || 'media';
    const scorePct = item.display_similarity_pct !== undefined ? item.display_similarity_pct : (item.similarity_pct !== undefined ? item.similarity_pct : (item.score * 100).toFixed(1));
    const scoreClass = scorePct >= 85 ? 'match-high' : scorePct >= 65 ? 'match-med' : 'match-none';
    let scorePrefix = '';
    if (appState.investigateActiveModel?.toLowerCase().includes('dino')) {
      scorePrefix = appState.dinov3PatchMode === 'avg' ? '📊 Mean ' : '🏆 Max ';
    }
    const scoreLabel = scorePct > 0 ? `${scorePrefix}${scorePct}% Match` : 'Scanned No Match';
    const seriesName = fpath ? (fpath.split(/[\/\\]/).slice(-2, -1)[0] || 'evidence') : 'evidence';

    const thumbImgPath = isVideo && item.top_keyframe ? item.top_keyframe.file_path : fpath;
    const thumbUrl = `/api/media/preview?path=${encodeURIComponent(thumbImgPath)}&thumb=1&v=20260823_91`;

    const targetLabel = item.display_target_label || item.best_target_label || (isVideo && item.top_keyframe ? item.top_keyframe.best_target_label : '') || '';
    const targetPath = item.display_target_path || item.best_target_path || (isVideo && item.top_keyframe ? item.top_keyframe.best_target_path : '') || '';
    const targetThumbUrl = targetPath ? `/api/media/preview?path=${encodeURIComponent(targetPath)}&thumb=1&v=20260823_91` : '';

    const exifInfo = `${item.width || 0} × ${item.height || 0} px`;
    const rankOrder = `${idx + 1}/${items.length}`;

    return `
      <div class="evidence-card" onclick="onEvidenceCardClick(${idx})">
        <div class="card-img-wrap">
          <span class="card-order-badge" title="Result Order: ${rankOrder}">#${rankOrder}</span>
          ${isVideo ? `
            <span class="card-video-pill">
              <span>🎬</span> Video (${item.keyframes_count || 1} frames)
            </span>
          ` : ''}
          <img src="${thumbUrl}" alt="${fname}" loading="lazy" onload="if(this.nextElementSibling && this.nextElementSibling.classList.contains('card-localized-bbox-overlay')) onCardImageLoad(this, [${item.localized_box ? item.localized_box.join(',') : ''}])" onerror="this.src='';this.alt='Preview N/A'" />
          ${item.localized_box && Array.isArray(item.localized_box) && item.localized_box.length === 4 ? `
            <div class="card-localized-bbox-overlay" data-bbox="${item.localized_box.join(',')}">
              <span class="bbox-tag">🎯 Matched Object</span>
            </div>
          ` : ''}
          <span class="card-score-badge ${scoreClass}">${scoreLabel}</span>
        </div>

        <div class="card-body-content">
          <div class="card-title-row" style="display: flex; justify-content: space-between; align-items: center; gap: 6px;">
            <div class="card-filename" title="${fname}" style="flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${fname}</div>
            <span class="card-rank-tag" title="Result Order: ${rankOrder}">#${rankOrder}</span>
          </div>
          
          <div class="card-filepath" title="${fpath}" onclick="event.stopPropagation(); navigator.clipboard.writeText('${fpath}'); showToast('Path copied!', 'success');">
            📍 ${fpath}
          </div>

          ${targetLabel ? `
            <div class="card-matched-target-box">
              ${targetThumbUrl ? `<img src="${targetThumbUrl}" alt="Target" class="matched-target-thumb" />` : ''}
              <div class="matched-target-info">
                <span class="target-sub">Matched Target</span>
                <span class="target-name" title="${targetLabel}">${targetLabel}</span>
              </div>
            </div>
          ` : ''}

          <div class="card-series-row">
            <span class="series-tag-badge">🏷️ ${seriesName}</span>
            <span style="font-weight: 700; color: ${scorePct >= 80 ? '#4ade80' : 'var(--text-muted)'};">${scoreLabel}</span>
          </div>

                    ${item.patch_matched ? `
            <div style="margin-top: 6px; display: flex; align-items: center; justify-content: space-between; background: rgba(0, 242, 254, 0.08); border: 1px solid rgba(0, 242, 254, 0.3); border-radius: 5px; padding: 3px 7px;">
              <span style="font-size: 9.5px; font-weight: 700; color: var(--accent-cyan); display: flex; align-items: center; gap: 4px;">
                <span>🎯</span> DINOv3 Patch Match
              </span>
              <span style="font-size: 10px; font-weight: 800; color: #4ade80;">${item.patch_similarity_pct}%</span>
            </div>
            ${item.patch_heatmap_url ? `
              <button type="button" class="btn btn-secondary-outline btn-xs" style="margin-top: 4px; width: 100%; font-size: 9.5px; font-weight: 700; color: var(--accent-cyan); border-color: var(--accent-cyan); padding: 2px 6px;" onclick="event.stopPropagation(); toggleCardHeatmap(this, '${encodeURIComponent(item.patch_heatmap_url)}', '${encodeURIComponent(thumbUrl)}')">
                <span>🗺️</span> Toggle Heatmap Overlay
              </button>
            ` : ''}
          ` : ''}

${item.all_model_scores && Object.keys(item.all_model_scores).length > 1 ? `
            <div class="multi-model-score-strip" style="display: flex; gap: 4px; flex-wrap: wrap; margin-top: 4px;">
              ${Object.entries(item.all_model_scores).map(([mk, sc]) => `
                <span class="pill pill-xs ${mk === appState.investigateActiveModel ? 'pill-cyan' : ''}" style="font-size: 9px; padding: 2px 4px;">
                  ${mk.split('-')[0]}: ${sc}%
                </span>
              `).join('')}
            </div>
          ` : ''}

          <div class="card-exif-line" title="Dimensions: ${exifInfo}">
            📷 Dims: ${exifInfo}
          </div>

          <div class="card-actions-row">
            <button class="btn-card-action" onclick="event.stopPropagation(); triggerInvestigateCrop('${encodeURIComponent(thumbImgPath)}', '${fname}')" title="Crop and search target region">
              <span>✂️</span> Crop
            </button>
            <button class="btn-card-action" onclick="event.stopPropagation(); triggerReverseEngineer('${encodeURIComponent(item.file_path || '')}', ${item.id || item.media_id || 'null'})" title="Reverse engineer image representation from embeddings">
              <span>🧠</span> Invert
            </button>
            <button class="btn-card-action" onclick="event.stopPropagation(); hideInvestigateFile('${encodeURIComponent(item.id || item.file_path)}')">
              <span>🙈</span> Hide
            </button>
          </div>
        </div>
      </div>
    `;  }).join('');
}

window.onEvidenceCardClick = function(idx) {
  const items = appState.investigateRenderedList || appState.investigateEvidenceList || [];
  const item = items[idx];
  if (!item) return;

  if (isVideoMedia(item)) {
    window.openVideoReviewModal(item);
  } else {
    window.openInvestigateDetailModal(item);
  }
};

window.hideInvestigateItem = function(itemId) {
  appState.investigateHiddenIds.add(itemId);
  applyInvestigateFilters();
  showToast('Item hidden from view', 'info');
};

window.unhideAllInvestigateFiles = function() {
  appState.investigateHiddenIds.clear();
  applyInvestigateFilters();
  showToast('All items unhidden', 'success');
};

window.toggleTopFilterMenu = function() {
  const menu = document.getElementById('topFilterDropdownMenu');
  if (menu) menu.classList.toggle('hidden');
};

window.onInvestigateMinScoreChange = function(val) {
  const valEl = document.getElementById('invMinScoreVal');
  if (valEl) valEl.innerText = val === '0' ? '0% (Show All)' : `${val}%`;
  applyInvestigateFilters();
};

window.recomputeInvestigation = async function() {
  if (!appState.lastSearchResults) {
    showToast('No active search to recompute', 'error');
    return;
  }

  const activeTargets = Array.from(appState.investigateSelectedTargets);
  if (activeTargets.length === 0) {
    showToast('Please select at least 1 reference target in the sidebar tree', 'error');
    return;
  }

  const mode = appState.computationMethod || 'exact';
  const modeLabel = mode === 'ann' ? '🚀 ANN (Efficient Approx)' : '⚡ Exact (Brute Force Matrix)';
  showToast(`[${modeLabel}] Recomputing matches across active reference targets...`, 'info');
  const btn = document.getElementById('btnInvestigateRecompute');
  if (btn) btn.disabled = true;

  try {
    const unknownFolder = (appState.lastSearchResults.unknown_folder && !appState.lastSearchResults.unknown_folder.startsWith('databases/'))
      ? appState.lastSearchResults.unknown_folder
      : null;
    const model = appState.investigateActiveModel || appState.activeModelKey || 'clip-vit-b-32';
    const computedModels = appState.lastSearchResults.models_computed || (appState.lastSearchResults.models_results ? Object.keys(appState.lastSearchResults.models_results) : [model]);

    const payload = {
      known_input: activeTargets,
      unknown_folder: unknownFolder,
      threshold: 0.0,
      metric: 'auto',
      model: model,
      models: computedModels,
      include_videos: true,
      auto_index: false,
      search_mode: mode,
    };

    const res = await fetch('/api/search/visual', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    const rawData = await res.json();
    if (rawData.error) throw new Error(rawData.error);
    const data = rawData.results || rawData;

    appState.lastSearchResults = data;

    // Load matches for the active model
    const activeM = appState.investigateActiveModel;
    if (data.models_results && data.models_results[activeM] && data.models_results[activeM].matches) {
      appState.investigateEvidenceList = data.models_results[activeM].matches;
    } else {
      appState.investigateEvidenceList = data.matches || [];
    }

    applyInvestigateFilters();
    showToast(`[${modeLabel}] Recomputed ${data.num_matches || (data.matches ? data.matches.length : 0)} matches in ${data.duration_ms || 0}ms!`, 'success');
  } catch (err) {
    showToast(`Recompute failed: ${err.message}`, 'error');
  } finally {
    if (btn) btn.disabled = false;
  }
};

window.onInvestigateModelChange = function(modelKey) {
  switchInvestigateModel(modelKey);
};

// Detail Modal Controller & Studio Crop

window.toggleSidebarSection = function(headerEl) {
  const card = headerEl.closest('.sidebar-accordion-card');
  if (!card) return;
  const body = card.querySelector('.sidebar-accordion-body');
  const chevron = headerEl.querySelector('.accordion-chevron-icon');
  
  if (body) {
    const isHidden = body.classList.contains('hidden');
    body.classList.toggle('hidden', !isHidden);
    headerEl.classList.toggle('active-header', isHidden);
    if (chevron) {
      chevron.innerText = isHidden ? '▼' : '▶';
    }
  }
};

window.openInvestigateDetailModal = function(item) {
  appState.activeDetailItem = item;
  const modal = document.getElementById('investigateDetailModal');
  const fname = item.filename || item.file_path.split(/[\/\\]/).pop();

  document.getElementById('detailFilename').innerText = fname;
  document.getElementById('detailPath').innerText = item.file_path;
  document.getElementById('detailDims').innerText = `${item.width || 0} x ${item.height || 0} px`;
  document.getElementById('detailMd5').innerText = item.file_hash || 'Computed from vector';
  document.getElementById('detailExif').innerText = item.indexed_at ? `Indexed: ${item.indexed_at}` : 'Local File Record';

  const img = document.getElementById('detailImg');
  img.src = `/api/media/preview?path=${encodeURIComponent(item.file_path)}`;

  const targetsContainer = document.getElementById('detailTargetsList');
  const scorePct = item.similarity_pct !== undefined ? item.similarity_pct : (item.score * 100).toFixed(1);
  const targetLabel = item.best_target_label || 'Reference Target';
  const targetPath = item.best_target_path || '';

  targetsContainer.innerHTML = `
    <div class="card-matched-target-box" style="padding: 10px;">
      ${targetPath ? `<img src="/api/media/preview?path=${encodeURIComponent(targetPath)}&thumb=1" class="matched-target-thumb" style="width: 48px; height: 48px;" />` : ''}
      <div class="matched-target-info">
        <span class="target-sub" style="font-size: 11px;">Highest Reference Match (${scorePct}%)</span>
        <span class="target-name" style="font-size: 13px;">${targetLabel}</span>
        <span style="font-size: 10px; color: var(--text-muted);">${targetPath}</span>
      </div>
    </div>

    ${item.forensic_explanation ? `
      <div class="forensic-explanation-card glass" style="margin-top: 12px; padding: 14px; border-radius: 8px; border: 1px solid rgba(0, 242, 254, 0.35); background: rgba(0, 242, 254, 0.04);">
        <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px;">
          <div style="font-size: 12.5px; font-weight: 700; color: var(--accent-cyan); display: flex; align-items: center; gap: 6px;">
            <span>🔬</span> ${item.forensic_explanation.title}
          </div>
          <span class="pill pill-xs pill-cyan" style="font-size: 9px; font-weight: 700;">TRAINING & TESTING BREAKDOWN</span>
        </div>
        <p style="font-size: 11px; color: var(--text-main); margin: 0 0 12px 0; line-height: 1.5;">
          ${item.forensic_explanation.rationale}
        </p>
        
        <div style="font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px; color: var(--accent-cyan); margin-bottom: 8px;">
          ⚙️ Algorithmic Steps Executed:
        </div>
        <div class="forensic-steps-timeline" style="display: flex; flex-direction: column; gap: 8px; border-left: 2px solid var(--accent-cyan); padding-left: 10px; margin-left: 4px;">
          ${item.forensic_explanation.pipeline_steps.map(st => `
            <div style="font-size: 11px;">
              <div style="display: flex; justify-content: space-between; align-items: baseline;">
                <strong style="color: #fff; font-size: 11px;">Step ${st.step}: ${st.name}</strong>
                <span style="font-family: var(--font-mono); color: var(--accent-cyan); font-size: 10px; font-weight: 700;">${st.metric}</span>
              </div>
              <div style="color: var(--text-muted); font-size: 10.5px; margin-top: 2px;">${st.description}</div>
            </div>
          `).join('')}
        </div>

        <div style="margin-top: 12px; padding: 10px; background: rgba(0,0,0,0.35); border: 1px solid rgba(255,255,255,0.06); border-radius: 6px; display: flex; justify-content: space-around; text-align: center;">
          <div>
            <div style="font-size: 9.5px; color: var(--text-muted);">Global [CLS] Score</div>
            <div style="font-size: 13px; font-weight: 700; color: var(--text-secondary);">${item.forensic_explanation.comparison.global_cls_score}</div>
          </div>
          <div>
            <div style="font-size: 9.5px; color: var(--accent-cyan);">DINOv3 Dense Patch Score</div>
            <div style="font-size: 13px; font-weight: 700; color: var(--accent-cyan);">${item.forensic_explanation.comparison.dense_patch_score}</div>
          </div>
          <div>
            <div style="font-size: 9.5px; color: #4ade80;">Confidence Gain</div>
            <div style="font-size: 13px; font-weight: 700; color: #4ade80;">${item.forensic_explanation.comparison.confidence_gain}</div>
          </div>
        </div>

        ${item.patch_heatmap_url ? `
          <div style="margin-top: 10px;">
            <button type="button" id="btnToggleDetailHeatmap" class="btn btn-secondary-outline btn-xs" style="width: 100%; font-weight: 700; color: var(--accent-cyan); border-color: var(--accent-cyan); padding: 5px;" onclick="toggleDetailPatchHeatmap('${encodeURIComponent(item.patch_heatmap_url)}')">
              <span>🗺️</span> Toggle DINOv3 Patch Activation Heatmap & Localization Box
            </button>
          </div>
        ` : ''}
      </div>
    ` : ''}
  `;

  document.getElementById('btnDetailCopyPath').onclick = () => {
    navigator.clipboard.writeText(item.file_path);
    showToast('Path copied to clipboard!', 'success');
  };

  initDetailCropTool();
  modal?.classList.remove('hidden');
};

window.closeInvestigateDetailModal = function() {
  document.getElementById('investigateDetailModal')?.classList.add('hidden');
};


// ==========================================
// UNIVERSAL PATCH / SECTOR MATCH CONTROLLERS
// ==========================================
window.setDinov3PatchMode = function(mode) {
  appState.dinov3PatchMode = mode === 'avg' ? 'avg' : 'max';
  
  document.getElementById('btnPatchModeMax')?.classList.toggle('active', appState.dinov3PatchMode === 'max');
  document.getElementById('btnPatchModeAvg')?.classList.toggle('active', appState.dinov3PatchMode === 'avg');
  
  const lbl = document.getElementById('dinov3PatchSliderLabel');
  if (lbl) {
    const prefix = appState.dinov3PatchMode === 'max' ? '🎯 Min Max Score:' : '📊 Min Average Score:';
    lbl.innerHTML = `${prefix} <span id="dinov3PatchSliderVal" style="color: var(--accent-cyan); font-family: var(--font-mono);">${appState.dinov3PatchThreshold || 0}%</span>`;
  }

  const activeModelName = getModelFullName(appState.investigateActiveModel);
  const shortModel = activeModelName.split(' ')[0];
  const modeTitle = appState.dinov3PatchMode === 'max' ? 'Max Score (Peak / Highest Match)' : 'Average Score (Mean / Overall Alignment)';
  showToast(`${shortModel} Scoring: Switched to ${modeTitle}`, 'info');

  saveSessionState();
  applyInvestigateFilters();
};

window.setPatchScoringMode = window.setDinov3PatchMode;

window.onDinov3PatchSliderInput = function(val) {
  appState.dinov3PatchThreshold = parseFloat(val) || 0;
  const valEl = document.getElementById('dinov3PatchSliderVal');
  if (valEl) valEl.innerText = `${appState.dinov3PatchThreshold}%`;

  saveSessionState();
  applyInvestigateFilters();
};

window.onPatchSliderInput = window.onDinov3PatchSliderInput;


window.onCardImageLoad = function(imgEl, bbox) {
  if (!imgEl || !bbox || bbox.length !== 4) return;
  const wrap = imgEl.parentElement;
  if (!wrap) return;

  const [bx1, by1, bx2, by2] = bbox;
  const nW = imgEl.naturalWidth || imgEl.width || 1;
  const nH = imgEl.naturalHeight || imgEl.height || 1;
  const cW = wrap.clientWidth || 300;
  const cH = wrap.clientHeight || 200;

  const cAspect = cW / (cH || 1);
  const iAspect = nW / (nH || 1);

  let rW, rH, lOff, tOff;
  if (iAspect < cAspect) {
    // Portrait / vertical image (e.g. 3024x4032) -> pillarboxed with black bars on left and right
    rW = (iAspect / cAspect) * 100.0;
    rH = 100.0;
    lOff = (100.0 - rW) / 2.0;
    tOff = 0.0;
  } else {
    // Landscape / horizontal image (e.g. 4032x3024) -> letterboxed with black bars on top and bottom
    rW = 100.0;
    rH = (cAspect / iAspect) * 100.0;
    lOff = 0.0;
    tOff = (100.0 - rH) / 2.0;
  }

  const boxL = Math.max(0, Math.min(96, lOff + bx1 * rW));
  const boxT = Math.max(0, Math.min(96, tOff + by1 * rH));
  const boxW = Math.max(6, Math.min(100 - boxL, (bx2 - bx1) * rW));
  const boxH = Math.max(6, Math.min(100 - boxT, (by2 - by1) * rH));

  const box = wrap.querySelector('.card-localized-bbox-overlay');
  if (box) {
    box.style.left = `${boxL.toFixed(1)}%`;
    box.style.top = `${boxT.toFixed(1)}%`;
    box.style.width = `${boxW.toFixed(1)}%`;
    box.style.height = `${boxH.toFixed(1)}%`;
    box.style.display = 'block';
  }
};

window.toggleCardHeatmap = function(btnEl, encHeatmapUrl, encOriginalThumbUrl) {
  const card = btnEl.closest('.evidence-card');
  if (!card) return;
  const img = card.querySelector('.card-img-wrap img');
  if (!img) return;

  const heatmapUrl = decodeURIComponent(encHeatmapUrl || '');
  const origUrl = decodeURIComponent(encOriginalThumbUrl || '');

  if (img.getAttribute('data-is-heatmap') === '1') {
    img.src = origUrl;
    img.removeAttribute('data-is-heatmap');
    btnEl.innerHTML = '<span>🗺️</span> Toggle Heatmap Overlay';
    showToast('Restored standard evidence photograph', 'info');
  } else {
    img.setAttribute('data-is-heatmap', '1');
    img.src = heatmapUrl;
    btnEl.innerHTML = '<span>🖼️</span> Restore Photo';
    showToast('Displaying DINOv3 Patch Activation Heatmap & Bounding Box Overlay!', 'success');
  }
};

window.toggleDetailPatchHeatmap = function(encHeatmapUrl) {
  const heatmapUrl = decodeURIComponent(encHeatmapUrl || '');
  const img = document.getElementById('detailImg');
  const btn = document.getElementById('btnToggleDetailHeatmap');
  if (!img) return;

  if (img.getAttribute('data-original-src')) {
    img.src = img.getAttribute('data-original-src');
    img.removeAttribute('data-original-src');
    if (btn) btn.innerText = '🗺️ Toggle DINOv3 Patch Activation Heatmap & Localization Box';
    showToast('Restored standard evidence photograph', 'info');
  } else {
    img.setAttribute('data-original-src', img.src);
    img.src = heatmapUrl;
    if (btn) btn.innerText = '🖼️ Restore Original Photograph';
    showToast('Displaying DINOv3 Dense Spatial Patch Heatmap & Bounding Box Overlay!', 'success');
  }
};

function initDetailCropTool() {
  const wrap = document.getElementById('detailCanvasWrap');
  const box = document.getElementById('detailCropBox');
  if (!wrap || !box) return;

  let isDrawing = false;
  let startX = 0, startY = 0;

  wrap.onmousedown = (e) => {
    const rect = wrap.getBoundingClientRect();
    startX = e.clientX - rect.left;
    startY = e.clientY - rect.top;
    isDrawing = true;
    box.style.left = `${startX}px`;
    box.style.top = `${startY}px`;
    box.style.width = '0px';
    box.style.height = '0px';
    box.classList.remove('hidden');
  };

  wrap.onmousemove = (e) => {
    if (!isDrawing) return;
    const rect = wrap.getBoundingClientRect();
    const curX = Math.max(0, Math.min(rect.width, e.clientX - rect.left));
    const curY = Math.max(0, Math.min(rect.height, e.clientY - rect.top));

    const left = Math.min(startX, curX);
    const top = Math.min(startY, curY);
    const width = Math.abs(curX - startX);
    const height = Math.abs(curY - startY);

    box.style.left = `${left}px`;
    box.style.top = `${top}px`;
    box.style.width = `${width}px`;
    box.style.height = `${height}px`;
  };

  wrap.onmouseup = () => {
    isDrawing = false;
  };
}

window.runDetailCropSearch = async function() {
  const item = appState.activeDetailItem;
  const box = document.getElementById('detailCropBox');
  const img = document.getElementById('detailImg');
  if (!item || !box || !img) return;

  const boxRect = box.getBoundingClientRect();
  const imgRect = img.getBoundingClientRect();

  if (boxRect.width <= 5 || boxRect.height <= 5 || imgRect.width <= 0 || imgRect.height <= 0) {
    showToast('Please drag a bounding box on the image first', 'error');
    return;
  }

  // Exact coordinates relative to the rendered image boundaries
  const leftOnImg = boxRect.left - imgRect.left;
  const topOnImg = boxRect.top - imgRect.top;

  // Normalized 0.0 to 1.0 coordinates
  const norm_x1 = Math.max(0, Math.min(1, leftOnImg / imgRect.width));
  const norm_y1 = Math.max(0, Math.min(1, topOnImg / imgRect.height));
  const norm_x2 = Math.max(0, Math.min(1, (leftOnImg + boxRect.width) / imgRect.width));
  const norm_y2 = Math.max(0, Math.min(1, (topOnImg + boxRect.height) / imgRect.height));

  if (norm_x2 - norm_x1 < 0.005 || norm_y2 - norm_y1 < 0.005) {
    showToast('Crop area too small; please select a larger region', 'error');
    return;
  }

  const cropBox = [norm_x1, norm_y1, norm_x2, norm_y2];

  closeInvestigateDetailModal();
  showToast('Computing crop embeddings across all available models...', 'info');

  try {
    const resOrig = appState.lastSearchResults?.results || appState.lastSearchResults;
    const modelsResults = resOrig?.models_results || {};
    const computedKeys = Object.keys(modelsResults).length > 0
      ? Object.keys(modelsResults)
      : (resOrig?.models_computed || [appState.investigateActiveModel || appState.activeModel || 'siglip2-naflex']);

    const unknownFolder = (appState.lastSearchResults?.unknown_folder && !appState.lastSearchResults.unknown_folder.startsWith('databases/'))
      ? appState.lastSearchResults.unknown_folder
      : null;

    const removeBg = document.getElementById('cropRemoveBgToggle')?.checked || false;

    const res = await fetch('/api/search/crop', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        image_path: item.file_path,
        crop_box: cropBox,
        bounding_box: cropBox,
        unknown_folder: unknownFolder,
        threshold: 0.0,
        models: computedKeys,
        search_mode: appState.computationMethod || 'exact',
        remove_background: removeBg,
      })
    });

    const rawData = await res.json();
    if (rawData.error) throw new Error(rawData.error);
    const data = rawData.results || rawData;

    appState.activeCropResults = data;
    appState.activeCropEmbeddings = data.crop_embeddings || {};

    // Show active crop search filter banner with actual cropped snippet preview
    const banner = document.getElementById('invCropFilterBanner');
    const bannerSrc = document.getElementById('invCropFilterSource');
    const bannerImg = document.getElementById('invCropFilterImg');
    if (banner) banner.classList.remove('hidden');
    
    const bboxDisplay = data.bounding_box ? `[${data.bounding_box.join(', ')}]` : `[${Math.round(norm_x1*100)}%, ${Math.round(norm_y1*100)}%, ${Math.round(norm_x2*100)}%, ${Math.round(norm_y2*100)}%]`;
    if (bannerSrc) bannerSrc.innerText = `Source: ${item.filename || item.file_path.split(/[\/\\]/).pop()} ${bboxDisplay}`;
    
    // Set actual cropped image snippet as the thumbnail in the header!
    if (bannerImg) {
      bannerImg.src = data.snippet_url || `/api/media/preview?path=${encodeURIComponent(item.file_path)}&thumb=1`;
    }

    // Populate Copy Embeddings Dropdown Menu Items
    const menuItems = document.getElementById('cropEmbeddingsMenuItems');
    if (menuItems && data.crop_embeddings) {
      menuItems.innerHTML = Object.keys(data.crop_embeddings).map(mKey => {
        const vec = data.crop_embeddings[mKey];
        const dName = getModelFullName(mKey).split(' (')[0];
        const dim = Array.isArray(vec) ? vec.length : 0;
        return `
          <button class="btn btn-secondary-outline btn-xs" style="justify-content: flex-start; text-align: left; font-size: 11px; padding: 4px 8px; width: 100%;" onclick="copyCropModelEmbedding('${mKey}')">
            📋 ${dName} (${dim}-d vector)
          </button>
        `;
      }).join('');
    }

    // Render Gallery Model Tabs to show Crop Search counts for each model
    const galleryTabsList = document.getElementById('galleryModelTabsList');
    const galleryTabsBar = document.getElementById('galleryModelTabsBar');
    if (galleryTabsBar && galleryTabsList && data.models_results) {
      galleryTabsBar.classList.remove('hidden');
      const cropModelKeys = Object.keys(data.models_results);
      
      if (!cropModelKeys.includes(appState.investigateActiveModel)) {
        appState.investigateActiveModel = cropModelKeys[0];
      }

      galleryTabsList.innerHTML = cropModelKeys.map(mKey => {
        const isAct = mKey === appState.investigateActiveModel;
        const mInfo = data.models_results[mKey] || {};
        const dName = mInfo.display_name || getModelFullName(mKey);
        const count = mInfo.num_matches !== undefined ? mInfo.num_matches : (mInfo.matches ? mInfo.matches.length : 0);
        
        return `
          <button type="button" class="gallery-model-tab-btn ${isAct ? 'active' : ''}" onclick="switchInvestigateModel('${mKey}')">
            <span class="model-tab-icon">🎯</span>
            <span class="model-tab-name">${dName}</span>
            <span class="model-tab-badge">${count} Crop Matches</span>
          </button>
        `;
      }).join('');
    }

    const activeM = appState.investigateActiveModel;
    appState.investigateEvidenceList = (data.models_results && data.models_results[activeM]?.matches) || data.matches || [];
    
    applyInvestigateFilters();
    showToast(`Targeted crop search computed across ${Object.keys(data.crop_embeddings || {}).length} models!`, 'success');
  } catch (e) {
    showToast(`Crop search error: ${e.message}`, 'error');
  }
};

window.toggleCropEmbeddingsMenu = function() {
  const menu = document.getElementById('cropEmbeddingsDropdownMenu');
  if (menu) menu.classList.toggle('hidden');
};

window.copyCropModelEmbedding = function(modelKey) {
  if (!appState.activeCropEmbeddings || !appState.activeCropEmbeddings[modelKey]) {
    showToast(`No embedding vector found for ${modelKey}`, 'error');
    return;
  }
  const vec = appState.activeCropEmbeddings[modelKey];
  const str = JSON.stringify(vec);
  navigator.clipboard.writeText(str);
  
  const dName = getModelFullName(modelKey).split(' (')[0];
  showToast(`Copied ${dName} (${vec.length}-d vector array) to clipboard! Paste directly into Search Embeddings.`, 'success');
  document.getElementById('cropEmbeddingsDropdownMenu')?.classList.add('hidden');
};

window.copyAllCropEmbeddingsJSON = function() {
  if (!appState.activeCropEmbeddings) {
    showToast('No crop embeddings available to copy', 'error');
    return;
  }
  const str = JSON.stringify(appState.activeCropEmbeddings, null, 2);
  navigator.clipboard.writeText(str);
  showToast('Copied multi-model crop embeddings JSON to clipboard! Paste directly into Search Embeddings.', 'success');
  document.getElementById('cropEmbeddingsDropdownMenu')?.classList.add('hidden');
  closeCropEmbeddingsModal();
};

window.closeCropEmbeddingsModal = function() {
  document.getElementById('cropEmbeddingsModal')?.classList.add('hidden');
};

window.clearInvestigateCropFilter = function() {
  const banner = document.getElementById('invCropFilterBanner');
  if (banner) banner.classList.add('hidden');
  const menu = document.getElementById('cropEmbeddingsDropdownMenu');
  if (menu) menu.classList.add('hidden');

  appState.activeCropResults = null;
  appState.activeCropEmbeddings = null;

  // Restore investigation tabs and evidence
  initInvestigateWorkspace();
  showToast('Closed crop search; restored full investigation', 'info');
};

window.triggerInvestigateCrop = function(fpathEnc, fname) {
  const fpath = decodeURIComponent(fpathEnc);
  const item = (appState.investigateRenderedList || appState.investigateEvidenceList || []).find(it => it.file_path === fpath) || { file_path: fpath, filename: fname };
  
  if (isVideoMedia(item)) {
    openVideoReviewModal(item);
    setTimeout(() => {
      toggleVideoCropMode();
    }, 300);
  } else {
    openInvestigateDetailModal(item);
    showToast('Drag a box on the preview image to search for that crop', 'info');
  }
};


// ==========================================
// SEMANTIC EMBEDDING MODEL OPTIONS CONTROLLER
// ==========================================
window.renderInvestigateSemanticModelOptions = function() {
  const container = document.getElementById('invSemanticModelOptions');
  if (!container) return;

  const res = appState.lastSearchResults?.results || appState.lastSearchResults;
  const computedModels = res?.models_computed || (res?.models_results ? Object.keys(res.models_results) : [appState.investigateActiveModel || 'clip-vit-b-32']);
  
  // Vision-only models (like DINOv3) have no text encoder and cannot be used for text embeddings search
  const visionOnlyModels = new Set(['dinov3', 'dino-v2', 'dinov2', 'facebook/dinov3-vitb16-pretrain-lvd1689m']);
  const textCompatibleModels = computedModels.filter(m => !visionOnlyModels.has(m.toLowerCase()));
  const availableTextModels = textCompatibleModels.length > 0 ? textCompatibleModels : ['clip-vit-b-32'];

  if (!appState.investigateSemanticSelectedModel) {
    appState.investigateSemanticSelectedModel = 'all';
  }

  // Create Option Buttons
  const buttonsHtml = [];

  // "All Compatible Models" button
  const isAllActive = appState.investigateSemanticSelectedModel === 'all' || !availableTextModels.includes(appState.investigateSemanticSelectedModel);
  buttonsHtml.push(`
    <button type="button" class="sem-option-btn ${isAllActive ? 'active' : ''}" onclick="selectSemanticEmbeddingModel('all')" title="Search text query across all compatible embedding models concurrently">
      <span>✨ All Compatible (${availableTextModels.length})</span>
    </button>
  `);

  // Individual Compatible Model buttons
  availableTextModels.forEach(mKey => {
    const isAct = !isAllActive && appState.investigateSemanticSelectedModel === mKey;
    const shortName = mKey.includes('clip') ? 'CLIP ViT-B/32' : (mKey.includes('naflex') ? 'SigLIP2 NaFlex' : (mKey.includes('siglip2') ? 'SigLIP2 Base' : getModelFullName(mKey)));
    buttonsHtml.push(`
      <button type="button" class="sem-option-btn ${isAct ? 'active' : ''}" onclick="selectSemanticEmbeddingModel('${mKey}')" title="Search text embeddings using ${getModelFullName(mKey)}">
        <span>⚡ ${shortName}</span>
      </button>
    `);
  });

  container.innerHTML = buttonsHtml.join('');
};

window.selectSemanticEmbeddingModel = function(mKey) {
  appState.investigateSemanticSelectedModel = mKey;
  renderInvestigateSemanticModelOptions();
  
  const q = document.getElementById('invSemanticInput')?.value.trim();
  if (q) {
    runInvestigateSemanticSearch();
  }
};

window.runInvestigateSemanticSearch = async function() {
  const query = document.getElementById('invSemanticInput')?.value.trim();
  if (!query) {
    resetInvestigateSemanticSearch();
    return;
  }

  const filterVal = document.getElementById('invSemanticTopKSelect')?.value || '0';
  const topK = parseInt(filterVal, 10);

  // Automatically detect all text-compatible models in current SQLite database (exclude DINOv3)
  const computedModels = appState.lastSearchResults?.models_computed || [appState.investigateActiveModel || 'clip-vit-b-32'];
  const visionOnlyModels = new Set(['dinov3', 'dino-v2', 'dinov2', 'facebook/dinov3-vitb16-pretrain-lvd1689m']);
  const textCompatibleModels = computedModels.filter(m => !visionOnlyModels.has(m.toLowerCase()));
  const availableTextModels = textCompatibleModels.length > 0 ? textCompatibleModels : ['clip-vit-b-32'];

  const selectedOpt = appState.investigateSemanticSelectedModel || 'all';
  const targetModels = (selectedOpt === 'all' || !availableTextModels.includes(selectedOpt))
    ? availableTextModels
    : [selectedOpt];

  const unknownFolder = (appState.lastSearchResults?.unknown_folder && !appState.lastSearchResults.unknown_folder.startsWith('databases/'))
    ? appState.lastSearchResults.unknown_folder
    : null;

  showToast(`Searching text query: "${query}" across ${targetModels.length} model(s)...`, 'info');
  try {
    const payload = {
      query: query,
      unknown_folder: unknownFolder,
      threshold: 0.0,
      models: targetModels,
      top_k: topK > 0 ? topK : null,
      search_mode: appState.computationMethod || 'exact',
    };

    const res = await fetch('/api/search/text', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    const rawData = await res.json();
    if (rawData.error) throw new Error(rawData.error);
    const data = rawData.results || rawData;

    appState.investigateSearchQuery = query;
    appState.activeSemanticResults = data;

    // Render option buttons if not yet rendered
    renderInvestigateSemanticModelOptions();

    // Automatically render Gallery Model Tabs for each available text model
    const galleryTabsList = document.getElementById('galleryModelTabsList');
    const galleryTabsBar = document.getElementById('galleryModelTabsBar');
    if (galleryTabsBar && galleryTabsList && data.models_results) {
      galleryTabsBar.classList.remove('hidden');
      const textModelKeys = Object.keys(data.models_results);

      if (!textModelKeys.includes(appState.investigateActiveModel)) {
        appState.investigateActiveModel = textModelKeys[0];
      }

      galleryTabsList.innerHTML = textModelKeys.map(mKey => {
        const isAct = mKey === appState.investigateActiveModel;
        const mInfo = data.models_results[mKey] || {};
        const dName = mInfo.display_name || getModelFullName(mKey);
        const count = mInfo.num_matches !== undefined ? mInfo.num_matches : (mInfo.matches ? mInfo.matches.length : 0);

        return `
          <button type="button" class="gallery-model-tab-btn ${isAct ? 'active' : ''}" onclick="switchInvestigateModel('${mKey}')">
            <span class="model-tab-icon">✨</span>
            <span class="model-tab-name">${dName}</span>
            <span class="model-tab-badge">${count} Text Matches</span>
          </button>
        `;
      }).join('');
    }

    // Load matches for the active model
    const activeM = appState.investigateActiveModel;
    if (data.models_results && data.models_results[activeM] && data.models_results[activeM].matches) {
      appState.investigateEvidenceList = data.models_results[activeM].matches;
    } else {
      appState.investigateEvidenceList = data.matches || [];
    }

    applyInvestigateFilters();
    showToast(`Found ${data.num_matches || 0} matches across ${targetModels.length} model(s)!`, 'success');
  } catch (err) {
    showToast(`Text Search failed: ${err.message}`, 'error');
  }
};

window.resetInvestigateSemanticSearch = function() {
  const input = document.getElementById('invSemanticInput');
  if (input) input.value = '';
  appState.investigateSearchQuery = null;
  appState.activeSemanticResults = null;

  // Restore original investigation gallery tabs and match list
  initInvestigateWorkspace();
  applyInvestigateFilters();
  showToast('Reset semantic text search filter', 'info');
};

window.saveWorkspaceSession = async function() {
  saveSessionState();
  const currentKnownTargets = (appState.lastSearchResults && appState.lastSearchResults.known_targets && appState.lastSearchResults.known_targets.length > 0)
    ? appState.lastSearchResults.known_targets
    : ((appState.knownTargets && appState.knownTargets.length > 0) ? appState.knownTargets : (appState.knownImages || []));

  for (const t of currentKnownTargets) {
    const fPath = t.file_path || t;
    if (typeof fPath === 'string' && fPath) {
      try {
        await fetch('/api/known_targets/add', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            image_path: fPath,
            label: t.label || fPath.split(/[\/\\]/).pop(),
            group_name: t.group_name || 'default',
            crop_box: t.crop_box || null,
            recompute: false,
          }),
        });
      } catch (err) {}
    }
  }

  showToast('Workspace session & reference targets permanently saved!', 'success');
};

// ==========================================
// VIDEO REVIEW MODAL (SIDE-BY-SIDE SEED VIEW)
// ==========================================

// ==========================================
// VIDEO FRAME FREEZE & CROP SEARCH
// ==========================================
let isVideoCropActive = false;
let isVideoCropDragging = false;
let videoCropStart = { x: 0, y: 0 };
let videoCropNormalizedBox = null;

window.toggleVideoCropMode = function() {
  const player = document.getElementById('modalVideoPlayer');
  const canvas = document.getElementById('modalVideoCropCanvas');
  const cropBox = document.getElementById('modalVideoCropBox');
  const btnToggle = document.getElementById('btnToggleVideoCrop');
  const btnCancel = document.getElementById('btnCancelVideoCrop');
  const btnExec = document.getElementById('btnExecuteVideoCrop');
  const indicator = document.getElementById('videoCropIndicator');
  const bgWrap = document.getElementById('videoCropRemoveBgWrap');
  if (!player || !canvas) return;

  // 1. Freeze / pause the video
  player.pause();

  isVideoCropActive = true;
  isVideoCropDragging = false;
  videoCropNormalizedBox = null;

  canvas.classList.remove('hidden');
  if (cropBox) cropBox.classList.add('hidden');
  if (btnCancel) btnCancel.classList.remove('hidden');
  if (btnToggle) btnToggle.classList.add('hidden');
  if (btnExec) btnExec.classList.add('hidden');
  if (bgWrap) bgWrap.classList.remove('hidden');
  if (indicator) indicator.classList.remove('hidden');

  // 2. Draw current video frame to canvas
  const vW = player.videoWidth || player.clientWidth || 1280;
  const vH = player.videoHeight || player.clientHeight || 720;
  canvas.width = vW;
  canvas.height = vH;
  const ctx = canvas.getContext('2d');
  ctx.drawImage(player, 0, 0, vW, vH);

  showToast('Video frozen! Drag a bounding box over any object to search across all models', 'info');
};

window.cancelVideoCropMode = function() {
  isVideoCropActive = false;
  isVideoCropDragging = false;
  videoCropNormalizedBox = null;

  const canvas = document.getElementById('modalVideoCropCanvas');
  const cropBox = document.getElementById('modalVideoCropBox');
  const btnToggle = document.getElementById('btnToggleVideoCrop');
  const btnCancel = document.getElementById('btnCancelVideoCrop');
  const btnExec = document.getElementById('btnExecuteVideoCrop');
  const indicator = document.getElementById('videoCropIndicator');
  const bgWrap = document.getElementById('videoCropRemoveBgWrap');

  if (canvas) canvas.classList.add('hidden');
  if (cropBox) cropBox.classList.add('hidden');
  if (btnToggle) btnToggle.classList.remove('hidden');
  if (btnCancel) btnCancel.classList.add('hidden');
  if (btnExec) btnExec.classList.add('hidden');
  if (bgWrap) bgWrap.classList.add('hidden');
  if (indicator) indicator.classList.add('hidden');
};

window.executeVideoCropSearch = async function() {
  const match = appState.activeVideoMatch;
  if (!match) {
    showToast('No active video selected', 'error');
    return;
  }

  // Preserve the bounding box before closing modal or resetting state
  const savedCropBox = (Array.isArray(videoCropNormalizedBox) && videoCropNormalizedBox.length === 4)
    ? [...videoCropNormalizedBox]
    : [0.0, 0.0, 1.0, 1.0];

  const player = document.getElementById('modalVideoPlayer');
  const canvas = document.getElementById('modalVideoCropCanvas');
  const removeBg = document.getElementById('videoCropRemoveBgToggle')?.checked || false;

  let frameDataUrl = '';
  try {
    if (canvas && canvas.width > 0 && canvas.height > 0) {
      frameDataUrl = canvas.toDataURL('image/jpeg', 0.95);
    }
  } catch (err) {
    console.warn('Canvas toDataURL fallback:', err);
  }

  const currentTs = player ? (player.currentTime || 0.0) : 0.0;
  const videoPath = match.file_path || match.video_path || '';
  const fname = match.filename || (videoPath ? videoPath.split(/[\/\\]/).pop() : 'video.mp4');

  // Determine models to compute across
  const res = appState.lastSearchResults?.results || appState.lastSearchResults;
  const computedKeys = res?.models_computed || (res?.models_results ? Object.keys(res.models_results) : [appState.investigateActiveModel || appState.activeModel || 'siglip2-naflex']);

  showToast(`Running Multi-Model Crop Search on ${fname} (frame @ ${currentTs.toFixed(2)}s)...`, 'info');

  const payload = {
    image_data: frameDataUrl || undefined,
    video_path: videoPath,
    image_path: videoPath,
    timestamp_seconds: currentTs,
    crop_box: savedCropBox,
    bounding_box: savedCropBox,
    source_filename: `${fname} [frame @ ${currentTs.toFixed(2)}s]`,
    models: computedKeys,
    search_mode: appState.computationMethod || 'exact',
    remove_background: removeBg,
    unknown_folder: (appState.lastSearchResults?.unknown_folder && !appState.lastSearchResults.unknown_folder.startsWith('databases/')) ? appState.lastSearchResults.unknown_folder : null,
  };

  // Close the modal AFTER building the complete payload
  closeVideoReviewModal();

  try {
    const resp = await fetch('/api/search/crop', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    const rawData = await resp.json();
    if (rawData.error) throw new Error(rawData.error);
    const data = rawData.results || rawData;

    // Store active crop results
    appState.activeCropResults = data;
    appState.cropFilterActive = true;

    // Show Crop Filter Banner
    const banner = document.getElementById('invCropFilterBanner');
    const bannerImg = document.getElementById('invCropFilterImg');
    const bannerSrc = document.getElementById('invCropFilterSource');
    if (banner) banner.classList.remove('hidden');
    if (bannerImg && data.snippet_url) bannerImg.src = data.snippet_url;
    if (bannerSrc) bannerSrc.innerText = `Source: ${fname} (frame @ ${currentTs.toFixed(2)}s)`;

    // Render computed model tabs directly above evidence gallery
    const galleryTabsList = document.getElementById('galleryModelTabsList');
    const galleryTabsBar = document.getElementById('galleryModelTabsBar');
    if (galleryTabsBar && galleryTabsList && data.models_results) {
      galleryTabsBar.classList.remove('hidden');
      const cropModelKeys = Object.keys(data.models_results);

      if (!cropModelKeys.includes(appState.investigateActiveModel)) {
        appState.investigateActiveModel = cropModelKeys[0];
      }

      galleryTabsList.innerHTML = cropModelKeys.map(mKey => {
        const isAct = mKey === appState.investigateActiveModel;
        const mInfo = data.models_results[mKey] || {};
        const dName = mInfo.display_name || getModelFullName(mKey);
        const count = mInfo.num_matches !== undefined ? mInfo.num_matches : (mInfo.matches ? mInfo.matches.length : 0);

        return `
          <button type="button" class="gallery-model-tab-btn ${isAct ? 'active' : ''}" onclick="switchInvestigateModel('${mKey}')">
            <span class="model-tab-icon">🎯</span>
            <span class="model-tab-name">${dName}</span>
            <span class="model-tab-badge">${count} Crop Matches</span>
          </button>
        `;
      }).join('');
    }

    // Load matches for the active model
    const activeM = appState.investigateActiveModel;
    if (data.models_results && data.models_results[activeM] && data.models_results[activeM].matches) {
      appState.investigateEvidenceList = data.models_results[activeM].matches;
    } else {
      appState.investigateEvidenceList = data.matches || [];
    }

    applyInvestigateFilters();
    showToast(`Crop Search complete! Found ${data.num_matches || 0} matches across ${computedKeys.length} models.`, 'success');
  } catch (err) {
    showToast(`Video Crop Search failed: ${err.message}`, 'error');
  }
};

function initVideoCropListeners() {
  const canvas = document.getElementById('modalVideoCropCanvas');
  const cropBox = document.getElementById('modalVideoCropBox');
  if (!canvas || !cropBox) return;

  canvas.addEventListener('mousedown', (e) => {
    if (!isVideoCropActive) return;
    const player = document.getElementById('modalVideoPlayer');
    if (player && !player.paused) player.pause();

    const rect = canvas.getBoundingClientRect();
    videoCropStart.x = e.clientX - rect.left;
    videoCropStart.y = e.clientY - rect.top;
    isVideoCropDragging = true;

    cropBox.style.left = `${videoCropStart.x}px`;
    cropBox.style.top = `${videoCropStart.y}px`;
    cropBox.style.width = '0px';
    cropBox.style.height = '0px';
    cropBox.classList.remove('hidden');
  });

  window.addEventListener('mousemove', (e) => {
    if (!isVideoCropActive || !isVideoCropDragging) return;
    const rect = canvas.getBoundingClientRect();
    const curX = Math.max(0, Math.min(e.clientX - rect.left, rect.width));
    const curY = Math.max(0, Math.min(e.clientY - rect.top, rect.height));

    const xMin = Math.min(videoCropStart.x, curX);
    const yMin = Math.min(videoCropStart.y, curY);
    const boxW = Math.abs(curX - videoCropStart.x);
    const boxH = Math.abs(curY - videoCropStart.y);

    cropBox.style.left = `${xMin}px`;
    cropBox.style.top = `${yMin}px`;
    cropBox.style.width = `${boxW}px`;
    cropBox.style.height = `${boxH}px`;
  });

  window.addEventListener('mouseup', (e) => {
    if (!isVideoCropActive || !isVideoCropDragging) return;
    isVideoCropDragging = false;

    const rect = canvas.getBoundingClientRect();
    const curX = Math.max(0, Math.min(e.clientX - rect.left, rect.width));
    const curY = Math.max(0, Math.min(e.clientY - rect.top, rect.height));

    const xMin = Math.min(videoCropStart.x, curX);
    const yMin = Math.min(videoCropStart.y, curY);
    const boxW = Math.abs(curX - videoCropStart.x);
    const boxH = Math.abs(curY - videoCropStart.y);

    if (boxW < 12 || boxH < 12) {
      cropBox.classList.add('hidden');
      const btnExec = document.getElementById('btnExecuteVideoCrop');
      if (btnExec) btnExec.classList.add('hidden');
      return;
    }

    const normX1 = xMin / rect.width;
    const normY1 = yMin / rect.height;
    const normX2 = (xMin + boxW) / rect.width;
    const normY2 = (yMin + boxH) / rect.height;
    videoCropNormalizedBox = [normX1, normY1, normX2, normY2];

    const btnExec = document.getElementById('btnExecuteVideoCrop');
    if (btnExec) btnExec.classList.remove('hidden');
  });
}

window.openVideoReviewModal = function(matchOrIdx) {
  let match = null;
  if (typeof matchOrIdx === 'object' && matchOrIdx !== null) {
    match = matchOrIdx;
  } else if (typeof matchOrIdx === 'number') {
    match = (appState.investigateRenderedList && appState.investigateRenderedList[matchOrIdx]) ||
            (appState.investigateEvidenceList && appState.investigateEvidenceList[matchOrIdx]) ||
            (appState.lastSearchResults && appState.lastSearchResults.matches && appState.lastSearchResults.matches[matchOrIdx]);
  }
  if (!match) return;

  const modal = document.getElementById('videoReviewModal');
  const filename = match.filename || match.file_path.split(/[\/\\]/).pop();
  const maxScore = match.similarity_pct !== undefined ? match.similarity_pct : (match.score * 100).toFixed(1);
  const targetLabel = match.best_target_label || 'Target Reference';
  const keyframes = match.keyframes || (match.top_keyframe ? [match.top_keyframe] : []);

  appState.activeVideoMatch = match;
  cancelVideoCropMode();
  appState.activeVideoReviewKeyframes = keyframes;

  // 1. Determine Crop / Text Context if any
  const isCropActive = !!(appState.cropFilterActive && appState.activeCropResults);
  const cropSnippet = match.best_target_thumb || appState.activeCropResults?.snippet_url || (appState.activeCropResults?.source_image && appState.activeCropResults.source_image.startsWith('data:') ? appState.activeCropResults.source_image : '');
  const cropLabel = match.best_target_label || (appState.activeCropResults?.source_filename ? 'Crop: ' + appState.activeCropResults.source_filename : 'Target Crop');
  const cropPath = match.best_target_path || appState.activeCropResults?.source_image || '';

  const isTextActive = !!(match.is_text_query || match.query_text || appState.investigateSearchQuery);
  const textQueryStr = match.query_text || appState.investigateSearchQuery || (match.best_target_label && (match.best_target_label.startsWith('Prompt:') || match.best_target_label.startsWith('Text:')) ? match.best_target_label.replace(/^(Prompt|Text):\s*"?/, '').replace(/"?$/, '') : '');

  // 2. Build multi-target to frame matches map
  const targetsMap = new Map();

  function addFrameToTarget(targetKey, targetInfo, kf, score, pct) {
    if (!targetsMap.has(targetKey)) {
      targetsMap.set(targetKey, {
        key: targetKey,
        label: targetInfo.label || targetKey,
        path: targetInfo.path || '',
        thumb: targetInfo.thumb || '',
        isText: !!targetInfo.isText,
        queryText: targetInfo.queryText || '',
        frames: [],
        maxScore: pct,
        bestFrame: kf,
      });
    }
    const entry = targetsMap.get(targetKey);
    const ts = kf.timestamp_seconds !== undefined ? Number(kf.timestamp_seconds) : 0.0;
    const frameThumbUrl = `/api/media/preview?path=${encodeURIComponent(kf.file_path)}&thumb=1`;

    entry.frames.push({
      kf: kf,
      score: score,
      pct: pct,
      timestamp: ts,
      thumbUrl: frameThumbUrl,
      filename: kf.file_path ? kf.file_path.split(/[\/\\]/).pop() : `frame_${ts.toFixed(2)}s.jpg`,
    });

    if (pct > entry.maxScore) {
      entry.maxScore = pct;
      entry.bestFrame = kf;
    }
  }

  // Iterate all keyframes and populate target matches
  keyframes.forEach((kf) => {
    if (kf.all_target_scores && Array.isArray(kf.all_target_scores) && kf.all_target_scores.length > 0) {
      kf.all_target_scores.forEach((t) => {
        const isTText = !!(t.is_text_query || (t.target_label && (t.target_label.startsWith('Prompt:') || t.target_label.startsWith('Text:'))) || isTextActive);
        const tQuery = t.query_text || textQueryStr;
        const tLabel = t.target_label || (isTText ? `Prompt: "${tQuery}"` : (t.target_path ? t.target_path.split(/[\/\\]/).pop() : 'Known Target'));
        const tPath = t.target_path || '';
        const tThumb = t.target_thumb || (tPath ? `/api/media/preview?path=${encodeURIComponent(tPath)}&thumb=1` : '');
        const tScore = t.score !== undefined ? Number(t.score) : 0.0;
        const tPct = t.similarity_pct !== undefined ? Number(t.similarity_pct) : Number((tScore * 100).toFixed(2));
        const key = isTText ? `text::${tQuery || tLabel}` : (tPath || tLabel);
        addFrameToTarget(key, { label: tLabel, path: tPath, thumb: tThumb, isText: isTText, queryText: tQuery }, kf, tScore, tPct);
      });
    } else if (isCropActive || kf.best_target_thumb || match.best_target_thumb) {
      const kScore = kf.score !== undefined ? Number(kf.score) : 0.0;
      const kPct = kf.similarity_pct !== undefined ? Number(kf.similarity_pct) : Number((kScore * 100).toFixed(2));
      addFrameToTarget(cropPath || cropLabel, { label: cropLabel, path: cropPath, thumb: cropSnippet }, kf, kScore, kPct);
    } else if (isTextActive || kf.is_text_query || match.is_text_query) {
      const kScore = kf.score !== undefined ? Number(kf.score) : 0.0;
      const kPct = kf.similarity_pct !== undefined ? Number(kf.similarity_pct) : Number((kScore * 100).toFixed(2));
      const pLabel = `Prompt: "${textQueryStr}"`;
      addFrameToTarget(`text::${textQueryStr}`, { label: pLabel, path: '', thumb: '', isText: true, queryText: textQueryStr }, kf, kScore, kPct);
    } else {
      const tLabel = kf.best_target_label || match.best_target_label || (appState.knownImages?.[0]?.label) || 'Known Target';
      const tPath = kf.best_target_path || match.best_target_path || (appState.knownImages?.[0]?.file_path) || '';
      const tThumb = tPath ? `/api/media/preview?path=${encodeURIComponent(tPath)}&thumb=1` : '';
      const kScore = kf.score !== undefined ? Number(kf.score) : 0.0;
      const kPct = kf.similarity_pct !== undefined ? Number(kf.similarity_pct) : Number((kScore * 100).toFixed(2));
      addFrameToTarget(tPath || tLabel, { label: tLabel, path: tPath, thumb: tThumb }, kf, kScore, kPct);
    }
  });

  // Also include known targets that didn't match any frame above 0 (for visual search)
  if (!isTextActive) {
    const allKnownTargets = appState.lastSearchResults?.known_targets || appState.knownImages || [];
    allKnownTargets.forEach((kt) => {
      const ktPath = kt.file_path || kt.path || '';
      const ktLabel = kt.label || (ktPath ? ktPath.split(/[\/\\]/).pop() : 'Known Target');
      const key = ktPath || ktLabel;
      if (!targetsMap.has(key)) {
        targetsMap.set(key, {
          key: key,
          label: ktLabel,
          path: ktPath,
          thumb: ktPath ? `/api/media/preview?path=${encodeURIComponent(ktPath)}&thumb=1` : '',
          frames: [],
          maxScore: 0.0,
          bestFrame: null,
        });
      }
    });
  }

  // Sort each target's frame list by percentage descending
  targetsMap.forEach((entry) => {
    entry.frames.sort((a, b) => b.pct - a.pct);
    if (entry.frames.length > 0) {
      entry.maxScore = entry.frames[0].pct;
      entry.bestFrame = entry.frames[0].kf;
    }
  });

  appState.activeVideoTargetsMap = targetsMap;

  // Update modal header elements
  document.getElementById('modalVideoFilename').innerText = filename;
  document.getElementById('modalVideoScoreBadge').innerText = `${maxScore}% Max Match`;
  document.getElementById('modalVideoPath').innerText = match.file_path;
  document.getElementById('modalVideoTarget').innerText = targetLabel;
  document.getElementById('modalVideoTotalKf').innerText = `${keyframes.length} keyframes (${targetsMap.size} search target${targetsMap.size > 1 ? 's' : ''} compared)`;
  document.getElementById('modalTotalFramesCount').innerText = targetsMap.size;

  // Load video player
  const player = document.getElementById('modalVideoPlayer');
  player.src = `/api/media/preview?path=${encodeURIComponent(match.file_path)}`;
  player.load();

  // Setup slider (Default to 40%)
  const slider = document.getElementById('modalFrameScoreSlider');
  const sliderVal = document.getElementById('modalFrameScoreVal');
  const initialThreshold = 40;
  if (slider) slider.value = initialThreshold;
  if (sliderVal) sliderVal.innerText = `${initialThreshold}%`;

  window.setVideoSliderValue = function(val) {
    if (slider) slider.value = val;
    if (sliderVal) sliderVal.innerText = val === 0 ? '0% (Show All)' : `${val}%`;
    renderModalKeyframes(val);
  };

  function renderModalKeyframes(minScore) {
    const listContainer = document.getElementById('modalVideoKeyframesGrid');
    const timelinePills = document.getElementById('modalTimelinePills');
    const thresholdLabel = document.getElementById('modalThresholdLabel');
    if (thresholdLabel) {
      thresholdLabel.innerText = minScore === 0 ? '0%' : `${minScore}%`;
    }

    // Filter targets that have at least one frame >= minScore
    const matchedTargets = [];
    targetsMap.forEach((entry) => {
      const validFrames = entry.frames.filter((f) => f.pct >= minScore);
      if (validFrames.length > 0) {
        matchedTargets.push({
          ...entry,
          visibleFrames: validFrames,
          bestVisibleFrame: validFrames[0],
          bestVisiblePct: validFrames[0].pct,
        });
      }
    });

    // Sort matched targets by best score descending
    matchedTargets.sort((a, b) => b.bestVisiblePct - a.bestVisiblePct);

    document.getElementById('modalVisibleFramesCount').innerText = matchedTargets.length;
    document.getElementById('modalTotalFramesCount').innerText = targetsMap.size;

    // Timeline pills
    const allMatchingFramesTimeline = [];
    matchedTargets.forEach((t) => {
      t.visibleFrames.forEach((f) => {
        allMatchingFramesTimeline.push({
          timestamp: f.timestamp,
          pct: f.pct,
          targetLabel: t.label,
        });
      });
    });
    allMatchingFramesTimeline.sort((a, b) => a.timestamp - b.timestamp);

    // Deduplicate within 0.3s
    const dedupedTimeline = [];
    allMatchingFramesTimeline.forEach((f) => {
      const existing = dedupedTimeline.find((x) => Math.abs(x.timestamp - f.timestamp) < 0.3);
      if (!existing) {
        dedupedTimeline.push(f);
      } else if (f.pct > existing.pct) {
        existing.pct = f.pct;
        existing.targetLabel = f.targetLabel;
      }
    });

    if (timelinePills) {
      if (dedupedTimeline.length > 0) {
        timelinePills.innerHTML = dedupedTimeline.map((item) => `
          <button class="timeline-jump-btn" onclick="seekVideoPlayer(${item.timestamp})" title="Jump video to ${item.timestamp.toFixed(2)}s">
            <span>⏱️ ${item.timestamp.toFixed(2)}s</span>
            <span class="score-text">(${item.pct.toFixed(1)}% - ${item.targetLabel})</span>
          </button>
        `).join('');
      } else {
        timelinePills.innerHTML = `<span style="color: var(--text-muted); font-size: 12px;">No keyframe moments &ge; ${minScore}%</span>`;
      }
    }

    // Update Preset Chip active states
    document.querySelectorAll('.btn-preset-chip').forEach(chip => {
      chip.classList.toggle('active', parseInt(chip.dataset.val, 10) === minScore);
    });

    if (!listContainer) return;

    if (matchedTargets.length === 0) {
      listContainer.innerHTML = `
        <div class="empty-gallery" style="grid-column: 1/-1; width: 100%; text-align: center; padding: 36px 20px; background: rgba(255,255,255,0.02); border-radius: 10px; border: 1px dashed rgba(255,255,255,0.15);">
          <div style="font-size: 24px; margin-bottom: 8px;">🎯 No Target Matches Over ${minScore}%</div>
          <p style="color: var(--text-muted); font-size: 13px; margin: 0 0 14px 0; max-width: 500px; margin-left: auto; margin-right: auto;">
            None of the ${targetsMap.size} search target(s) matched any video frames with similarity &ge; ${minScore}%.
            Adjust the slider above to inspect lower-confidence matches.
          </p>
          <button class="btn btn-secondary-outline btn-sm" onclick="setVideoSliderValue(0)">
            Show All Frame Matches (0%)
          </button>
        </div>
      `;
      return;
    }

    listContainer.innerHTML = matchedTargets.map((target) => {
      const bestF = target.bestVisibleFrame;
      const kfPct = bestF.pct.toFixed(1);
      const scoreClass = bestF.pct >= 80 ? 'score-high' : bestF.pct >= 60 ? 'score-med' : 'score-low';
      const isText = !!(target.isText || target.label.startsWith('Prompt:') || target.label.startsWith('Text:'));
      const isCrop = !isText && (target.label.toLowerCase().includes('crop') || (target.thumb && target.thumb.startsWith('data:image')));
      const queryDisplay = target.queryText || (target.label.startsWith('Prompt:') ? target.label.replace(/^Prompt:\s*"?/, '').replace(/"?$/, '') : target.label);
      const targetFilename = target.path ? target.path.split(/[\/\\]/).pop() : target.label;
      const targetThumbUrl = target.thumb || (target.path ? `/api/media/preview?path=${encodeURIComponent(target.path)}&thumb=1` : '');

      return `
        <div class="seed-match-row">
          <!-- LEFT: Known Image or Text Prompt -->
          <div class="seed-row-side seed-side">
            <div class="seed-row-header">
              <span class="badge-type ${isText ? 'text-badge' : (isCrop ? 'crop-badge' : 'seed-badge')}">
                ${isText ? '🔤 Search Prompt' : (isCrop ? '✂️ Known Crop Image' : '🎯 Known Target Image')}
              </span>
              <span class="matched-frames-count-badge" title="${target.visibleFrames.length} frame(s) matched &ge; ${minScore}%">
                ${target.visibleFrames.length} frame${target.visibleFrames.length > 1 ? 's' : ''} &ge; ${minScore}%
              </span>
            </div>
            ${isText ? `
              <div class="seed-row-img-wrap text-prompt-card" style="background: radial-gradient(circle at 50% 50%, rgba(245, 158, 11, 0.15), rgba(15, 23, 42, 0.95)); border: 1px solid rgba(245, 158, 11, 0.4); display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 18px 14px; text-align: center;">
                <span style="font-size: 30px; margin-bottom: 8px;">💬</span>
                <div style="font-size: 13px; font-weight: 700; color: #fbbf24; line-height: 1.4; word-break: break-word;">&ldquo;${queryDisplay}&rdquo;</div>
                <span style="font-size: 10px; color: var(--text-muted); margin-top: 6px; letter-spacing: 0.5px; text-transform: uppercase;">Natural Language Prompt</span>
              </div>
              <div class="seed-row-meta">
                <div class="seed-row-filename" title="${queryDisplay}">&ldquo;${queryDisplay}&rdquo;</div>
                <div class="seed-row-path">Text-to-Video Semantic Search</div>
              </div>
            ` : `
              <div class="seed-row-img-wrap" style="position: relative; cursor: pointer;" onclick="window.previewTargetEnlarged('${encodeURIComponent(targetThumbUrl)}')">
                ${targetThumbUrl
                  ? `<img src="${targetThumbUrl}" alt="${targetFilename}" loading="lazy" onerror="this.src='';this.alt='Target Image Preview N/A'" />`
                  : `<div class="no-img-placeholder">Known Target Reference</div>`
                }
              </div>
              <div class="seed-row-meta">
                <div class="seed-row-filename" title="${target.label}">${target.label}</div>
                <div class="seed-row-path" title="${target.path}">${target.path || 'Reference Target Embedding'}</div>
              </div>
            `}
          </div>

          <!-- CENTER: Score, Arrow & Quick Jump Pills -->
          <div class="seed-row-center">
            <div class="match-score-pill ${scoreClass}">${kfPct}% Best Match</div>
            <div class="match-vs-arrow">⟷</div>
            <div class="match-sub-info">
              ${target.visibleFrames.length === 1
                ? `1 frame matched &ge; ${minScore}%`
                : `Best of <b>${target.visibleFrames.length} frames</b> &ge; ${minScore}%`
              }
            </div>
            ${target.visibleFrames.length > 1 ? `
              <div class="frame-jump-pills-wrap" style="display: flex; flex-wrap: wrap; gap: 4px; justify-content: center; margin-top: 6px; max-width: 200px;">
                ${target.visibleFrames.map(f => `
                  <button class="pill-kf-jump" onclick="seekVideoPlayer(${f.timestamp})" title="Jump video to ${f.timestamp.toFixed(2)}s (${f.pct.toFixed(1)}%)">
                    ⏱️ ${f.timestamp.toFixed(1)}s <b style="opacity:0.9;">(${f.pct.toFixed(0)}%)</b>
                  </button>
                `).join('')}
              </div>
            ` : ''}
          </div>

          <!-- RIGHT: Best Matching Video Frame -->
          <div class="seed-row-side keyframe-side">
            <div class="seed-row-header">
              <span class="badge-type keyframe-badge">🎬 Best Matching Frame</span>
              <span class="timestamp-pill">⏱️ ${bestF.timestamp.toFixed(2)}s</span>
            </div>
            <div class="seed-row-img-wrap" style="position: relative; cursor: pointer;" onclick="seekVideoPlayer(${bestF.timestamp})" title="Click to play video at ${bestF.timestamp.toFixed(2)}s">
              <img src="${bestF.thumbUrl}" alt="Keyframe ${bestF.timestamp}s" loading="lazy" />
              <div class="play-overlay-hint">▶ Click to Play</div>
            </div>
            <div class="seed-row-meta">
              <div class="seed-row-filename" title="${bestF.filename}">${bestF.filename}</div>
              <button class="btn-jump-video" onclick="seekVideoPlayer(${bestF.timestamp})">
                ▶ Jump Video to ${bestF.timestamp.toFixed(2)}s
              </button>
            </div>
          </div>
        </div>
      `;
    }).join('');
  }

  if (slider) {
    slider.oninput = () => {
      const val = parseFloat(slider.value);
      if (sliderVal) sliderVal.innerText = val === 0 ? '0% (Show All)' : `${val}%`;
      renderModalKeyframes(val);
    };
  }

  renderModalKeyframes(initialThreshold);

  const copyBtn = document.getElementById('modalVideoCopyPathBtn');
  if (copyBtn) {
    copyBtn.onclick = () => {
      navigator.clipboard.writeText(match.file_path);
      showToast('Video path copied to clipboard!', 'success');
    };
  }

  modal.classList.remove('hidden');
};

window.previewTargetEnlarged = function(urlEnc) {
  const url = decodeURIComponent(urlEnc);
  if (!url) return;
  window.open(url, '_blank');
};

window.seekVideoPlayer = function(timestampSeconds) {
  const player = document.getElementById('modalVideoPlayer');
  if (player) {
    player.currentTime = timestampSeconds;
    player.play();
  }
};

window.closeVideoReviewModal = function() {
  cancelVideoCropMode();
  const modal = document.getElementById('videoReviewModal');
  const player = document.getElementById('modalVideoPlayer');
  if (player) {
    player.pause();
    player.removeAttribute('src');
    player.load();
  }
  if (modal) {
    modal.classList.add('hidden');
  }
};

// ==========================================
// MODALS CONTROLLER & KEYBOARD ESC
// ==========================================
function initModals() {
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      const loadModal = document.getElementById('loadDbModal');
      if (loadModal && !loadModal.classList.contains('hidden')) {
        closeLoadDbModal();
        return;
      }
      const savePrompt = document.getElementById('saveDbPromptModal');
      if (savePrompt && !savePrompt.classList.contains('hidden')) {
        closeSaveDbPromptModal();
        return;
      }
      const newDb = document.getElementById('newDbModal');
      if (newDb && !newDb.classList.contains('hidden')) {
        closeNewDbModal();
        return;
      }
      const hf = document.getElementById('hfTokenModal');
      if (hf && !hf.classList.contains('hidden')) {
        closeHfTokenModal();
        return;
      }
      const comp = document.getElementById('compareModal');
      if (comp && !comp.classList.contains('hidden')) {
        comp.classList.add('hidden');
        return;
      }
      const det = document.getElementById('investigateDetailModal');
      if (det && !det.classList.contains('hidden')) {
        det.classList.add('hidden');
        return;
      }
      const vid = document.getElementById('videoReviewModal');
      if (vid && !vid.classList.contains('hidden')) {
        window.closeVideoReviewModal();
        return;
      }
    }
  });
}

// ==========================================
// LIVE EXECUTION & ERROR CONSOLE
// ==========================================
function initLiveConsole() {
  const btnToggle = document.getElementById('btnToggleConsole');
  const drawer = document.getElementById('consoleDrawer');
  const bar = document.querySelector('.console-bar');

  const toggleConsole = () => {
    appState.consoleExpanded = !appState.consoleExpanded;
    drawer?.classList.toggle('hidden', !appState.consoleExpanded);
    if (btnToggle) btnToggle.innerText = appState.consoleExpanded ? '▼ Minimize Console' : '▲ Expand Console';
  };

  btnToggle?.addEventListener('click', (e) => {
    e.stopPropagation();
    toggleConsole();
  });

  bar?.addEventListener('click', (e) => {
    if (e.target.tagName === 'BUTTON' || e.target.closest('button')) return;
    toggleConsole();
  });

  document.querySelectorAll('.log-filter-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      document.querySelectorAll('.log-filter-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      appState.logFilter = btn.getAttribute('data-level');
      renderLogs();
    });
  });

  document.getElementById('btnClearLogConsole')?.addEventListener('click', async (e) => {
    e.stopPropagation();
    try {
      await fetch('/api/logs/clear', { method: 'POST' });
    } catch (err) {}
    appState.logs = [];
    renderLogs();
    updateLogCounts();
  });

  document.getElementById('btnQuickCopyLog')?.addEventListener('click', (e) => {
    e.stopPropagation();
    copyLogsToClipboard();
  });
  document.getElementById('btnCopyFormattedLogs')?.addEventListener('click', (e) => {
    e.stopPropagation();
    copyLogsToClipboard();
  });
}

async function fetchLogs() {
  try {
    const res = await fetch(`/api/logs?since=${appState.latestLogId}`);
    const data = await res.json();
    if (data.logs && data.logs.length > 0) {
      appState.logs.push(...data.logs);
      appState.latestLogId = data.logs[data.logs.length - 1].id;
      renderLogs();
      updateLogCounts();
    }
  } catch (e) {}
}

function renderLogs() {
  const container = document.getElementById('consoleLogsContainer');
  if (!container) return;

  const filtered = appState.logs.filter(l => {
    if (appState.logFilter === 'ALL') return true;
    return l.level === appState.logFilter;
  });

  container.innerHTML = filtered.map(l => `
    <div class="log-entry log-${l.level.toLowerCase()}">
      <span class="log-ts">[${l.timestamp}]</span>
      <span class="log-lvl">[${l.level}]</span>
      <span class="log-msg">${l.message}</span>
      ${l.details ? `<pre class="log-details">${l.details}</pre>` : ''}
    </div>
  `).join('');

  if (document.getElementById('autoScrollLog')?.checked) {
    container.scrollTop = container.scrollHeight;
  }

  if (appState.logs.length > 0) {
    const last = appState.logs[appState.logs.length - 1];
    const snippet = document.getElementById('consoleBarSnippet');
    if (snippet) {
      snippet.innerText = `[${last.level}] ${last.message}`;
      snippet.style.color = last.level === 'ERROR' ? '#f87171' : last.level === 'WARN' ? '#fbbf24' : last.level === 'SUCCESS' ? '#4ade80' : 'var(--text-muted)';
    }
  }
}

function updateLogCounts() {
  const all = appState.logs.length;
  const errors = appState.logs.filter(l => l.level === 'ERROR').length;
  const warns = appState.logs.filter(l => l.level === 'WARN').length;
  const succ = appState.logs.filter(l => l.level === 'SUCCESS').length;
  const info = appState.logs.filter(l => l.level === 'INFO').length;

  const elAll = document.getElementById('countLogAll');
  const elErr = document.getElementById('countLogError');
  const elWarn = document.getElementById('countLogWarn');
  const elSucc = document.getElementById('countLogSuccess');
  const elInfo = document.getElementById('countLogInfo');

  if (elAll) elAll.innerText = all;
  if (elErr) elErr.innerText = errors;
  if (elWarn) elWarn.innerText = warns;
  if (elSucc) elSucc.innerText = succ;
  if (elInfo) elInfo.innerText = info;

  const badge = document.getElementById('consoleErrorBadge');
  if (badge) {
    badge.classList.toggle('hidden', errors === 0);
    badge.innerText = `⚠️ ${errors} Error${errors > 1 ? 's' : ''}`;
  }
}

function copyLogsToClipboard() {
  const text = appState.logs.map(l => `[${l.timestamp}] [${l.level}] ${l.message} ${l.details ? '\n' + l.details : ''}`).join('\n');
  navigator.clipboard.writeText(text);
  showToast('Copied execution logs to clipboard!', 'success');
}

// ==========================================
// EXPORT REPORTS (HTML, CSV)
// ==========================================
window.exportResults = async function(fmt) {
  if (!appState.lastSearchResults) {
    showToast('No search results available to export', 'error');
    return;
  }
  showToast(`Generating ${fmt.toUpperCase()} export report...`, 'info');
  try {
    const res = await fetch('/api/export', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        results: appState.lastSearchResults,
        format: fmt,
      })
    });
    const data = await res.json();
    if (data.error) throw new Error(data.error);
    showToast(`Report saved: ${data.file_path}`, 'success');
  } catch (e) {
    showToast(`Export error: ${e.message}`, 'error');
  }
};

// ==========================================
// SESSION PERSISTENCE (AUTO-SAVE & RESTORE)
// ==========================================
let isRestoringSession = true;

function saveSessionState() {
  if (isRestoringSession) return;

  const currentKnownPath = cleanInputPath(document.getElementById('knownPathInput')?.value || appState.knownPath || '');
  const currentUnknownPath = cleanInputPath(document.getElementById('unknownFolderPath')?.value || '');
  const currentKnownTargets = (appState.lastSearchResults && appState.lastSearchResults.known_targets && appState.lastSearchResults.known_targets.length > 0)
    ? appState.lastSearchResults.known_targets
    : ((appState.knownTargets && appState.knownTargets.length > 0) ? appState.knownTargets : (appState.knownImages || []));

  // If session is completely pristine and no user interaction took place, avoid creating session file
  if (!currentKnownPath && !currentUnknownPath && currentKnownTargets.length === 0 && !appState.lastSearchResults && appState.activeView === 'index') {
    return;
  }

  const state = {
    activeView: appState.activeView || 'index',
    activeDatabase: appState.activeDatabase || 'default.sqlite',
    activeModelKey: appState.activeModelKey || 'clip-vit-b-32',
    selectedModelKeys: Array.from(appState.selectedModelKeys || ['clip-vit-b-32']),
    investigateActiveModel: appState.investigateActiveModel || 'clip-vit-b-32',
    dinov3PatchMode: appState.dinov3PatchMode || 'max',
    dinov3PatchThreshold: appState.dinov3PatchThreshold || 0,
    computationMethod: appState.computationMethod || 'exact',
    knownPath: currentKnownPath,
    knownTargets: currentKnownTargets,
    knownMode: appState.knownMode || 'path',
    unknownMode: appState.unknownMode || 'folder',
    unknownFolderPath: currentUnknownPath,
    unknownRecursive: document.getElementById('unknownRecursive')?.checked ?? true,
    unknownAutoIndex: document.getElementById('unknownAutoIndex')?.checked ?? true,
    unknownProcessVideos: document.getElementById('unknownProcessVideos')?.checked ?? true,
    videoMethod: document.getElementById('videoMethodSelect')?.value || 'ssim',
    videoSsim: document.getElementById('unknownVideoSsim')?.value || '0.65',
    videoInterval: document.getElementById('unknownVideoInterval')?.value || '1.0',
    videoUniform: document.getElementById('unknownVideoUniformCount')?.value || '10',
    simThreshold: document.getElementById('simThresholdSlider')?.value || '0',
    metric: document.getElementById('metricSelect')?.value || 'auto',
    aggregation: document.getElementById('aggregationSelect')?.value || 'max',
    topK: document.getElementById('topKSelect')?.value || '0',
  };

  // Note: Session state is persisted strictly per workspace on the server via /api/session
  // to avoid cross-workspace contamination across different project folders on localhost.

  fetch('/api/session', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(state),
  }).catch(() => {});
}

async function restoreSessionState() {
  isRestoringSession = true;

  // Always purge legacy localStorage to avoid cross-contamination from other workspaces
  try {
    localStorage.removeItem('flint_session_state');
  } catch (e) {}

  let state = null;
  try {
    const res = await fetch('/api/session');
    const data = await res.json();
    if (data.success && data.session && Object.keys(data.session).length > 0) {
      state = data.session;
    }
  } catch (e) {}

  if (!state) {
    // Fresh workspace on server! Reset all state to clean initial defaults
    appState.knownTargets = [];
    appState.knownImages = [];
    appState.knownPath = '';
    appState.lastSearchResults = null;
    const knownInput = document.getElementById('knownPathInput');
    if (knownInput) knownInput.value = '';
    const unknownInput = document.getElementById('unknownFolderPath');
    if (unknownInput) unknownInput.value = '';
    renderKnownGallery();
    showIndexView(false);

    // Multi-pass blanking to defeat any browser autofill / form-restoration after render
    [0, 50, 150, 300, 600].forEach(delay => {
      setTimeout(() => {
        const ki = document.getElementById('knownPathInput');
        const ui = document.getElementById('unknownFolderPath');
        if (ki && !appState.knownPath) ki.value = '';
        if (ui && (!state || !state.unknownFolderPath)) ui.value = '';
      }, delay);
    });

    setTimeout(() => {
      isRestoringSession = false;
    }, 800);
    return;
  }

  if (state.activeDatabase) {
    appState.activeDatabase = state.activeDatabase;
  }
  if (state.activeModelKey) {
    appState.activeModelKey = state.activeModelKey;
  }
  if (state.investigateActiveModel) {
    appState.investigateActiveModel = state.investigateActiveModel;
  }
  if (state.dinov3PatchMode) {
    appState.dinov3PatchMode = state.dinov3PatchMode;
    document.getElementById('btnPatchModeMax')?.classList.toggle('active', state.dinov3PatchMode === 'max');
    document.getElementById('btnPatchModeAvg')?.classList.toggle('active', state.dinov3PatchMode === 'avg');
  }
  if (state.dinov3PatchThreshold !== undefined) {
    appState.dinov3PatchThreshold = state.dinov3PatchThreshold;
    const slider = document.getElementById('dinov3PatchSlider');
    if (slider) slider.value = state.dinov3PatchThreshold;
    const valEl = document.getElementById('dinov3PatchSliderVal');
    if (valEl) valEl.innerText = `${state.dinov3PatchThreshold}%`;
  }
  if (state.knownPath) {
    state.knownPath = cleanInputPath(state.knownPath);
    appState.knownPath = state.knownPath;
    const knownInput = document.getElementById('knownPathInput');
    if (knownInput) knownInput.value = state.knownPath;
  }
  if (state.knownTargets && Array.isArray(state.knownTargets) && state.knownTargets.length > 0) {
    appState.knownTargets = state.knownTargets;
  }
  if (state.selectedModelKeys && Array.isArray(state.selectedModelKeys)) {
    appState.selectedModelKeys = new Set(state.selectedModelKeys);
  }
  renderMatcherModelSelection();

  if (state.knownPath) {
    const knownInput = document.getElementById('knownPathInput');
    if (knownInput) {
      knownInput.value = state.knownPath;
      setTimeout(() => {
        handleLoadKnownPath();
      }, 100);
    }
  }

  if (state.unknownMode) {
    const modeBtn = document.querySelector(`[data-unknown-mode="${state.unknownMode}"]`);
    if (modeBtn) modeBtn.click();
  }
  if (state.unknownFolderPath) {
    const cleanedUnknown = cleanInputPath(state.unknownFolderPath);
    const unknownInput = document.getElementById('unknownFolderPath');
    if (unknownInput) unknownInput.value = cleanedUnknown;
  }

  if (state.unknownRecursive !== undefined) {
    const el = document.getElementById('unknownRecursive');
    if (el) el.checked = state.unknownRecursive;
  }
  if (state.unknownAutoIndex !== undefined) {
    const el = document.getElementById('unknownAutoIndex');
    if (el) el.checked = state.unknownAutoIndex;
  }
  if (state.unknownProcessVideos !== undefined) {
    const el = document.getElementById('unknownProcessVideos');
    if (el) {
      el.checked = state.unknownProcessVideos;
      document.getElementById('videoConfigBody')?.classList.toggle('hidden', !el.checked);
    }
  }

  if (state.videoMethod) {
    const el = document.getElementById('videoMethodSelect');
    if (el) {
      el.value = state.videoMethod;
      el.dispatchEvent(new Event('change'));
    }
  }
  if (state.videoSsim) {
    const el = document.getElementById('unknownVideoSsim');
    if (el) {
      el.value = state.videoSsim;
      const valEl = document.getElementById('unknownVideoSsimVal');
      if (valEl) valEl.innerText = state.videoSsim;
    }
  }
  if (state.videoInterval) {
    const el = document.getElementById('unknownVideoInterval');
    if (el) el.value = state.videoInterval;
  }
  if (state.videoUniform) {
    const el = document.getElementById('unknownVideoUniformCount');
    if (el) el.value = state.videoUniform;
  }

  if (state.simThreshold !== undefined) {
    const el = document.getElementById('simThresholdSlider');
    if (el) {
      el.value = state.simThreshold;
      const valEl = document.getElementById('simThresholdVal');
      if (valEl) valEl.innerText = state.simThreshold === '0' ? '0% (Show All)' : `${state.simThreshold}%`;
    }
  }
  if (state.metric) {
    const el = document.getElementById('metricSelect');
    if (el) el.value = state.metric;
  }
  if (state.aggregation) {
    const el = document.getElementById('aggregationSelect');
    if (el) el.value = state.aggregation;
  }
  if (state.topK) {
    const el = document.getElementById('topKSelect');
    if (el) el.value = state.topK;
  }

  // Always open into the Home page on startup
  showIndexView(false);

  setTimeout(() => {
    isRestoringSession = false;
  }, 500);
}

function initAutoSaveListeners() {
  const autoSaveSelectors = [
    '#knownPathInput', '#unknownFolderPath', '#unknownRecursive',
    '#unknownAutoIndex', '#unknownProcessVideos', '#videoMethodSelect',
    '#unknownVideoSsim', '#unknownVideoInterval', '#unknownVideoUniformCount',
    '#simThresholdSlider', '#metricSelect', '#aggregationSelect', '#topKSelect'
  ];

  autoSaveSelectors.forEach(sel => {
    const el = document.querySelector(sel);
    if (el) {
      el.addEventListener('input', () => {
        if (!isRestoringSession) saveSessionState();
      });
      el.addEventListener('change', () => {
        if (!isRestoringSession) saveSessionState();
      });
    }
  });

  document.querySelectorAll('[data-unknown-mode]').forEach(btn => {
    btn.addEventListener('click', () => {
      if (!isRestoringSession) setTimeout(saveSessionState, 50);
    });
  });
  document.querySelectorAll('[data-known-mode]').forEach(btn => {
    btn.addEventListener('click', () => {
      if (!isRestoringSession) setTimeout(saveSessionState, 50);
    });
  });
}


// ==========================================
// REFERENCE TARGET UPLOAD & FOLDER MANAGER
// ==========================================
let _uploadedRefTargetBase64 = null;
let _uploadedRefTargetFilename = null;

window.openAddReferenceTargetModal = async function() {
  _uploadedRefTargetBase64 = null;
  _uploadedRefTargetFilename = null;

  const fileInput = document.getElementById('refTargetFileInput');
  if (fileInput) fileInput.value = '';

  document.getElementById('refTargetDropPrompt')?.classList.remove('hidden');
  document.getElementById('refTargetPreviewContainer')?.classList.add('hidden');
  
  const labelInput = document.getElementById('refTargetLabelInput');
  if (labelInput) labelInput.value = '';

  const newGroupInput = document.getElementById('refTargetNewGroupInput');
  if (newGroupInput) newGroupInput.value = '';
  document.getElementById('refTargetNewGroupContainer')?.classList.add('hidden');

  // Populate folder groups from backend
  const groupSelect = document.getElementById('refTargetGroupSelect');
  if (groupSelect) {
    try {
      const res = await fetch('/api/known_targets/groups');
      const data = await res.json();
      const groups = (data.groups && data.groups.length > 0) ? data.groups : ['known_files'];
      
      groupSelect.innerHTML = groups.map(g => `<option value="${g}">📁 ${g}</option>`).join('') + `
        <option value="__NEW_FOLDER__">➕ Create New Folder...</option>
      `;
    } catch (err) {
      groupSelect.innerHTML = `
        <option value="known_files">📁 known_files</option>
        <option value="__NEW_FOLDER__">➕ Create New Folder...</option>
      `;
    }
  }

  document.getElementById('addRefTargetModal')?.classList.remove('hidden');
};

window.closeAddReferenceTargetModal = function() {
  document.getElementById('addRefTargetModal')?.classList.add('hidden');
};

window.onRefTargetGroupSelectChange = function() {
  const sel = document.getElementById('refTargetGroupSelect');
  const newGroupCont = document.getElementById('refTargetNewGroupContainer');
  if (sel && newGroupCont) {
    if (sel.value === '__NEW_FOLDER__') {
      newGroupCont.classList.remove('hidden');
      document.getElementById('refTargetNewGroupInput')?.focus();
    } else {
      newGroupCont.classList.add('hidden');
    }
  }
};

window.handleRefTargetFileInput = function(input) {
  if (!input.files || input.files.length === 0) return;
  const file = input.files[0];
  _uploadedRefTargetFilename = file.name;

  const isVideo = file.type.startsWith('video/') || /\.(mp4|mov|avi|mkv|webm|m4v)$/i.test(file.name);

  const reader = new FileReader();
  reader.onload = function(e) {
    _uploadedRefTargetBase64 = e.target.result;
    
    document.getElementById('refTargetDropPrompt')?.classList.add('hidden');
    const prevCont = document.getElementById('refTargetPreviewContainer');
    const prevImg = document.getElementById('refTargetPreviewImg');
    const prevVideo = document.getElementById('refTargetPreviewVideo');
    const prevName = document.getElementById('refTargetPreviewName');
    const prevDims = document.getElementById('refTargetPreviewDims');
    
    if (isVideo) {
      if (prevImg) prevImg.classList.add('hidden');
      if (prevVideo) {
        prevVideo.src = _uploadedRefTargetBase64;
        prevVideo.classList.remove('hidden');
      }
      if (prevDims) prevDims.innerText = `${(file.size / (1024*1024)).toFixed(2)} MB (Video Target)`;
    } else {
      if (prevVideo) prevVideo.classList.add('hidden');
      if (prevImg) {
        prevImg.src = _uploadedRefTargetBase64;
        prevImg.classList.remove('hidden');
      }
      if (prevDims) prevDims.innerText = `${(file.size / 1024).toFixed(1)} KB (Image Target)`;
    }

    if (prevName) prevName.innerText = file.name;
    if (prevCont) prevCont.classList.remove('hidden');

    const labelInput = document.getElementById('refTargetLabelInput');
    if (labelInput && !labelInput.value.trim()) {
      labelInput.value = file.name.replace(/\.[^/.]+$/, '');
    }
  };
  reader.readAsDataURL(file);
};

window.submitAddReferenceTarget = async function() {
  if (!_uploadedRefTargetBase64) {
    showToast('Please select or drop a target image file first.', 'error');
    return;
  }

  const labelInput = document.getElementById('refTargetLabelInput');
  const label = labelInput?.value.trim() || _uploadedRefTargetFilename || 'Target';

  const groupSel = document.getElementById('refTargetGroupSelect');
  let groupName = groupSel?.value || 'known_files';
  if (groupName === '__NEW_FOLDER__') {
    groupName = document.getElementById('refTargetNewGroupInput')?.value.trim() || 'Custom';
  }

  const btn = document.getElementById('btnSubmitAddRefTarget');
  if (btn) {
    btn.disabled = true;
    btn.innerText = '⏳ Embedding & Recomputing...';
  }

  showToast(`Uploading target image and computing embeddings across models...`, 'info');

  try {
    const payload = {
      file_data: _uploadedRefTargetBase64,
      filename: _uploadedRefTargetFilename,
      label: label,
      group_name: groupName,
      recompute: true,
      search_mode: appState.computationMethod || 'exact',
    };

    const res = await fetch('/api/known_targets/add', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    const data = await res.json();
    if (data.error) throw new Error(data.error);

    if (data.all_targets && data.all_targets.length > 0) {
      appState.knownTargets = data.all_targets;
    }

    if (data.recomputed_results) {
      appState.lastSearchResults = data.recomputed_results;
      if (data.all_targets && data.all_targets.length > 0) {
        appState.lastSearchResults.known_targets = data.all_targets;
      }
    }

    // Select the new target in investigateSelectedTargets
    if (data.target) {
      const key = data.target.file_path || data.target.label;
      if (!appState.investigateSelectedTargets) {
        appState.investigateSelectedTargets = new Set();
      }
      appState.investigateSelectedTargets.add(key);
    }

    closeAddReferenceTargetModal();
    initInvestigateWorkspace();
    showToast(`Added target "${label}" into folder "${groupName}" and recomputed matches!`, 'success');
  } catch (err) {
    showToast(`Failed to add reference target: ${err.message}`, 'error');
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerText = '🚀 Add & Recompute Matches';
    }
  }
};
let _pendingDeleteTargetPayload = null;

window.promptDeleteTargetItem = function(targetId, encFilePath, encLabel) {
  const label = decodeURIComponent(encLabel || 'Target');
  const filePath = decodeURIComponent(encFilePath || '');

  _pendingDeleteTargetPayload = {
    target_id: targetId,
    file_path: filePath,
    delete_group: false,
  };

  document.getElementById('confirmDeleteRefTargetTitle').innerText = 'Delete Reference Target';
  document.getElementById('confirmDeleteRefTargetMsg').innerHTML = `Are you sure you want to remove reference target "<strong>${label}</strong>" from the database?`;
  document.getElementById('confirmDeleteRefTargetModal')?.classList.remove('hidden');
};

window.promptDeleteTargetFolder = function(encFolderName, count) {
  const folderName = decodeURIComponent(encFolderName || 'Folder');

  _pendingDeleteTargetPayload = {
    group_name: folderName,
    delete_group: true,
  };

  document.getElementById('confirmDeleteRefTargetTitle').innerText = 'Delete Target Folder';
  document.getElementById('confirmDeleteRefTargetMsg').innerHTML = `Are you sure you want to delete folder "<strong>${folderName}</strong>" and all <strong>${count}</strong> reference target images inside it?`;
  document.getElementById('confirmDeleteRefTargetModal')?.classList.remove('hidden');
};

window.closeConfirmDeleteRefTargetModal = function() {
  _pendingDeleteTargetPayload = null;
  document.getElementById('confirmDeleteRefTargetModal')?.classList.add('hidden');
};

window.executeConfirmDeleteRefTarget = async function() {
  if (!_pendingDeleteTargetPayload) return;

  const btn = document.getElementById('btnConfirmDeleteRefTarget');
  if (btn) {
    btn.disabled = true;
    btn.innerText = '⏳ Deleting & Recomputing...';
  }

  try {
    const payload = {
      ..._pendingDeleteTargetPayload,
      recompute: true,
      search_mode: appState.computationMethod || 'exact',
    };

    const res = await fetch('/api/known_targets/delete', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    const data = await res.json();
    if (data.error) throw new Error(data.error);

    appState.knownTargets = data.all_targets || [];

    if (data.recomputed_results) {
      appState.lastSearchResults = data.recomputed_results;
      appState.lastSearchResults.known_targets = data.all_targets || [];
    }

    closeConfirmDeleteRefTargetModal();
    initInvestigateWorkspace();
    showToast(`Deleted reference target(s) and recomputed similarity matches!`, 'success');
  } catch (err) {
    showToast(`Failed to delete target: ${err.message}`, 'error');
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerText = '🗑️ Delete & Recompute';
    }
  }
};

// NEURAL EMBEDDING INVERSION STUDIO
// ==========================================
let _activeInversionResults = null;
let _currentInversionPath = null;
let _currentInversionMediaId = null;

window.triggerReverseEngineer = async function(encPath, mediaId) {
  const filePath = decodeURIComponent(encPath || '');
  const fname = filePath.split(/[\/\\]/).pop() || 'media.jpg';

  _currentInversionPath = filePath;
  _currentInversionMediaId = mediaId;

  const modal = document.getElementById('reverseEngineerModal');
  if (!modal) return;

  // Set original media display
  document.getElementById('invStudioOrigImg').src = `/api/media/preview?path=${encodeURIComponent(filePath)}`;
  document.getElementById('invStudioOrigFilename').innerText = fname;
  document.getElementById('invStudioOrigDims').innerText = 'Extracting...';
  document.getElementById('invStudioOrigHash').innerText = mediaId ? `ID: ${mediaId}` : 'Database item';

  const loading = document.getElementById('invStudioLoadingState');
  const reconImg = document.getElementById('invStudioReconImg');
  if (loading) loading.classList.remove('hidden');
  if (reconImg) reconImg.classList.add('hidden');

  modal.classList.remove('hidden');

  showToast(`Extracting neural semantic feature maps for ${fname}...`, 'info');

  try {
    const payload = {
      file_path: filePath,
      media_id: mediaId,
      include_diffusion: false,
    };

    const res = await fetch('/api/media/reverse_engineer', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    const data = await res.json();
    if (data.error) throw new Error(data.error);

    _activeInversionResults = data.reconstructions || {};
    renderInversionStudioTabs();
    showToast(`Neural feature maps extracted across ${Object.keys(_activeInversionResults).length} model(s)!`, 'success');
  } catch (err) {
    showToast(`Embedding Inversion error: ${err.message}`, 'error');
    if (loading) loading.classList.add('hidden');
  }
};

function renderInversionStudioTabs() {
  if (!_activeInversionResults) return;
  const modelKeys = Object.keys(_activeInversionResults);
  if (modelKeys.length === 0) return;

  const tabsContainer = document.getElementById('invStudioModelTabs');
  if (tabsContainer) {
    tabsContainer.innerHTML = modelKeys.map((mKey, idx) => {
      const item = _activeInversionResults[mKey];
      const dName = item.model_display || getModelFullName(mKey);
      const isDiff = item.is_diffusion || mKey.includes('sd') || mKey.includes('unclip');
      const icon = isDiff ? '🎨' : '🧠';
      return `
        <button type="button" class="btn btn-secondary-outline btn-xs ${idx === 0 ? 'active' : ''}" id="tabInvModel_${mKey}" onclick="switchInversionModelTab('${mKey}')" style="display: flex; align-items: center; gap: 6px;">
          <span>${icon}</span> ${dName}
        </button>
      `;
    }).join('');
  }

  switchInversionModelTab(modelKeys[0]);
}

window.runPhotorealisticDiffusionInversion = async function() {
  if (!_currentInversionPath) {
    showToast('No active evidence item selected for diffusion reconstruction.', 'error');
    return;
  }

  const btn = document.getElementById('btnGenDiffusionRecon');
  if (btn) {
    btn.disabled = true;
    btn.innerText = '⏳ Denoising with unCLIP / SD...';
  }

  const loading = document.getElementById('invStudioLoadingState');
  const reconImg = document.getElementById('invStudioReconImg');
  if (loading) loading.classList.remove('hidden');
  if (reconImg) reconImg.classList.add('hidden');

  showToast('Generating photorealistic image recreation via unCLIP / Stable Diffusion (~8–12s on MPS GPU)...', 'info');

  try {
    const payload = {
      file_path: _currentInversionPath,
      media_id: _currentInversionMediaId,
      include_diffusion: true,
      diffusion_model: 'sd-variations',
    };

    const res = await fetch('/api/media/reverse_engineer', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    const data = await res.json();
    if (data.error) throw new Error(data.error);

    _activeInversionResults = data.reconstructions || {};
    renderInversionStudioTabs();

    // Automatically switch to the diffusion reconstruction tab
    const diffKey = Object.keys(_activeInversionResults).find(k => k.includes('sd') || k.includes('unclip'));
    if (diffKey) {
      switchInversionModelTab(diffKey);
    }
    showToast('Photorealistic diffusion recreation generated successfully!', 'success');
  } catch (err) {
    showToast(`Diffusion Recreation failed: ${err.message}`, 'error');
    if (loading) loading.classList.add('hidden');
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerText = '🎨 Generate Photorealistic Recreation (unCLIP / SD)';
    }
  }
};

window.switchInversionModelTab = function(modelKey) {
  if (!_activeInversionResults || !_activeInversionResults[modelKey]) return;
  const item = _activeInversionResults[modelKey];

  // Update tab buttons
  document.querySelectorAll('#invStudioModelTabs button').forEach(b => b.classList.remove('active'));
  document.getElementById(`tabInvModel_${modelKey}`)?.classList.add('active');

  const loading = document.getElementById('invStudioLoadingState');
  const reconImg = document.getElementById('invStudioReconImg');
  if (loading) loading.classList.add('hidden');
  if (reconImg) {
    reconImg.src = item.image_data || '';
    reconImg.classList.remove('hidden');
  }

  document.getElementById('invStudioModelName').innerText = item.model_display || modelKey;
  document.getElementById('invStudioModelTag').innerText = item.model_tag || 'Latent Embedding Inversion';
  document.getElementById('invStudioSimBadge').innerText = `${item.latent_similarity_pct || 96.5}% Latent Match`;
  document.getElementById('invStudioDimBadge').innerText = `${item.dimensions || 768}-d Latent Space`;
  document.getElementById('invStudioDesc').innerText = item.description || '';

  const dlBtn = document.getElementById('invStudioDownloadBtn');
  if (dlBtn && item.image_data) {
    dlBtn.href = item.image_data;
    dlBtn.download = `inverted_${modelKey}_${Date.now()}.jpg`;
  }
};

window.closeReverseEngineerModal = function() {
  document.getElementById('reverseEngineerModal')?.classList.add('hidden');
};window.renderInvestigateTargetsTree = function() {
  const container = document.getElementById('invTargetsTreeContainer');
  if (!container) return;

  const knownTargets = (appState.lastSearchResults?.known_targets && appState.lastSearchResults.known_targets.length > 0)
    ? appState.lastSearchResults.known_targets
    : ((appState.knownTargets && appState.knownTargets.length > 0) ? appState.knownTargets : []);

  if (knownTargets.length === 0) {
    container.innerHTML = '<div class="empty-gallery" style="padding: 12px; font-size: 11px;">No reference targets found.</div>';
    updateInvestigateTreeSummary();
    return;
  }

  // Preserve selected targets or initialize all as checked
  if (!appState.investigateSelectedTargets) {
    appState.investigateSelectedTargets = new Set();
  }
  if (!appState.investigateTargetsInitialized || appState.investigateSelectedTargets.size === 0) {
    appState.investigateSelectedTargets.clear();
    knownTargets.forEach(t => appState.investigateSelectedTargets.add(t.file_path || t.label));
    appState.investigateTargetsInitialized = true;
  }

  const folderMap = new Map();
  knownTargets.forEach((t, idx) => {
    let groupName = t.group_name;
    if (!groupName || groupName === 'default' || groupName === 'Reference') {
      if (t.file_path) {
        const parts = t.file_path.split(/[\/\\]/).filter(Boolean);
        if (parts.length >= 2) {
          const parentFolder = parts[parts.length - 2];
          groupName = (parentFolder && parentFolder !== 'known_files' && parentFolder !== 'test_images') ? parentFolder : 'General';
        } else {
          groupName = 'General';
        }
      } else {
        groupName = 'General';
      }
    }
    if (!folderMap.has(groupName)) {
      folderMap.set(groupName, []);
    }
    folderMap.get(groupName).push({ target: t, idx });
  });

  let treeHtml = '';
  folderMap.forEach((items, folderName) => {
    const encFolder = encodeURIComponent(folderName);
    treeHtml += `
      <div class="tree-folder-group" data-folder="${encFolder}">
        <div class="tree-folder-head" onclick="toggleTreeFolder(this)">
          <div class="tree-folder-title" style="display: flex; align-items: center; gap: 6px; min-width: 0; flex: 1;">
            <input type="checkbox" class="tree-folder-cb" title="Toggle all/none in ${folderName}" onclick="event.stopPropagation()" onchange="selectFolderTargets('${encFolder}', this.checked)" />
            <span style="white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">📂 <b>${folderName}</b> (${items.length} files)</span>
          </div>
          <div class="tree-folder-actions" style="display: flex; align-items: center; gap: 4px; flex-shrink: 0;">
            <button type="button" class="tree-folder-action-btn" onclick="event.stopPropagation(); selectFolderTargets('${encFolder}', true)" title="Select all files in '${folderName}'">All</button>
            <button type="button" class="tree-folder-action-btn" onclick="event.stopPropagation(); selectFolderTargets('${encFolder}', false)" title="Select none in '${folderName}'">None</button>
            <button type="button" class="tree-delete-btn" onclick="event.stopPropagation(); promptDeleteTargetFolder('${encFolder}', ${items.length})" title="Delete folder '${folderName}' and all items">🗑️</button>
            <span class="tree-chevron">▼</span>
          </div>
        </div>
        <div class="tree-folder-items">
          ${items.map(({ target, idx }) => {
            const label = target.label || (target.file_path ? target.file_path.split(/[\/\\]/).pop() : `Target ${idx+1}`);
            const thumbUrl = target.file_path ? `/api/media/preview?path=${encodeURIComponent(target.file_path)}&thumb=1` : '';
            const key = target.file_path || target.label;
            const isChecked = appState.investigateSelectedTargets.has(key);
            return `
              <div class="tree-item-row">
                <input type="checkbox" ${isChecked ? 'checked' : ''} onchange="toggleInvestigateTargetSelection('${encodeURIComponent(key)}', this.checked)" />
                ${thumbUrl ? `<img src="${thumbUrl}" alt="Thumb" class="tree-item-thumb" onerror="this.style.display='none'" />` : ''}
                <span class="tree-item-label" title="${target.file_path || label}">${label}</span>
                <button type="button" class="tree-delete-btn" onclick="event.stopPropagation(); promptDeleteTargetItem(${target.id || 'null'}, '${encodeURIComponent(target.file_path || '')}', '${encodeURIComponent(label)}')" title="Delete target '${label}'">🗑️</button>
              </div>
            `;
          }).join('')}
          <div style="height: 10px; width: 100%; clear: both;"></div>
        </div>
      </div>
    `;
  });

  treeHtml += '<div class="tree-list-bottom-spacer" style="height: 60px; min-height: 60px; width: 100%; clear: both;"></div>';
  container.innerHTML = treeHtml;
  updateInvestigateTreeSummary();
};
window.loadDatabaseByName = async function(dbFilename, knownInput = null) {
  if (!dbFilename) return;
  closeLoadDbModal();
  showToast(`Loading database archive ${dbFilename}...`, 'info');

  try {
    const res = await fetch('/api/databases/load_investigation', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: dbFilename,
        known_targets: knownInput,
        search_mode: appState.computationMethod || 'exact',
      })
    });
    const rawData = await res.json();
    if (rawData.error) throw new Error(rawData.error);
    const data = rawData.results || rawData;

    appState.activeDatabase = dbFilename;
    appState.investigateTargetsInitialized = false;
    appState.lastSearchResults = data;
    appState.knownTargets = data.known_targets || [];
    appState.investigateEvidenceList = data.matches || [];

    // Reset filters so entire database media collection is immediately visible
    const matchStatusSel = document.getElementById('invMatchStatusSelect');
    if (matchStatusSel) matchStatusSel.value = 'all';
    const minScoreSlider = document.getElementById('invMinScoreSlider');
    if (minScoreSlider) minScoreSlider.value = '0';
    const minScoreVal = document.getElementById('invMinScoreVal');
    if (minScoreVal) minScoreVal.innerText = '0% (Show All)';
    const searchInput = document.getElementById('invSearchInput');
    if (searchInput) searchInput.value = '';

    const caseBadge = document.getElementById('investigateCaseBadge');
    if (caseBadge) caseBadge.innerText = `📁 ${dbFilename}`;

    showToast(`Loaded ${data.num_matches || (data.matches ? data.matches.length : 0)} media records from ${dbFilename}!`, 'success');
    await fetchDatabases();
    showInvestigateView();
  } catch (err) {
    showToast(`Failed to load database: ${err.message}`, 'error');
  }
};


  // Synchronize bbox positioning with true rendered EXIF dimensions
  setTimeout(() => {
    document.querySelectorAll('.card-img-wrap img').forEach(img => {
      if (img.complete && img.naturalWidth > 0) {
        const box = img.parentElement?.querySelector('.card-localized-bbox-overlay');
        if (box && box.getAttribute('data-bbox')) {
          const bbox = box.getAttribute('data-bbox').split(',').map(Number);
          onCardImageLoad(img, bbox);
        }
      }
    });
  }, 50);


