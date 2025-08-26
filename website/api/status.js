// api/status.js - Optimized Status Endpoint
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
            serverSelectionTimeoutMS: 3000,
            socketTimeoutMS: 3000
        });
        
        await client.connect();
        const db = client.db(process.env.DATABASE_NAME || 'discord_bot');
        
        // Parallel fetch all data
        const [config, stats, leaderboard] = await Promise.all([
            db.collection('config').findOne(
                { _id: 'bot_config' },
                { projection: { last_activity: 1, maintenance_mode: 1 } }
            ),
            db.collection('statistics').findOne(
                { _id: 'global_stats' },
                { projection: { 
                    all_time_claims: 1,
                    total_points_distributed: 1,
                    total_users: 1,
                    total_servers: 1,
                    active_today: 1
                }}
            ),
            db.collection('users')
                .find(
                    { blacklisted: { $ne: true } },
                    { projection: { username: 1, points: 1 } }
                )
                .sort({ points: -1 })
                .limit(10)
                .toArray()
        ]);
        
        // Check bot status
        const lastActivity = config?.last_activity;
        const isOnline = lastActivity && 
            (now - new Date(lastActivity).getTime()) < 300000; // 5 minutes
        
        // Format response
        const responseData = {
            online: isOnline && !config?.maintenance_mode,
            stats: {
                users: stats?.total_users || 0,
                servers: stats?.total_servers || 0,
                points: stats?.total_points_distributed || 0,
                cookies: stats?.all_time_claims || 0,
                active: stats?.active_today || 0
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
        console.error('Status error:', error.message);
        
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