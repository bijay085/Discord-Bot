// script.js - Cookie Bot Status JavaScript (Updated)

// Utility Functions
function isValidDiscordId(id) {
    return /^\d{17,20}$/.test(id);
}

function isValidUsername(username) {
    return username.length >= 2 && username.length <= 32;
}

function formatTimeAgo(date) {
    const now = new Date();
    const diff = Math.floor((now - date) / 1000);
    
    if (diff < 60) return 'Just now';
    if (diff < 3600) return Math.floor(diff / 60) + 'm ago';
    if (diff < 86400) return Math.floor(diff / 3600) + 'h ago';
    return Math.floor(diff / 86400) + 'd ago';
}

// Toast Notification System
function showToast(message, type = 'info') {
    const existingToast = document.querySelector('.toast');
    if (existingToast) existingToast.remove();
    
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;
    document.body.appendChild(toast);
    
    setTimeout(() => toast.remove(), 5000);
}

// Local Storage Functions
function saveUserInfo() {
    const userId = document.getElementById('discordId').value;
    const username = document.getElementById('username').value;
    if (userId && username) {
        localStorage.setItem('discordId', userId);
        localStorage.setItem('username', username);
    }
}

function loadUserInfo() {
    const savedId = localStorage.getItem('discordId');
    const savedUsername = localStorage.getItem('username');
    if (savedId) document.getElementById('discordId').value = savedId;
    if (savedUsername) document.getElementById('username').value = savedUsername;
}

// Update Status Display
function updateStatusDisplay(data) {
    const statusDot = document.getElementById('statusDot');
    const statusText = document.getElementById('statusText');
    const onlineStatus = document.getElementById('onlineStatus');
    
    if (data.online) {
        statusDot.className = 'status-dot online';
        statusText.textContent = 'ONLINE';
        statusText.style.color = '#4caf50';
        onlineStatus.textContent = '🟢';
        
        // Only show toast on initial load or status change
        if (!window.lastOnlineStatus || window.lastOnlineStatus !== data.online) {
            showToast('Bot is online!', 'success');
        }
    } else {
        statusDot.className = 'status-dot offline';
        statusText.textContent = 'OFFLINE';
        statusText.style.color = '#f44336';
        onlineStatus.textContent = '🔴';
        
        // Show offline toast if status changed
        if (window.lastOnlineStatus === true) {
            showToast('Bot went offline', 'warning');
        }
    }
    
    window.lastOnlineStatus = data.online;
}

// Update Statistics
function updateStatistics(data) {
    document.getElementById('totalUsers').textContent = data.totalUsers?.toLocaleString() || '0';
    document.getElementById('activeUsers').textContent = data.activeUsers?.toLocaleString() || '0';
    document.getElementById('totalServers').textContent = data.totalServers?.toLocaleString() || '0';
    document.getElementById('totalCookies').textContent = data.totalCookies?.toLocaleString() || '0';
    
    if (data.lastSeen) {
        const lastSeen = new Date(data.lastSeen);
        document.getElementById('uptime').textContent = formatTimeAgo(lastSeen);
    }
}

// Update Leaderboard
function updateLeaderboard(data) {
    const leaderboardDiv = document.getElementById('leaderboard');
    
    if (data.leaderboard && data.leaderboard.length > 0) {
        leaderboardDiv.innerHTML = '';
        
        data.leaderboard.forEach((user, index) => {
            const rankClass = index === 0 ? 'gold' : index === 1 ? 'silver' : index === 2 ? 'bronze' : '';
            const medal = index === 0 ? '🥇' : index === 1 ? '🥈' : index === 2 ? '🥉' : '';
            
            const item = document.createElement('div');
            item.className = 'leaderboard-item';
            item.innerHTML = `
                <div style="display: flex; align-items: center; gap: 15px;">
                    <span class="rank ${rankClass}">${medal || '#' + user.rank}</span>
                    <span style="font-weight: bold;">${user.username}</span>
                </div>
                <span style="font-weight: bold; color: #667eea;">${user.points.toLocaleString()} pts</span>
            `;
            
            leaderboardDiv.appendChild(item);
        });
    } else {
        leaderboardDiv.innerHTML = '<p style="text-align: center; color: #999;">No users yet</p>';
    }
}

