// Bubble Bot - Enhanced JavaScript with Clear Feedback

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
    cooldownTimer: null,
    currentBalance: 0
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
}

// Cache DOM elements
function cacheElements() {
    // Status elements
    elements.statusDot = document.getElementById('statusDot');
    elements.statusText = document.getElementById('statusText');
    elements.statusBadge = document.getElementById('statusBadge');
    
    // Stats elements
    elements.totalUsers = document.getElementById('totalUsers');
    elements.totalPoints = document.getElementById('totalPoints');
    elements.totalCookies = document.getElementById('totalCookies');
    elements.activeToday = document.getElementById('activeToday');
    
    // Leaderboard
    elements.leaderboard = document.getElementById('leaderboard');
    
    // Claim form elements
    elements.claimForm = document.getElementById('claimForm');
    elements.userId = document.getElementById('userId');
    elements.claimButton = document.getElementById('claimButton');
    elements.buttonIcon = document.getElementById('buttonIcon');
    elements.buttonText = document.getElementById('buttonText');
    elements.spinner = document.getElementById('spinner');
    
    // Feedback elements
    elements.feedbackContainer = document.getElementById('feedbackContainer');
    elements.feedbackMessage = document.getElementById('feedbackMessage');
    elements.cooldownTimer = document.getElementById('cooldownTimer');
    elements.timerDisplay = document.getElementById('timerDisplay');
    
    // Input helper elements
    elements.inputStatus = document.getElementById('inputStatus');
    elements.charCount = document.getElementById('charCount');
    
    // Balance display
    elements.balanceDisplay = document.getElementById('balanceDisplay');
    elements.balanceValue = document.getElementById('balanceValue');
}

// Load saved Discord ID
function loadSavedId() {
    const savedId = localStorage.getItem('discordId');
    if (savedId && elements.userId) {
        elements.userId.value = savedId;
        updateCharCount();
        validateId(savedId);
    }
}

// Setup event listeners
function setupEventListeners() {
    // Form submission
    if (elements.claimForm) {
        elements.claimForm.addEventListener('submit', handleClaim);
    }
    
    // Discord ID input validation
    if (elements.userId) {
        elements.userId.addEventListener('input', (e) => {
            // Only allow numbers
            e.target.value = e.target.value.replace(/\D/g, '');
            updateCharCount();
            validateId(e.target.value);
        });
        
        elements.userId.addEventListener('paste', (e) => {
            setTimeout(() => {
                e.target.value = e.target.value.replace(/\D/g, '');
                updateCharCount();
                validateId(e.target.value);
            }, 0);
        });
    }
}

// Update character count display
function updateCharCount() {
    if (elements.charCount && elements.userId) {
        const length = elements.userId.value.length;
        elements.charCount.textContent = `${length}/15-25`;
        
        if (length >= 15 && length <= 25) {
            elements.charCount.style.color = 'var(--accent-green)';
        } else if (length > 0) {
            elements.charCount.style.color = 'var(--accent-orange)';
        } else {
            elements.charCount.style.color = 'var(--text-muted)';
        }
    }
}

// Validate Discord ID
function validateId(id) {
    const isValid = /^[0-9]{15,25}$/.test(id);
    
    if (elements.userId) {
        if (id.length === 0) {
            elements.userId.classList.remove('error', 'success');
            elements.inputStatus.textContent = '';
            elements.inputStatus.className = 'input-status';
        } else if (isValid) {
            elements.userId.classList.remove('error');
            elements.userId.classList.add('success');
            elements.inputStatus.textContent = '✓ Valid Discord ID format';
            elements.inputStatus.className = 'input-status valid';
        } else {
            elements.userId.classList.add('error');
            elements.userId.classList.remove('success');
            if (id.length < 15) {
                elements.inputStatus.textContent = `Need ${15 - id.length} more digits`;
            } else if (id.length > 25) {
                elements.inputStatus.textContent = `Too many digits (max 25)`;
            } else {
                elements.inputStatus.textContent = '✗ Invalid ID format';
            }
            elements.inputStatus.className = 'input-status invalid';
        }
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
        elements.statusText.textContent = state.isOnline ? 'BOT ONLINE' : 'BOT OFFLINE';
    }
    
    // Stats with animation
    if (data.stats) {
        animateNumber('totalUsers', data.stats.users);
        animateNumber('totalPoints', data.stats.points);
        animateNumber('totalCookies', data.stats.cookies);
        animateNumber('activeToday', data.stats.active);
    }
}

