// Bubble Bot - Redesigned JavaScript
// Clean, efficient, no unnecessary animations

// ============================================
// Configuration
// ============================================
const CONFIG = {
    API_BASE: window.location.hostname === 'localhost' 
        ? 'http://localhost:3000/api' 
        : '/api',
    UPDATE_INTERVAL: 30000,
    COOLDOWN_DURATION: 86400000, // 24 hours
    MIN_ID_LENGTH: 15,
    MAX_ID_LENGTH: 25
};

// ============================================
// State Management
// ============================================
const state = {
    isOnline: false,
    cooldownTimer: null,
    updateInterval: null,
    lastClaimTime: 0
};

// ============================================
// DOM Cache
// ============================================
const elements = {};

// ============================================
// Initialize Application
// ============================================
document.addEventListener('DOMContentLoaded', () => {
    cacheElements();
    loadSavedData();
    setupEventListeners();
    initializeApp();
});

// ============================================
// Cache DOM Elements
// ============================================
function cacheElements() {
    // Status
    elements.statusDot = document.getElementById('statusDot');
    elements.statusText = document.getElementById('statusText');
    
    // Stats
    elements.totalUsers = document.getElementById('totalUsers');
    elements.totalPoints = document.getElementById('totalPoints');
    elements.activeToday = document.getElementById('activeToday');
    elements.totalCookies = document.getElementById('totalCookies');
    
    // Form
    elements.claimForm = document.getElementById('claimForm');
    elements.userId = document.getElementById('userId');
    elements.claimButton = document.getElementById('claimButton');
    elements.buttonText = document.getElementById('buttonText');
    elements.spinner = document.getElementById('spinner');
    elements.charCount = document.getElementById('charCount');
    
    // Feedback
    elements.alertBox = document.getElementById('alertBox');
    elements.timerBox = document.getElementById('timerBox');
    elements.timerValue = document.getElementById('timerValue');
    elements.balanceBox = document.getElementById('balanceBox');
    elements.balanceValue = document.getElementById('balanceValue');
    
    // Leaderboard
    elements.leaderboard = document.getElementById('leaderboard');
}

// ============================================
// Load Saved Data
// ============================================
function loadSavedData() {
    // Load saved Discord ID
    const savedId = localStorage.getItem('discordId');
    if (savedId && elements.userId) {
        elements.userId.value = savedId;
        validateInput();
    }
    
    // Load saved balance
    const lastBalance = localStorage.getItem('lastBalance');
    if (lastBalance && elements.balanceValue) {
        elements.balanceBox.classList.remove('hidden');
        elements.balanceValue.textContent = `${formatNumber(lastBalance)} points`;
    }
    
    // Load last claim time
    const lastClaim = localStorage.getItem('lastClaimTime');
    if (lastClaim) {
        state.lastClaimTime = parseInt(lastClaim);
        checkCooldown();
    }
}

// ============================================
// Setup Event Listeners
// ============================================
function setupEventListeners() {
    // Form submission
    if (elements.claimForm) {
        elements.claimForm.addEventListener('submit', handleClaim);
    }
    
    // Input validation
    if (elements.userId) {
        elements.userId.addEventListener('input', validateInput);
        elements.userId.addEventListener('paste', (e) => {
            setTimeout(validateInput, 0);
        });
    }
}

// ============================================
// Initialize Application
// ============================================
async function initializeApp() {
    // Initial status update
    await updateStatus();
    
    // Setup periodic updates
    state.updateInterval = setInterval(updateStatus, CONFIG.UPDATE_INTERVAL);
}

// ============================================
// Validate Input
// ============================================
function validateInput() {
    const input = elements.userId;
    const value = input.value.replace(/\D/g, ''); // Remove non-digits
    
    if (value !== input.value) {
        input.value = value;
    }
    
    const length = value.length;
    
    // Update character count
    if (elements.charCount) {
        elements.charCount.textContent = `${length}/${CONFIG.MIN_ID_LENGTH}-${CONFIG.MAX_ID_LENGTH}`;
        
        if (length === 0) {
            elements.charCount.style.color = 'var(--text-muted)';
            input.classList.remove('error', 'success');
        } else if (length >= CONFIG.MIN_ID_LENGTH && length <= CONFIG.MAX_ID_LENGTH) {
            elements.charCount.style.color = 'var(--success)';
            input.classList.remove('error');
            input.classList.add('success');
        } else {
            elements.charCount.style.color = 'var(--warning)';
            input.classList.add('error');
            input.classList.remove('success');
        }
    }
    
    return length >= CONFIG.MIN_ID_LENGTH && length <= CONFIG.MAX_ID_LENGTH;
}

// ============================================
// Update Status & Stats
// ============================================
async function updateStatus() {
    try {
        const response = await fetch(`${CONFIG.API_BASE}/status`);
        if (!response.ok) throw new Error('Failed to fetch status');
        
        const data = await response.json();
        
        // Update bot status
        updateBotStatus(data.online);
        
        // Update stats
        updateStats(data.stats);
        
        // Update leaderboard
        updateLeaderboard(data.leaderboard);
        
    } catch (error) {
        console.error('Status update failed:', error);
        updateBotStatus(false);
    }
}

