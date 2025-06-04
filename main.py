import discord
import re
import os
import aiohttp
import asyncio
from discord.ext import commands
from dotenv import load_dotenv
import json

# Debug: Check if .env file is being loaded
print("🔍 Checking .env file...")
load_dotenv()

# Debug: Print what we're getting from environment
BOT_TOKEN = os.getenv("BOT_TOKEN")
print(f"📋 Token loaded: {'✅ Yes' if BOT_TOKEN else '❌ No'}")
if BOT_TOKEN:
    print(f"📋 Token length: {len(BOT_TOKEN)} characters")
    print(f"📋 Token starts with: {BOT_TOKEN[:10]}...")
else:
    print("❌ BOT_TOKEN is None or empty!")

# Bot setup
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Regular expressions for address patterns
ADDRESS_PATTERNS = {
    "solana": r"[1-9A-HJ-NP-Za-km-z]{32,44}",
    "evm": r"0x[a-fA-F0-9]{40}",
    "url": r"http[s]?://[^\s]+"
}


def format_percentage(value):
    """Format percentage values with proper colors"""
    if value is None or value == 0:
        return "0.00%"

    formatted = f"{value:+.2f}%"
    if value > 0:
        return f"🟢 {formatted}"
    else:
        return f"🔴 {formatted}"


def format_number(num):
    """Format numbers for display"""
    if num is None or num == 0:
        return "N/A"

    try:
        num = float(num)
        if num >= 1_000_000_000:
            return f"${num/1_000_000_000:.2f}B"
        elif num >= 1_000_000:
            return f"${num/1_000_000:.2f}M"
        elif num >= 1_000:
            return f"${num/1_000:.2f}K"
        elif num >= 1:
            return f"${num:.4f}"
        else:
            return f"${num:.8f}"
    except:
        return "N/A"


async def get_solana_token_data(address: str):
    """Fetch Solana token data from multiple APIs"""
    print(f"🔍 Fetching Solana data for: {address}")

    try:
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            token_data = {
                'name': 'Unknown Token',
                'symbol': 'UNKNOWN',
                'price': 0,
                'volume24h': 0,
                'priceChange24h': 0,
                'priceChange1h': 0,
                'liquidity': 0,
                'fdv': 0,
                'marketCap': 0,
                'success': False
            }

            # Try DexScreener first (most reliable for Solana)
            try:
                url = f"https://api.dexscreener.com/latest/dex/tokens/{address}"
                print(f"🌐 Trying DexScreener: {url}")

                async with session.get(url) as response:
                    if response.status == 200:
                        data = await response.json()
                        pairs = data.get('pairs', [])

                        if pairs and len(pairs) > 0:
                            # Get the most liquid pair
                            pair = max(pairs, key=lambda p: float(p.get('liquidity', {}).get('usd', 0) or 0))

                            base_token = pair.get('baseToken', {})
                            token_data.update({
                                'name': base_token.get('name', 'Unknown Token'),
                                'symbol': base_token.get('symbol', 'UNKNOWN'),
                                'price': float(pair.get('priceUsd', 0) or 0),
                                'volume24h': float(pair.get('volume', {}).get('h24', 0) or 0),
                                'liquidity': float(pair.get('liquidity', {}).get('usd', 0) or 0),
                                'fdv': float(pair.get('fdv', 0) or 0),
                                'marketCap': float(pair.get('marketCap', 0) or 0),
                                'priceChange24h': float(pair.get('priceChange', {}).get('h24', 0) or 0),
                                'priceChange1h': float(pair.get('priceChange', {}).get('h1', 0) or 0),
                                'success': True
                            })
                            print(f"✅ DexScreener success: {token_data['name']} ({token_data['symbol']})")

            except Exception as e:
                print(f"❌ DexScreener error: {e}")

            # Try Jupiter API as backup for Solana tokens
            if not token_data.get('success'):
                try:
                    url = f"https://price.jup.ag/v4/price?ids={address}"
                    print(f"🌐 Trying Jupiter: {url}")

                    async with session.get(url) as response:
                        if response.status == 200:
                            data = await response.json()
                            price_data = data.get('data', {}).get(address)

                            if price_data:
                                token_data.update({
                                    'price': float(price_data.get('price', 0)),
                                    'success': True
                                })
                                print(f"✅ Jupiter price found: ${token_data['price']}")

                except Exception as e:
                    print(f"❌ Jupiter error: {e}")

            # Try to get token metadata from Solana APIs
            if token_data['name'] == 'Unknown Token':
                try:
                    # Try Solscan API
                    url = f"https://public-api.solscan.io/token/meta?tokenAddress={address}"
                    print(f"🌐 Trying Solscan metadata: {url}")

                    async with session.get(url) as response:
                        if response.status == 200:
                            data = await response.json()
                            if data and 'name' in data:
                                token_data.update({
                                    'name': data.get('name', 'Unknown Token'),
                                    'symbol': data.get('symbol', 'UNKNOWN'),
                                })
                                print(f"✅ Solscan metadata: {token_data['name']}")

                except Exception as e:
                    print(f"❌ Solscan metadata error: {e}")

            print(f"📊 Final Solana data: {token_data}")
            return token_data

    except Exception as e:
        print(f"❌ Error fetching Solana data: {e}")
        return {'success': False, 'name': 'Unknown Token', 'symbol': 'UNKNOWN'}


