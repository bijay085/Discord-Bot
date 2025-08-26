// Cookie Bot - Optimized Application Script

// State & Config
const AppState = {
    isOnline: false,
    lastClaim: 0
};

const Config = {
    API_BASE: window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1' 
        ? 'http://localhost:3000/api' 
        : window.location.origin + '/api',
    UPDATE_INTERVAL: 30000
};

// Initialize
document.addEventListener('DOMContentLoaded', initApp);

async function initApp() {
    loadSavedData();
    await updateStatus();
    setupListeners();
    setInterval(updateStatus, Config.UPDATE_INTERVAL);
    showContent();
}

function showContent() {
    const loading = document.getElementById('loadingScreen');
    const main = document.getElementById('mainContainer');
    if (loading) loading.style.display = 'none';
    if (main) main.style.display = 'block';
}

// Data Management
function loadSavedData() {
    const savedId = localStorage.getItem('discordId');
    const savedName = localStorage.getItem('username');
    
    const idInput = document.getElementById('userId');
    const nameInput = document.getElementById('username');
    
    if (savedId && idInput) idInput.value = savedId;
    if (savedName && nameInput) nameInput.value = savedName;
}

function saveData(userId, username) {
    localStorage.setItem('discordId', userId);
    if (username) {
        localStorage.setItem('username', username);
    }
}

// Validation
function validateId(id) {
    return /^[0-9]{17,20}$/.test(id);
}

function validateName(name) {
    // Username is optional, so empty is valid
    if (!name) return true;
    return name.length >= 2 && name.length <= 32 && /^[a-zA-Z0-9_.-]+$/.test(name);
}

// Status Updates
async function updateStatus() {
    try {
        const response = await fetch(`${Config.API_BASE}/status`);
        const data = await response.json();
        
        displayStatus(data);
        displayLeaderboard(data.leaderboard || []);
    } catch (error) {
        console.error('Status update failed:', error);
        displayStatus({ online: false });
    }
}

function displayStatus(data) {
    AppState.isOnline = data.online || false;
    
    const dot = document.getElementById('statusDot');
    const text = document.getElementById('statusText');
    
    if (dot && text) {
        if (AppState.isOnline) {
            dot.className = 'status-dot online';
            text.textContent = 'ONLINE';
            text.style.color = '#3BA55C';
        } else {
            dot.className = 'status-dot offline';
            text.textContent = 'OFFLINE';
            text.style.color = '#ED4245';
        }
    }
    
    // Update stats
    updateElement('totalUsers', data.totalUsers || 0);
    updateElement('totalPoints', data.totalPoints || 0);
    updateElement('totalCookies', data.totalCookies || 0);
    updateElement('activeToday', data.activeToday || 0);
    
    const lastUpdate = document.getElementById('lastUpdate');
    if (lastUpdate) {
        lastUpdate.textContent = `Last updated: ${new Date().toLocaleTimeString()}`;
    }
}

function updateElement(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = formatNumber(value);
}

function displayLeaderboard(leaderboard) {
    const board = document.getElementById('leaderboard');
    if (!board) return;
    
    if (!leaderboard.length) {
        board.innerHTML = '<div class="leaderboard-loading"><p>No data available</p></div>';
        return;
    }
    
    board.innerHTML = '';
    
    leaderboard.slice(0, 10).forEach((user, i) => {
        const item = document.createElement('div');
        item.className = 'leaderboard-item';
        
        const medal = i === 0 ? '🥇' : i === 1 ? '🥈' : i === 2 ? '🥉' : `#${i + 1}`;
        const rankClass = i === 0 ? 'gold' : i === 1 ? 'silver' : i === 2 ? 'bronze' : '';
        
        item.innerHTML = `
            <div class="leaderboard-rank">
                <span class="rank-badge ${rankClass}">${medal}</span>
                <span class="leaderboard-user">${escapeHtml(user.username || 'Unknown')}</span>
            </div>
            <span class="leaderboard-points">${formatNumber(user.points || 0)} pts</span>
        `;
        
        board.appendChild(item);
    });
}