// ============================================
// Update Bot Status
// ============================================
function updateBotStatus(isOnline) {
    state.isOnline = isOnline;
    
    if (elements.statusDot && elements.statusText) {
        if (isOnline) {
            elements.statusDot.classList.add('online');
            elements.statusDot.classList.remove('offline');
            elements.statusText.textContent = 'Bot Online';
        } else {
            elements.statusDot.classList.add('offline');
            elements.statusDot.classList.remove('online');
            elements.statusText.textContent = 'Bot Offline';
        }
    }
}

// ============================================
// Update Stats
// ============================================
function updateStats(stats) {
    if (!stats) return;
    
    // Update each stat with animation
    animateNumber(elements.totalUsers, stats.users || 0);
    animateNumber(elements.totalPoints, stats.points || 0);
    animateNumber(elements.activeToday, stats.active || 0);
    animateNumber(elements.totalCookies, stats.cookies || 0);
}

// ============================================
// Animate Number Change
// ============================================
function animateNumber(element, target) {
    if (!element) return;
    
    const current = parseInt(element.textContent.replace(/,/g, '')) || 0;
    const difference = target - current;
    
    if (difference === 0) return;
    
    const duration = 500;
    const steps = 20;
    const stepDuration = duration / steps;
    const increment = difference / steps;
    
    let step = 0;
    const timer = setInterval(() => {
        step++;
        if (step >= steps) {
            element.textContent = formatNumber(target);
            clearInterval(timer);
        } else {
            const value = Math.round(current + (increment * step));
            element.textContent = formatNumber(value);
        }
    }, stepDuration);
}

// ============================================
// Update Leaderboard
// ============================================
function updateLeaderboard(leaderboard) {
    if (!elements.leaderboard || !leaderboard) return;
    
    if (leaderboard.length === 0) {
        elements.leaderboard.innerHTML = '<div class="loading">No data available</div>';
        return;
    }
    
    elements.leaderboard.innerHTML = leaderboard
        .slice(0, 10)
        .map((user, index) => {
            const rankClass = index === 0 ? 'gold' : index === 1 ? 'silver' : index === 2 ? 'bronze' : '';
            const rankDisplay = index < 3 ? ['🥇', '🥈', '🥉'][index] : `${index + 1}`;
            
            return `
                <div class="leaderboard-item">
                    <div class="leaderboard-rank">
                        <span class="rank-number ${rankClass}">${rankDisplay}</span>
                        <span class="leaderboard-name">${escapeHtml(user.name || 'Anonymous')}</span>
                    </div>
                    <span class="leaderboard-points">${formatNumber(user.points)} pts</span>
                </div>
            `;
        })
        .join('');
}

// ============================================
// Handle Claim
// ============================================
async function handleClaim(e) {
    e.preventDefault();
    
    // Rate limiting
    const now = Date.now();
    if (now - state.lastClaimTime < 2000) {
        showAlert('warning', 'Please wait a moment before trying again.');
        return;
    }
    
    // Validate input
    if (!validateInput()) {
        showAlert('error', `Discord ID must be ${CONFIG.MIN_ID_LENGTH}-${CONFIG.MAX_ID_LENGTH} digits.`);
        return;
    }
    
    const userId = elements.userId.value.trim();
    
    // Save Discord ID
    localStorage.setItem('discordId', userId);
    
    // Update UI
    setLoadingState(true);
    hideAlerts();
    
    try {
        const response = await fetch(`${CONFIG.API_BASE}/daily`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ userId })
        });
        
        const data = await response.json();
        
        if (response.ok) {
            handleClaimSuccess(data);
        } else {
            handleClaimError(data, response.status);
        }
        
    } catch (error) {
        console.error('Claim error:', error);
        showAlert('error', 'Connection failed. Please check your internet and try again.');
    } finally {
        setLoadingState(false);
        state.lastClaimTime = now;
    }
}

// ============================================
// Handle Claim Success
// ============================================
function handleClaimSuccess(data) {
    // Show success state
    elements.claimButton.classList.add('success');
    elements.buttonText.textContent = '✓ Claimed Successfully!';
    
    // Simple success bounce
    elements.claimButton.style.animation = 'bounce 0.5s';
    setTimeout(() => elements.claimButton.style.animation = '', 500);
    
    // Show success message
    showAlert('success', `You received ${data.points} points! Balance: ${formatNumber(data.balance)} points`);
    
    // Update balance
    if (elements.balanceBox && elements.balanceValue) {
        elements.balanceBox.classList.remove('hidden');
        elements.balanceValue.textContent = `${formatNumber(data.balance)} points`;
        localStorage.setItem('lastBalance', data.balance);
    }
    
    // Start cooldown
    if (data.next) {
        const nextClaim = new Date(data.next);
        localStorage.setItem('lastClaimTime', Date.now().toString());
        startCooldownTimer(nextClaim);
    }
    
    // Reset button after delay
    setTimeout(() => {
        elements.claimButton.classList.remove('success');
        elements.buttonText.textContent = 'Already Claimed Today';
        elements.claimButton.disabled = true;
    }, 3000);
    
    // Update stats
    updateStatus();
}

