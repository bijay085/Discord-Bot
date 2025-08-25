import { MongoClient } from 'mongodb';

export default async function handler(req, res) {
    // Enable CORS
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Access-Control-Allow-Methods', 'GET');
    
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
        const totalServers = await db.collection('servers').countDocuments({});
        const stats = await db.collection('statistics').findOne({ _id: 'global_stats' });
        
        // Get cookie stock (from config)
        const cookieStock = {};
        if (config?.default_cookies) {
            // You'd need to store stock counts in DB when bot updates them
            for (const [type, data] of Object.entries(config.default_cookies)) {
                cookieStock[type] = data.stock || 0;
            }
        }
        
        // Get recent activity (last 5 claims)
        const recentClaims = await db.collection('users')
            .find({ 'last_claim.date': { $exists: true } })
            .sort({ 'last_claim.date': -1 })
            .limit(5)
            .toArray();
        
        const recentActivity = recentClaims.map(user => {
            const date = new Date(user.last_claim.date);
            const timeAgo = Math.floor((new Date() - date) / 60000);
            return `${user.username} claimed ${user.last_claim.type} (${timeAgo}m ago)`;
        });
        
        // Send response
        res.status(200).json({
            online: isOnline,
            lastSeen: lastActivity,
            totalUsers,
            totalServers,
            totalCookies: stats?.all_time_claims || 0,
            cookieStock,
            recentActivity,
            uptime: config?.current_uptime || null
        });
        
    } catch (error) {
        console.error('Database error:', error);
        res.status(500).json({ 
            error: 'Database connection failed',
            online: false 
        });
    } finally {
        if (client) {
            await client.close();
        }
    }
}