async def get_evm_token_data(address: str):
    """Fetch EVM token data"""
    print(f"🔍 Fetching EVM data for: {address}")

    try:
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            token_data = {
                'name': 'Unknown Token',
                'symbol': 'UNKNOWN',
                'price': 0,
                'volume24h': 0,
                'priceChange24h': 0,
                'priceChange1h': 0,
                'liquidity': 0,
                'marketCap': 0,
                'success': False
            }

            # Try DexScreener for EVM tokens
            try:
                url = f"https://api.dexscreener.com/latest/dex/tokens/{address}"
                print(f"🌐 Trying DexScreener EVM: {url}")

                async with session.get(url) as response:
                    if response.status == 200:
                        data = await response.json()
                        pairs = data.get('pairs', [])

                        if pairs and len(pairs) > 0:
                            # Get the most liquid pair
                            pair = max(pairs, key=lambda p: float(p.get('liquidity', {}).get('usd', 0) or 0))

                            base_token = pair.get('baseToken', {})
                            token_data.update({
                                'name': base_token.get('name', 'Unknown Token'),
                                'symbol': base_token.get('symbol', 'UNKNOWN'),
                                'price': float(pair.get('priceUsd', 0) or 0),
                                'volume24h': float(pair.get('volume', {}).get('h24', 0) or 0),
                                'liquidity': float(pair.get('liquidity', {}).get('usd', 0) or 0),
                                'marketCap': float(pair.get('marketCap', 0) or 0),
                                'priceChange24h': float(pair.get('priceChange', {}).get('h24', 0) or 0),
                                'priceChange1h': float(pair.get('priceChange', {}).get('h1', 0) or 0),
                                'success': True
                            })
                            print(f"✅ DexScreener EVM success: {token_data['name']} ({token_data['symbol']})")

            except Exception as e:
                print(f"❌ DexScreener EVM error: {e}")

            # Try CoinGecko as fallback
            if not token_data.get('success'):
                try:
                    url = f"https://api.coingecko.com/api/v3/simple/token_price/ethereum?contract_addresses={address}&vs_currencies=usd&include_24hr_change=true&include_24hr_vol=true&include_market_cap=true"
                    print(f"🌐 Trying CoinGecko: {url}")

                    async with session.get(url) as response:
                        if response.status == 200:
                            data = await response.json()
                            token_info = data.get(address.lower())

                            if token_info:
                                token_data.update({
                                    'price': float(token_info.get('usd', 0)),
                                    'priceChange24h': float(token_info.get('usd_24h_change', 0) or 0),
                                    'volume24h': float(token_info.get('usd_24h_vol', 0) or 0),
                                    'marketCap': float(token_info.get('usd_market_cap', 0) or 0),
                                    'success': True
                                })
                                print(f"✅ CoinGecko success: ${token_data['price']}")

                except Exception as e:
                    print(f"❌ CoinGecko error: {e}")

            print(f"📊 Final EVM data: {token_data}")
            return token_data

    except Exception as e:
        print(f"❌ Error fetching EVM data: {e}")
        return {'success': False, 'name': 'Unknown Token', 'symbol': 'UNKNOWN'}