// Animate number changes
function animateNumber(elementId, targetValue) {
    const element = elements[elementId];
    if (!element) return;
    
    const currentValue = parseInt(element.textContent.replace(/,/g, '')) || 0;
    const increment = Math.ceil((targetValue - currentValue) / 20);
    let current = currentValue;
    
    const timer = setInterval(() => {
        current += increment;
        if ((increment > 0 && current >= targetValue) || 
            (increment < 0 && current <= targetValue)) {
            current = targetValue;
            clearInterval(timer);
        }
        element.textContent = formatNumber(current);
    }, 50);
}

// Set offline status
function setOfflineStatus() {
    state.isOnline = false;
    if (elements.statusBadge && elements.statusDot && elements.statusText) {
        elements.statusBadge.className = 'status-badge offline';
        elements.statusDot.className = 'status-dot offline';
        elements.statusText.textContent = 'BOT OFFLINE';
    }
}

// Update leaderboard
function updateLeaderboard(users) {
    if (!elements.leaderboard) return;
    
    if (!users.length) {
        elements.leaderboard.innerHTML = `
            <div class="leaderboard-loading">
                <p>No leaderboard data available yet</p>
            </div>
        `;
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
        showFeedback('warning', '⚡', 'Slow Down!', 'Please wait a moment before trying again.');
        return;
    }
    
    const userId = elements.userId.value.trim();
    
    if (!validateId(userId)) {
        showFeedback('error', '❌', 'Invalid Discord ID', 
            `Discord IDs must be 15-25 digits long. Your ID has ${userId.length} digits.`);
        return;
    }
    
    // Save ID
    localStorage.setItem('discordId', userId);
    state.lastClaim = now;
    
    // UI state
    setLoadingState(true);
    hideFeedback();
    
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
            handleClaimError(data, response.status);
        }
    } catch (error) {
        console.error('Claim error:', error);
        showFeedback('error', '🔌', 'Connection Error', 
            'Unable to connect to the server. Please check your internet connection and try again.');
    } finally {
        setLoadingState(false);
    }
}

// Set loading state
function setLoadingState(loading) {
    const button = elements.claimButton;
    if (button) {
        button.disabled = loading;
        
        if (loading) {
            elements.buttonIcon.classList.add('hidden');
            elements.spinner.classList.remove('hidden');
            elements.buttonText.textContent = 'CLAIMING REWARD...';
        } else {
            elements.buttonIcon.classList.remove('hidden');
            elements.spinner.classList.add('hidden');
            elements.buttonText.textContent = 'CLAIM DAILY REWARD';
        }
    }
}

// Handle successful claim
function handleClaimSuccess(data) {
    // Update button state
    const button = elements.claimButton;
    if (button) {
        button.classList.add('success');
        elements.buttonIcon.textContent = '✅';
        elements.buttonText.textContent = 'REWARD CLAIMED!';
    }
    
    // Show success feedback
    showFeedback('success', '🎉', 'Points Claimed Successfully!', 
        `You've received <strong>${data.points} points</strong>! Your new balance is <strong>${formatNumber(data.balance)} points</strong>.`);
    
    // Update balance display
    state.currentBalance = data.balance;
    updateBalanceDisplay(data.balance);
    
    // Start cooldown timer
    if (data.next) {
        startCooldownTimer(new Date(data.next));
    }
    
    // Reset button after delay
    setTimeout(() => {
        if (button) {
            button.classList.remove('success');
            elements.buttonIcon.textContent = '✓';
            elements.buttonText.textContent = 'CLAIMED TODAY';
            button.disabled = true;
        }
        updateStatus();
    }, 3000);
}

