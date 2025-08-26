// api/daily.js - Optimized Daily Claim Endpoint
import { MongoClient } from 'mongodb';

// Configuration
const CLAIM_COOLDOWN = 86400000; // 24 hours
const POINTS_PER_CLAIM = 2;

// Rate limiting with automatic cleanup
const rateLimiter = new Map();
const RATE_LIMIT_WINDOW = 2000; // 2 seconds
const MAX_ENTRIES = 1000;

export default async function handler(req, res) {
    // Set CORS and cache headers
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Access-Control-Allow-Methods', 'POST');
    res.setHeader('Cache-Control', 'no-cache, no-store, must-revalidate');
    
    // Only allow POST
    if (req.method !== 'POST') {
        return res.status(405).json({ error: 'Method not allowed' });
    }
    
    // Rate limiting
    const clientIp = req.headers['x-forwarded-for']?.split(',')[0] || 
                    req.headers['x-real-ip'] || 
                    req.connection?.remoteAddress || 'unknown';
    
    const now = Date.now();
    const lastRequest = rateLimiter.get(clientIp) || 0;
    
    if (now - lastRequest < RATE_LIMIT_WINDOW) {
        return res.status(429).json({ 
            error: 'Too fast! Please wait.',
            retryAfter: Math.ceil((RATE_LIMIT_WINDOW - (now - lastRequest)) / 1000)
        });
    }
    
    rateLimiter.set(clientIp, now);
    
    // Cleanup old entries periodically
    if (rateLimiter.size > MAX_ENTRIES) {
        const cutoff = now - 60000;
        for (const [ip, time] of rateLimiter.entries()) {
            if (time < cutoff) rateLimiter.delete(ip);
        }
    }
    
    // Validate request
    const { userId } = req.body;
    
    if (!userId || !/^[0-9]{17,20}$/.test(userId)) {
        return res.status(400).json({ error: 'Invalid Discord ID' });
    }
    
    const userIdNum = parseInt(userId);
    let client;
    
    try {
        // Quick MongoDB connection
        client = new MongoClient(process.env.MONGODB_URI, {
            maxPoolSize: 10,
            serverSelectionTimeoutMS: 5000,
            socketTimeoutMS: 5000
        });
        
        await client.connect();
        const db = client.db(process.env.DATABASE_NAME || 'discord_bot');
        
        // Check maintenance mode
        const config = await db.collection('config').findOne(
            { _id: 'bot_config' },
            { projection: { maintenance_mode: 1, point_rates: 1 } }
        );
        
        if (config?.maintenance_mode) {
            return res.status(503).json({ 
                error: 'System maintenance. Please try again later.' 
            });
        }
        
        const basePoints = config?.point_rates?.daily || POINTS_PER_CLAIM;
        
        // Get or create user with single operation
        const user = await db.collection('users').findOneAndUpdate(
            { user_id: userIdNum },
            {
                $setOnInsert: {
                    user_id: userIdNum,
                    username: `User${userIdNum.toString().slice(-6)}`,
                    points: 0,
                    total_earned: 0,
                    total_spent: 0,
                    daily_claimed: null,
                    blacklisted: false,
                    account_created: new Date(),
                    created_via: 'website'
                },
                $set: { last_active: new Date() }
            },
            { 
                upsert: true, 
                returnDocument: 'before',
                projection: { 
                    points: 1, 
                    daily_claimed: 1, 
                    blacklisted: 1,
                    total_earned: 1
                }
            }
        );
        
        // Check if blacklisted
        if (user.value?.blacklisted) {
            return res.status(403).json({ 
                error: 'Account blacklisted.' 
            });
        }
        
        // Check cooldown
        const lastClaim = user.value?.daily_claimed;
        if (lastClaim) {
            const timeSinceLastClaim = now - new Date(lastClaim).getTime();
            
            if (timeSinceLastClaim < CLAIM_COOLDOWN) {
                const timeLeft = CLAIM_COOLDOWN - timeSinceLastClaim;
                const hoursLeft = Math.floor(timeLeft / 3600000);
                const minutesLeft = Math.floor((timeLeft % 3600000) / 60000);
                
                return res.status(429).json({ 
                    error: 'Already claimed!',
                    timeLeft: `${hoursLeft}h ${minutesLeft}m`,
                    nextClaim: new Date(new Date(lastClaim).getTime() + CLAIM_COOLDOWN),
                    balance: user.value.points || 0
                });
            }
        }
        
        // Award points with batch operations
        const currentTime = new Date();
        const [updateResult] = await Promise.all([
            db.collection('users').updateOne(
                { user_id: userIdNum },
                {
                    $set: { 
                        daily_claimed: currentTime,
                        last_active: currentTime
                    },
                    $inc: {
                        points: basePoints,
                        total_earned: basePoints
                    }
                }
            ),
            db.collection('transactions').insertOne({
                user_id: userIdNum,
                type: 'daily_claim',
                amount: basePoints,
                description: `Web daily - ${basePoints}pts`,
                timestamp: currentTime,
                source: 'website'
            }),
            db.collection('statistics').updateOne(
                { _id: 'global_stats' },
                {
                    $inc: {
                        total_points_distributed: basePoints,
                        web_claims_total: 1
                    },
                    $set: { last_updated: currentTime }
                },
                { upsert: true }
            )
        ]);
        
        // Calculate new balance
        const oldPoints = user.value?.points || 0;
        const newBalance = oldPoints + basePoints;
        const totalEarned = (user.value?.total_earned || 0) + basePoints;
        
        // Success response
        return res.status(200).json({
            success: true,
            points: basePoints,
            balance: newBalance,
            total: totalEarned,
            next: new Date(Date.now() + CLAIM_COOLDOWN),
            message: `+${basePoints} points! Discord bot offers up to 20 points with role bonuses!`
        });
        
    } catch (error) {
        console.error('Claim error:', error.message);
        return res.status(500).json({ 
            error: 'Service unavailable. Try again later.'
        });
    } finally {
        if (client) {
            await client.close();
        }
    }
}