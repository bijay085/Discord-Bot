// Bubble Bot - Fixed JavaScript

// Configuration
const CONFIG = {
    API_BASE: window.location.hostname === 'localhost' ? 
        'http://localhost:3000/api' : '/api',
    UPDATE_INTERVAL: 30000,
    COOLDOWN: 86400000
};

// State
const state = {
    isOnline: false,
    lastClaim: 0,
    cooldownTimer: null
};

// DOM Elements
const elements = {};

// Initialize
document.addEventListener('DOMContentLoaded', init);

async function init() {
    cacheElements();
    loadSavedId();
    setupEventListeners();
    await updateStatus();
    // Removed auto-update - only updates on page refresh
}

// Cache DOM elements for better performance
function cacheElements() {
    elements.statusDot = document.getElementById('statusDot');
    elements.statusText = document.getElementById('statusText');
    elements.statusBadge = document.getElementById('statusBadge');
    elements.totalUsers = document.getElementById('totalUsers');
    elements.totalPoints = document.getElementById('totalPoints');
    elements.totalCookies = document.getElementById('totalCookies');
    elements.activeToday = document.getElementById('activeToday');
    elements.leaderboard = document.getElementById('leaderboard');
    elements.claimForm = document.getElementById('claimForm');
    elements.userId = document.getElementById('userId');
    elements.claimButton = document.getElementById('claimButton');
    elements.buttonText = document.getElementById('buttonText');
    elements.spinner = document.getElementById('spinner');
    elements.claimResult = document.getElementById('claimResult');
    elements.claimTimer = document.getElementById('claimTimer');
    elements.timerValue = document.getElementById('timerValue');
}

// Load saved Discord ID
function loadSavedId() {
    const savedId = localStorage.getItem('discordId');
    if (savedId && elements.userId) {
        elements.userId.value = savedId;
    }
}

// Setup event listeners
function setupEventListeners() {
    // Form submission
    if (elements.claimForm) {
        elements.claimForm.addEventListener('submit', handleClaim);
    }
    
    // Discord ID validation
    if (elements.userId) {
        elements.userId.addEventListener('input', (e) => {
            e.target.value = e.target.value.replace(/\D/g, '');
            validateId(e.target.value);
        });
    }
}

// Validate Discord ID
function validateId(id) {
    const isValid = /^[0-9]{17,20}$/.test(id);
    if (elements.userId) {
        elements.userId.classList.toggle('error', !isValid && id.length > 0);
    }
    return isValid;
}

// Update status and stats
async function updateStatus() {
    try {
        const response = await fetch(`${CONFIG.API_BASE}/status`);
        if (!response.ok) throw new Error('Status fetch failed');
        
        const data = await response.json();
        updateUI(data);
        updateLeaderboard(data.leaderboard || []);
        
    } catch (error) {
        console.error('Status update failed:', error);
        setOfflineStatus();
    }
}

// Update UI with status data
function updateUI(data) {
    // Bot status
    state.isOnline = data.online || false;
    
    if (elements.statusBadge && elements.statusDot && elements.statusText) {
        const statusClass = state.isOnline ? 'online' : 'offline';
        elements.statusBadge.className = `status-badge ${statusClass}`;
        elements.statusDot.className = `status-dot ${statusClass}`;
        elements.statusText.textContent = state.isOnline ? 'ONLINE' : 'OFFLINE';
    }
    
    // Stats
    if (data.stats) {
        updateStat('totalUsers', data.stats.users);
        updateStat('totalPoints', data.stats.points);
        updateStat('totalCookies', data.stats.cookies);
        updateStat('activeToday', data.stats.active);
    }
}

// Update individual stat
function updateStat(id, value) {
    if (elements[id]) {
        elements[id].textContent = formatNumber(value || 0);
    }
}

// Set offline status
function setOfflineStatus() {
    state.isOnline = false;
    if (elements.statusBadge && elements.statusDot && elements.statusText) {
        elements.statusBadge.className = 'status-badge offline';
        elements.statusDot.className = 'status-dot offline';
        elements.statusText.textContent = 'OFFLINE';
    }
}

// Update leaderboard
function updateLeaderboard(users) {
    if (!elements.leaderboard) return;
    
    if (!users.length) {
        elements.leaderboard.innerHTML = '<div class="loading">No data available</div>';
        return;
    }
    
    elements.leaderboard.innerHTML = users.slice(0, 10).map((user, i) => {
        const medal = i === 0 ? '🥇' : i === 1 ? '🥈' : i === 2 ? '🥉' : `#${i + 1}`;
        return `
            <div class="leaderboard-item">
                <div class="leaderboard-rank">
                    <span class="rank-medal">${medal}</span>
                    <span class="leaderboard-user">${escapeHtml(user.name || 'Anonymous')}</span>
                </div>
                <span class="leaderboard-points">${formatNumber(user.points)} pts</span>
            </div>
        `;
    }).join('');
}

