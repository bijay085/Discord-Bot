// api/daily.js - Simple Daily Claim Endpoint
import { MongoClient } from 'mongodb';

// Configuration
const CLAIM_COOLDOWN = 86400000; // 24 hours
const MIN_REQUEST_INTERVAL = 2000; // 2 seconds between requests

// Simple rate limiting
const lastRequestTime = new Map();

export default async function handler(req, res) {
    // CORS headers
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Access-Control-Allow-Methods', 'POST');
    
    // Only allow POST
    if (req.method !== 'POST') {
        return res.status(405).json({ error: 'Method not allowed' });
    }
    
    // Get client IP
    const clientIp = req.headers['x-forwarded-for']?.split(',')[0] || 
                    req.headers['x-real-ip'] || 
                    req.connection.remoteAddress;
    
    // Simple rate limiting - prevent rapid requests
    const now = Date.now();
    const lastRequest = lastRequestTime.get(clientIp) || 0;
    
    if (now - lastRequest < MIN_REQUEST_INTERVAL) {
        return res.status(429).json({ 
            error: 'Too fast! Please wait a moment.',
            retryAfter: 2
        });
    }
    
    lastRequestTime.set(clientIp, now);
    
    // Clean up old entries (keep map size manageable)
    if (lastRequestTime.size > 1000) {
        const cutoff = now - 60000; // Remove entries older than 1 minute
        for (const [ip, time] of lastRequestTime.entries()) {
            if (time < cutoff) {
                lastRequestTime.delete(ip);
            }
        }
    }
    
    // Validate request body
    const { userId, username } = req.body;
    
    if (!userId || !username) {
        return res.status(400).json({ error: 'Missing required fields' });
    }
    
    // Basic validation
    if (!/^[0-9]{17,20}$/.test(userId)) {
        return res.status(400).json({ error: 'Invalid Discord ID format' });
    }
    
    if (username.length < 2 || username.length > 32) {
        return res.status(400).json({ error: 'Invalid username length' });
    }
    
    let client;
    
    try {
        // Connect to MongoDB
        client = new MongoClient(process.env.MONGODB_URI, {
            maxPoolSize: 10,
            serverSelectionTimeoutMS: 5000
        });
        
        await client.connect();
        const db = client.db(process.env.DATABASE_NAME || 'discord_bot');
        
        // Get bot config (but don't block claims if bot is offline)
        const config = await db.collection('config').findOne({ _id: 'bot_config' });
        
        // Check if maintenance mode (this is the only blocking condition)
        if (config?.maintenance_mode) {
            return res.status(503).json({ 
                error: 'System is under maintenance. Please try again later.' 
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
                username: username,
                points: 0,
                total_earned: 0,
                total_spent: 0,
                daily_claimed: null,
                blacklisted: false,
                account_created: new Date(),
                last_active: new Date(),
                created_via: 'website'
            };
            
            await db.collection('users').insertOne(user);
        }
        
        // Check if blacklisted
        if (user.blacklisted) {
            return res.status(403).json({ 
                error: 'Your account has been blacklisted.' 
            });
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
        
        // Award points
        const totalPoints = basePoints;
        
        // Update user (only update username if provided and not "Anonymous")
        const updateData = {
            $set: {
                daily_claimed: new Date(),
                last_active: new Date()
            },
            $inc: {
                points: totalPoints,
                total_earned: totalPoints
            }
        };
        
        // Only update username if it's not "Anonymous" (meaning user actually entered something)
        if (username && username !== 'Anonymous') {
            updateData.$set.username = username;
        }
        
        await db.collection('users').updateOne(
            { user_id: userIdNum },
            updateData
        );
        
        // Log transaction
        await db.collection('transactions').insertOne({
            user_id: userIdNum,
            type: 'daily_claim',
            amount: totalPoints,
            description: `Daily claim (web) - ${totalPoints} points`,
            timestamp: new Date(),
            source: 'website'
        });
        
        // Update statistics
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
        
        return res.status(500).json({ 
            error: 'Service temporarily unavailable. Please try again later.'
        });
        
    } finally {
        if (client) {
            await client.close();
        }
    }
}