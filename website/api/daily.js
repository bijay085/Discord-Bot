import { MongoClient } from 'mongodb';

export default async function handler(req, res) {
    // Enable CORS
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Access-Control-Allow-Methods', 'GET, POST');
    
    if (req.method !== 'POST') {
        return res.status(405).json({ error: 'Method not allowed' });
    }
    
    const { userId, username } = req.body;
    
    if (!userId || !username) {
        return res.status(400).json({ error: 'User ID and username required' });
    }
    
    let client;
    
    try {
        client = new MongoClient(process.env.MONGODB_URI);
        await client.connect();
        
        const db = client.db(process.env.DATABASE_NAME || 'discord_bot');
        
        // Check if bot is online
        const config = await db.collection('config').findOne({ _id: 'bot_config' });
        const lastActivity = config?.last_activity;
        const isOnline = lastActivity && 
            (new Date() - new Date(lastActivity)) < (5 * 60 * 1000);
        
        if (!isOnline) {
            return res.status(503).json({ 
                error: 'Bot is offline! Please wait for bot to come online.' 
            });
        }
        
        // Get or create user
        let user = await db.collection('users').findOne({ user_id: parseInt(userId) });
        
        if (!user) {
            // Create new user
            user = {
                user_id: parseInt(userId),
                username: username,
                points: 0,
                total_earned: 0,
                total_spent: 0,
                trust_score: 50,
                account_created: new Date(),
                first_seen: new Date(),
                last_active: new Date(),
                daily_claimed: null,
                total_claims: 0,
                web_user: true
            };
            await db.collection('users').insertOne(user);
        }
        
        // Check if already claimed today
        if (user.daily_claimed) {
            const lastClaim = new Date(user.daily_claimed);
            const now = new Date();
            
            // Check if it's the same day (UTC)
            const lastClaimDay = new Date(lastClaim).setUTCHours(0,0,0,0);
            const today = new Date(now).setUTCHours(0,0,0,0);
            
            if (lastClaimDay === today) {
                const tomorrow = new Date(today);
                tomorrow.setDate(tomorrow.getDate() + 1);
                const hoursLeft = Math.floor((tomorrow - now) / (1000 * 60 * 60));
                const minutesLeft = Math.floor(((tomorrow - now) % (1000 * 60 * 60)) / (1000 * 60));
                
                return res.status(429).json({ 
                    error: 'Already claimed today!',
                    timeLeft: `${hoursLeft}h ${minutesLeft}m`,
                    nextClaim: tomorrow
                });
            }
        }
        
        // Give daily points (web bonus!)
        const baseDaily = 2;
        const webBonus = 3; // Extra for using website
        const totalPoints = baseDaily + webBonus;
        
        // Update user
        await db.collection('users').updateOne(
            { user_id: parseInt(userId) },
            {
                $set: {
                    daily_claimed: new Date(),
                    last_active: new Date(),
                    username: username // Update username
                },
                $inc: {
                    points: totalPoints,
                    total_earned: totalPoints
                }
            }
        );
        
        // Log the claim
        await db.collection('analytics').insertOne({
            type: 'web_daily_claim',
            user_id: parseInt(userId),
            username: username,
            points_earned: totalPoints,
            timestamp: new Date()
        });
        
        return res.status(200).json({
            success: true,
            points_earned: totalPoints,
            new_balance: user.points + totalPoints,
            message: `You got ${totalPoints} points! (${baseDaily} base + ${webBonus} web bonus)`
        });
        
    } catch (error) {
        console.error('Error processing daily claim:', error);
        return res.status(500).json({ 
            error: 'Database error. Please try again.' 
        });
    } finally {
        if (client) {
            await client.close();
        }
    }
}