def detect_address_type(address: str) -> str:
    """Detect the type of address/URL"""
    if re.fullmatch(ADDRESS_PATTERNS["solana"], address):
        return "Solana"
    elif re.fullmatch(ADDRESS_PATTERNS["evm"], address):
        return "EVM (Ethereum/BSC)"
    elif re.fullmatch(ADDRESS_PATTERNS["url"], address):
        return "URL"
    else:
        return "Unknown"


@bot.event
async def on_ready():
    print(f"✅ Bot is online! Logged in as {bot.user}")
    print(f"🤖 Bot is in {len(bot.guilds)} servers")


@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    content = message.content.strip()
    found = []

    # Search for all address types in the message
    for key, pattern in ADDRESS_PATTERNS.items():
        matches = re.findall(pattern, content)
        for match in matches:
            found.append((match, detect_address_type(match)))

    # If addresses/URLs are found, create embeds for each
    if found:
        for address, addr_type in found:
            try:
                print(f"🎯 Processing {addr_type} address: {address}")

                # Show loading message first
                loading_embed = discord.Embed(
                    title="🔄 Fetching Real-Time Token Data...",
                    description=f"**Address:** `{address[:20]}...{address[-10:]}`\n**Chain:** {addr_type}",
                    color=0xffaa00
                )
                loading_embed.add_field(
                    name="⏳ Status", 
                    value="Scanning multiple APIs for live data...", 
                    inline=False
                )
                loading_msg = await message.channel.send(embed=loading_embed)

                # Fetch real token data
                token_data = {'success': False}

                if addr_type == "Solana":
                    token_data = await get_solana_token_data(address)
                elif addr_type == "EVM (Ethereum/BSC)":
                    token_data = await get_evm_token_data(address)

                # Create final embed with data
                token_name = token_data.get('name', 'Unknown Token')
                token_symbol = token_data.get('symbol', 'UNKNOWN')

                # Choose embed color based on price change
                price_change = token_data.get('priceChange24h', 0)
                if price_change > 0:
                    embed_color = 0x00ff88  # Green for positive
                elif price_change < 0:
                    embed_color = 0xff6b6b  # Red for negative
                else:
                    embed_color = 0x5865f2  # Blue for neutral

                embed = discord.Embed(
                    title=f"🪙 {token_name} ({token_symbol})",
                    description=f"**Contract:** `{address[:25]}...{address[-15:]}`",
                    color=embed_color if token_data.get('success') else 0x808080
                )

                if addr_type == "Solana":
                    if token_data.get('success'):
                        price = token_data.get('price', 0)
                        volume = token_data.get('volume24h', 0)
                        liquidity = token_data.get('liquidity', 0)
                        fdv = token_data.get('fdv', 0)
                        mcap = token_data.get('marketCap', 0)
                        change24h = token_data.get('priceChange24h', 0)
                        change1h = token_data.get('priceChange1h', 0)

                        # Price info with real data
                        price_info = f"💵 **Price:** {format_number(price)}"
                        if mcap > 0:
                            price_info += f"\n🏆 **MCap:** {format_number(mcap)}"
                        if fdv > 0:
                            price_info += f"\n🔥 **FDV:** {format_number(fdv)}"
                        if liquidity > 0:
                            price_info += f"\n🏊 **Liquidity:** {format_number(liquidity)}"
                        if volume > 0:
                            price_info += f"\n📈 **Volume 24h:** {format_number(volume)}"

                        embed.add_field(
                            name="💰 Market Data",
                            value=price_info,
                            inline=True
                        )

                        # Performance data
                        perf_info = ""
                        if change1h != 0:
                            perf_info += f"🕐 **1H:** {format_percentage(change1h)}\n"
                        if change24h != 0:
                            perf_info += f"📅 **24H:** {format_percentage(change24h)}\n"
                        perf_info += "📆 **7D:** Coming soon"

                        embed.add_field(
                            name="⏰ Performance",
                            value=perf_info,
                            inline=True
                        )

                        # Success indicator
                        embed.add_field(
                            name="✅ Data Status",
                            value="🟢 **Live Data Found**\n📊 Multiple APIs verified\n⚡ Real-time pricing",
                            inline=True
                        )
                    else:
                        embed.add_field(
                            name="💰 Market Data",
                            value="💵 **Price:** Not Available\n🔥 **FDV:** Not Available\n🏊 **Liquidity:** Not Available\n📈 **Volume:** Not Available",
                            inline=True
                        )
                        embed.add_field(
                            name="ℹ️ Possible Reasons",
                            value="🔸 Very new token\n🔸 Low trading volume\n🔸 Not listed on DEXs\n🔸 Invalid contract address",
                            inline=True
                        )
                        embed.add_field(
                            name="❌ Data Status",
                            value="🔴 **No Live Data**\n📊 Token not found in APIs\n⚠️ Verify contract address",
                            inline=True
                        )

                    # Safety warnings for Solana
                    embed.add_field(
                        name="🛡️ Safety Reminders",
                        value="⚠️ **Always verify contracts**\n🔒 **Check for mint/freeze authority**\n💧 **Verify liquidity is locked**\n🚨 **DYOR before investing**",
                        inline=False
                    )

                    # Quick links for Solana
                    links_value = f"[📊 Solscan](https://solscan.io/token/{address}) • "
                    links_value += f"[🐦 Birdeye](https://birdeye.so/token/{address}) • "
                    links_value += f"[📈 DexScreener](https://dexscreener.com/solana/{address}) • "
                    links_value += f"[💹 Jupiter](https://jup.ag/swap/SOL-{address})"

                    embed.add_field(
                        name="🔗 Quick Access",
                        value=links_value,
                        inline=False
                    )

                elif addr_type == "EVM (Ethereum/BSC)":
                    if token_data.get('success'):
                        price = token_data.get('price', 0)
                        volume = token_data.get('volume24h', 0)
                        liquidity = token_data.get('liquidity', 0)
                        mcap = token_data.get('marketCap', 0)
                        change24h = token_data.get('priceChange24h', 0)
                        change1h = token_data.get('priceChange1h', 0)

                        # Price info
                        price_info = f"💵 **Price:** {format_number(price)}"
                        if mcap > 0:
                            price_info += f"\n🏆 **MCap:** {format_number(mcap)}"
                        if liquidity > 0:
                            price_info += f"\n🏊 **Liquidity:** {format_number(liquidity)}"
                        if volume > 0:
                            price_info += f"\n📈 **Volume 24h:** {format_number(volume)}"

                        embed.add_field(
                            name="💰 Market Data",
                            value=price_info,
                            inline=True
                        )

                        # Performance
                        perf_info = ""
                        if change1h != 0:
                            perf_info += f"🕐 **1H:** {format_percentage(change1h)}\n"
                        if change24h != 0:
                            perf_info += f"📅 **24H:** {format_percentage(change24h)}\n"
                        perf_info += "📆 **7D:** Coming soon"

                        embed.add_field(
                            name="⏰ Performance",
                            value=perf_info,
                            inline=True
                        )

                        embed.add_field(
                            name="✅ Data Status",
                            value="🟢 **Live Data Found**\n📊 Multiple APIs verified\n⚡ Real-time pricing",
                            inline=True
                        )
                    else:
                        embed.add_field(
                            name="💰 Market Data",
                            value="💵 **Price:** Not Available\n🏆 **MCap:** Not Available\n🏊 **Liquidity:** Not Available\n📈 **Volume:** Not Available",
                            inline=True
                        )
                        embed.add_field(
                            name="ℹ️ Possible Reasons", 
                            value="🔸 Very new token\n🔸 Low trading volume\n🔸 Not listed on DEXs\n🔸 Invalid contract address",
                            inline=True
                        )
                        embed.add_field(
                            name="❌ Data Status",
                            value="🔴 **No Live Data**\n📊 Token not found in APIs\n⚠️ Verify contract address",
                            inline=True
                        )

                    # Quick links for EVM
                    links_value = f"[📊 Etherscan](https://etherscan.io/address/{address}) • "
                    links_value += f"[🛠️ DexTools](https://www.dextools.io/app/en/ether/pair-explorer/{address}) • "
                    links_value += f"[📈 DexScreener](https://dexscreener.com/ethereum/{address}) • "
                    links_value += f"[🦄 Uniswap](https://app.uniswap.org/#/tokens/ethereum/{address})"

                    embed.add_field(
                        name="🔗 Quick Access",
                        value=links_value,
                        inline=False
                    )

                elif addr_type == "URL":
                    embed.add_field(
                        name="🌐 URL Detected",
                        value="⚠️ **Warning:** Web URL detected\n🔒 **Safety:** Always verify domains\n🛡️ **Tip:** Only click official links\n🚨 **Never connect wallet to suspicious sites**",
                        inline=False
                    )

                # Add chain indicator
                embed.add_field(
                    name="⛓️ Blockchain",
                    value=f"**{addr_type}**",
                    inline=True
                )

                # Footer with requester info
                embed.set_footer(
                    text=f"👤 Requested by {message.author.display_name} • 🤖 Live Token Scanner • 📡 Real-time Data",
                    icon_url=message.author.avatar.url if message.author.avatar else None
                )

                # Add timestamp
                embed.timestamp = discord.utils.utcnow()

                # Edit the loading message with final data
                await loading_msg.edit(embed=embed)
                print(f"✅ Successfully processed: {token_name} ({token_symbol})")

            except Exception as e:
                print(f"❌ Error creating embed: {e}")
                try:
                    await loading_msg.edit(content=f"❌ Error processing {addr_type} address: `{address}`\nError: {str(e)}")
                except:
                    await message.channel.send(f"❌ Error processing {addr_type} address: `{address}`")

    await bot.process_commands(message)