// Handle claim error
function handleClaimError(data, statusCode) {
    // Update button state
    const button = elements.claimButton;
    if (button) {
        button.classList.add('error');
        elements.buttonIcon.textContent = '❌';
        elements.buttonText.textContent = 'CLAIM FAILED';
    }
    
    setTimeout(() => {
        if (button) {
            button.classList.remove('error');
            elements.buttonIcon.textContent = '💎';
            elements.buttonText.textContent = 'CLAIM DAILY REWARD';
        }
    }, 3000);
    
    const error = data.error || 'Unknown error';
    
    // Handle specific error cases
    if (error.includes('Already claimed')) {
        showFeedback('warning', '⏰', 'Already Claimed Today', 
            `You've already claimed your daily points. Come back in <strong>${data.timeLeft || '24 hours'}</strong>. Your current balance: <strong>${formatNumber(data.balance)} points</strong>.`);
        
        if (data.nextClaim) {
            startCooldownTimer(new Date(data.nextClaim));
        }
        updateBalanceDisplay(data.balance);
    } else if (error.includes('blacklisted')) {
        showFeedback('error', '🚫', 'Account Restricted', 
            'Your account has been temporarily restricted. Please contact support if you believe this is an error.');
    } else if (statusCode === 400) {
        showFeedback('error', '⚠️', 'Invalid Discord ID', 
            'The Discord ID you entered is not valid. Please check and try again.');
    } else if (statusCode === 429) {
        showFeedback('warning', '⚡', 'Too Many Requests', 
            `Please wait ${data.retryAfter || 'a moment'} before trying again.`);
    } else {
        showFeedback('error', '❌', 'Claim Failed', error);
    }
}

// Show feedback message
function showFeedback(type, icon, title, message) {
    if (!elements.feedbackContainer || !elements.feedbackMessage) return;
    
    elements.feedbackMessage.className = `feedback-message ${type}`;
    elements.feedbackMessage.innerHTML = `
        <span class="feedback-icon">${icon}</span>
        <div class="feedback-content">
            <span class="feedback-title">${title}</span>
            <span class="feedback-text">${message}</span>
        </div>
    `;
    
    elements.feedbackContainer.classList.remove('hidden');
    
    // Auto-hide after delay
    setTimeout(() => {
        hideFeedback();
    }, 10000);
}

// Hide feedback message
function hideFeedback() {
    if (elements.feedbackContainer) {
        elements.feedbackContainer.classList.add('hidden');
    }
}

// Update balance display
function updateBalanceDisplay(balance) {
    if (elements.balanceDisplay && elements.balanceValue) {
        elements.balanceValue.textContent = `${formatNumber(balance)} points`;
        elements.balanceDisplay.classList.remove('hidden');
    }
}