// Handle claim submission
async function handleClaim(e) {
    e.preventDefault();
    
    // Rate limiting
    const now = Date.now();
    if (now - state.lastClaim < 2000) {
        showResult('error', 'Too fast! Wait a moment.');
        return;
    }
    
    const userId = elements.userId.value.trim();
    
    if (!validateId(userId)) {
        showResult('error', 'Invalid Discord ID format! Must be 17-20 digits.');
        return;
    }
    
    // Save ID
    localStorage.setItem('discordId', userId);
    state.lastClaim = now;
    
    // UI state
    setLoadingState(true);
    
    try {
        const response = await fetch(`${CONFIG.API_BASE}/daily`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ userId })
        });
        
        const data = await response.json();
        
        if (response.ok) {
            handleClaimSuccess(data);
        } else {
            handleClaimError(data);
        }
    } catch (error) {
        console.error('Claim error:', error);
        showResult('error', 'Connection error. Try again.');
    } finally {
        setLoadingState(false);
    }
}

// Set loading state
function setLoadingState(loading) {
    if (elements.claimButton) {
        elements.claimButton.disabled = loading;
    }
    if (elements.buttonText) {
        elements.buttonText.textContent = loading ? 'CLAIMING...' : 'CLAIM DAILY POINTS';
    }
    if (elements.spinner) {
        elements.spinner.classList.toggle('hidden', !loading);
    }
}

// Handle successful claim
function handleClaimSuccess(data) {
    if (elements.claimButton) {
        elements.claimButton.classList.add('success');
    }
    if (elements.buttonText) {
        elements.buttonText.textContent = '✅ CLAIMED!';
    }
    
    showResult('success', `
        <strong>🎉 Success!</strong><br>
        +${data.points} POINTS<br>
        Balance: ${formatNumber(data.balance)} points
    `);
    
    // Start cooldown timer
    if (data.next) {
        startCooldownTimer(new Date(data.next));
    }
    
    setTimeout(() => {
        if (elements.claimButton) {
            elements.claimButton.classList.remove('success');
        }
        if (elements.buttonText) {
            elements.buttonText.textContent = 'CLAIMED TODAY ✓';
        }
        updateStatus();
    }, 3000);
}

// Handle claim error
function handleClaimError(data) {
    if (elements.claimButton) {
        elements.claimButton.classList.add('error');
    }
    if (elements.buttonText) {
        elements.buttonText.textContent = '❌ ERROR';
    }
    
    setTimeout(() => {
        if (elements.claimButton) {
            elements.claimButton.classList.remove('error');
        }
        if (elements.buttonText) {
            elements.buttonText.textContent = 'CLAIM DAILY POINTS';
        }
    }, 3000);
    
    const error = data.error || 'Unknown error';
    
    if (error.includes('Already claimed')) {
        showResult('error', `
            <strong>❌ Already Claimed</strong><br>
            ${data.timeLeft || 'Wait 24 hours'}<br>
            Balance: ${formatNumber(data.balance)} points
        `);
        
        if (data.nextClaim) {
            startCooldownTimer(new Date(data.nextClaim));
        }
    } else {
        showResult('error', `<strong>❌ Error</strong><br>${error}`);
    }
}

// Show result message
function showResult(type, message) {
    if (!elements.claimResult) return;
    
    elements.claimResult.className = `result-box ${type}`;
    elements.claimResult.innerHTML = message;
    elements.claimResult.classList.remove('hidden');
    
    setTimeout(() => {
        elements.claimResult.classList.add('hidden');
    }, 10000);
}

// Start cooldown timer
function startCooldownTimer(nextClaim) {
    if (state.cooldownTimer) {
        clearInterval(state.cooldownTimer);
    }
    
    if (!elements.claimTimer || !elements.timerValue) return;
    
    elements.claimTimer.classList.remove('hidden');
    
    const updateTimer = () => {
        const now = Date.now();
        const timeLeft = nextClaim.getTime() - now;
        
        if (timeLeft <= 0) {
            clearInterval(state.cooldownTimer);
            elements.claimTimer.classList.add('hidden');
            if (elements.buttonText) {
                elements.buttonText.textContent = 'CLAIM DAILY POINTS';
            }
            return;
        }
        
        const hours = Math.floor(timeLeft / 3600000);
        const minutes = Math.floor((timeLeft % 3600000) / 60000);
        const seconds = Math.floor((timeLeft % 60000) / 1000);
        
        elements.timerValue.textContent = 
            `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
    };
    
    updateTimer();
    state.cooldownTimer = setInterval(updateTimer, 1000);
}

// Utility functions
function formatNumber(num) {
    return new Intl.NumberFormat().format(num);
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}