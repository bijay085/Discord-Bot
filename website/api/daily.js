// api/daily.js - Match Discord Bot's User Structure
import { MongoClient } from 'mongodb';

// Configuration
const CLAIM_COOLDOWN = 86400000; // 24 hours
const POINTS_PER_CLAIM = 2;

// Rate limiting
const rateLimiter = new Map();
const RATE_LIMIT_WINDOW = 2000; // 2 seconds

export default async function handler(req, res) {
    // CORS headers
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Access-Control-Allow-Methods', 'POST');
    res.setHeader('Cache-Control', 'no-cache, no-store, must-revalidate');
    
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
    
    // Validate request
    const { userId } = req.body;
    
    if (!userId || !/^[0-9]{17,20}$/.test(userId)) {
        return res.status(400).json({ 
            error: 'Invalid Discord ID! Must be 17-20 digits.' 
        });
    }
    
    // Use MongoDB Long type for Discord IDs to avoid precision loss
    const { Long } = await import('mongodb');
    const userIdLong = Long.fromString(userId);
    
    let client;
    
    try {
        client = new MongoClient(process.env.MONGODB_URI, {
            maxPoolSize: 10,
            serverSelectionTimeoutMS: 5000
        });
        
        await client.connect();
        const db = client.db(process.env.DATABASE_NAME || 'discord_bot');
        
        // Find user - matching Discord bot's structure (user_id as number/Long)
        let user = await db.collection('users').findOne(
            { user_id: userIdLong },
            { projection: { 
                user_id: 1,
                username: 1,
                points: 1, 
                daily_claimed: 1, 
                blacklisted: 1,
                total_earned: 1
            }}
        );
        
        // If user doesn't exist, create with same structure as Discord bot
        if (!user) {
            console.log(`Creating new user with Discord ID: ${userId}`);
            
            const currentTime = new Date();
            const newUser = {
                // Core fields matching Discord bot
                user_id: userIdLong,  // Store as Long to handle large numbers
                username: "",  // Empty as requested, will be updated by Discord bot
                points: 0,
                total_earned: 0,
                total_spent: 0,
                trust_score: 50,
                account_created: currentTime,
                first_seen: currentTime,
                last_active: currentTime,
                daily_claimed: null,
                invite_count: 0,
                last_claim: null,
                cookie_claims: {},
                daily_claims: {},
                weekly_claims: 0,
                total_claims: 0,
                blacklisted: false,
                blacklist_expires: null,
                invited_users: [],
                pending_invites: 0,
                verified_invites: 0,
                fake_invites: 0,
                preferences: {
                    dm_notifications: true,
                    claim_confirmations: true,
                    feedback_reminders: true
                },
                statistics: {
                    feedback_streak: 0,
                    perfect_ratings: 0,
                    favorite_cookie: null
                },
                // Additional field to track creation source
                created_via: 'website'
            };
            
            await db.collection('users').insertOne(newUser);
            user = newUser;
        }
        
        // Check if blacklisted
        if (user.blacklisted) {
            // Check if blacklist expired
            if (user.blacklist_expires && new Date(user.blacklist_expires) < new Date()) {
                // Blacklist expired, unblacklist user
                await db.collection('users').updateOne(
                    { user_id: userIdLong },
                    { 
                        $set: { 
                            blacklisted: false,
                            blacklist_expires: null 
                        }
                    }
                );
            } else {
                return res.status(403).json({ 
                    error: 'Account blacklisted.' 
                });
            }
        }
        
        // Check cooldown
        if (user.daily_claimed) {
            const lastClaimTime = new Date(user.daily_claimed).getTime();
            const timeSinceLastClaim = now - lastClaimTime;
            
            if (timeSinceLastClaim < CLAIM_COOLDOWN) {
                const timeLeft = CLAIM_COOLDOWN - timeSinceLastClaim;
                const hoursLeft = Math.floor(timeLeft / 3600000);
                const minutesLeft = Math.floor((timeLeft % 3600000) / 60000);
                
                return res.status(429).json({ 
                    error: 'Already claimed!',
                    timeLeft: `${hoursLeft}h ${minutesLeft}m`,
                    nextClaim: new Date(lastClaimTime + CLAIM_COOLDOWN),
                    balance: user.points || 0
                });
            }
        }
        
        // Award points
        const currentTime = new Date();
        
        await db.collection('users').updateOne(
            { user_id: userIdLong },
            {
                $set: { 
                    daily_claimed: currentTime,
                    last_claim: currentTime,
                    last_active: currentTime
                },
                $inc: {
                    points: POINTS_PER_CLAIM,
                    total_earned: POINTS_PER_CLAIM,
                    total_claims: 1,
                    weekly_claims: 1
                }
            }
        );
        
        // Update daily_claims object for tracking
        const dateKey = currentTime.toISOString().split('T')[0];
        await db.collection('users').updateOne(
            { user_id: userIdLong },
            {
                $set: {
                    [`daily_claims.${dateKey}`]: currentTime
                }
            }
        );
        
        // Log transaction
        await db.collection('transactions').insertOne({
            user_id: userIdLong,
            type: 'daily_claim',
            amount: POINTS_PER_CLAIM,
            description: `Web daily - ${POINTS_PER_CLAIM}pts`,
            timestamp: currentTime,
            source: 'website'
        });
        
        // Update global stats
        await db.collection('statistics').updateOne(
            { _id: 'global_stats' },
            {
                $inc: {
                    total_points_distributed: POINTS_PER_CLAIM,
                    web_claims_total: 1,
                    all_time_claims: 1
                },
                $set: { last_updated: currentTime }
            },
            { upsert: true }
        );
        
        // Update daily active users count
        const todayStart = new Date();
        todayStart.setHours(0, 0, 0, 0);
        
        const activeToday = await db.collection('users').countDocuments({
            last_active: { $gte: todayStart }
        });
        
        await db.collection('statistics').updateOne(
            { _id: 'global_stats' },
            { $set: { active_today: activeToday } }
        );
        
        // Calculate new balance
        const newBalance = (user.points || 0) + POINTS_PER_CLAIM;
        const totalEarned = (user.total_earned || 0) + POINTS_PER_CLAIM;
        
        console.log(`User ${userId} claimed. New balance: ${newBalance}`);
        
        return res.status(200).json({
            success: true,
            userId: userId,
            points: POINTS_PER_CLAIM,
            balance: newBalance,
            total: totalEarned,
            next: new Date(Date.now() + CLAIM_COOLDOWN),
            message: `+${POINTS_PER_CLAIM} points! Discord bot offers up to 20 points with role bonuses!`
        });
        
    } catch (error) {
        console.error('Claim error:', error);
        return res.status(500).json({ 
            error: 'Service unavailable. Try again later.'
        });
    } finally {
        if (client) {
            await client.close();
        }
    }
}