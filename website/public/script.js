// Cookie Bot - Main Application Script

// State Management
const AppState = {
    isOnline: false,
    userData: null,
    rateLimitActive: false,
    lastClaimAttempt: 0,
    attemptCount: 0
};

// Configuration - Update this with your actual API endpoint
const Config = {
    API_BASE: '', // Will be set based on environment
    UPDATE_INTERVAL: 30000,
    MAX_ATTEMPTS: 3,
    RATE_LIMIT_WINDOW: 60000,
    MIN_REQUEST_INTERVAL: 2000
};

// Set API base URL based on environment
if (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') {
    Config.API_BASE = 'http://localhost:3000/api';
} else {
    // Update this with your Vercel app URL
    Config.API_BASE = window.location.origin + '/api';
}

// Initialize Application
document.addEventListener('DOMContentLoaded', function() {
    console.log('Initializing Cookie Bot...');
    initializeApp();
});

// Application Initialization
async function initializeApp() {
    try {
        // Hide honeypot field
        const honeypot = document.getElementById('hpt');
        if (honeypot) {
            honeypot.style.display = 'none';
        }

        // Load saved data
        loadSavedData();
        
        // Initial status update
        await updateBotStatus();
        
        // Setup event listeners
        setupEventListeners();
        
        // Start auto update
        startAutoUpdate();
        
        // Show content
        showContent();
        
    } catch (error) {
        console.error('Initialization error:', error);
        showOfflineStatus();
    }
}

// Show content after loading
function showContent() {
    const loading = document.querySelector('.loading');
    const content = document.getElementById('content');
    
    if (loading) {
        loading.style.display = 'none';
    }
    
    if (content) {
        content.style.display = 'block';
    }
}

// Show offline status
function showOfflineStatus() {
    showContent();
    updateStatusDisplay({ 
        online: false,
        totalUsers: 0,
        totalServers: 0,
        totalCookies: 0,
        lastActivity: null,
        leaderboard: []
    });
}

// Load Saved User Data
function loadSavedData() {
    try {
        const savedId = localStorage.getItem('discordId');
        const savedUsername = localStorage.getItem('username');
        
        if (savedId && isValidDiscordId(savedId)) {
            document.getElementById('discordId').value = savedId;
        }
        
        if (savedUsername && isValidUsername(savedUsername)) {
            document.getElementById('username').value = savedUsername;
        }
    } catch (e) {
        console.error('Failed to load saved data:', e);
    }
}

// Save User Data
function saveUserData(userId, username) {
    try {
        localStorage.setItem('discordId', userId);
        localStorage.setItem('username', username);
    } catch (e) {
        console.error('Failed to save user data:', e);
    }
}

// Validation Functions
function isValidDiscordId(id) {
    return /^[0-9]{17,20}$/.test(id);
}

function isValidUsername(username) {
    return username && username.length >= 2 && username.length <= 32 && 
           /^[a-zA-Z0-9_.-]+$/.test(username);
}

// Update Bot Status
async function updateBotStatus() {
    try {
        console.log('Fetching status from:', Config.API_BASE + '/status');
        
        const response = await fetch(`${Config.API_BASE}/status`, {
            method: 'GET',
            headers: {
                'Accept': 'application/json'
            }
        });
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const data = await response.json();
        console.log('Status data received:', data);
        
        updateStatusDisplay(data);
        updateLeaderboard(data.leaderboard || []);
        
    } catch (error) {
        console.error('Failed to update status:', error);
        showOfflineStatus();
    }
}

// Update Status Display
function updateStatusDisplay(data) {
    const statusDot = document.getElementById('statusDot');
    const statusText = document.getElementById('statusText');
    
    AppState.isOnline = data.online || false;
    
    if (statusDot && statusText) {
        if (AppState.isOnline) {
            statusDot.classList.add('online');
            statusDot.classList.remove('offline');
            statusText.textContent = 'ONLINE';
            statusText.style.color = '#3BA55C';
        } else {
            statusDot.classList.remove('online');
            statusDot.classList.add('offline');
            statusText.textContent = 'OFFLINE';
            statusText.style.color = '#ED4245';
        }
    }
    
    // Update stats
    const totalUsers = document.getElementById('totalUsers');
    const totalServers = document.getElementById('totalServers');
    const totalCookies = document.getElementById('totalCookies');
    const lastActivity = document.getElementById('lastActivity');
    
    if (totalUsers) totalUsers.textContent = formatNumber(data.totalUsers || 0);
    if (totalServers) totalServers.textContent = formatNumber(data.totalServers || 0);
    if (totalCookies) totalCookies.textContent = formatNumber(data.totalCookies || 0);
    
    if (lastActivity) {
        if (data.lastActivity) {
            lastActivity.textContent = formatTimeAgo(new Date(data.lastActivity));
        } else {
            lastActivity.textContent = 'Unknown';
        }
    }
    
    // Update last update time
    const lastUpdate = document.getElementById('lastUpdate');
    if (lastUpdate) {
        lastUpdate.textContent = `Last updated: ${new Date().toLocaleTimeString()}`;
    }
}

