import discord
from discord.ext import commands, tasks
import random
import sqlite3
from datetime import datetime

intents = discord.Intents.default()
intents.messages = True
intents.guilds = True
intents.voice_states = True
intents.message_content = True

bot = commands.Bot(command_prefix='!', intents=intents)
bot.remove_command("help")

# Идентификаторы ролей
casino = 1162180508000731145
odyssy = 1198479407229182102
admin = 1196481123883175986

# Подключение к базе данных SQLite
conn = sqlite3.connect('economy_bot.db')
c = conn.cursor()

c.execute('''CREATE TABLE IF NOT EXISTS balances (
             user_id INTEGER PRIMARY KEY,
             balance INTEGER DEFAULT 0
             )''')

c.execute('''CREATE TABLE IF NOT EXISTS roles_prices (
             role_id INTEGER PRIMARY KEY,
             price INTEGER NOT NULL
             )''')
conn.commit()

# Создаем таблицу для хранения времени, проведенного пользователями в голосовых каналах
c.execute('''CREATE TABLE IF NOT EXISTS voice_time (
             user_id INTEGER,
             channel_id INTEGER,
             time_spent INTEGER,
             PRIMARY KEY (user_id, channel_id)
             )''')
conn.commit()

# Создаем таблицу для хранения накопленных монет
c.execute('''CREATE TABLE IF NOT EXISTS accumulated_coins (
             user_id INTEGER PRIMARY KEY,
             coins_accumulated INTEGER DEFAULT 0
             )''')
conn.commit()

# Функции для работы с базой данных
def update_balance(user_id, amount):
    c.execute('SELECT balance FROM balances WHERE user_id = ?', (user_id,))
    result = c.fetchone()
    if result:
        new_balance = result[0] + amount
        c.execute('UPDATE balances SET balance = ? WHERE user_id = ?', (new_balance, user_id))
    else:
        c.execute('INSERT INTO balances (user_id, balance) VALUES (?, ?)', (user_id, amount))
    conn.commit()

def get_balance(user_id):
    c.execute('SELECT balance FROM balances WHERE user_id = ?', (user_id,))
    result = c.fetchone()
    return result[0] if result else 0

def add_role_price(role_id, price):
    c.execute('INSERT INTO roles_prices (role_id, price) VALUES (?, ?)', (role_id, price))
    conn.commit()

def get_all_roles_prices():
    c.execute('SELECT role_id, price FROM roles_prices')
    return {str(row[0]): row[1] for row in c.fetchall()}

def remove_role_price(role_id):
    c.execute('DELETE FROM roles_prices WHERE role_id = ?', (role_id,))
    conn.commit()

def get_role_by_id(guild, role_id):
    return discord.utils.get(guild.roles, id=role_id)

def update_voice_time(user_id, channel_id, time_spent):
    c.execute('INSERT OR REPLACE INTO voice_time (user_id, channel_id, time_spent) VALUES (?, ?, ?)', (user_id, channel_id, time_spent))
    conn.commit()

def get_voice_time(user_id, channel_id):
    c.execute('SELECT time_spent FROM voice_time WHERE user_id = ? AND channel_id = ?', (user_id, channel_id))
    result = c.fetchone()
    return result[0] if result else 0

def update_accumulated_coins(user_id, amount):
    c.execute('SELECT coins_accumulated FROM accumulated_coins WHERE user_id = ?', (user_id,))
    result = c.fetchone()
    if result:
        new_accumulated = result[0] + amount
        c.execute('UPDATE accumulated_coins SET coins_accumulated = ? WHERE user_id = ?', (new_accumulated, user_id))
    else:
        new_accumulated = amount
        c.execute('INSERT INTO accumulated_coins (user_id, coins_accumulated) VALUES (?, ?)', (user_id, new_accumulated))
    conn.commit()
    return new_accumulated

def get_total_voice_time(user_id):
    c.execute('SELECT SUM(time_spent) FROM voice_time WHERE user_id = ?', (user_id,))
    result = c.fetchone()
    return result[0] if result else 0

roles_prices = get_all_roles_prices()




# События и команды
@bot.event
async def on_ready():
    print(f'Вошли как {bot.user}')
    check_voice_channels.start()


@tasks.loop(minutes=1)
async def check_voice_channels():
    try:
        for guild in bot.guilds:
            for vc in guild.voice_channels:
                for member in vc.members:
                    if not member.bot:
                        time_spent = get_voice_time(member.id, vc.id) + 1  # Добавляем 1 минуту
                        update_voice_time(member.id, vc.id, time_spent)
                        total_time_spent = get_total_voice_time(member.id)
                        
                        # Обновляем баланс и накопленные монеты
                        new_balance = update_balance(member.id, 1)
                        accumulated_coins = update_accumulated_coins(member.id, 1)

                        # Отправляем сообщение каждые 1000 накопленных монет
                        if accumulated_coins % 1000 == 0:
                            await member.send(f'Вы получили 1000 монет за нахождение в голосовом канале.\nВы провели в голосовом канале: {total_time_spent} минут.\nВаш текущий баланс: {new_balance} монет.')
                            print(f'получили 1000 монет {member.name}.')
                        print(f'Выдано 1 монет {member.name} за нахождение в голосовом канале.')
    except Exception as e:
        print(f'Ошибка при проверке голосовых каналов: {e}')
        
