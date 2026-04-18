import asyncio
import os
import aiohttp
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.enums import ParseMode
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.exceptions import TelegramBadRequest
from aiogram.types.web_app_info import WebAppInfo
from aiogram.types import MenuButtonWebApp, WebAppInfo

# Загружаем переменные
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
TONAPI_KEY = os.getenv("TONAPI_KEY")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

TARGET_PROFIT_TON = 0.5
CHECK_INTERVAL = 30

# Настройки снайпера
MY_ID = 1198371921
sent_alerts = []

# Коллекция подарков
COLLECTIONS = {
    "Snoop Dogg": {"name": "Spoon Dog", "address": "EQAoJw7BpOcBD3y9voMuEQ-qhS3K4gtM-6EePLxkzk8iSifX", "icon": "🐶"},
    "Candy Cane": {"name": "Candy Cane", "address": "EQDLM65t0shS7gZAg0lMltGHYhsU94PzsMJHhYibmRV7kdUs", "icon": "🍭"},
    "Chill Flame": {"name": "Chill Flame", "address": "EQBlBJ4n01pmYez5VPd8Wo598s8agbQCyVOjucXKxLDAi9r7", "icon": "🔥"},
    "Ginger Cookie": {"name": "Ginger Cookies", "address": "EQBCe75G0AhjqC64B7H_BHP0wgfONX_x98rszmsEwndDVAjG", "icon": "🍪"},
}

# Универсальная функция запроса к TON
async def get_collection_info(address):
    url = f"https://tonapi.io/v2/nfts/collections/{address}"
    headers = {"Authorization": f"Bearer {TONAPI_KEY}"}
    async with aiohttp.ClientSession(headers=headers) as session:
        try:
            async with session.get(url, timeout=10) as response:
                if response.status == 200:
                    data = await response.json()
                    stats = data.get("stats", {})
                    floor = stats.get("floor_price")
                    return {
                        "floor": floor / 1_000_000_000 if floor else 0, #"floor": floor / 1_000_000_000 if floor else None,
                        "items": stats.get("items_count", 0)
                    }
                return {"floor": 0, "items": 0}
        except:
            return {"floor": 0, "items": 0}

def get_main_menu(name=None, price=None, items=None, img=None):
    builder = InlineKeyboardBuilder()
    BASE_URL = "https://likemeepwn.github.io/my_app/"

    if name:
        # Режим после выбора конкретного подарка
        safe_name = name.replace(" ", "%20")
        web_app_url = f"{BASE_URL}?name={safe_name}&price={price}&items={items}&img={img}"
        builder.row(types.InlineKeyboardButton(text=f"📊 Открыть {name} (Web)", web_app=WebAppInfo(url=web_app_url)))
        builder.row(types.InlineKeyboardButton(text="⬅️ Назад к списку", callback_data="back_to_menu"))
    else:
        # Режим главного меню
        builder.row(types.InlineKeyboardButton(text="🌐 Открыть весь мониторинг", web_app=WebAppInfo(url=BASE_URL)))
        # Кнопки по 2 в ряд
        for key, item in COLLECTIONS.items():
            builder.add(types.InlineKeyboardButton(text=f"{item.get('icon')} {item['name']}", callback_data=f"check_{key}"))
        builder.adjust(1, 2)
    
    return builder.as_markup()

# --- ОБРАБОТЧИКИ СОБЫТИЙ ---
        
@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    await message.answer("🚀 **NFTintel: Мониторинг запущен**\nВыбери коллекцию:", reply_markup=get_main_menu(), parse_mode=ParseMode.MARKDOWN)

@dp.callback_query(F.data.startswith("check_"))
async def process_check(callback: types.CallbackQuery):
    coll_key = callback.data.split("_")[1]
    info = COLLECTIONS.get(coll_key)
    if not info: return

    try: await callback.answer("⏳ Загрузка...")
    except TelegramBadRequest: pass
    
    data = await get_collection_info(info['address'])
    floor = data['floor'] if data else "Н/Д"
    text = f"📊 **Аналитика:** {info['name']}\n💰 Floor: `{floor} TON`"
    await callback.message.delete()
    await callback.message.answer(text, reply_markup=get_main_menu(info['name'], floor, data['items'], None), parse_mode=ParseMode.MARKDOWN)

