// Bubble Bot - Clean UI Feedback (No Alerts)
// Simple, clean, no duplicate messages

// ============================================
// Configuration
// ============================================
const CONFIG = {
    API_BASE: window.location.hostname === 'localhost' 
        ? 'http://localhost:3000/api' 
        : '/api',
    UPDATE_INTERVAL: 30000,
    COOLDOWN_DURATION: 86400000, // 24 hours
    MIN_ID_LENGTH: 17,
    MAX_ID_LENGTH: 20
};

// ============================================
// State Management
// ============================================
const state = {
    isOnline: false,
    cooldownTimer: null,
    updateInterval: null,
    lastClaimTime: 0,
    isProcessing: false
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
    
    // UI Feedback (no alerts)
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
    
    // Hide info box after loading
    if (elements.alertBox && !lastClaim) {
        // Keep info box visible only for first-time users
        elements.alertBox.classList.remove('hidden');
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
    
    // Update character count and input state
    if (elements.charCount) {
        if (length === 0) {
            elements.charCount.textContent = `${CONFIG.MIN_ID_LENGTH}-${CONFIG.MAX_ID_LENGTH} digits`;
            elements.charCount.style.color = 'var(--text-muted)';
            input.classList.remove('error', 'success');
        } else if (length >= CONFIG.MIN_ID_LENGTH && length <= CONFIG.MAX_ID_LENGTH) {
            elements.charCount.textContent = `✓ Valid (${length} digits)`;
            elements.charCount.style.color = 'var(--success)';
            input.classList.remove('error');
            input.classList.add('success');
        } else if (length < CONFIG.MIN_ID_LENGTH) {
            elements.charCount.textContent = `${CONFIG.MIN_ID_LENGTH - length} more digits needed`;
            elements.charCount.style.color = 'var(--warning)';
            input.classList.add('error');
            input.classList.remove('success');
        } else {
            elements.charCount.textContent = `Too long! Max ${CONFIG.MAX_ID_LENGTH} digits`;
            elements.charCount.style.color = 'var(--danger)';
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
        .slice(0, 7)
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
    
    // Prevent double submission
    if (state.isProcessing) {
        return;
    }
    
    // Validate input
    if (!validateInput()) {
        // Just shake the input, no alert
        elements.userId.focus();
        elements.userId.style.animation = 'errorShake 0.5s';
        setTimeout(() => elements.userId.style.animation = '', 500);
        return;
    }
    
    const userId = elements.userId.value.trim();
    
    // Save Discord ID
    localStorage.setItem('discordId', userId);
    
    // Set processing state
    state.isProcessing = true;
    setLoadingState(true);
    
    // Hide info box when claiming
    if (elements.alertBox) {
        elements.alertBox.classList.add('hidden');
    }
    
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
        setButtonState('error');
    } finally {
        state.isProcessing = false;
        setLoadingState(false);
    }
}

// ============================================
// Handle Claim Success
// ============================================
function handleClaimSuccess(data) {
    // Hide info box
    if (elements.alertBox) {
        elements.alertBox.classList.add('hidden');
    }
    
    // Show SUCCESS message in timer box
    if (elements.timerBox) {
        elements.timerBox.classList.remove('hidden');
        elements.timerBox.style.background = 'linear-gradient(135deg, rgba(16, 185, 129, 0.2), rgba(5, 150, 105, 0.1))';
        elements.timerBox.style.borderColor = 'rgba(16, 185, 129, 0.5)';
        
        elements.timerBox.innerHTML = `
            <span style="font-size: 2.5rem;">✅</span>
            <div class="timer-content">
                <span style="color: var(--success); font-size: 1.25rem; font-weight: 700;">SUCCESSFULLY CLAIMED!</span>
                <span style="display: block; color: var(--text-primary); font-size: 1rem; margin-top: 0.5rem;">
                    You got: <strong style="color: var(--success);">+${data.points} points</strong><br>
                    Your balance: <strong style="color: var(--success);">${formatNumber(data.balance)} points</strong><br>
                    Next claim in: <strong style="color: var(--warning);">24 hours</strong>
                </span>
            </div>
        `;
    }
    
    // Update balance
    localStorage.setItem('lastBalance', data.balance);
    
    // Update button
    setButtonState('success');
    
    // After 5 seconds, switch to countdown timer
    setTimeout(() => {
        if (data.next) {
            const nextClaim = new Date(data.next);
            localStorage.setItem('lastClaimTime', Date.now().toString());
            startCooldownTimer(nextClaim);
        }
    }, 5000);
    
    // Update stats
    setTimeout(updateStatus, 1000);
}

// ============================================
// Handle Claim Error
// ============================================
function handleClaimError(data, statusCode) {
    const error = data.error || 'Unknown error occurred';
    
    // Hide info box
    if (elements.alertBox) {
        elements.alertBox.classList.add('hidden');
    }
    
    if (statusCode === 429 && error.includes('Already claimed')) {
        // ALREADY CLAIMED TODAY - Show clear message
        if (elements.timerBox) {
            elements.timerBox.classList.remove('hidden');
            elements.timerBox.style.background = 'linear-gradient(135deg, rgba(245, 158, 11, 0.2), rgba(251, 191, 36, 0.1))';
            elements.timerBox.style.borderColor = 'rgba(245, 158, 11, 0.5)';
            
            elements.timerBox.innerHTML = `
                <span style="font-size: 2.5rem;">⚠️</span>
                <div class="timer-content">
                    <span style="color: var(--warning); font-size: 1.25rem; font-weight: 700;">ALREADY CLAIMED TODAY!</span>
                    <span style="display: block; color: var(--text-primary); font-size: 1rem; margin-top: 0.5rem;">
                        Your balance: <strong>${formatNumber(data.balance || 0)} points</strong><br>
                        Time remaining: <strong style="color: var(--warning);">${data.timeLeft || '24 hours'}</strong><br>
                        Come back tomorrow to claim again!
                    </span>
                </div>
            `;
        }
        
        // Update balance if provided
        if (data.balance !== undefined) {
            localStorage.setItem('lastBalance', data.balance);
        }
        
        // Start countdown after 3 seconds
        if (data.nextClaim) {
            setTimeout(() => {
                startCooldownTimer(new Date(data.nextClaim));
            }, 3000);
        }
        
        setButtonState('disabled');
        
    } else if (statusCode === 429) {
        // RATE LIMITED - Too fast
        if (elements.timerBox) {
            elements.timerBox.classList.remove('hidden');
            elements.timerBox.style.background = 'linear-gradient(135deg, rgba(245, 158, 11, 0.2), rgba(251, 191, 36, 0.1))';
            elements.timerBox.style.borderColor = 'rgba(245, 158, 11, 0.5)';
            
            elements.timerBox.innerHTML = `
                <span style="font-size: 2.5rem;">⏱️</span>
                <div class="timer-content">
                    <span style="color: var(--warning); font-size: 1.25rem; font-weight: 700;">TOO FAST!</span>
                    <span style="display: block; color: var(--text-primary); font-size: 1rem; margin-top: 0.5rem;">
                        Please wait <strong>${data.retryAfter || 2} seconds</strong> and try again.<br>
                        Slow down to avoid being blocked.
                    </span>
                </div>
            `;
            
            // Hide after retry time
            setTimeout(() => {
                elements.timerBox.classList.add('hidden');
            }, (data.retryAfter || 2) * 1000);
        }
        
        setButtonState('rate-limited');
        
    } else if (statusCode === 400) {
        // INVALID DISCORD ID
        if (elements.timerBox) {
            elements.timerBox.classList.remove('hidden');
            elements.timerBox.style.background = 'linear-gradient(135deg, rgba(239, 68, 68, 0.2), rgba(220, 38, 38, 0.1))';
            elements.timerBox.style.borderColor = 'rgba(239, 68, 68, 0.5)';
            
            elements.timerBox.innerHTML = `
                <span style="font-size: 2.5rem;">❌</span>
                <div class="timer-content">
                    <span style="color: var(--danger); font-size: 1.25rem; font-weight: 700;">INVALID DISCORD ID!</span>
                    <span style="display: block; color: var(--text-primary); font-size: 1rem; margin-top: 0.5rem;">
                        Discord ID must be <strong>17-20 digits</strong> only.<br>
                        Example: <code style="background: var(--bg-secondary); padding: 2px 6px; border-radius: 4px;">823456789012345678</code>
                    </span>
                </div>
            `;
            
            // Hide after 5 seconds
            setTimeout(() => {
                elements.timerBox.classList.add('hidden');
            }, 5000);
        }
        
        elements.userId.style.animation = 'errorShake 0.5s';
        setTimeout(() => elements.userId.style.animation = '', 500);
        setButtonState('error');
        
    } else if (statusCode === 403) {
        // ACCOUNT BLACKLISTED
        if (elements.timerBox) {
            elements.timerBox.classList.remove('hidden');
            elements.timerBox.style.background = 'linear-gradient(135deg, rgba(239, 68, 68, 0.2), rgba(220, 38, 38, 0.1))';
            elements.timerBox.style.borderColor = 'rgba(239, 68, 68, 0.5)';
            
            elements.timerBox.innerHTML = `
                <span style="font-size: 2.5rem;">🚫</span>
                <div class="timer-content">
                    <span style="color: var(--danger); font-size: 1.25rem; font-weight: 700;">ACCOUNT BLACKLISTED!</span>
                    <span style="display: block; color: var(--text-primary); font-size: 1rem; margin-top: 0.5rem;">
                        Your account has been restricted from claiming points.<br>
                        Contact support on Discord if you think this is a mistake.
                    </span>
                </div>
            `;
        }
        
        setButtonState('error');
        
    } else if (statusCode === 500 || statusCode === 503) {
        // SERVER ERROR
        if (elements.timerBox) {
            elements.timerBox.classList.remove('hidden');
            elements.timerBox.style.background = 'linear-gradient(135deg, rgba(239, 68, 68, 0.2), rgba(220, 38, 38, 0.1))';
            elements.timerBox.style.borderColor = 'rgba(239, 68, 68, 0.5)';
            
            elements.timerBox.innerHTML = `
                <span style="font-size: 2.5rem;">⚠️</span>
                <div class="timer-content">
                    <span style="color: var(--danger); font-size: 1.25rem; font-weight: 700;">SERVER ERROR!</span>
                    <span style="display: block; color: var(--text-primary); font-size: 1rem; margin-top: 0.5rem;">
                        The service is temporarily unavailable.<br>
                        Please try again in a few minutes.
                    </span>
                </div>
            `;
            
            // Hide after 5 seconds
            setTimeout(() => {
                elements.timerBox.classList.add('hidden');
            }, 5000);
        }
        
        setButtonState('error');
        
    } else {
        // GENERIC ERROR
        if (elements.timerBox) {
            elements.timerBox.classList.remove('hidden');
            elements.timerBox.style.background = 'linear-gradient(135deg, rgba(239, 68, 68, 0.2), rgba(220, 38, 38, 0.1))';
            elements.timerBox.style.borderColor = 'rgba(239, 68, 68, 0.5)';
            
            elements.timerBox.innerHTML = `
                <span style="font-size: 2.5rem;">❌</span>
                <div class="timer-content">
                    <span style="color: var(--danger); font-size: 1.25rem; font-weight: 700;">ERROR!</span>
                    <span style="display: block; color: var(--text-primary); font-size: 1rem; margin-top: 0.5rem;">
                        ${error}<br>
                        Please try again.
                    </span>
                </div>
            `;
            
            // Hide after 5 seconds
            setTimeout(() => {
                elements.timerBox.classList.add('hidden');
            }, 5000);
        }
        
        setButtonState('error');
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
        elements.buttonText.textContent = 'Processing...';
        elements.claimButton.style.cursor = 'wait';
    } else {
        elements.spinner.classList.add('hidden');
        elements.claimButton.style.cursor = 'pointer';
    }
}

// ============================================
// Set Button State
// ============================================
function setButtonState(state) {
    if (!elements.claimButton) return;
    
    // Remove all state classes
    elements.claimButton.classList.remove('success', 'error');
    
    switch(state) {
        case 'success':
            elements.claimButton.classList.add('success');
            elements.buttonText.textContent = '✅ Claimed Successfully!';
            elements.claimButton.disabled = true;
            
            // Reset after 3 seconds
            setTimeout(() => {
                elements.claimButton.classList.remove('success');
                elements.buttonText.textContent = 'Already Claimed Today';
            }, 3000);
            break;
            
        case 'rate-limited':
            elements.claimButton.classList.add('error');
            elements.buttonText.textContent = '⏱️ Too Fast! Wait 2s';
            
            // Reset after 2 seconds
            setTimeout(() => {
                elements.claimButton.classList.remove('error');
                elements.buttonText.textContent = 'Claim Daily Points';
                elements.claimButton.disabled = false;
            }, 2000);
            break;
            
        case 'error':
            elements.claimButton.classList.add('error');
            elements.buttonText.textContent = '❌ Try Again';
            
            // Reset after 3 seconds
            setTimeout(() => {
                elements.claimButton.classList.remove('error');
                elements.buttonText.textContent = 'Claim Daily Points';
                elements.claimButton.disabled = false;
            }, 3000);
            break;
            
        case 'disabled':
            elements.buttonText.textContent = 'Already Claimed Today';
            elements.claimButton.disabled = true;
            break;
            
        default:
            elements.buttonText.textContent = 'Claim Daily Points';
            elements.claimButton.disabled = false;
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
        elements.timerBox.style.animation = 'slideDown 0.3s ease-out';
    }
    
    // Disable claim button
    elements.claimButton.disabled = true;
    elements.buttonText.textContent = 'Already Claimed Today';
    
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
            
            // Hide timer
            elements.timerBox.classList.add('hidden');
            
            // Enable button
            elements.claimButton.disabled = false;
            elements.buttonText.textContent = '🎉 Claim Available!';
            elements.claimButton.classList.add('success');
            
            // Clear saved time
            localStorage.removeItem('lastClaimTime');
            
            // Play a subtle sound if available
            try {
                const audio = new Audio('data:audio/wav;base64,UklGRigAAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQQAAACAAABgAA==');
                audio.volume = 0.3;
                audio.play();
            } catch(e) {}
            
            // Reset button after animation
            setTimeout(() => {
                elements.claimButton.classList.remove('success');
                elements.buttonText.textContent = 'Claim Daily Points';
            }, 3000);
            
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
    
    // Start timer immediately
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
        
        // Hide info box if in cooldown
        if (elements.alertBox) {
            elements.alertBox.classList.add('hidden');
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

// ============================================
// Page Visibility API - Pause/Resume timers
// ============================================
document.addEventListener('visibilitychange', () => {
    if (document.hidden) {
        // Page is hidden, clear update interval to save resources
        if (state.updateInterval) {
            clearInterval(state.updateInterval);
            state.updateInterval = null;
        }
    } else {
        // Page is visible again, restart updates
        if (!state.updateInterval) {
            updateStatus();
            state.updateInterval = setInterval(updateStatus, CONFIG.UPDATE_INTERVAL);
        }
    }
});

// ============================================
// Debug Mode (only in development)
// ============================================
if (window.location.hostname === 'localhost') {
    window.debugReset = () => {
        localStorage.clear();
        location.reload();
        console.log('Debug: All data cleared');
    };
    
    window.debugClaim = () => {
        localStorage.removeItem('lastClaimTime');
        location.reload();
        console.log('Debug: Claim timer reset');
    };
    
    console.log('Debug mode enabled. Use debugReset() or debugClaim()');
}