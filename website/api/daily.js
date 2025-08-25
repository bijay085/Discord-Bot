// api/daily.js - Secure Daily Claim Endpoint with Anti-Bot Protection
import { MongoClient } from 'mongodb';
import crypto from 'crypto';

// Security configurations
const RATE_LIMIT_WINDOW = 60000; // 1 minute
const MAX_ATTEMPTS = 3; // Max attempts per window
const CLAIM_COOLDOWN = 86400000; // 24 hours
const MIN_REQUEST_INTERVAL = 2000; // 2 seconds between requests

// Rate limiting and anti-bot tracking
const rateLimitMap = new Map();
const suspiciousIPs = new Set();
const claimHistory = new Map();

// Security utilities
function hashIP(ip) {
    return crypto.createHash('sha256').update(ip + process.env.SALT || 'default').digest('hex');
}

function isValidDiscordId(id) {
    return /^[0-9]{17,20}$/.test(id);
}

function isValidUsername(username) {
    return username && 
           username.length >= 2 && 
           username.length <= 32 && 
           /^[a-zA-Z0-9_.-]+$/.test(username);
}

function detectBot(headers, body) {
    // Check for common bot indicators
    const userAgent = headers['user-agent'] || '';
    const botPatterns = [
        /bot/i, /crawl/i, /spider/i, /scraper/i, /curl/i, /wget/i, /python/i, /java/i
    ];
    
    if (botPatterns.some(pattern => pattern.test(userAgent))) {
        return true;
    }
    
    // Check for missing headers that real browsers send
    if (!headers['accept-language'] || !headers['accept-encoding']) {
        return true;
    }
    
    // Check for suspicious timing patterns
    if (body.timestamp) {
        const requestTime = parseInt(body.timestamp);
        const serverTime = Date.now();
        const timeDiff = Math.abs(serverTime - requestTime);
        
        // If time difference is more than 5 minutes, likely automated
        if (timeDiff > 300000) {
            return true;
        }
    }
    
    return false;
}