@tasks.loop(hours=24)
async def check_role_payments():
    now = datetime.now()
    for role_id, (price, user_id, created_at) in get_all_roles_prices().items():
        if (now - datetime.strptime(created_at, "%Y-%m-%d %H:%M:%S.%f")).days >= 30:
            balance = get_balance(user_id)
            if balance >= 5000:
                update_balance(user_id, -5000)
                c.execute('UPDATE roles_prices SET created_at = ? WHERE role_id = ?', (now, role_id))
                conn.commit()
                user = bot.get_user(user_id)
                if user:
                    await user.send(f'С вас снято 5000 монет за продление роли {role_id}.')
            else:
                guild = bot.get_guild(bot.guilds[0].id)
                role = get_role_by_id(guild, int(role_id))
                if role:
                    await role.delete()
                    remove_role_price(role_id)
                    user = bot.get_user(user_id)
                    if user:
                        await user.send(f'Ваша роль {role_id} была удалена из-за недостатка средств для продления.')


@bot.command()
async def balance(ctx, member: discord.Member = None):
    user_id = member.id if member else ctx.author.id
    balance = get_balance(user_id)

    allowed_roles_ids = [casino, odyssy, admin]
    if any(role.id in allowed_roles_ids for role in ctx.author.roles):
        embed = discord.Embed(title="Баланс", description=f"Баланс у {member.mention if member else ctx.author.mention}: {balance} монет.", color=discord.Color.green())
    else:
        embed = discord.Embed(title="Баланс", description=f"{balance} монет.", color=discord.Color.green())
    
    await ctx.send(embed=embed)

@bot.command()
async def give(ctx, amount: int, member: discord.Member):
    if amount < 0:
        await ctx.send("Нельзя выдавать отрицательное количество монет.")
        return

    allowed_roles_ids = [casino, odyssy, admin]
    if not any(role.id in allowed_roles_ids for role in ctx.author.roles):
        await ctx.send("У вас нет прав на выполнение этой команды.")
        return

    update_balance(member.id, amount)
    await ctx.send(f"Выдано {amount} монет {member.mention}.")

@bot.command()
async def deduct(ctx, amount: int, member: discord.Member):
    if amount < 0:
        await ctx.send("Нельзя вычитать отрицательное количество монет.")
        return

    allowed_roles_ids = [casino, odyssy, admin]
    if any(role.id in allowed_roles_ids for role in ctx.author.roles):
        update_balance(member.id, -amount)
        await ctx.send(embed=discord.Embed(description=f"У {member.mention} вычтено {amount} монет.", color=discord.Color.red()))
    else:
        await ctx.send("У вас нет прав на выполнение этой команды.")

@bot.command()
async def shop(ctx):
    embed = discord.Embed(title="Магазин", description="Доступные роли для покупки", color=discord.Color.blue())
    buttons = []
    for role_id, price in roles_prices.items():
        if isinstance(price, tuple) and len(price) == 3:  # Проверяем, является ли значение кортежем и имеет ли длину 3
            role = get_role_by_id(ctx.guild, int(role_id))
            if role:
                price_value, _, _ = price  # Распаковываем кортеж
                embed.add_field(name=role.name, value=f"{price_value} монет", inline=False)
                button = discord.ui.Button(label=role.name, custom_id=str(role_id), style=discord.ButtonStyle.primary)
                buttons.append(button)

    view = discord.ui.View()
    for button in buttons:
        async def button_callback(interaction: discord.Interaction):
            role_id = int(interaction.custom_id)
            role = get_role_by_id(ctx.guild, role_id)
            if role:
                price = roles_prices.get(str(role_id))
                if price and isinstance(price, tuple) and len(price) == 3:  # Проверяем корректность данных в словаре
                    price_value, _, _ = price
                    if get_balance(interaction.user.id) >= price_value:
                        update_balance(interaction.user.id, -price_value)
                        await interaction.user.add_roles(role)
                        await interaction.response.send_message(f"Вы успешно купили роль {role.name}.", ephemeral=True)
                    else:
                        await interaction.response.send_message("Недостаточно средств для покупки этой роли.", ephemeral=True)
                else:
                    await interaction.response.send_message("Данные о цене роли некорректны.", ephemeral=True)
        button.callback = button_callback
        view.add_item(button)
    
    await ctx.send(embed=embed, view=view)
    


@bot.command()
async def coinflip(ctx, amount: int = None):
    if amount is None:
        await ctx.send(embed=discord.Embed(description="Пожалуйста, укажите количество монет для ставки.", color=discord.Color.red()))
        return

    user_id = ctx.author.id
    balance = get_balance(user_id)
    
    if balance >= amount:
        if random.choice([True, False]):
            update_balance(user_id, amount * 2)  # Умножаем на 2, если игрок выиграл
            await ctx.send(embed=discord.Embed(description=f"Поздравляем! Вы выиграли {amount * 2} монет!", color=discord.Color.green()))
        else:
            update_balance(user_id, -amount)
            await ctx.send(embed=discord.Embed(description=f"К сожалению, вы проиграли {amount} монет.", color=discord.Color.red()))
    else:
        await ctx.send(embed=discord.Embed(description="У вас недостаточно монет для этой ставки.", color=discord.Color.red()))