// Start cooldown timer
function startCooldownTimer(nextClaim) {
    if (state.cooldownTimer) {
        clearInterval(state.cooldownTimer);
    }
    
    if (!elements.cooldownTimer || !elements.timerDisplay) return;
    
    elements.cooldownTimer.classList.remove('hidden');
    
    const updateTimer = () => {
        const now = Date.now();
        const timeLeft = nextClaim.getTime() - now;
        
        if (timeLeft <= 0) {
            clearInterval(state.cooldownTimer);
            elements.cooldownTimer.classList.add('hidden');
            if (elements.claimButton) {
                elements.claimButton.disabled = false;
                elements.buttonIcon.textContent = '🎁';
                elements.buttonText.textContent = 'CLAIM DAILY POINTS';
            }
            return;
        }
        
        const hours = Math.floor(timeLeft / 3600000);
        const minutes = Math.floor((timeLeft % 3600000) / 60000);
        const seconds = Math.floor((timeLeft % 60000) / 1000);
        
        elements.timerDisplay.textContent = 
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
// Add this JavaScript to your script.js file or in a <script> tag

// Slider functionality for Premium Services with TRUE INFINITE SCROLL
function initServiceSlider() {
    // Get slider elements
    const sliderWrapper = document.querySelector('.services-slider-wrapper');
    const servicesGrid = document.querySelector('.services-grid');
    const originalCards = Array.from(document.querySelectorAll('.service-card'));
    
    // Check if elements exist
    if (!servicesGrid || originalCards.length === 0) {
        console.log('Slider elements not found');
        return;
    }
    
    // Configuration
    const slideWidth = 100; // percentage
    const totalSlides = originalCards.length;
    let currentPosition = 0;
    let isAnimating = false;
    
    // Clone management
    const clonesPerSide = 2; // Number of full sets to clone on each side
    
    function setupInfiniteSlides() {
        servicesGrid.innerHTML = '';
        
        // Add multiple sets of clones at the beginning
        for (let set = 0; set < clonesPerSide; set++) {
            originalCards.forEach(card => {
                const clone = card.cloneNode(true);
                clone.classList.add('clone-before');
                servicesGrid.appendChild(clone);
            });
        }
        
        // Add original slides
        originalCards.forEach(card => {
            servicesGrid.appendChild(card);
        });
        
        // Add multiple sets of clones at the end
        for (let set = 0; set < clonesPerSide; set++) {
            originalCards.forEach(card => {
                const clone = card.cloneNode(true);
                clone.classList.add('clone-after');
                servicesGrid.appendChild(clone);
            });
        }
        
        // Set initial position (start at first original slide)
        currentPosition = -(clonesPerSide * totalSlides * slideWidth);
        servicesGrid.style.transform = `translateX(${currentPosition}%)`;
        servicesGrid.style.transition = 'none';
    }
    
    setupInfiniteSlides();
    
    // Create navigation elements
    createNavigationElements();
    
    function createNavigationElements() {
        // Create arrows if they don't exist
        let prevButton = document.querySelector('.slider-arrow.prev');
        let nextButton = document.querySelector('.slider-arrow.next');
        
        if (!prevButton) {
            prevButton = document.createElement('button');
            prevButton.className = 'slider-arrow prev';
            prevButton.innerHTML = '←';
            sliderWrapper.appendChild(prevButton);
        }
        
        if (!nextButton) {
            nextButton = document.createElement('button');
            nextButton.className = 'slider-arrow next';
            nextButton.innerHTML = '→';
            sliderWrapper.appendChild(nextButton);
        }
        
        // Create dots
        let dotsContainer = document.querySelector('.slider-dots');
        if (!dotsContainer) {
            dotsContainer = document.createElement('div');
            dotsContainer.className = 'slider-dots';
            
            for (let i = 0; i < totalSlides; i++) {
                const dot = document.createElement('button');
                dot.className = 'slider-dot';
                if (i === 0) dot.classList.add('active');
                dot.onclick = () => goToSlide(i);
                dotsContainer.appendChild(dot);
            }
            
            sliderWrapper.parentNode.insertBefore(dotsContainer, sliderWrapper.nextSibling);
        }
        
        // Event listeners
        prevButton.onclick = () => move('prev');
        nextButton.onclick = () => move('next');
    }
    
    function move(direction) {
        if (isAnimating) return;
        isAnimating = true;
        
        // Calculate movement
        const moveAmount = direction === 'next' ? -slideWidth : slideWidth;
        currentPosition += moveAmount;
        
        // Update dots IMMEDIATELY when animation starts
        updateDots();
        
        // Animate the movement with faster transition
        servicesGrid.style.transition = 'transform 0.3s cubic-bezier(0.4, 0, 0.2, 1)';
        servicesGrid.style.transform = `translateX(${currentPosition}%)`;
        
        // Check boundaries and reset if needed
        setTimeout(() => {
            const totalWidth = totalSlides * slideWidth;
            const resetThreshold = clonesPerSide * totalWidth;
            
            if (currentPosition <= -(resetThreshold + totalWidth)) {
                // Moved too far right, reset to left side
                servicesGrid.style.transition = 'none';
                currentPosition += totalWidth;
                servicesGrid.style.transform = `translateX(${currentPosition}%)`;
            } else if (currentPosition >= -resetThreshold + totalWidth) {
                // Moved too far left, reset to right side
                servicesGrid.style.transition = 'none';
                currentPosition -= totalWidth;
                servicesGrid.style.transform = `translateX(${currentPosition}%)`;
            }
            
            isAnimating = false;
        }, 300);
    }
    
    function goToSlide(index) {
        if (isAnimating) return;
        isAnimating = true;
        
        // Calculate the position for this slide
        const targetPosition = -(clonesPerSide * totalSlides * slideWidth + index * slideWidth);
        
        // Update dots IMMEDIATELY
        const dots = document.querySelectorAll('.slider-dot');
        dots.forEach((dot, i) => {
            dot.classList.toggle('active', i === index);
        });
        
        servicesGrid.style.transition = 'transform 0.3s cubic-bezier(0.4, 0, 0.2, 1)';
        currentPosition = targetPosition;
        servicesGrid.style.transform = `translateX(${currentPosition}%)`;
        
        setTimeout(() => {
            isAnimating = false;
        }, 300);
    }
    
    function updateDots() {
        const dots = document.querySelectorAll('.slider-dot');
        const normalizedPosition = Math.abs(currentPosition + (clonesPerSide * totalSlides * slideWidth));
        const currentSlideIndex = Math.round(normalizedPosition / slideWidth) % totalSlides;
        
        dots.forEach((dot, index) => {
            dot.classList.toggle('active', index === currentSlideIndex);
        });
    }
    
    // Touch support with momentum
    let startX = 0;
    let currentX = 0;
    let isDragging = false;
    let startTime = 0;
    let velocity = 0;
    
    function handleStart(clientX) {
        if (isAnimating) return;
        isDragging = true;
        startX = clientX;
        currentX = clientX;
        startTime = Date.now();
        velocity = 0;
        servicesGrid.style.transition = 'none';
    }
    
    function handleMove(clientX) {
        if (!isDragging || isAnimating) return;
        
        const deltaX = clientX - currentX;
        const deltaTime = Date.now() - startTime;
        
        if (deltaTime > 0) {
            velocity = deltaX / deltaTime;
        }
        
        currentX = clientX;
        startTime = Date.now();
        
        const diff = clientX - startX;
        const movePercent = (diff / window.innerWidth) * 100;
        servicesGrid.style.transform = `translateX(${currentPosition + movePercent}%)`;
    }
    
    function handleEnd(clientX) {
        if (!isDragging || isAnimating) return;
        isDragging = false;
        
        const diff = clientX - startX;
        const threshold = window.innerWidth * 0.2; // 20% of screen width
        const momentumThreshold = 0.5;
        
        // Check velocity for momentum scrolling
        if (Math.abs(velocity) > momentumThreshold) {
            move(velocity > 0 ? 'prev' : 'next');
        } else if (Math.abs(diff) > threshold) {
            move(diff > 0 ? 'prev' : 'next');
        } else {
            // Snap back with faster animation
            servicesGrid.style.transition = 'transform 0.2s ease-out';
            servicesGrid.style.transform = `translateX(${currentPosition}%)`;
        }
        
        velocity = 0;
    }
    
    // Touch events
    servicesGrid.addEventListener('touchstart', e => handleStart(e.touches[0].clientX));
    servicesGrid.addEventListener('touchmove', e => handleMove(e.touches[0].clientX));
    servicesGrid.addEventListener('touchend', e => handleEnd(e.changedTouches[0].clientX));
    
    // Mouse events
    servicesGrid.addEventListener('mousedown', e => {
        e.preventDefault();
        handleStart(e.clientX);
    });
    
    document.addEventListener('mousemove', e => {
        if (isDragging) {
            e.preventDefault();
            handleMove(e.clientX);
        }
    });
    
    document.addEventListener('mouseup', e => {
        if (isDragging) {
            handleEnd(e.clientX);
        }
    });
    
    // Keyboard
    document.addEventListener('keydown', e => {
        if (e.key === 'ArrowLeft') move('prev');
        if (e.key === 'ArrowRight') move('next');
    });
    
    // Auto-play
    let autoplayInterval;
    
    function startAutoplay(delay = 3000) {
        stopAutoplay();
        autoplayInterval = setInterval(() => move('next'), delay);
    }
    
    function stopAutoplay() {
        if (autoplayInterval) {
            clearInterval(autoplayInterval);
            autoplayInterval = null;
        }
    }
    
    // Optional: Enable autoplay
    // startAutoplay(3000);
    
    // Stop on hover
    servicesGrid.addEventListener('mouseenter', stopAutoplay);
    servicesGrid.addEventListener('touchstart', stopAutoplay);
    
    // Initialize
    updateDots();
}

// Initialize when ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initServiceSlider);
} else {
    initServiceSlider();
}