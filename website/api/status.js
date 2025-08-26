// api/status.js - Fixed Status Endpoint with Proper Stats
import { MongoClient } from 'mongodb';

// Cache for status data
let statusCache = null;
let cacheTime = 0;
const CACHE_DURATION = 30000; // 30 seconds

export default async function handler(req, res) {
    // Headers
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Access-Control-Allow-Methods', 'GET');
    res.setHeader('Cache-Control', 'public, max-age=30, s-maxage=30');
    
    if (req.method !== 'GET') {
        return res.status(405).json({ error: 'Method not allowed' });
    }
    
    // Return cached data if valid
    const now = Date.now();
    if (statusCache && (now - cacheTime) < CACHE_DURATION) {
        return res.status(200).json(statusCache);
    }
    
    let client;
    
    try {
        client = new MongoClient(process.env.MONGODB_URI, {
            maxPoolSize: 5,
            serverSelectionTimeoutMS: 3000
        });
        
        await client.connect();
        const db = client.db(process.env.DATABASE_NAME || 'discord_bot');
        
        // Calculate stats directly from collections
        const todayStart = new Date();
        todayStart.setHours(0, 0, 0, 0);
        
        // Parallel fetch all data
        const [
            userCount,
            activeToday,
            totalPointsResult,
            totalClaimsResult,
            config,
            leaderboard,
            stats
        ] = await Promise.all([
            // Count total users
            db.collection('users').countDocuments({}),
            
            // Count active users today
            db.collection('users').countDocuments({
                last_active: { $gte: todayStart }
            }),
            
            // Sum total points earned
            db.collection('users').aggregate([
                { $group: { _id: null, total: { $sum: "$total_earned" } } }
            ]).toArray(),
            
            // Count total claims from transactions
            db.collection('transactions').countDocuments({
                type: 'daily_claim'
            }),
            
            // Get bot config
            db.collection('config').findOne(
                { _id: 'bot_config' },
                { projection: { last_activity: 1, maintenance_mode: 1 } }
            ),
            
            // Get leaderboard
            db.collection('users')
                .find(
                    { blacklisted: { $ne: true } },
                    { projection: { username: 1, points: 1 } }
                )
                .sort({ points: -1 })
                .limit(10)
                .toArray(),
            
            // Get existing stats (if any)
            db.collection('statistics').findOne({ _id: 'global_stats' })
        ]);
        
        // Calculate total points (fallback to stats if aggregation fails)
        const totalPoints = totalPointsResult?.[0]?.total || 
                          stats?.total_points_distributed || 0;
        
        // Use calculated claims or fallback to stats
        const totalClaims = totalClaimsResult || 
                          stats?.all_time_claims || 0;
        
        // Check bot status
        const lastActivity = config?.last_activity;
        const isOnline = lastActivity && 
            (now - new Date(lastActivity).getTime()) < 300000; // 5 minutes
        
        // Update statistics collection with current counts
        await db.collection('statistics').updateOne(
            { _id: 'global_stats' },
            {
                $set: {
                    total_users: userCount,
                    active_today: activeToday,
                    total_points_distributed: totalPoints,
                    all_time_claims: totalClaims,
                    last_updated: new Date()
                }
            },
            { upsert: true }
        );
        
        // Format response
        const responseData = {
            online: isOnline && !config?.maintenance_mode,
            stats: {
                users: userCount || 0,
                servers: stats?.total_servers || 0,
                points: totalPoints || 0,
                cookies: totalClaims || 0,
                active: activeToday || 0
            },
            leaderboard: leaderboard.map((user, i) => ({
                rank: i + 1,
                name: user.username || 'Anonymous',
                points: user.points || 0
            })),
            timestamp: new Date().toISOString()
        };
        
        // Update cache
        statusCache = responseData;
        cacheTime = now;
        
        return res.status(200).json(responseData);
        
    } catch (error) {
        console.error('Status error:', error);
        
        // Return minimal response on error
        return res.status(200).json({
            online: false,
            stats: { users: 0, servers: 0, points: 0, cookies: 0, active: 0 },
            leaderboard: [],
            timestamp: new Date().toISOString()
        });
        
    } finally {
        if (client) {
            await client.close();
        }
    }
}