@bot.command()
@commands.has_any_role('odyssy', 'administrator', 'casino owner')
async def gm(ctx, amount: int, member: discord.Member):
    update_balance(member.id, amount)
    await ctx.send(embed=discord.Embed(description=f"Выдано {amount} монет {member.mention}.", color=discord.Color.green()))

@bot.command()
@commands.has_permissions(administrator=True)
async def ar(ctx, role_name: str, price: int):
    guild = ctx.guild
    existing_role = discord.utils.get(guild.roles, name=role_name)
    
    if existing_role:
        await ctx.send("Роль с таким названием уже существует.")
        return
    
    try:
        new_role = await guild.create_role(name=role_name)
        add_role_price(new_role.id, price)
        roles_prices[str(new_role.id)] = price
        await ctx.send(f"Роль `{role_name}` была успешно добавлена в магазин с ценой {price} монет.")
    except discord.Forbidden:
        await ctx.send("У меня нет разрешения на создание ролей.")
    except ValueError:
        await ctx.send("Цена роли должна быть числом.")

@bot.command()
@commands.has_permissions(administrator=True)
async def rr(ctx, role_name: str):
    guild = ctx.guild
    existing_role = discord.utils.get(guild.roles, name=role_name)
    
    if existing_role:
        await existing_role.delete()
        role_id = str(existing_role.id)
        if role_id in roles_prices:
            remove_role_price(role_id)
            del roles_prices[role_id]
        await ctx.send(f"Роль `{role_name}` была успешно удалена из магазина.")
    else:
        await ctx.send("Роль с таким названием не найдена в магазине.")

# Добавляем игру в рулетку
class RouletteView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)
        self.value = None

    @discord.ui.button(label="Число", style=discord.ButtonStyle.primary)
    async def number_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Введите число от 0 до 36 для ставки:", ephemeral=True)

        def check(m):
            return m.author == interaction.user and m.channel == interaction.channel and m.content.isdigit()

        try:
            msg = await bot.wait_for("message", check=check, timeout=60)
            number = int(msg.content)
            if 0 <= number <= 36:
                await self.handle_bet(interaction, "number", number)
            else:
                await interaction.followup.send("Число должно быть от 0 до 36.", ephemeral=True)
        except asyncio.TimeoutError:
            await interaction.followup.send("Время вышло. Пожалуйста, попробуйте снова.", ephemeral=True)

    @discord.ui.button(label="Черный", style=discord.ButtonStyle.secondary)
    async def black_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_bet(interaction, "color", "черный")

    @discord.ui.button(label="Красный", style=discord.ButtonStyle.danger)
    async def red_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_bet(interaction, "color", "красный")

    async def handle_bet(self, interaction: discord.Interaction, bet_type: str, bet_value):
        user_id = interaction.user.id
        balance = get_balance(user_id)

        await interaction.response.send_message("Введите количество монет для ставки:", ephemeral=True)

        def check(m):
            return m.author == interaction.user and m.channel == interaction.channel and m.content.isdigit()

        try:
            msg = await bot.wait_for("message", check=check, timeout=60)
            amount = int(msg.content)
            if amount > balance:
                await interaction.followup.send("У вас недостаточно монет для этой ставки.", ephemeral=True)
                return

            if bet_type == "number":
                win_number = random.randint(0, 36)
                if bet_value == win_number:
                    update_balance(user_id, amount * 35)
                    await interaction.followup.send(f"Поздравляем! Вы выиграли {amount * 35} монет! Выпавшее число: {win_number}.", ephemeral=True)
                else:
                    update_balance(user_id, -amount)
                    await interaction.followup.send(f"К сожалению, вы проиграли {amount} монет. Выпавшее число: {win_number}.", ephemeral=True)

            elif bet_type == "color":
                win_color = random.choice(["черный", "красный"])
                if bet_value == win_color:
                    update_balance(user_id, amount * 2)
                    await interaction.followup.send(f"Поздравляем! Вы выиграли {amount * 2} монет! Выпавший цвет: {win_color}.", ephemeral=True)
                else:
                    update_balance(user_id, -amount)
                    await interaction.followup.send(f"К сожалению, вы проиграли {amount} монет. Выпавший цвет: {win_color}.", ephemeral=True)

        except asyncio.TimeoutError:
            await interaction.followup.send("Время вышло. Пожалуйста, попробуйте снова.", ephemeral=True)

@bot.command()
async def roulette(ctx):
    view = RouletteView()
    await ctx.send("Выберите тип ставки:", view=view)
    



bot.run("...")

# Закрытие соединения с базой данных при завершении работы бота
@bot.event
async def on_disconnect():
    conn.close()
