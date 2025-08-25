import { MongoClient } from 'mongodb';

export default async function handler(req, res) {
    // Enable CORS
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Access-Control-Allow-Methods', 'GET, POST');
    
    let client;
    
    try {
        // Connect to MongoDB
        client = new MongoClient(process.env.MONGODB_URI);
        await client.connect();
        
        const db = client.db(process.env.DATABASE_NAME || 'discord_bot');
        
        // Get bot config
        const config = await db.collection('config').findOne({ _id: 'bot_config' });
        
        // Check if bot is online (last activity within 5 minutes)
        const lastActivity = config?.last_activity;
        const isOnline = lastActivity && 
            (new Date() - new Date(lastActivity)) < (5 * 60 * 1000);
        
        // Get statistics
        const totalUsers = await db.collection('users').countDocuments({});
        const now = new Date();
        const todayStart = new Date(now.setUTCHours(0, 0, 0, 0));
        
        const activeToday = await db.collection('users').countDocuments({
            last_active: { $gte: todayStart }
        });
        
        const totalServers = await db.collection('servers').countDocuments({});
        const enabledServers = await db.collection('servers').countDocuments({ enabled: true });
        
        const stats = await db.collection('statistics').findOne({ _id: 'global_stats' });
        
        // REMOVED cookie stock fetching - not needed anymore
        
        // Get leaderboard - top 10 users by points
        const topUsers = await db.collection('users')
            .find(
                { 
                    blacklisted: { $ne: true },
                    points: { $gt: 0 }
                },
                { 
                    projection: { 
                        username: 1, 
                        points: 1, 
                        trust_score: 1,
                        total_claims: 1,
                        user_id: 1
                    } 
                }
            )
            .sort({ points: -1 })
            .limit(10)
            .toArray();
        
        // Format leaderboard
        const leaderboard = topUsers.map((user, index) => ({
            rank: index + 1,
            username: user.username || 'Unknown User',
            points: user.points,
            trust_score: user.trust_score || 50,
            total_claims: user.total_claims || 0,
            user_id: user.user_id
        }));
        
        // Get recent activity - last 10 claims
        const recentClaims = await db.collection('cookie_logs')
            .find({})
            .sort({ timestamp: -1 })
            .limit(10)
            .toArray();
        
        // If no cookie_logs, try to get from users' last_claim
        let recentActivity = [];
        
        if (recentClaims.length > 0) {
            recentActivity = await Promise.all(recentClaims.map(async (claim) => {
                const user = await db.collection('users').findOne(
                    { user_id: claim.user_id },
                    { projection: { username: 1 } }
                );
                
                const timeAgo = Math.floor((new Date() - new Date(claim.timestamp)) / 60000);
                return `${user?.username || 'Unknown'} claimed ${claim.cookie_type} (${timeAgo}m ago)`;
            }));
        } else {
            // Fallback to users with recent claims
            const usersWithClaims = await db.collection('users')
                .find({ 
                    'last_claim.date': { $exists: true } 
                })
                .sort({ 'last_claim.date': -1 })
                .limit(5)
                .toArray();
            
            recentActivity = usersWithClaims.map(user => {
                if (user.last_claim?.date) {
                    const timeAgo = Math.floor((new Date() - new Date(user.last_claim.date)) / 60000);
                    return `${user.username} claimed ${user.last_claim.type || 'cookie'} (${timeAgo}m ago)`;
                }
                return null;
            }).filter(Boolean);
        }
        
        // Get daily claims count
        const dailyClaimsToday = await db.collection('users').countDocuments({
            daily_claimed: { $gte: todayStart }
        });
        
        // REMOVED game stats - not needed for status page
        
        // Check if a specific user exists (if userId query param provided)
        let userData = null;
        if (req.query.userId) {
            const userIdNum = parseInt(req.query.userId);
            const user = await db.collection('users').findOne({ user_id: userIdNum });
            
            if (user) {
                userData = {
                    exists: true,
                    username: user.username,
                    points: user.points,
                    trust_score: user.trust_score,
                    total_claims: user.total_claims,
                    daily_claimed: user.daily_claimed,
                    blacklisted: user.blacklisted,
                    can_claim_daily: !user.daily_claimed || 
                        (new Date() - new Date(user.daily_claimed)) >= (24 * 60 * 60 * 1000)
                };
            } else {
                userData = { exists: false };
            }
        }
        
        // Build response
        const response = {
            online: isOnline,
            lastSeen: lastActivity,
            totalUsers,
            activeUsers: activeToday,
            totalServers,
            enabledServers,
            totalCookies: stats?.all_time_claims || 0,
            dailyClaimsToday,
            leaderboard,
            recentActivity,
            uptime: config?.current_uptime || null,
            maintenanceMode: config?.maintenance_mode || false,
            botVersion: config?.version || '2.0.0',
            timestamp: new Date()
        };
        
        // Add user data if requested
        if (userData) {
            response.userData = userData;
        }
        
        // Send response
        res.status(200).json(response);
        
    } catch (error) {
        console.error('Database error:', error);
        res.status(500).json({ 
            error: 'Database connection failed',
            online: false,
            details: process.env.NODE_ENV === 'development' ? error.message : undefined
        });
    } finally {
        if (client) {
            await client.close();
        }
    }
}