// ============================================
// Handle Claim Error
// ============================================
function handleClaimError(data, statusCode) {
    // Show error state
    elements.claimButton.classList.add('error');
    elements.buttonText.textContent = '✗ Claim Failed';
    
    setTimeout(() => {
        elements.claimButton.classList.remove('error');
        elements.buttonText.textContent = 'Claim Daily Points';
    }, 3000);
    
    // Handle specific errors
    const error = data.error || 'Unknown error occurred';
    
    if (error.includes('Already claimed')) {
        showAlert('warning', `Already claimed. Next claim: ${data.timeLeft || 'in 24 hours'}`);
        if (data.balance) {
            elements.balanceBox.classList.remove('hidden');
            elements.balanceValue.textContent = `${formatNumber(data.balance)} points`;
            localStorage.setItem('lastBalance', data.balance);
        }
        if (data.nextClaim) {
            startCooldownTimer(new Date(data.nextClaim));
        }
    } else if (statusCode === 400) {
        showAlert('error', 'Invalid Discord ID. Please check and try again.');
    } else if (statusCode === 403) {
        showAlert('error', 'Account restricted. Contact support if this is an error.');
    } else if (statusCode === 429) {
        showAlert('warning', `Too many requests. Wait ${data.retryAfter || 'a moment'}.`);
    } else {
        showAlert('error', error);
    }
}

// ============================================
// Show Alert
// ============================================
function showAlert(type, message) {
    if (!elements.alertBox) return;
    
    const icons = {
        info: 'ℹ️',
        success: '✅',
        warning: '⚠️',
        error: '❌'
    };
    
    elements.alertBox.className = `alert alert-${type}`;
    elements.alertBox.innerHTML = `
        <span class="alert-icon">${icons[type]}</span>
        <div class="alert-content">
            <p>${message}</p>
        </div>
    `;
    
    elements.alertBox.classList.remove('hidden');
}

// ============================================
// Hide Alerts
// ============================================
function hideAlerts() {
    if (elements.alertBox) {
        elements.alertBox.classList.add('hidden');
    }
}

// ============================================
// Set Loading State
// ============================================
function setLoadingState(loading) {
    if (!elements.claimButton) return;
    
    elements.claimButton.disabled = loading;
    
    if (loading) {
        elements.spinner.classList.remove('hidden');
        elements.buttonText.textContent = 'Claiming...';
    } else {
        elements.spinner.classList.add('hidden');
        elements.buttonText.textContent = 'Claim Daily Points';
    }
}

// ============================================
// Start Cooldown Timer
// ============================================
function startCooldownTimer(nextClaimTime) {
    // Clear existing timer
    if (state.cooldownTimer) {
        clearInterval(state.cooldownTimer);
    }
    
    // Show timer box
    if (elements.timerBox) {
        elements.timerBox.classList.remove('hidden');
    }
    
    // Update timer function
    const updateTimer = () => {
        const now = Date.now();
        const remaining = nextClaimTime.getTime() - now;
        
        if (remaining <= 0) {
            // Cooldown finished
            if (state.cooldownTimer) {
                clearInterval(state.cooldownTimer);
                state.cooldownTimer = null;
            }
            
            elements.timerBox.classList.add('hidden');
            elements.claimButton.disabled = false;
            elements.buttonText.textContent = 'Claim Daily Points';
            
            localStorage.removeItem('lastClaimTime');
            return;
        }
        
        // Calculate time parts
        const hours = Math.floor(remaining / 3600000);
        const minutes = Math.floor((remaining % 3600000) / 60000);
        const seconds = Math.floor((remaining % 60000) / 1000);
        
        // Update display
        if (elements.timerValue) {
            elements.timerValue.textContent = 
                `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
        }
    };
    
    // Start timer
    updateTimer();
    state.cooldownTimer = setInterval(updateTimer, 1000);
}

// ============================================
// Check Cooldown
// ============================================
function checkCooldown() {
    if (!state.lastClaimTime) return;
    
    const now = Date.now();
    const elapsed = now - state.lastClaimTime;
    
    if (elapsed < CONFIG.COOLDOWN_DURATION) {
        // Still in cooldown
        const nextClaim = new Date(state.lastClaimTime + CONFIG.COOLDOWN_DURATION);
        startCooldownTimer(nextClaim);
        
        if (elements.claimButton) {
            elements.claimButton.disabled = true;
            elements.buttonText.textContent = 'Already Claimed Today';
        }
    } else {
        // Cooldown expired
        localStorage.removeItem('lastClaimTime');
    }
}

// ============================================
// Utility Functions
// ============================================
function formatNumber(num) {
    return new Intl.NumberFormat().format(num);
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// ============================================
// Cleanup on page unload
// ============================================
window.addEventListener('beforeunload', () => {
    if (state.cooldownTimer) {
        clearInterval(state.cooldownTimer);
    }
    if (state.updateInterval) {
        clearInterval(state.updateInterval);
    }
});