// Update Recent Activity
function updateRecentActivity(data) {
    const activityDiv = document.getElementById('recentActivity');
    
    if (data.recentActivity && data.recentActivity.length > 0) {
        activityDiv.innerHTML = '<div style="background: #f5f5f5; border-radius: 10px; padding: 15px;">';
        
        data.recentActivity.forEach(activity => {
            const activityItem = document.createElement('div');
            activityItem.style.cssText = 'padding: 10px; background: white; margin: 10px 0; border-radius: 8px; border-left: 3px solid #667eea;';
            activityItem.textContent = '📌 ' + activity;
            activityDiv.firstChild.appendChild(activityItem);
        });
    } else {
        activityDiv.innerHTML = '<p style="text-align: center; color: #999;">No recent activity</p>';
    }
}

// Main Update Function
async function updateStatus() {
    try {
        const response = await fetch('/api/status');
        
        // Check if response is ok
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const data = await response.json();
        
        // Hide loading, show content
        document.getElementById('loading').style.display = 'none';
        document.getElementById('content').style.display = 'block';
        
        // Check if we got valid data
        if (data.error) {
            // Show error state
            updateFailedStatus();
            showToast('Database connection failed', 'error');
            return;
        }
        
        // Update all sections
        updateStatusDisplay(data);
        updateStatistics(data);
        updateLeaderboard(data);
        updateRecentActivity(data);
        
        // Update timestamp
        document.getElementById('lastUpdate').textContent = 'Last updated: ' + new Date().toLocaleTimeString();
        
    } catch (error) {
        console.error('Error fetching status:', error);
        
        // Hide loading if it's still showing
        document.getElementById('loading').style.display = 'none';
        document.getElementById('content').style.display = 'block';
        
        // Update to failed status
        updateFailedStatus();
        showToast('Failed to connect to server', 'error');
    }
}

// Update Failed Status Display
function updateFailedStatus() {
    const statusDot = document.getElementById('statusDot');
    const statusText = document.getElementById('statusText');
    const onlineStatus = document.getElementById('onlineStatus');
    
    statusDot.className = 'status-dot offline';
    statusText.textContent = 'CONNECTION FAILED';
    statusText.style.color = '#f44336';
    onlineStatus.textContent = '⚠️';
    
    // Set all stats to error state
    document.getElementById('totalUsers').textContent = 'N/A';
    document.getElementById('activeUsers').textContent = 'N/A';
    document.getElementById('totalServers').textContent = 'N/A';
    document.getElementById('totalCookies').textContent = 'N/A';
    document.getElementById('uptime').textContent = 'Unknown';
    
    // Show error in leaderboard
    document.getElementById('leaderboard').innerHTML = '<p style="text-align: center; color: #f44336;">⚠️ Unable to load leaderboard</p>';
    
    // Show error in activity
    document.getElementById('recentActivity').innerHTML = '<p style="text-align: center; color: #f44336;">⚠️ Unable to load activity</p>';
    
    // Update timestamp
    document.getElementById('lastUpdate').textContent = 'Connection failed at: ' + new Date().toLocaleTimeString();
}