// Update Leaderboard
function updateLeaderboard(leaderboard) {
    const leaderboardDiv = document.getElementById('leaderboard');
    
    if (!leaderboardDiv) return;
    
    if (!leaderboard || leaderboard.length === 0) {
        leaderboardDiv.innerHTML = `
            <div class="leaderboard-loading">
                <p>No leaderboard data available</p>
            </div>
        `;
        return;
    }
    
    leaderboardDiv.innerHTML = '';
    
    leaderboard.slice(0, 10).forEach((user, index) => {
        const item = document.createElement('div');
        item.className = 'leaderboard-item';
        
        const rankClass = index === 0 ? 'gold' : 
                         index === 1 ? 'silver' : 
                         index === 2 ? 'bronze' : '';
        
        const medal = index === 0 ? '🥇' : 
                     index === 1 ? '🥈' : 
                     index === 2 ? '🥉' : `#${index + 1}`;
        
        item.innerHTML = `
            <div class="leaderboard-rank">
                <span class="rank-number ${rankClass}">${medal}</span>
                <span class="leaderboard-user">${escapeHtml(user.username || 'Unknown')}</span>
            </div>
            <span class="leaderboard-points">${formatNumber(user.points || 0)} pts</span>
        `;
        
        leaderboardDiv.appendChild(item);
    });
}

// Setup Event Listeners
function setupEventListeners() {
    // Form submission
    const form = document.getElementById('dailyForm');
    if (form) {
        form.addEventListener('submit', handleDailyClaim);
    }
    
    // Input validation
    const discordIdInput = document.getElementById('discordId');
    const usernameInput = document.getElementById('username');
    
    if (discordIdInput) {
        discordIdInput.addEventListener('input', validateDiscordId);
        discordIdInput.addEventListener('paste', handlePaste);
    }
    
    if (usernameInput) {
        usernameInput.addEventListener('input', validateUsername);
    }
}

// Handle Paste Event
function handlePaste(e) {
    e.preventDefault();
    const paste = (e.clipboardData || window.clipboardData).getData('text');
    const cleaned = paste.replace(/[^0-9]/g, '');
    e.target.value = cleaned.substring(0, 20);
}

// Validate Discord ID
function validateDiscordId(e) {
    const input = e.target;
    const value = input.value;
    const errorSpan = document.getElementById('idError');
    
    // Only allow numbers
    input.value = value.replace(/[^0-9]/g, '');
    
    if (errorSpan) {
        if (input.value && !isValidDiscordId(input.value)) {
            input.classList.add('error');
            errorSpan.textContent = 'Discord ID must be 17-20 digits';
            errorSpan.classList.add('show');
        } else {
            input.classList.remove('error');
            errorSpan.classList.remove('show');
        }
    }
}

// Validate Username
function validateUsername(e) {
    const input = e.target;
    const errorSpan = document.getElementById('usernameError');
    
    if (errorSpan) {
        if (input.value && !isValidUsername(input.value)) {
            input.classList.add('error');
            errorSpan.textContent = 'Username must be 2-32 characters';
            errorSpan.classList.add('show');
        } else {
            input.classList.remove('error');
            errorSpan.classList.remove('show');
        }
    }
}

// Handle Daily Claim
async function handleDailyClaim(e) {
    e.preventDefault();
    
    // Check rate limit
    if (AppState.rateLimitActive) {
        showToast('Please wait before trying again', 'warning');
        return;
    }
    
    // Check minimum interval
    const now = Date.now();
    if (now - AppState.lastClaimAttempt < Config.MIN_REQUEST_INTERVAL) {
        showToast('Too fast! Please wait a moment', 'warning');
        return;
    }
    
    // Check bot status
    if (!AppState.isOnline) {
        showToast('Bot is offline. Please try again later', 'error');
        return;
    }
    
    // Get form data
    const discordId = document.getElementById('discordId').value.trim();
    const username = document.getElementById('username').value.trim();
    const honeypot = document.getElementById('hpt').value;
    
    // Honeypot check
    if (honeypot) {
        console.warn('Bot detected');
        return;
    }
    
    // Validation
    if (!isValidDiscordId(discordId)) {
        showToast('Invalid Discord ID', 'error');
        return;
    }
    
    if (!isValidUsername(username)) {
        showToast('Invalid username', 'error');
        return;
    }
    
    // Update UI
    const button = document.getElementById('claimButton');
    const originalText = button.textContent;
    
    button.disabled = true;
    button.textContent = 'CLAIMING...';
    
    // Save data
    saveUserData(discordId, username);
    
    try {
        AppState.lastClaimAttempt = now;
        AppState.attemptCount++;
        
        console.log('Claiming daily from:', Config.API_BASE + '/daily');
        
        const response = await fetch(`${Config.API_BASE}/daily`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                userId: discordId,
                username: username,
                timestamp: now
            })
        });
        
        const data = await response.json();
        
        if (response.ok) {
            handleClaimSuccess(data, button);
            AppState.attemptCount = 0;
        } else {
            handleClaimError(data, button);
        }
        
    } catch (error) {
        console.error('Claim error:', error);
        showToast('Connection error. Please try again', 'error');
        showResult('error', 'Connection failed', 'Please check your internet connection');
        button.textContent = originalText;
    } finally {
        button.disabled = false;
    }
}