// Event Handlers
function setupListeners() {
    const form = document.getElementById('claimForm');
    if (form) form.addEventListener('submit', handleClaim);
    
    const idInput = document.getElementById('userId');
    const nameInput = document.getElementById('username');
    
    if (idInput) {
        idInput.addEventListener('input', e => {
            e.target.value = e.target.value.replace(/[^0-9]/g, '');
            e.target.classList.toggle('error', !validateId(e.target.value) && e.target.value);
        });
    }
    
    if (nameInput) {
        nameInput.addEventListener('input', e => {
            e.target.classList.toggle('error', !validateName(e.target.value) && e.target.value);
        });
    }
}

// Claim Handler
async function handleClaim(e) {
    e.preventDefault();
    
    // Rate limit check
    const now = Date.now();
    if (now - AppState.lastClaim < 2000) {
        showToast('Too fast! Wait a moment', 'warning');
        return;
    }
    
    const userId = document.getElementById('userId').value.trim();
    const username = document.getElementById('username').value.trim() || 'Anonymous'; // Default if empty
    
    if (!validateId(userId)) {
        showToast('Invalid Discord ID format', 'error');
        return;
    }
    
    if (!validateName(username)) {
        showToast('Invalid username format', 'error');
        return;
    }
    
    const button = document.getElementById('claimButton');
    const text = button.querySelector('.button-text');
    const loader = button.querySelector('.button-loader');
    
    button.disabled = true;
    text.textContent = 'CLAIMING...';
    if (loader) loader.style.display = 'flex';
    
    saveData(userId, username);
    AppState.lastClaim = now;
    
    try {
        const response = await fetch(`${Config.API_BASE}/daily`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                userId,
                username
            })
        });
        
        const data = await response.json();
        
        if (response.ok) {
            handleSuccess(data, button, text, loader);
        } else {
            handleError(data, button, text, loader);
        }
    } catch (error) {
        console.error('Claim failed:', error);
        showToast('Connection error', 'error');
        text.textContent = 'CLAIM DAILY POINTS';
        if (loader) loader.style.display = 'none';
    } finally {
        button.disabled = false;
    }
}

function handleSuccess(data, button, text, loader) {
    button.classList.add('success');
    text.textContent = '✅ CLAIMED!';
    if (loader) loader.style.display = 'none';
    
    showToast(`Claimed ${data.points_earned} points!`, 'success');
    showResult('success',
        '🎉 Success!',
        `+${data.points_earned} POINTS`,
        `New Balance: ${formatNumber(data.new_balance)} points`
    );
    
    setTimeout(() => {
        button.classList.remove('success');
        text.textContent = 'CLAIMED TODAY ✓';
    }, 3000);
    
    setTimeout(updateStatus, 2000);
}

function handleError(data, button, text, loader) {
    button.classList.add('error');
    text.textContent = '❌ ERROR';
    if (loader) loader.style.display = 'none';
    
    setTimeout(() => {
        button.classList.remove('error');
        text.textContent = 'CLAIM DAILY POINTS';
    }, 3000);
    
    const error = data.error || 'Unknown error';
    
    if (error.includes('already claimed')) {
        showToast('Already claimed today!', 'error');
        showResult('error', '❌ Already Claimed', error, 
            data.nextClaim ? `Next: ${new Date(data.nextClaim).toLocaleString()}` : '');
    } else {
        showToast(error, 'error');
        showResult('error', '❌ Error', error);
    }
}

// UI Helpers
function showResult(type, title, ...messages) {
    const result = document.getElementById('claimResult');
    if (!result) return;
    
    result.className = `claim-result ${type}`;
    result.innerHTML = `
        <div class="result-title">${title}</div>
        ${messages.filter(m => m).map(m => 
            `<div class="result-${m.startsWith('+') ? 'points' : 'message'}">${m}</div>`
        ).join('')}
    `;
    result.style.display = 'block';
}

function showToast(message, type = 'info') {
    const container = document.getElementById('toastContainer');
    if (!container) return;
    
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    
    const icons = {
        success: '✅',
        error: '❌',
        warning: '⚠️',
        info: 'ℹ️'
    };
    
    toast.innerHTML = `<span>${icons[type]}</span><span>${message}</span>`;
    container.appendChild(toast);
    
    setTimeout(() => {
        toast.style.opacity = '0';
        setTimeout(() => toast.remove(), 300);
    }, 5000);
}

// Utilities
function formatNumber(num) {
    return new Intl.NumberFormat().format(num);
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}