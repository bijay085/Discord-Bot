// api/status.js - Secure Status Endpoint
import { MongoClient } from 'mongodb';

// Rate limiting cache
const rateLimit = new Map();
const RATE_LIMIT_WINDOW = 60000; // 1 minute
const MAX_REQUESTS = 30; // 30 requests per minute

export default async function handler(req, res) {
    // Enable CORS with restrictions
    res.setHeader('Access-Control-Allow-Origin', process.env.ALLOWED_ORIGIN || '*');
    res.setHeader('Access-Control-Allow-Methods', 'GET');
    res.setHeader('Access-Control-Max-Age', '3600');
    res.setHeader('X-Content-Type-Options', 'nosniff');
    res.setHeader('X-Frame-Options', 'DENY');
    res.setHeader('X-XSS-Protection', '1; mode=block');
    
    // Only allow GET
    if (req.method !== 'GET') {
        return res.status(405).json({ error: 'Method not allowed' });
    }
    
    // Get client IP
    const clientIp = req.headers['x-forwarded-for'] || 
                    req.headers['x-real-ip'] || 
                    req.connection.remoteAddress;
    
    // Rate limiting
    const now = Date.now();
    const userRateLimit = rateLimit.get(clientIp) || { count: 0, resetTime: now + RATE_LIMIT_WINDOW };
    
    if (now > userRateLimit.resetTime) {
        userRateLimit.count = 0;
        userRateLimit.resetTime = now + RATE_LIMIT_WINDOW;
    }
    
    userRateLimit.count++;
    rateLimit.set(clientIp, userRateLimit);
    
    if (userRateLimit.count > MAX_REQUESTS) {
        return res.status(429).json({ 
            error: 'Too many requests',
            retryAfter: Math.ceil((userRateLimit.resetTime - now) / 1000)
        });
    }
    
    // Clean up old rate limit entries
    if (rateLimit.size > 1000) {
        for (const [ip, data] of rateLimit.entries()) {
            if (now > data.resetTime) {
                rateLimit.delete(ip);
            }
        }
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
        
        // Check bot status
        const config = await db.collection('config').findOne(
            { _id: 'bot_config' },
            { projection: { last_activity: 1, maintenance_mode: 1 } }
        );
        
        const lastActivity = config?.last_activity;
        const isOnline = lastActivity && 
            (new Date() - new Date(lastActivity)) < (5 * 60 * 1000);
        
        // Get basic statistics (minimal data)
        const [totalUsers, totalServers, globalStats] = await Promise.all([
            db.collection('users').countDocuments({}),
            db.collection('servers').countDocuments({ enabled: true }),
            db.collection('statistics').findOne(
                { _id: 'global_stats' },
                { projection: { all_time_claims: 1 } }
            )
        ]);
        
        // Get top 10 users for leaderboard (no sensitive data)
        const leaderboard = await db.collection('users')
            .find(
                { blacklisted: { $ne: true } },
                { 
                    projection: { 
                        username: 1, 
                        points: 1,
                        _id: 0 
                    }
                }
            )
            .sort({ points: -1 })
            .limit(10)
            .toArray();
        
        // Clean usernames for security
        const cleanLeaderboard = leaderboard.map((user, index) => ({
            rank: index + 1,
            username: user.username ? 
                user.username.substring(0, 20).replace(/[^a-zA-Z0-9_.-]/g, '') : 
                'Anonymous',
            points: Math.floor(user.points || 0)
        }));
        
        // Response data (minimal, no sensitive info)
        const responseData = {
            online: isOnline && !config?.maintenance_mode,
            totalUsers: totalUsers || 0,
            totalServers: totalServers || 0,
            totalCookies: globalStats?.all_time_claims || 0,
            lastActivity: isOnline ? lastActivity : null,
            leaderboard: cleanLeaderboard,
            timestamp: new Date().toISOString()
        };
        
        // Cache headers
        res.setHeader('Cache-Control', 'public, max-age=30');
        
        return res.status(200).json(responseData);
        
    } catch (error) {
        console.error('Status endpoint error:', error.message);
        
        // Don't expose internal errors
        return res.status(500).json({ 
            error: 'Service temporarily unavailable',
            online: false
        });
        
    } finally {
        if (client) {
            await client.close();
        }
    }
}