// Handle Claim Success
function handleClaimSuccess(data, button) {
    button.classList.add('success');
    button.textContent = '✅ CLAIMED!';
    
    showToast(`Claimed ${data.points_earned} points!`, 'success');
    
    showResult('success', 
        `🎉 Success!`,
        `+${data.points_earned} POINTS`,
        `New Balance: ${formatNumber(data.new_balance)} points`,
        'Use Discord bot for role bonuses up to 20 points!'
    );
    
    // Reset button after delay
    setTimeout(() => {
        button.classList.remove('success');
        button.textContent = 'CLAIMED TODAY ✓';
    }, 3000);
    
    // Refresh status
    setTimeout(updateBotStatus, 2000);
}

// Handle Claim Error
function handleClaimError(data, button) {
    button.classList.add('error');
    button.textContent = '❌ ERROR';
    
    setTimeout(() => {
        button.classList.remove('error');
        button.textContent = 'CLAIM DAILY POINTS';
    }, 3000);
    
    if (data.error.includes('already claimed') || data.error.includes('Daily already claimed')) {
        showToast('Already claimed today!', 'error');
        showResult('error', 
            '❌ Already Claimed',
            data.error,
            data.timeLeft ? `Time left: ${data.timeLeft}` : '',
            data.nextClaim ? `Next claim: ${new Date(data.nextClaim).toLocaleString()}` : ''
        );
    } else if (data.error.includes('blacklisted')) {
        showToast('You are blacklisted', 'error');
        showResult('error', '🚫 Blacklisted', data.error);
    } else if (data.error.includes('offline')) {
        showToast('Bot is offline', 'error');
        showResult('error', '🔴 Bot Offline', 'Please wait for the bot to come online');
    } else {
        showToast(data.error || 'Claim failed', 'error');
        showResult('error', '❌ Error', data.error || 'Unknown error occurred');
    }
}

// Show Result
function showResult(type, title, ...messages) {
    const resultDiv = document.getElementById('dailyResult');
    
    if (!resultDiv) return;
    
    const resultCard = document.createElement('div');
    resultCard.className = `result-card ${type}`;
    
    let html = `<div class="result-title">${title}</div>`;
    
    messages.forEach(msg => {
        if (msg) {
            if (msg.startsWith('+') && msg.includes('POINTS')) {
                html += `<div class="result-points">${msg}</div>`;
            } else {
                html += `<div class="result-message">${msg}</div>`;
            }
        }
    });
    
    resultCard.innerHTML = html;
    resultDiv.innerHTML = '';
    resultDiv.appendChild(resultCard);
}

// Show Toast Notification
function showToast(message, type = 'info') {
    const container = document.getElementById('toastContainer');
    
    if (!container) return;
    
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    
    const icon = type === 'success' ? '✅' : 
                type === 'error' ? '❌' : 
                type === 'warning' ? '⚠️' : 'ℹ️';
    
    toast.innerHTML = `<span>${icon}</span><span>${message}</span>`;
    container.appendChild(toast);
    
    setTimeout(() => {
        toast.style.opacity = '0';
        setTimeout(() => toast.remove(), 300);
    }, 5000);
}

// Format Number
function formatNumber(num) {
    return new Intl.NumberFormat().format(num);
}

// Format Time Ago
function formatTimeAgo(date) {
    const seconds = Math.floor((new Date() - date) / 1000);
    
    if (seconds < 60) return 'Just now';
    if (seconds < 3600) return Math.floor(seconds / 60) + 'm ago';
    if (seconds < 86400) return Math.floor(seconds / 3600) + 'h ago';
    if (seconds < 604800) return Math.floor(seconds / 86400) + 'd ago';
    return date.toLocaleDateString();
}

// Escape HTML
function escapeHtml(text) {
    const map = {
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#039;'
    };
    return text.replace(/[&<>"']/g, m => map[m]);
}

// Start Auto Update
function startAutoUpdate() {
    setInterval(updateBotStatus, Config.UPDATE_INTERVAL);
}