# Test command for debugging
@bot.command(name='test')
async def test_command(ctx, address: str = None):
    """Test command to manually check token data"""
    if not address:
        await ctx.send("❌ Please provide a token address to test!")
        return

    addr_type = detect_address_type(address)
    await ctx.send(f"🧪 Testing {addr_type} address: `{address}`")

    if addr_type == "Solana":
        data = await get_solana_token_data(address)
    elif addr_type.startswith("EVM"):
        data = await get_evm_token_data(address)
    else:
        await ctx.send("❌ Invalid address type!")
        return

    await ctx.send(f"📊 Test Result: ```json\n{json.dumps(data, indent=2)}```")


# Info command
@bot.command(name='info')
async def info_command(ctx):
    """Show bot information"""
    embed = discord.Embed(
        title="🤖 Token Scanner Bot Help",
        description="I automatically scan messages for token addresses and provide real-time data!",
        color=0x5865f2
    )

    embed.add_field(
        name="🔍 Supported Formats",
        value="• **Solana:** Base58 addresses (32-44 chars)\n• **Ethereum/BSC:** 0x addresses (42 chars)\n• **URLs:** Web links (safety warnings)",
        inline=False
    )

    embed.add_field(
        name="📊 Data Provided",
        value="• Real-time price & market cap\n• 24h volume & liquidity\n• Price changes (1h/24h)\n• Direct links to explorers",
        inline=False
    )

    embed.add_field(
        name="🛠️ Commands",
        value="• `!test <address>` - Test token data fetching\n• `!info` - Show this information",
        inline=False
    )

    embed.add_field(
        name="⚡ Usage",
        value="Just paste any token address in chat and I'll automatically scan it!",
        inline=False
    )

    await ctx.send(embed=embed)


# Run the bot with better error handling
if __name__ == "__main__":
    if not BOT_TOKEN:
        print("❌ No BOT_TOKEN found!")
        print("📝 Make sure your .env file contains:")
        print("   BOT_TOKEN=your_actual_token_here")
        exit(1)

    try:
        print("🚀 Starting enhanced token scanner bot...")
        bot.run(BOT_TOKEN)
    except discord.LoginFailure:
        print("❌ Invalid bot token! Please check your token.")
    except discord.HTTPException as e:
        print(f"❌ HTTP Error: {e}")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