// Claim Daily Points Function
async function claimDaily() {
    const userIdInput = document.getElementById('discordId');
    const usernameInput = document.getElementById('username');
    const userId = userIdInput.value.trim();
    const username = usernameInput.value.trim();
    const button = document.getElementById('claimButton');
    const resultDiv = document.getElementById('dailyResult');
    
    // Reset error states
    userIdInput.classList.remove('error');
    usernameInput.classList.remove('error');
    
    // Validation
    let hasError = false;
    
    if (!userId) {
        userIdInput.classList.add('error');
        hasError = true;
    } else if (!isValidDiscordId(userId)) {
        userIdInput.classList.add('error');
        showToast('Invalid Discord ID! Must be 17-20 digits.', 'error');
        hasError = true;
    }
    
    if (!username) {
        usernameInput.classList.add('error');
        hasError = true;
    } else if (!isValidUsername(username)) {
        usernameInput.classList.add('error');
        showToast('Username must be 2-32 characters!', 'error');
        hasError = true;
    }
    
    if (hasError) {
        resultDiv.innerHTML = '<div class="daily-result error">⚠️ Please fill in all fields correctly!</div>';
        return;
    }
    
    // Save for next time
    saveUserInfo();
    
    // Disable button and show loading
    button.disabled = true;
    button.textContent = '⏳ CLAIMING...';
    resultDiv.innerHTML = '';
    
    try {
        const response = await fetch('/api/daily', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ userId, username })
        });
        
        const data = await response.json();
        
        if (response.ok) {
            // Success
            button.classList.add('success');
            button.textContent = '✅ CLAIMED!';
            
            resultDiv.innerHTML = `
                <div class="daily-result success">
                    <div>🎉 Success!</div>
                    <div class="points-animation">+${data.points_earned} POINTS</div>
                    <div>New Balance: ${data.new_balance} points</div>
                    <div style="margin-top: 10px; font-size: 12px; opacity: 0.8;">
                        💡 Use Discord bot for role bonuses!
                    </div>
                </div>
            `;
            
            showToast('Daily points claimed successfully!', 'success');
            
            // Reset button after 3 seconds
            setTimeout(() => {
                button.classList.remove('success');
                button.textContent = 'CLAIMED TODAY ✓';
            }, 3000);
            
        } else {
            // Error handling
            if (data.error.includes('Already claimed') || data.error.includes('Daily already claimed')) {
                button.textContent = '❌ ALREADY CLAIMED';
                resultDiv.innerHTML = `
                    <div class="daily-result error">
                        <div>❌ ${data.error}</div>
                        <div>⏰ Time left: ${data.timeLeft}</div>
                        <div>Next claim: ${new Date(data.nextClaim).toLocaleString()}</div>
                    </div>
                `;
                showToast('You already claimed today!', 'error');
                
            } else if (data.error.includes('offline')) {
                button.textContent = '🔴 BOT OFFLINE';
                resultDiv.innerHTML = `
                    <div class="daily-result error">
                        <div>🔴 Bot is offline!</div>
                        <div>Please wait for the bot to come online.</div>
                    </div>
                `;
                showToast('Bot is offline!', 'error');
                button.disabled = false;
                
            } else if (data.error.includes('blacklisted')) {
                button.textContent = '🚫 BLACKLISTED';
                resultDiv.innerHTML = `
                    <div class="daily-result error">
                        <div>🚫 ${data.error}</div>
                    </div>
                `;
                showToast('You are blacklisted!', 'error');
                
            } else {
                button.textContent = '❌ ERROR';
                resultDiv.innerHTML = `
                    <div class="daily-result error">
                        <div>❌ ${data.error}</div>
                    </div>
                `;
                showToast(data.error, 'error');
                button.disabled = false;
            }
        }
        
    } catch (error) {
        console.error('Error:', error);
        button.textContent = 'TRY AGAIN';
        button.disabled = false;
        resultDiv.innerHTML = `
            <div class="daily-result error">
                ❌ Connection error! Please try again.
            </div>
        `;
        showToast('Connection error!', 'error');
    }
}

// Event Listeners
window.addEventListener('DOMContentLoaded', () => {
    loadUserInfo();
    updateStatus();
    
    // Add enter key support
    document.getElementById('discordId').addEventListener('keypress', (e) => {
        if (e.key === 'Enter') claimDaily();
    });
    
    document.getElementById('username').addEventListener('keypress', (e) => {
        if (e.key === 'Enter') claimDaily();
    });
    
    // Add retry button functionality
    document.addEventListener('click', (e) => {
        if (e.target.id === 'retryButton') {
            updateStatus();
        }
    });
});

// Auto-update every 30 seconds
setInterval(updateStatus, 30000);

// Export functions for global access
window.claimDaily = claimDaily;
window.updateStatus = updateStatus;