@dp.callback_query(F.data == "back_to_menu")
async def back_to_menu(callback: types.CallbackQuery):
    try: await callback.message.delete()
    except: pass
    await callback.message.answer("🚀 Выбери коллекцию:", reply_markup=get_main_menu(), parse_mode=ParseMode.MARKDOWN)

# --- СНАЙПЕР ---

async def sniper_mode():
    print("🎯 Снайпер запущен: режим охоты за листингами...")
    
    FEES = 0.20 # 20% на комиссии
    
    while True:
        for key, item in COLLECTIONS.items():
            try:
                # 1. Сначала узнаем текущий Floor коллекции для сравнения
                coll_data = await get_collection_info(item['address'])
                market_floor = coll_data['floor'] if coll_data else 0 #market_floor = coll_data['floor'] if coll_data and isinstance(coll_data['floor'], (int, float)) else None
                
                # Если цена не найдена (0), переходим к следующему предмету
                if market_floor <= 0:
                    continue

                # 2. Ищем новые листинги
                url = f"https://tonapi.io/v2/nfts/collections/{item['address']}/items?limit=10"
                headers = {"Authorization": f"Bearer {TONAPI_KEY}"}
                
                async with aiohttp.ClientSession(headers=headers) as session:
                    async with session.get(url, timeout=10) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            for nft in data.get('nft_items', []):
                                address = nft['address']
                                sale = nft.get('sale')
                                
                                # Если NFT продается и мы еще не присылали об этом алерт
                                if sale and sale.get('price') and address not in sent_alerts:
                                    price_ton = int(sale['price']['value']) / 1_000_000_000
                                    
                                    # ЛОГИКА: если цена лота ниже текущего Floor хотя бы на 10%
                                    if price_ton < market_floor * 0.9 and price_ton < 15.0:
                                        # Определяем маркетплейс
                                        market_name = sale.get('market', {}).get('name', 'Market')
                                        link = f"https://fragment.com/nft/{address}" if "fragment" in market_name.lower() else f"https://getgems.io/nft/{address}"

                                        clean_profit = (market_floor * (1 - FEES)) - price_ton

                                        text = (
                                            f"🚨 **СНАЙПЕРСКИЙ ВЫСТРЕЛ!**\n"
                                            f"📦 `{nft['metadata']['name']}`\n"
                                            f"💰 Цена: `{price_ton} TON` (Floor: {market_floor})\n"
                                            f"🏪 Маркет: {market_name}\n"
                                            f"📈 Чистый профит: `~{clean_profit:.2f} TON`\n\n"
                                            f"🔗 [ОТКРЫТЬ ЛОТ]({link})"
                                        )
                                        await bot.send_message(MY_ID, text, parse_mode=ParseMode.MARKDOWN)
                                        sent_alerts.append(address)
                                        if len(sent_alerts) > 50: sent_alerts.pop(0)
                                        
            except Exception as e: print(f"Ошибка снайпера: {e}")
        
        # Для снайпера 10-15 секунд — оптимально. 
        # Слишком часто (1 сек) — TonAPI забанит за нагрузку.
        await asyncio.sleep(15)

async def main():
    # Устанавливаем кнопку приложения рядом с полем ввода
    await bot.set_chat_menu_button(menu_button=MenuButtonWebApp(text="NFTintel App", web_app=WebAppInfo(url="https://likemeepwn.github.io/my_app/")))
    
    # Запуск фонового сканера
    asyncio.create_task(sniper_mode())
    print("🚀 Бот и Сканер запущены!")


    print("🚀 Кнопка приложения установлена!")

    # Проверка ключей в консоли при старте
    print(f"--- ПРОВЕРКА НАСТРОЕК ---")
    print(f"Token бота: {'✅ Ок' if BOT_TOKEN else '❌ ОТСУТСТВУЕТ'}")
    print(f"TonAPI ключ: {'✅ Ок' if TONAPI_KEY else '❌ ОТСУТСТВУЕТ'}")
    print(f"------------------------")
    print("🚀 NFTintel запущен и готов к работе...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())