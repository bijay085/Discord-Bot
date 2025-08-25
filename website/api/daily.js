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
        
        // Convert userId to number - EXACT same as bot
        const userIdNum = parseInt(userId);
        
        // Get point rates from config - EXACT same as bot
        const pointRates = config?.point_rates || {
            daily: 2,
            invite: 2,
            boost: 5,
            vote: 2,
            feedback_bonus: 1,
            perfect_rating_bonus: 0
        };
        
        // Get or create user - EXACT structure as bot
        let user = await db.collection('users').findOne({ user_id: userIdNum });
        
        const now = new Date();
        
        // Log for debugging
        console.log(`Daily claim attempt for user ${userIdNum} at ${now.toISOString()}`);
        if (user?.daily_claimed) {
            console.log(`Last claim was at: ${new Date(user.daily_claimed).toISOString()}`);
        }
        
        if (!user) {
            // Create new user with EXACT same structure as bot
            user = {
                user_id: userIdNum,
                username: username,
                points: 0,
                total_earned: 0,
                total_spent: 0,
                trust_score: 50,
                cookie_claims: {},
                total_claims: 0,
                weekly_claims: 0,
                daily_claimed: null,
                invite_count: 0,
                invited_users: [],
                pending_invites: 0,
                verified_invites: 0,
                fake_invites: 0,
                blacklisted: false,
                blacklist_expires: null,
                warnings: [],
                daily_claims: {},
                last_claim: null,
                account_created: now,
                first_seen: now,
                last_active: now,
                preferences: {
                    dm_notifications: true,
                    claim_confirmations: true,
                    feedback_reminders: true
                },
                statistics: {
                    feedback_streak: 0,
                    perfect_ratings: 0,
                    favorite_cookie: null,
                    divine_gambles: 0,
                    divine_wins: 0,
                    divine_losses: 0,
                    rob_wins: 0,
                    rob_losses: 0,
                    rob_winnings: 0,
                    rob_losses_amount: 0,
                    times_robbed: 0,
                    amount_stolen_from: 0,
                    slots_played: 0,
                    slots_won: 0,
                    slots_lost: 0,
                    slots_profit: 0,
                    slots_biggest_win: 0,
                    slots_current_streak: 0,
                    slots_best_streak: 0
                },
                game_stats: {
                    slots: { played: 0, won: 0, profit: 0 },
                    bet: { played: 0, won: 0, profit: 0 },
                    rob: { attempts: 0, successes: 0, profit: 0 },
                    gamble: { attempts: 0, wins: 0 }
                }
            };
            
            await db.collection('users').insertOne(user);
        }
        
        // Check if blacklisted - EXACT same as bot
        if (user.blacklisted) {
            if (user.blacklist_expires && new Date(user.blacklist_expires) > now) {
                const timeLeft = new Date(user.blacklist_expires) - now;
                const daysLeft = Math.floor(timeLeft / (1000 * 60 * 60 * 24));
                
                return res.status(403).json({ 
                    error: `You are blacklisted for ${daysLeft} more days!`,
                    blacklist_expires: user.blacklist_expires
                });
            } else if (!user.blacklist_expires) {
                return res.status(403).json({ 
                    error: 'You are permanently blacklisted!'
                });
            }
        }
        
        // Check cooldown - EXACT same as bot (24 hours)
        if (user.daily_claimed) {
            const lastClaim = new Date(user.daily_claimed);
            const cooldownHours = config?.cooldown_settings?.daily_hours || 24;
            const cooldownMs = cooldownHours * 60 * 60 * 1000;
            const timeSinceLastClaim = now - lastClaim;
            
            // Check if 24 hours have passed
            if (timeSinceLastClaim < cooldownMs) {
                const timeLeft = cooldownMs - timeSinceLastClaim;
                const hoursLeft = Math.floor(timeLeft / (1000 * 60 * 60));
                const minutesLeft = Math.floor((timeLeft % (1000 * 60 * 60)) / (1000 * 60));
                
                return res.status(429).json({ 
                    error: 'Daily already claimed!',
                    timeLeft: `${hoursLeft}h ${minutesLeft}m`,
                    nextClaim: new Date(lastClaim.getTime() + cooldownMs),
                    currentBalance: user.points,
                    lastClaim: lastClaim,
                    debug: {
                        lastClaimTime: lastClaim.toISOString(),
                        currentTime: now.toISOString(),
                        timeSinceLastClaim: Math.floor(timeSinceLastClaim / 1000 / 60) + ' minutes',
                        cooldownHours: cooldownHours
                    }
                });
            }
        }
        
        // WEBSITE GIVES ONLY BASE POINTS - NO BONUSES
        // Role bonuses require Discord authentication which we don't have
        const basePoints = pointRates.daily; // This is 2 points
        const totalPoints = basePoints; // ONLY base points, no bonuses
        
        // Update user - EXACT same fields as bot
        const updateResult = await db.collection('users').updateOne(
            { user_id: userIdNum },
            {
                $set: {
                    daily_claimed: now,
                    last_active: now,
                    username: username // Update username if changed
                },
                $inc: {
                    points: totalPoints,
                    total_earned: totalPoints
                }
            }
        );
        
        if (updateResult.matchedCount === 0) {
            return res.status(500).json({ 
                error: 'Failed to update user data. Please try again.' 
            });
        }
        
        // Log transaction - EXACT same as bot
        await db.collection('transactions').insertOne({
            user_id: userIdNum,
            type: 'daily_claim',
            amount: totalPoints,
            description: `Daily claim (web) - ${totalPoints} points`,
            timestamp: now,
            source: 'website'
        });
        
        // Update analytics - EXACT same as bot
        await db.collection('analytics').insertOne({
            type: 'command_usage',
            command: 'daily',
            user_id: userIdNum,
            guild_id: null, // No guild for web claims
            timestamp: now,
            source: 'website'
        });
        
        // Update global statistics - EXACT same as bot
        await db.collection('statistics').updateOne(
            { _id: 'global_stats' },
            {
                $inc: {
                    total_points_distributed: totalPoints,
                    daily_claims_total: 1
                },
                $set: {
                    last_updated: now
                }
            },
            { upsert: true }
        );
        
        // Build response with embed-like structure
        const embed = {
            title: '💰 Daily Points Claimed!',
            description: `You received **${totalPoints} points**!`,
            color: 0x00ff00,
            fields: [
                {
                    name: '💳 New Balance',
                    value: `${user.points + totalPoints} points`,
                    inline: true
                },
                {
                    name: '⏰ Next Claim',
                    value: `In 24 hours`,
                    inline: true
                },
                {
                    name: '💡 Tip',
                    value: `Use the Discord bot for role bonuses!`,
                    inline: false
                }
            ],
            footer: {
                text: `Total Earned: ${user.total_earned + totalPoints} points • Web claim gives base points only`
            }
        };
        
        return res.status(200).json({
            success: true,
            points_earned: totalPoints,
            new_balance: user.points + totalPoints,
            total_earned: user.total_earned + totalPoints,
            next_claim: new Date(now.getTime() + (24 * 60 * 60 * 1000)),
            message: `Successfully claimed ${totalPoints} points! (Web claims give base points only. Use Discord bot for role bonuses!)`,
            breakdown: {
                base: basePoints,
                web_bonus: 0, // No web bonus
                role_bonus: 0  // No role bonus (requires Discord auth)
            },
            embed: embed
        });
        
    } catch (error) {
        console.error('Error processing daily claim:', error);
        
        // Log error to analytics
        try {
            await db.collection('analytics').insertOne({
                type: 'error',
                source: 'website_daily',
                error: error.message,
                user_id: parseInt(userId),
                timestamp: new Date()
            });
        } catch (e) {
            // Silent fail for analytics
        }
        
        return res.status(500).json({ 
            error: 'Database error. Please try again.',
            details: process.env.NODE_ENV === 'development' ? error.message : undefined
        });
    } finally {
        if (client) {
            await client.close();
        }
    }
}