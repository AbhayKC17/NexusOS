function syncReplies() {
  const btn = document.getElementById('syncBtn');
  const status = document.getElementById('syncStatus');

  if (btn) {
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span> Syncing…';
  }
  if (status) status.textContent = 'Syncing…';

  fetch('/api/sync-replies', { method: 'POST' })
    .then(r => r.json())
    .then(data => {
      if (btn) {
        btn.disabled = false;
        btn.innerHTML = '<i class="bi bi-arrow-repeat"></i> Sync Replies';
      }
      if (data.error) {
        if (status) { status.textContent = 'Error'; status.className = 'badge bg-danger'; }
        alert('Sync error: ' + data.error);
      } else {
        const msg = data.new_replies > 0
          ? `${data.new_replies} new reply${data.new_replies > 1 ? 'ies' : ''} received!`
          : 'No new replies';
        if (status) {
          status.textContent = msg;
          status.className = data.new_replies > 0 ? 'badge bg-success' : 'badge bg-secondary';
        }
        if (data.new_replies > 0) {
          setTimeout(() => window.location.reload(), 1200);
        }
      }
    })
    .catch(err => {
      if (btn) { btn.disabled = false; btn.innerHTML = '<i class="bi bi-arrow-repeat"></i> Sync Replies'; }
      if (status) { status.textContent = 'Failed'; status.className = 'badge bg-danger'; }
    });
}

// auto-dismiss alerts after 6 seconds
document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('.alert').forEach(el => {
    setTimeout(() => {
      const bsAlert = bootstrap.Alert.getOrCreateInstance(el);
      bsAlert.close();
    }, 6000);
  });
});
