// api/status.js - Simple Status Endpoint
import { MongoClient } from 'mongodb';

export default async function handler(req, res) {
    // CORS header
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Access-Control-Allow-Methods', 'GET');
    
    // Only allow GET
    if (req.method !== 'GET') {
        return res.status(405).json({ error: 'Method not allowed' });
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
        
        // Get basic statistics
        const [totalUsers, totalServers, globalStats] = await Promise.all([
            db.collection('users').countDocuments({}),
            db.collection('servers').countDocuments({ enabled: true }),
            db.collection('statistics').findOne(
                { _id: 'global_stats' },
                { projection: { 
                    all_time_claims: 1,
                    total_points_distributed: 1 
                } }
            )
        ]);
        
        // Get top 10 users for leaderboard
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
        
        // Format leaderboard
        const cleanLeaderboard = leaderboard.map((user, index) => ({
            rank: index + 1,
            username: user.username || 'Anonymous',
            points: user.points || 0
        }));
        
        // Get active users today (optional - can remove if not needed)
        const todayStart = new Date();
        todayStart.setHours(0, 0, 0, 0);
        
        const activeToday = await db.collection('users').countDocuments({
            last_active: { $gte: todayStart }
        });
        
        // Response data
        const responseData = {
            online: isOnline && !config?.maintenance_mode,
            totalUsers: totalUsers || 0,
            totalServers: totalServers || 0,
            totalPoints: globalStats?.total_points_distributed || 0,
            totalCookies: globalStats?.all_time_claims || 0,
            activeToday: activeToday || 0,
            lastActivity: isOnline ? lastActivity : null,
            leaderboard: cleanLeaderboard,
            timestamp: new Date().toISOString()
        };
        
        // Simple cache header
        res.setHeader('Cache-Control', 'public, max-age=30');
        
        return res.status(200).json(responseData);
        
    } catch (error) {
        console.error('Status endpoint error:', error.message);
        
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