export default async function handler(req, res) {
    // Security headers
    res.setHeader('Access-Control-Allow-Origin', process.env.ALLOWED_ORIGIN || '*');
    res.setHeader('Access-Control-Allow-Methods', 'POST');
    res.setHeader('X-Content-Type-Options', 'nosniff');
    res.setHeader('X-Frame-Options', 'DENY');
    res.setHeader('X-XSS-Protection', '1; mode=block');
    res.setHeader('Content-Security-Policy', "default-src 'none'");
    
    // Only allow POST
    if (req.method !== 'POST') {
        return res.status(405).json({ error: 'Method not allowed' });
    }
    
    // Get client information
    const clientIp = req.headers['x-forwarded-for']?.split(',')[0] || 
                    req.headers['x-real-ip'] || 
                    req.connection.remoteAddress;
    
    const ipHash = hashIP(clientIp);
    
    // Check if IP is already flagged as suspicious
    if (suspiciousIPs.has(ipHash)) {
        return res.status(403).json({ error: 'Access denied' });
    }
    
    // Bot detection
    if (detectBot(req.headers, req.body)) {
        suspiciousIPs.add(ipHash);
        return res.status(403).json({ error: 'Automated requests not allowed' });
    }
    
    // Rate limiting
    const now = Date.now();
    const userRateLimit = rateLimitMap.get(ipHash) || { 
        count: 0, 
        resetTime: now + RATE_LIMIT_WINDOW,
        lastRequest: 0 
    };
    
    // Check minimum interval between requests
    if (now - userRateLimit.lastRequest < MIN_REQUEST_INTERVAL) {
        return res.status(429).json({ 
            error: 'Too fast! Please wait a moment',
            retryAfter: 2
        });
    }
    
    // Reset rate limit window if expired
    if (now > userRateLimit.resetTime) {
        userRateLimit.count = 0;
        userRateLimit.resetTime = now + RATE_LIMIT_WINDOW;
    }
    
    userRateLimit.count++;
    userRateLimit.lastRequest = now;
    rateLimitMap.set(ipHash, userRateLimit);
    
    // Check rate limit
    if (userRateLimit.count > MAX_ATTEMPTS) {
        const timeLeft = Math.ceil((userRateLimit.resetTime - now) / 1000);
        return res.status(429).json({ 
            error: 'Too many attempts. Please try again later',
            retryAfter: timeLeft
        });
    }
    
    // Clean up old rate limit entries periodically
    if (rateLimitMap.size > 1000) {
        for (const [hash, data] of rateLimitMap.entries()) {
            if (now > data.resetTime + RATE_LIMIT_WINDOW) {
                rateLimitMap.delete(hash);
            }
        }
    }
    
    // Validate request body
    const { userId, username, sessionToken } = req.body;
    
    if (!userId || !username) {
        return res.status(400).json({ error: 'Missing required fields' });
    }
    
    // Validate Discord ID
    if (!isValidDiscordId(userId)) {
        suspiciousIPs.add(ipHash);
        return res.status(400).json({ error: 'Invalid Discord ID format' });
    }
    
    // Validate username
    if (!isValidUsername(username)) {
        return res.status(400).json({ error: 'Invalid username format' });
    }
    
    // Check session token (basic validation)
    if (!sessionToken || sessionToken.length < 32) {
        return res.status(400).json({ error: 'Invalid session' });
    }
    
    // Check claim history for this IP
    const lastClaim = claimHistory.get(ipHash);
    if (lastClaim && (now - lastClaim.timestamp < 60000)) {
        // Same IP claiming within 1 minute - suspicious
        if (lastClaim.userId !== userId) {
            suspiciousIPs.add(ipHash);
            return res.status(403).json({ error: 'Suspicious activity detected' });
        }
    }
    
    let client;
    
    try {
        // Connect to MongoDB with timeout
        client = new MongoClient(process.env.MONGODB_URI, {
            maxPoolSize: 10,
            serverSelectionTimeoutMS: 5000,
            connectTimeoutMS: 5000
        });
        
        await client.connect();
        const db = client.db(process.env.DATABASE_NAME || 'discord_bot');
        
        // Check bot status
        const config = await db.collection('config').findOne({ _id: 'bot_config' });
        const lastActivity = config?.last_activity;
        const isOnline = lastActivity && 
            (new Date() - new Date(lastActivity)) < (5 * 60 * 1000);
        
        if (!isOnline) {
            return res.status(503).json({ 
                error: 'Bot is offline! Please wait for bot to come online.' 
            });
        }
        
        if (config?.maintenance_mode) {
            return res.status(503).json({ 
                error: 'Bot is under maintenance. Please try again later.' 
            });
        }
        
        // Parse user ID as number
        const userIdNum = parseInt(userId);
        
        // Get point rates
        const pointRates = config?.point_rates || { daily: 2 };
        const basePoints = pointRates.daily;
        
        // Get or create user
        let user = await db.collection('users').findOne({ user_id: userIdNum });
        
        if (!user) {
            // Create new user
            user = {
                user_id: userIdNum,
                username: username.substring(0, 32),
                points: 0,
                total_earned: 0,
                total_spent: 0,
                trust_score: 50,
                cookie_claims: {},
                total_claims: 0,
                weekly_claims: 0,
                daily_claimed: null,
                invite_count: 0,
                blacklisted: false,
                blacklist_expires: null,
                account_created: new Date(),
                first_seen: new Date(),
                last_active: new Date(),
                created_via: 'website',
                ip_hash: ipHash // Store hashed IP for security tracking
            };
            
            await db.collection('users').insertOne(user);
        }
        
        // Check if blacklisted
        if (user.blacklisted) {
            if (user.blacklist_expires && new Date(user.blacklist_expires) > new Date()) {
                const timeLeft = new Date(user.blacklist_expires) - new Date();
                const daysLeft = Math.floor(timeLeft / (1000 * 60 * 60 * 24));
                
                return res.status(403).json({ 
                    error: `You are blacklisted for ${daysLeft} more days!`,
                    blacklist_expires: user.blacklist_expires
                });
            } else if (!user.blacklist_expires) {
                return res.status(403).json({ 
                    error: 'You are permanently blacklisted!'
                });
            }
        }
        
        // Check cooldown
        if (user.daily_claimed) {
            const lastClaim = new Date(user.daily_claimed);
            const timeSinceLastClaim = new Date() - lastClaim;
            
            if (timeSinceLastClaim < CLAIM_COOLDOWN) {
                const timeLeft = CLAIM_COOLDOWN - timeSinceLastClaim;
                const hoursLeft = Math.floor(timeLeft / (1000 * 60 * 60));
                const minutesLeft = Math.floor((timeLeft % (1000 * 60 * 60)) / (1000 * 60));
                
                return res.status(429).json({ 
                    error: 'Daily already claimed!',
                    timeLeft: `${hoursLeft}h ${minutesLeft}m`,
                    nextClaim: new Date(lastClaim.getTime() + CLAIM_COOLDOWN),
                    currentBalance: user.points
                });
            }
        }
        
        // Award points (base only - no role bonuses for web)
        const totalPoints = basePoints;
        
        // Update user
        const updateResult = await db.collection('users').updateOne(
            { user_id: userIdNum },
            {
                $set: {
                    daily_claimed: new Date(),
                    last_active: new Date(),
                    username: username.substring(0, 32),
                    last_claim_ip: ipHash
                },
                $inc: {
                    points: totalPoints,
                    total_earned: totalPoints
                }
            }
        );
        
        if (updateResult.matchedCount === 0) {
            return res.status(500).json({ 
                error: 'Failed to update user data. Please try again.' 
            });
        }
        
        // Log transaction
        await db.collection('transactions').insertOne({
            user_id: userIdNum,
            type: 'daily_claim',
            amount: totalPoints,
            description: `Daily claim (web) - ${totalPoints} points`,
            timestamp: new Date(),
            source: 'website',
            ip_hash: ipHash
        });
        
        // Update analytics
        await db.collection('analytics').insertOne({
            type: 'command_usage',
            command: 'daily',
            user_id: userIdNum,
            timestamp: new Date(),
            source: 'website'
        });
        
        // Update global statistics
        await db.collection('statistics').updateOne(
            { _id: 'global_stats' },
            {
                $inc: {
                    total_points_distributed: totalPoints,
                    web_claims_total: 1
                },
                $set: {
                    last_updated: new Date()
                }
            },
            { upsert: true }
        );
        
        // Track successful claim
        claimHistory.set(ipHash, {
            userId: userIdNum,
            timestamp: now
        });
        
        // Clean up claim history
        if (claimHistory.size > 500) {
            for (const [hash, data] of claimHistory.entries()) {
                if (now - data.timestamp > 3600000) { // 1 hour old
                    claimHistory.delete(hash);
                }
            }
        }
        
        // Success response
        return res.status(200).json({
            success: true,
            points_earned: totalPoints,
            new_balance: user.points + totalPoints,
            total_earned: user.total_earned + totalPoints,
            next_claim: new Date(Date.now() + CLAIM_COOLDOWN),
            message: `Successfully claimed ${totalPoints} points! Use Discord bot for role bonuses up to 20 points!`
        });
        
    } catch (error) {
        console.error('Daily claim error:', error.message);
        
        // Log error without exposing details
        try {
            if (client && client.db) {
                await client.db(process.env.DATABASE_NAME || 'discord_bot')
                    .collection('error_logs')
                    .insertOne({
                        type: 'daily_claim_error',
                        error: error.message,
                        timestamp: new Date(),
                        ip_hash: ipHash
                    });
            }
        } catch (logError) {
            // Silent fail for logging
        }
        
        return res.status(500).json({ 
            error: 'Service temporarily unavailable. Please try again later.'
        });
        
    } finally {
        if (client) {
            await client.close();
        }
    }
}