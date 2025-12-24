#!/usr/bin/env python3
"""
DARK KITCHEN ANSAN - Telegram Bot
Версия 2.3 - Исправлены уведомления администраторам и сохранение кнопок
"""

import os
import logging
import re
import time
import sys
import socket
from datetime import datetime
from typing import Dict, List, Any
from pathlib import Path

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters
)

from dotenv import load_dotenv

# Загружаем .env файл
load_dotenv()

BOT_TOKEN = "8447150166:AAEqWqBJOBYK5pgVp7euAx-7q3mF5iOz6Ko" 
GROUP_ID = os.getenv('GROUP_ID', '-5045934907')  # ID группы администраторов

# Проверяем GROUP_ID
if not GROUP_ID or GROUP_ID == '-5045934907':
    print("⚠️ ВНИМАНИЕ: GROUP_ID не установлен или имеет значение по умолчанию!")
    print("💡 Создайте файл .env и добавьте: GROUP_ID='-ваш_ид_группы'")

# Время работы
WORK_TIME = "с 22:00 по 10:00 утра"
HANGOVER_TIME = "с 5:00 по 8:00"
DELIVERY_COST = 4000
DELIVERY_AREA = "Ансан"
CURRENCY = "won"

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ==================== ТЕКСТЫ ====================
TEXTS = {
    'welcome': f"""🍖 <b>Добро пожаловать в Dark_kitchen_Ansan!</b>

⏰ Мы работаем <b>{WORK_TIME}</b>
🍺 Также у нас есть похмельное время <b>{HANGOVER_TIME}</b> когда рассол и огурчики <b>БЕСПЛАТНО</b> Смех!!!

🚚 Доставка осуществляется по <b>{DELIVERY_AREA}</b> и составляет <b>{DELIVERY_COST}{CURRENCY}</b>

😊 Мы рады и благодарны за то что выбираете нас спасибо!!!""",
    
    'main_menu': "🏠 <b>Главное меню</b>\nВыберите действие:",
    
    'menu_title': "🍽️ <b>Наше меню</b>",
    
    'categories': {
        'first': "🍲 Первые блюда (всё по 12.000won)",
        'second': "🍛 Вторые блюда (всё по 12.000won)", 
        'extra': "🥖 Дополнительно",
        'hangover': "🍺 Похмельное меню"
    },
    
    'dishes': {
        # Первые блюда
        'borsch': {"name": "Борщ", "price": 12000, "cat": "first"},
        'solyanka': {"name": "Солянка", "price": 12000, "cat": "first"},
        'puktyay': {"name": "Пуктяй", "price": 12000, "cat": "first"},
        'siruyaktyamuri': {"name": "Сируяктямури", "price": 12000, "cat": "first"},
        
        # Вторые блюда
        'lagman': {"name": "Лагман", "price": 12000, "cat": "second"},
        'gulyash': {"name": "Гуляш", "price": 12000, "cat": "second"},
        
        # Дополнительно
        'bread': {"name": "Хлеб", "price": 1000, "cat": "extra"},
        'porridge': {"name": "Каша", "price": 1000, "cat": "extra"},
        
        # Похмельное меню
        'pickle': {"name": "Рассол", "price": 0, "cat": "hangover"},
        'cucumbers': {"name": "Огурчики", "price": 0, "cat": "hangover"}
    }
}

# ==================== БАЗА ДАННЫХ ====================
class Database:
    """Простая база данных в памяти"""
    def __init__(self):
        self.user_data = {}  # {user_id: {'cart': {...}, 'last_order': order_id, ...}}
        self.orders = {}     # {order_id: order_data}
        self.order_counter = 0
    
    def get_user(self, user_id: int) -> Dict:
        """Получить данные пользователя"""
        if user_id not in self.user_data:
            self.user_data[user_id] = {'cart': {}, 'last_order': None, 'phone': None, 'address': None, 'address_photo': None}
        return self.user_data[user_id]
    
    def get_cart(self, user_id: int) -> Dict:
        """Получить корзину пользователя"""
        user = self.get_user(user_id)
        return user.get('cart', {})
    
    def add_to_cart(self, user_id: int, dish_id: str, dish_name: str, price: int, quantity: int = 1) -> Dict:
        """Добавить блюдо в корзину"""
        cart = self.get_cart(user_id)
        
        if dish_id in cart:
            cart[dish_id]['quantity'] += quantity
        else:
            cart[dish_id] = {
                'name': dish_name,
                'price': price,
                'quantity': quantity
            }
        
        self.user_data[user_id]['cart'] = cart
        return cart
    
    def remove_from_cart(self, user_id: int, dish_id: str) -> Dict:
        """Удалить блюдо из корзины"""
        cart = self.get_cart(user_id)
        if dish_id in cart:
            del cart[dish_id]
        return cart
    
    def clear_cart(self, user_id: int) -> Dict:
        """Очистить корзину"""
        if user_id in self.user_data:
            self.user_data[user_id]['cart'] = {}
        return {}
    
    def create_order(self, user_id: int, username: str, phone: str, address: str, cart: Dict, address_photo: str = None) -> str:
        """Создать новый заказ"""
        self.order_counter += 1
        order_id = f"ORDER_{self.order_counter:06d}"
        
        # Рассчитываем сумму
        order_total = sum(item['price'] * item['quantity'] for item in cart.values())
        final_total = order_total + DELIVERY_COST
        
        # Сохраняем заказ
        self.orders[order_id] = {
            'user_id': user_id,
            'username': username,
            'phone': phone,
            'address': address,
            'address_photo': address_photo,
            'cart': cart.copy(),
            'total': order_total,
            'final_total': final_total,
            'status': 'waiting_payment',
            'created_at': time.time(),
            'payment_status': 'pending',
            'screenshot_sent': False,
            'address_photo_sent': False
        }
        
        # Сохраняем ID последнего заказа и данные пользователя
        user_data = self.get_user(user_id)
        user_data['last_order'] = order_id
        user_data['phone'] = phone
        user_data['address'] = address
        user_data['address_photo'] = address_photo
        
        # Очищаем корзину
        self.clear_cart(user_id)
        
        logger.info(f"Создан заказ {order_id} для пользователя {user_id}")
        return order_id
    
    def get_order(self, order_id: str) -> Dict:
        """Получить заказ по ID"""
        return self.orders.get(order_id)
    
    def get_user_last_order(self, user_id: int) -> str:
        """Получить ID последнего заказа пользователя"""
        user = self.get_user(user_id)
        return user.get('last_order')
    
    def update_order_status(self, order_id: str, status: str, payment_status: str = None):
        """Обновить статус заказа"""
        if order_id in self.orders:
            self.orders[order_id]['status'] = status
            if payment_status:
                self.orders[order_id]['payment_status'] = payment_status
            return True
        return False
    
    def mark_screenshot_sent(self, order_id: str):
        """Отметить, что скриншот отправлен"""
        if order_id in self.orders:
            self.orders[order_id]['screenshot_sent'] = True
            return True
        return False
    
    def mark_address_photo_sent(self, order_id: str):
        """Отметить, что фото адреса отправлено"""
        if order_id in self.orders:
            self.orders[order_id]['address_photo_sent'] = True
            return True
        return False

# Создаем глобальную базу данных
db = Database()

# ==================== КЛАВИАТУРЫ ====================
def get_main_menu_keyboard():
    """Клавиатура главного меню"""
    keyboard = [
        [InlineKeyboardButton("🍽️ Посмотреть меню", callback_data="view_menu")],
        [InlineKeyboardButton("🛒 Корзина", callback_data="view_cart")],
        [InlineKeyboardButton("📞 Способы заказа", callback_data="order_methods")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_categories_keyboard():
    """Клавиатура категорий меню"""
    keyboard = [
        [InlineKeyboardButton(TEXTS['categories']['first'], callback_data="cat_first")],
        [InlineKeyboardButton(TEXTS['categories']['second'], callback_data="cat_second")],
        [InlineKeyboardButton(TEXTS['categories']['extra'], callback_data="cat_extra")],
        [InlineKeyboardButton(TEXTS['categories']['hangover'], callback_data="cat_hangover")],
        [InlineKeyboardButton("🛒 Корзина", callback_data="view_cart")],
        [InlineKeyboardButton("🔙 Назад", callback_data="main_menu")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_dishes_keyboard(category: str):
    """Клавиатура блюд по категории"""
    keyboard = []
    for dish_id, dish in TEXTS['dishes'].items():
        if dish['cat'] == category:
            price_text = f" ({dish['price']}{CURRENCY})" if dish['price'] > 0 else " (БЕСПЛАТНО)"
            button_text = f"{dish['name']}{price_text}"
            keyboard.append([InlineKeyboardButton(button_text, callback_data=f"dish_{dish_id}")])
    
    keyboard.append([
        InlineKeyboardButton("🛒 Корзина", callback_data="view_cart"),
        InlineKeyboardButton("🍽️ Меню", callback_data="menu_categories")
    ])
    return InlineKeyboardMarkup(keyboard)

def get_cart_keyboard(cart: Dict, with_checkout: bool = True):
    """Клавиатура корзины"""
    keyboard = []
    
    for dish_id, item in cart.items():
        keyboard.append([
            InlineKeyboardButton(
                f"❌ {item['name']} x{item['quantity']}", 
                callback_data=f"remove_{dish_id}"
            )
        ])
    
    if cart:
        if with_checkout:
            keyboard.append([
                InlineKeyboardButton("🗑️ Очистить корзину", callback_data="clear_cart"),
                InlineKeyboardButton("✅ Оформить заказ", callback_data="checkout")
            ])
        else:
            keyboard.append([
                InlineKeyboardButton("🗑️ Очистить корзину", callback_data="clear_cart")
            ])
    else:
        keyboard.append([
            InlineKeyboardButton("🍽️ В меню", callback_data="view_menu"),
            InlineKeyboardButton("🏠 Главное", callback_data="main_menu")
        ])
    
    keyboard.append([InlineKeyboardButton("🔙 Главное меню", callback_data="main_menu")])
    return InlineKeyboardMarkup(keyboard)

def get_back_keyboard(back_to: str = "main_menu"):
    """Простая кнопка Назад"""
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data=back_to)]]
    return InlineKeyboardMarkup(keyboard)

def get_admin_order_keyboard(order_id: str, status: str = 'pending'):
    """Клавиатура для администратора с учетом статуса"""
    if status == 'confirmed':
        keyboard = [
            [
                InlineKeyboardButton("✅ ОПЛАТА ПОДТВЕРЖДЕНА", callback_data="noop"),
                InlineKeyboardButton("👨‍🍳 ЗАКАЗ ГОТОВИТСЯ", callback_data="noop")
            ]
        ]
    elif status == 'rejected':
        keyboard = [
            [
                InlineKeyboardButton("❌ ОПЛАТА ОТКЛОНЕНА", callback_data="noop"),
                InlineKeyboardButton("📞 СВЯЗАТЬСЯ С КЛИЕНТОМ", callback_data="noop")
            ]
        ]
    else:
        keyboard = [
            [
                InlineKeyboardButton("✅ Подтвердить оплату", callback_data=f"admin_confirm_{order_id}"),
                InlineKeyboardButton("❌ Отклонить платеж", callback_data=f"admin_reject_{order_id}")
            ]
        ]
    return InlineKeyboardMarkup(keyboard)

# ==================== ЗАЩИТА ОТ МНОГОКРАТНОГО ЗАПУСКА ====================
def check_single_instance():
    """Проверка, что бот запущен только в одном экземпляре"""
    try:
        lock_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        lock_socket.bind(('localhost', 9999))
        logger.info("🔒 Проверка блокировки: OK - бот может быть запущен")
        return lock_socket
    except socket.error:
        logger.error("❌ Бот уже запущен в другом процессе!")
        logger.error("💡 Завершите предыдущий процесс и запустите снова")
        sys.exit(1)

# ==================== УВЕДОМЛЕНИЯ АДМИНИСТРАТОРАМ ====================
async def send_admin_notification(context: ContextTypes.DEFAULT_TYPE, admin_user_id: int, order_id: str, action: str):
    """Отправка уведомления администратору в личный чат"""
    try:
        order = db.get_order(order_id)
        if not order:
            return
        
        if action == 'confirm':
            message = f"""✅ <b>Вы подтвердили оплату для заказа {order_id}</b>

👤 Клиент: {order['username']}
📞 Телефон: {order['phone']}
💰 Сумма: {order['final_total']}{CURRENCY}
🏠 Адрес: {order['address'][:100]}{'...' if len(order['address']) > 100 else ''}
⏰ Время: {datetime.now().strftime('%H:%M:%S %d.%m.%Y')}

✅ <i>Клиент уведомлен о начале приготовления заказа.</i>"""
        
        elif action == 'reject':
            message = f"""❌ <b>Вы отклонили оплату для заказа {order_id}</b>

👤 Клиент: {order['username']}
📞 Телефон: {order['phone']}
💰 Сумма: {order['final_total']}{CURRENCY}
🏠 Адрес: {order['address'][:100]}{'...' if len(order['address']) > 100 else ''}
⏰ Время: {datetime.now().strftime('%H:%M:%S %d.%m.%Y')}

⚠️ <i>Клиент уведомлен об отклонении платежа.</i>"""
        
        await context.bot.send_message(
            chat_id=admin_user_id,
            text=message,
            parse_mode='HTML'
        )
        logger.info(f"✅ Уведомление отправлено администратору {admin_user_id}")
        
    except Exception as e:
        logger.error(f"❌ Ошибка отправки уведомления администратору: {e}")

# ==================== ОБРАБОТЧИКИ ====================
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка команды /start"""
    logger.info(f"Команда /start от пользователя {update.effective_user.id}")
    
    await update.message.reply_text(
        TEXTS['welcome'],
        reply_markup=get_main_menu_keyboard(),
        parse_mode='HTML'
    )

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка всех callback запросов"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    data = query.data
    
    logger.info(f"Callback от {user_id}: {data}")
    
    # Главное меню
    if data == "main_menu":
        await query.edit_message_text(
            TEXTS['main_menu'],
            reply_markup=get_main_menu_keyboard(),
            parse_mode='HTML'
        )
    
    # Просмотр меню
    elif data == "view_menu" or data == "menu_categories":
        await query.edit_message_text(
            TEXTS['menu_title'],
            reply_markup=get_categories_keyboard(),
            parse_mode='HTML'
        )
    
    # Категории меню
    elif data.startswith("cat_"):
        category = data[4:]  # first, second, extra, hangover
        category_name = TEXTS['categories'][category]
        
        await query.edit_message_text(
            f"🍽️ <b>{category_name}</b>\nВыберите блюдо:",
            reply_markup=get_dishes_keyboard(category),
            parse_mode='HTML'
        )
    
    # Выбор блюда
    elif data.startswith("dish_"):
        dish_id = data[5:]
        dish = TEXTS['dishes'].get(dish_id)
        
        if dish:
            context.user_data['selected_dish'] = dish_id
            context.user_data['quantity'] = 1
            
            price_text = f"{dish['price']}{CURRENCY}" if dish['price'] > 0 else "БЕСПЛАТНО"
            
            keyboard = [
                [
                    InlineKeyboardButton("➖", callback_data="dec_quantity"),
                    InlineKeyboardButton("1", callback_data="noop"),
                    InlineKeyboardButton("➕", callback_data="inc_quantity")
                ],
                [
                    InlineKeyboardButton("✅ Добавить в корзину", callback_data="add_to_cart"),
                    InlineKeyboardButton("🛒 В корзину", callback_data="view_cart")
                ],
                [
                    InlineKeyboardButton("🍽️ Меню", callback_data="menu_categories"),
                    InlineKeyboardButton("🏠 Главное", callback_data="main_menu")
                ]
            ]
            
            dish_name = dish['name']
            await query.edit_message_text(
                f"🍽️ <b>{dish_name}</b>\n\n"
                f"💰 Цена: <b>{price_text}</b>\n\n"
                f"Выберите количество:",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='HTML'
            )
    
    # Увеличение количества
    elif data == "inc_quantity":
        if 'selected_dish' in context.user_data:
            current_qty = context.user_data.get('quantity', 1)
            context.user_data['quantity'] = current_qty + 1
            await update_quantity_display(query, context)
    
    # Уменьшение количества
    elif data == "dec_quantity":
        if 'selected_dish' in context.user_data:
            current_qty = context.user_data.get('quantity', 1)
            if current_qty > 1:
                context.user_data['quantity'] = current_qty - 1
                await update_quantity_display(query, context)
    
    # Кнопка без действия
    elif data == "noop":
        return
    
    # Добавление в корзину
    elif data == "add_to_cart":
        if 'selected_dish' in context.user_data:
            dish_id = context.user_data['selected_dish']
            dish = TEXTS['dishes'].get(dish_id)
            quantity = context.user_data.get('quantity', 1)
            
            if dish:
                dish_name = dish['name']
                db.add_to_cart(user_id, dish_id, dish_name, dish['price'], quantity)
                
                # Очищаем контекст
                if 'selected_dish' in context.user_data:
                    del context.user_data['selected_dish']
                if 'quantity' in context.user_data:
                    del context.user_data['quantity']
                
                await query.edit_message_text(
                    f"✅ <b>{dish_name}</b> x{quantity} добавлено в корзину!",
                    reply_markup=get_back_keyboard(f"cat_{dish['cat']}"),
                    parse_mode='HTML'
                )
    
    # Корзина
    elif data == "view_cart":
        cart = db.get_cart(user_id)
        
        if not cart:
            await query.edit_message_text(
                "🛒 Корзина пуста",
                reply_markup=get_cart_keyboard(cart, with_checkout=False)
            )
            return
        
        cart_text = "<b>🛒 Ваша корзина:</b>\n\n"
        total = 0
        
        for item_id, item in cart.items():
            item_total = item['price'] * item['quantity']
            total += item_total
            cart_text += f"• {item['name']} x{item['quantity']} - {item_total}{CURRENCY}\n"
        
        cart_text += f"\n💰 <b>Итого: {total}{CURRENCY}</b>"
        cart_text += f"\n🚚 <b>Доставка: {DELIVERY_COST}{CURRENCY}</b>"
        cart_text += f"\n💵 <b>К оплате: {total + DELIVERY_COST}{CURRENCY}</b>"
        
        await query.edit_message_text(
            cart_text,
            reply_markup=get_cart_keyboard(cart),
            parse_mode='HTML'
        )
    
    # Удаление из корзины
    elif data.startswith("remove_"):
        dish_id = data[7:]
        db.remove_from_cart(user_id, dish_id)
        
        cart = db.get_cart(user_id)
        
        if not cart:
            await query.edit_message_text(
                "🛒 Корзина пуста",
                reply_markup=get_cart_keyboard(cart, with_checkout=False)
            )
            return
        
        cart_text = "<b>🛒 Ваша корзина:</b>\n\n"
        total = 0
        
        for item_id, item in cart.items():
            item_total = item['price'] * item['quantity']
            total += item_total
            cart_text += f"• {item['name']} x{item['quantity']} - {item_total}{CURRENCY}\n"
        
        cart_text += f"\n💰 <b>Итого: {total}{CURRENCY}</b>"
        cart_text += f"\n🚚 <b>Доставка: {DELIVERY_COST}{CURRENCY}</b>"
        cart_text += f"\n💵 <b>К оплате: {total + DELIVERY_COST}{CURRENCY}</b>"
        
        await query.edit_message_text(
            cart_text,
            reply_markup=get_cart_keyboard(cart),
            parse_mode='HTML'
        )
    
    # Очистка корзины
    elif data == "clear_cart":
        db.clear_cart(user_id)
        await query.edit_message_text(
            "🗑️ Корзина очищена",
            reply_markup=get_cart_keyboard({}, with_checkout=False)
        )
    
    # Оформление заказа
    elif data == "checkout":
        cart = db.get_cart(user_id)
        
        if not cart:
            await query.edit_message_text(
                "🛒 Корзина пуста",
                reply_markup=get_cart_keyboard(cart, with_checkout=False)
            )
            return
        
        context.user_data['checkout_step'] = 'phone'
        context.user_data['username'] = query.from_user.username or query.from_user.first_name
        
        user_data = db.get_user(user_id)
        saved_phone = user_data.get('phone')
        
        if saved_phone:
            keyboard = [
                [InlineKeyboardButton(f"📞 Использовать: {saved_phone}", callback_data="use_saved_phone")],
                [InlineKeyboardButton("📝 Ввести новый телефон", callback_data="enter_new_phone")]
            ]
            
            await query.edit_message_text(
                f"📞 <b>У вас есть сохраненный телефон:</b>\n\n"
                f"{saved_phone}\n\n"
                f"Хотите использовать его?",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='HTML'
            )
        else:
            await query.edit_message_text(
                "📞 <b>Введите ваш телефон:</b>\n\n"
                "Пример: 01012345678 или 010-1234-5678",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 Назад", callback_data="view_cart")]
                ]),
                parse_mode='HTML'
            )
    
    # Использовать сохраненный телефон
    elif data == "use_saved_phone":
        user_id = query.from_user.id
        user_data = db.get_user(user_id)
        saved_phone = user_data.get('phone')
        
        if saved_phone:
            context.user_data['phone'] = saved_phone
            context.user_data['checkout_step'] = 'address'
            
            saved_address = user_data.get('address')
            
            if saved_address:
                keyboard = [
                    [InlineKeyboardButton(f"🏠 Использовать: {saved_address}", callback_data="use_saved_address")],
                    [InlineKeyboardButton("📝 Ввести новый адрес", callback_data="enter_new_address")]
                ]
                
                await query.edit_message_text(
                    f"🏠 <b>У вас есть сохраненный адрес:</b>\n\n"
                    f"{saved_address}\n\n"
                    f"Хотите использовать его?",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='HTML'
                )
            else:
                await query.edit_message_text(
                    "🏠 <b>Выберите способ указания адреса:</b>\n\n"
                    "1️⃣ Написать адрес текстом\n"
                    "2️⃣ Отправить фото адреса (скриншот карты или текста)",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("📝 Ввести адрес текстом", callback_data="enter_address_text")],
                        [InlineKeyboardButton("📸 Отправить фото адреса", callback_data="enter_address_photo")],
                        [InlineKeyboardButton("🔙 Назад", callback_data="view_cart")]
                    ]),
                    parse_mode='HTML'
                )
    
    # Ввести новый телефон
    elif data == "enter_new_phone":
        context.user_data['checkout_step'] = 'phone'
        await query.edit_message_text(
            "📞 <b>Введите ваш телефон:</b>\n\n"
            "Пример: 01012345678 или 010-1234-5678",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Назад", callback_data="view_cart")]
            ]),
            parse_mode='HTML'
        )
    
    # Использовать сохраненный адрес
    elif data == "use_saved_address":
        user_id = query.from_user.id
        user_data = db.get_user(user_id)
        saved_address = user_data.get('address')
        
        if saved_address:
            context.user_data['address'] = saved_address
            
            username = context.user_data['username']
            phone = context.user_data['phone']
            address = saved_address
            cart = db.get_cart(user_id)
            
            if not cart:
                await query.edit_message_text("❌ Корзина пуста!")
                return
            
            order_id = db.create_order(user_id, username, phone, address, cart)
            order = db.get_order(order_id)
            
            await complete_order_creation(query, context, order_id, order)
    
    # Ввести адрес текстом
    elif data == "enter_address_text":
        context.user_data['checkout_step'] = 'address_text'
        await query.edit_message_text(
            "🏠 <b>Введите адрес доставки текстом:</b>\n\n"
            "Пример:\n"
            "Ансан, район Танвон-гу, улица Хвачжон, дом 123, квартира 456\n"
            "Код домофона: 1234#\n\n"
            "<i>После ввода адреса заказ будет автоматически оформлен</i>",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Назад", callback_data="view_cart")]
            ]),
            parse_mode='HTML'
        )
    
    # Ввести адрес фото
    elif data == "enter_address_photo":
        context.user_data['checkout_step'] = 'address_photo'
        await query.edit_message_text(
            "📸 <b>Отправьте фото адреса:</b>\n\n"
            "Можно отправить:\n"
            "• Скриншот из Naver Maps/Google Maps\n"
            "• Фото текста с адресом\n"
            "• Фото вашего дома/подъезда\n\n"
            "<i>После отправки фото заказ будет автоматически оформлен</i>",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Назад", callback_data="view_cart")]
            ]),
            parse_mode='HTML'
        )
    
    # Ввести новый адрес
    elif data == "enter_new_address":
        context.user_data['checkout_step'] = 'address_choice'
        await query.edit_message_text(
            "🏠 <b>Выберите способ указания адреса:</b>\n\n"
            "1️⃣ Написать адрес текстом\n"
            "2️⃣ Отправить фото адреса (скриншот карты или текста)",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📝 Ввести адрес текстом", callback_data="enter_address_text")],
                [InlineKeyboardButton("📸 Отправить фото адреса", callback_data="enter_address_photo")],
                [InlineKeyboardButton("🔙 Назад", callback_data="view_cart")]
            ]),
            parse_mode='HTML'
        )
    
    # Добавить текстовый адрес к фото
    elif data == "add_address_text":
        context.user_data['checkout_step'] = 'add_text_to_photo'
        await query.edit_message_text(
            "📝 <b>Введите текстовый адрес или комментарий:</b>\n\n"
            "Пример:\n"
            "Ансан, район Танвон-гу, улица Хвачжон, дом 123, квартира 456\n"
            "Код домофона: 1234#\n\n"
            "<i>Это поможет курьеру быстрее найти ваш адрес</i>",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⏩ Пропустить", callback_data="complete_with_photo_only")]
            ]),
            parse_mode='HTML'
        )
    
    # Завершить с только фото
    elif data == "complete_with_photo_only":
        if 'address_photo' in context.user_data:
            user_id = query.from_user.id
            username = context.user_data['username']
            phone = context.user_data['phone']
            address_photo = context.user_data['address_photo']
            cart = db.get_cart(user_id)
            
            if not cart:
                await query.edit_message_text("❌ Корзина пуста!")
                return
            
            # Создаем заказ с фото адреса
            order_id = db.create_order(user_id, username, phone, "Адрес на фото (см. фото ниже)", cart, address_photo)
            order = db.get_order(order_id)
            
            # ОТПРАВЛЯЕМ ФОТО АДРЕСА В ГРУППУ АДМИНИСТРАТОРОВ
            await send_address_photo_to_admin(context, order_id, order, address_photo)
            
            await complete_order_creation(query, context, order_id, order)
    
    # Способы заказа
    elif data == "order_methods":
        keyboard = [
            [InlineKeyboardButton("☎️ Заказать по телефону", callback_data="order_phone")],
            [InlineKeyboardButton("🤖 Заказать через бота", callback_data="order_bot")],
            [InlineKeyboardButton("🛒 Корзина", callback_data="view_cart")],
            [InlineKeyboardButton("🔙 Назад", callback_data="main_menu")]
        ]
        
        await query.edit_message_text(
            "📞 <b>Способы заказа:</b>",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML'
        )
    
    elif data == "order_phone":
        phone_text = f"""📱 <b>Заказ по телефону:</b>

Вы можете позвонить нам по номеру:
<b>010-8361-6165</b>

📞 Работаем {WORK_TIME}
🍺 Похмельное время: {HANGOVER_TIME}"""
        
        await query.edit_message_text(
            phone_text,
            reply_markup=get_back_keyboard("order_methods"),
            parse_mode='HTML'
        )
    
    elif data == "order_bot":
        await query.edit_message_text(
            "🤖 <b>Заказ через бота:</b>\n\n"
            "1. Выберите блюда из меню 🍽️\n"
            "2. Добавьте в корзину 🛒\n"
            "3. Оформите заказ ✅\n"
            "4. Оплатите по реквизитам 💳\n"
            "5. Отправьте скриншот 📸\n\n"
            "<i>Администратор получит ваш заказ сразу!</i>",
            reply_markup=get_back_keyboard("order_methods"),
            parse_mode='HTML'
        )
    
    # Действия администратора
    elif data.startswith("admin_"):
        await handle_admin_action(query, data, context)

async def update_quantity_display(query, context):
    """Обновить отображение количества"""
    if 'selected_dish' not in context.user_data:
        return
    
    dish_id = context.user_data['selected_dish']
    dish = TEXTS['dishes'].get(dish_id)
    quantity = context.user_data.get('quantity', 1)
    
    if dish:
        price_text = f"{dish['price']}{CURRENCY}" if dish['price'] > 0 else "БЕСПЛАТНО"
        
        keyboard = [
            [
                InlineKeyboardButton("➖", callback_data="dec_quantity"),
                InlineKeyboardButton(str(quantity), callback_data="noop"),
                InlineKeyboardButton("➕", callback_data="inc_quantity")
            ],
            [
                InlineKeyboardButton("✅ Добавить в корзину", callback_data="add_to_cart"),
                InlineKeyboardButton("🛒 В корзину", callback_data="view_cart")
            ],
            [
                InlineKeyboardButton("🍽️ Меню", callback_data="menu_categories"),
                InlineKeyboardButton("🏠 Главное", callback_data="main_menu")
            ]
        ]
        
        dish_name = dish['name']
        await query.edit_message_text(
            f"🍽️ <b>{dish_name}</b>\n\n"
            f"💰 Цена: <b>{price_text}</b>\n\n"
            f"Выберите количество:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML'
        )

# ==================== ОБРАБОТКА ФОТО АДРЕСА ====================
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка фотографий (скриншотов оплаты и фото адреса)"""
    user_id = update.effective_user.id
    photo = update.message.photo[-1]  # Берем самое большое фото
    
    logger.info(f"Получено фото от пользователя {user_id}")
    
    # Проверяем, находится ли пользователь в процессе оформления заказа
    if 'checkout_step' in context.user_data:
        step = context.user_data['checkout_step']
        
        if step == 'address_photo':
            # Пользователь отправляет фото адреса
            context.user_data['address_photo'] = photo.file_id
            
            # ОТПРАВЛЯЕМ ПОДТВЕРЖДЕНИЕ ПОЛЬЗОВАТЕЛЮ
            await update.message.reply_text(
                "✅ <b>Фото адреса получено!</b>\n\n"
                "Теперь можно добавить текстовый комментарий к адресу или сразу завершить оформление заказа:",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("📝 Добавить текстовый адрес", callback_data="add_address_text")],
                    [InlineKeyboardButton("✅ Завершить оформление", callback_data="complete_with_photo_only")]
                ]),
                parse_mode='HTML'
            )
            return
        
        elif step == 'add_text_to_photo':
            # Если пользователь отправил фото вместо текста
            context.user_data['address_photo'] = photo.file_id
            await update.message.reply_text(
                "📸 <b>Фото адреса получено!</b>\n\n"
                "Теперь можно добавить текстовый комментарий к адресу:",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("⏩ Пропустить", callback_data="complete_with_photo_only")]
                ]),
                parse_mode='HTML'
            )
            return
    
    # Если не фото адреса, то проверяем скриншот оплаты
    await handle_payment_screenshot(update, context, photo)

async def send_address_photo_to_admin(context: ContextTypes.DEFAULT_TYPE, order_id: str, order: Dict, address_photo: str):
    """Автоматическая отправка фото адреса в группу администраторов"""
    try:
        caption = f"""📍 <b>ФОТО АДРЕСА ДЛЯ ДОСТАВКИ</b>

🆔 ID заказа: {order_id}
👤 Клиент: {order['username']}
📞 Телефон: {order['phone']}
🏠 Адрес: {order['address']}
💰 Сумма: {order['final_total']}{CURRENCY}
⏰ Время: {datetime.now().strftime('%H:%M:%S %d.%m.%Y')}"""
        
        logger.info(f"Отправка фото адреса заказа {order_id} в группу {GROUP_ID}")
        
        # Отправляем фото адреса в группу
        try:
            await context.bot.send_photo(
                chat_id=GROUP_ID,
                photo=address_photo,
                caption=caption,
                parse_mode='HTML'
            )
            logger.info(f"✅ Фото адреса отправлено в группу администраторов")
            db.mark_address_photo_sent(order_id)
        except Exception as e:
            logger.error(f"❌ Не удалось отправить фото адреса: {e}")
            
            # Отправляем только текст
            text_with_info = f"""{caption}

⚠️ <i>Пользователь отправил фото адреса, но бот не может отправить его.
Запросите фото у пользователя {order['username']} ({order['phone']})</i>"""
            
            await context.bot.send_message(
                chat_id=GROUP_ID,
                text=text_with_info,
                parse_mode='HTML'
            )
    
    except Exception as e:
        logger.error(f"❌ Ошибка отправки фото адреса: {e}")

# ==================== ОБРАБОТКА СКРИНШОТОВ ОПЛАТЫ ====================
async def handle_payment_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE, photo):
    """Обработка скриншота оплаты"""
    user_id = update.effective_user.id
    
    logger.info(f"Получен скриншот оплаты от пользователя {user_id}")
    
    last_order_id = db.get_user_last_order(user_id)
    
    if not last_order_id:
        await update.message.reply_text(
            "❌ <b>У вас нет активных заказов!</b>\n\n"
            "Сначала оформите заказ, а затем отправьте скриншот оплаты.",
            parse_mode='HTML'
        )
        return
    
    order = db.get_order(last_order_id)
    
    if not order:
        await update.message.reply_text(
            "❌ <b>Заказ не найден!</b>\n\n"
            "Сначала оформите заказ, а затем отправьте скриншот оплаты.",
            parse_mode='HTML'
        )
        return
    
    await update.message.reply_text(
        "✅ <b>Скриншот оплаты получен!</b>\n\n"
        f"🆔 ID заказа: {last_order_id}\n"
        f"💰 Сумма: {order['final_total']}{CURRENCY}\n\n"
        "⏳ <i>Администратор проверит оплату в течение 5-10 минут.</i>",
        parse_mode='HTML'
    )
    
    await send_screenshot_to_admin(update, context, photo, last_order_id, order, user_id)

async def send_screenshot_to_admin(update: Update, context: ContextTypes.DEFAULT_TYPE, photo, order_id: str, order: Dict, user_id: int):
    """Отправка скриншота в группу администраторов"""
    try:
        caption = f"""📸 <b>СКРИНШОТ ОПЛАТЫ ПОЛУЧЕН</b>

🆔 ID заказа: {order_id}
👤 Клиент: {order['username']}
📞 Телефон: {order['phone']}
🏠 Адрес: {order['address'][:100]}{'...' if len(order['address']) > 100 else ''}
💰 Сумма: {order['final_total']}{CURRENCY}
⏰ Время: {datetime.now().strftime('%H:%M:%S %d.%m.%Y')}
👤 User ID: {user_id}"""
        
        logger.info(f"Отправка скриншота заказа {order_id} в группу {GROUP_ID}")
        
        try:
            await context.bot.send_photo(
                chat_id=GROUP_ID,
                photo=photo.file_id,
                caption=caption,
                parse_mode='HTML',
                reply_markup=get_admin_order_keyboard(order_id, 'pending')
            )
            logger.info(f"✅ Скриншот отправлен в группу администраторов")
        except Exception as e:
            logger.warning(f"❌ Не удалось отправить фото: {e}")
            
            try:
                await context.bot.send_photo(chat_id=GROUP_ID, photo=photo.file_id)
                await context.bot.send_message(
                    chat_id=GROUP_ID,
                    text=caption,
                    parse_mode='HTML',
                    reply_markup=get_admin_order_keyboard(order_id, 'pending')
                )
                logger.info(f"✅ Фото и текст отправлены раздельно")
            except Exception as e2:
                logger.warning(f"❌ Не удалось отправить фото: {e2}")
                text_with_info = f"""{caption}

⚠️ <i>Пользователь отправил скриншот оплаты, но бот не может отправить фото.</i>"""
                
                await context.bot.send_message(
                    chat_id=GROUP_ID,
                    text=text_with_info,
                    parse_mode='HTML',
                    reply_markup=get_admin_order_keyboard(order_id, 'pending')
                )
                logger.info(f"✅ Текстовая информация отправлена")
        
        db.mark_screenshot_sent(order_id)
        
        await update.message.reply_text(
            "📤 <b>Скриншот успешно передан администратору!</b>\n\n"
            "Ваш заказ поставлен в очередь на обработку.",
            parse_mode='HTML'
        )
        
    except Exception as e:
        logger.error(f"❌ Ошибка отправки скриншота: {e}")
        
        error_msg = f"""❌ ОШИБКА ОТПРАВКИ СКРИНШОТА
Время: {datetime.now().strftime('%H:%M:%S %d.%m.%Y')}
Группа: {GROUP_ID}
Заказ: {order_id}
Пользователь: {order['username']}
Телефон: {order['phone']}
Сумма: {order['final_total']}{CURRENCY}
Ошибка: {str(e)}"""
        
        with open('screenshot_errors.log', 'a', encoding='utf-8') as f:
            f.write(f"\n{error_msg}\n")
        
        error_message = f"""⚠️ <b>Не удалось отправить скриншот в группу администраторов!</b>

📞 <b>Пожалуйста, отправьте скриншот напрямую администратору по телефону:</b>
<b>010-8361-6165</b>

📋 <b>Информация для администратора:</b>
🆔 ID заказа: {order_id}
👤 Клиент: {order['username']}
📞 Телефон: {order['phone']}
💰 Сумма: {order['final_total']}{CURRENCY}"""
        
        await update.message.reply_text(
            error_message,
            parse_mode='HTML'
        )

# ==================== ОБРАБОТКА ТЕКСТОВЫХ СООБЩЕНИЙ ====================
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка текстовых сообщений"""
    user_id = update.effective_user.id
    text = update.message.text.strip()
    
    if 'checkout_step' in context.user_data:
        step = context.user_data['checkout_step']
        
        if step == 'phone':
            phone_pattern = r'^01[016789][0-9]{7,8}$'
            clean_phone = re.sub(r'\D', '', text)
            
            if not re.match(phone_pattern, clean_phone):
                await update.message.reply_text(
                    "❌ <b>Неверный формат телефона!</b>\n\n"
                    "Правильный формат:\n"
                    "• 01012345678\n"
                    "• 010-1234-5678\n"
                    "• +821012345678",
                    parse_mode='HTML'
                )
                return
            
            context.user_data['phone'] = clean_phone
            context.user_data['checkout_step'] = 'address_choice'
            
            await update.message.reply_text(
                "✅ <b>Телефон сохранен!</b>\n\n"
                "🏠 <b>Теперь выберите способ указания адреса:</b>\n\n"
                "1️⃣ Написать адрес текстом\n"
                "2️⃣ Отправить фото адреса (скриншот карты или текста)",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("📝 Ввести адрес текстом", callback_data="enter_address_text")],
                    [InlineKeyboardButton("📸 Отправить фото адреса", callback_data="enter_address_photo")],
                    [InlineKeyboardButton("🔙 Назад", callback_data="view_cart")]
                ]),
                parse_mode='HTML'
            )
        
        elif step == 'address_text':
            if len(text) < 10:
                await update.message.reply_text(
                    "❌ <b>Адрес слишком короткий!</b>\n\n"
                    "Пожалуйста, укажите полный адрес доставки.",
                    parse_mode='HTML'
                )
                return
            
            context.user_data['address'] = text
            context.user_data['checkout_step'] = 'confirmation'
            
            username = context.user_data['username']
            phone = context.user_data['phone']
            address = text
            cart = db.get_cart(user_id)
            
            if not cart:
                await update.message.reply_text("❌ Корзина пуста!")
                return
            
            order_id = db.create_order(user_id, username, phone, address, cart)
            order = db.get_order(order_id)
            
            await complete_order_creation(None, context, order_id, order, update)
        
        elif step == 'add_text_to_photo':
            if len(text) < 5:
                await update.message.reply_text(
                    "❌ <b>Комментарий слишком короткий!</b>\n\n"
                    "Пожалуйста, добавьте текстовое описание адреса.",
                    parse_mode='HTML'
                )
                return
            
            context.user_data['address'] = text
            context.user_data['checkout_step'] = 'confirmation'
            
            username = context.user_data['username']
            phone = context.user_data['phone']
            address = text
            address_photo = context.user_data.get('address_photo')
            cart = db.get_cart(user_id)
            
            if not cart:
                await update.message.reply_text("❌ Корзина пуста!")
                return
            
            order_id = db.create_order(user_id, username, phone, address, cart, address_photo)
            order = db.get_order(order_id)
            
            # ОТПРАВЛЯЕМ ФОТО АДРЕСА В ГРУППУ АДМИНИСТРАТОРОВ
            if address_photo:
                await send_address_photo_to_admin(context, order_id, order, address_photo)
            
            await complete_order_creation(None, context, order_id, order, update)
    
    else:
        await update.message.reply_text(
            "Используйте меню для навигации или команду /start",
            reply_markup=get_main_menu_keyboard()
        )

# ==================== СОЗДАНИЕ И ОТПРАВКА ЗАКАЗА ====================
async def complete_order_creation(query, context, order_id, order, update=None):
    """Завершение создания заказа и отправка подтверждения"""
    order_text = f"""✅ <b>Заказ оформлен!</b>

📋 <b>Ваш заказ:</b>"""
    
    for item_id, item in order['cart'].items():
        item_total = item['price'] * item['quantity']
        order_text += f"\n• {item['name']} x{item['quantity']} - {item_total}{CURRENCY}"
    
    order_text += f"\n\n💰 <b>Итого: {order['total']}{CURRENCY}</b>"
    order_text += f"\n🚚 <b>Доставка: {DELIVERY_COST}{CURRENCY}</b>"
    order_text += f"\n💵 <b>К оплате: {order['final_total']}{CURRENCY}</b>"
    order_text += f"\n🆔 <b>ID заказа: {order_id}</b>"
    order_text += f"\n🏠 <b>Адрес: {order['address'][:50]}{'...' if len(order['address']) > 50 else ''}</b>"
    
    payment_text = f"""💳 <b>Реквизиты для оплаты:</b>

🏦 Банк: <b>전북은행 (JEONBUK BANK)</b>
📊 Счет: <b>9100053711589</b>
👤 Владелец: <b>Денис 010-8361-6165</b>

💵 <b>Сумма к оплате: {order['final_total']}{CURRENCY}</b>
🆔 <b>ID заказа: {order_id}</b>

📸 <b>После оплаты отправьте скриншот чека в этот чат!</b>

<i>Обязательно укажите ID заказа при оплате!</i>"""
    
    if query:
        await query.edit_message_text(order_text, parse_mode='HTML')
        await context.bot.send_message(
            chat_id=query.from_user.id,
            text=payment_text,
            parse_mode='HTML'
        )
    elif update:
        await update.message.reply_text(order_text, parse_mode='HTML')
        await update.message.reply_text(payment_text, parse_mode='HTML')
    
    # Очищаем состояние
    if 'checkout_step' in context.user_data:
        del context.user_data['checkout_step']
    if 'username' in context.user_data:
        del context.user_data['username']
    if 'phone' in context.user_data:
        del context.user_data['phone']
    if 'address' in context.user_data:
        del context.user_data['address']
    if 'address_photo' in context.user_data:
        del context.user_data['address_photo']
    
    # Отправляем заказ в группу админов
    await send_order_to_admin(context, order_id, order)

async def send_order_to_admin(context: ContextTypes.DEFAULT_TYPE, order_id: str, order: Dict):
    """Отправка заказа администратору"""
    try:
        admin_text = f"""🆕 <b>НОВЫЙ ЗАКАЗ ЧЕРЕЗ БОТА</b>

👤 Клиент: {order['username']}
📞 Телефон: {order['phone']}
🏠 Адрес: {order['address']}
{'📸 Адрес фото: Да' if order.get('address_photo') else '📝 Адрес: Текст'}

📦 <b>Заказ:</b>"""
        
        for item_id, item in order['cart'].items():
            item_total = item['price'] * item['quantity']
            admin_text += f"\n• {item['name']} x{item['quantity']} - {item_total}{CURRENCY}"
        
        admin_text += f"\n\n💰 Итого: {order['total']}{CURRENCY}"
        admin_text += f"\n🚚 Доставка: {DELIVERY_COST}{CURRENCY}"
        admin_text += f"\n💵 К оплате: {order['final_total']}{CURRENCY}"
        admin_text += f"\n🆔 ID заказа: {order_id}"
        admin_text += f"\n⏰ Время: {datetime.now().strftime('%H:%M:%S %d.%m.%Y')}"
        admin_text += f"\n👤 User ID: {order['user_id']}"
        
        logger.info(f"Отправка заказа {order_id} в группу {GROUP_ID}")
        
        # Отправляем только текст с кнопками
        await context.bot.send_message(
            chat_id=GROUP_ID,
            text=admin_text,
            reply_markup=get_admin_order_keyboard(order_id, 'pending'),
            parse_mode='HTML'
        )
        
        logger.info(f"✅ Заказ {order_id} отправлен админу")
        
        with open('orders.log', 'a', encoding='utf-8') as f:
            f.write(f"\n{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - Заказ {order_id}\n{admin_text}\n")
        
    except Exception as e:
        logger.error(f"❌ Ошибка отправки админу: {e}")
        
        with open('failed_orders.log', 'a', encoding='utf-8') as f:
            f.write(f"\n{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - Ошибка отправки заказа {order_id}\n")
            f.write(f"Ошибка: {str(e)}\n")

# ==================== ДЕЙСТВИЯ АДМИНИСТРАТОРА ====================
async def handle_admin_action(query, data, context):
    """Обработка действий администратора"""
    try:
        current_chat_id = str(query.message.chat.id)
        group_id_str = str(GROUP_ID).replace('-', '').lstrip('-')
        
        if current_chat_id != group_id_str:
            await query.answer("Эта команда доступна только администраторам", show_alert=True)
            return
    except:
        await query.answer("Ошибка проверки прав доступа", show_alert=True)
        return
    
    parts = data.split('_')
    if len(parts) < 3:
        return
    
    action = parts[1]
    order_id = '_'.join(parts[2:])
    
    order = db.get_order(order_id)
    if not order:
        await query.edit_message_text(f"❌ Заказ {order_id} не найден")
        return
    
    if action == 'confirm':
        # Подтверждение оплаты
        db.update_order_status(order_id, 'preparing', 'confirmed')
        
        # Уведомление клиента
        try:
            await context.bot.send_message(
                chat_id=order['user_id'],
                text=f"""🎉 <b>Оплата подтверждена!</b>

✅ <b>Ваш заказ №{order_id} принят в работу!</b>
💰 Сумма: {order['final_total']}{CURRENCY}
👨‍🍳 <b>Заказ готовится! Ожидайте доставки в течение 30-45 минут.</b>
🚚 Курьер выедет к вам по адресу: {order['address'][:50]}{'...' if len(order['address']) > 50 else ''}
📞 Контактный телефон курьера: <b>010-8361-6165</b>
⏰ Время подтверждения: {datetime.now().strftime('%H:%M:%S %d.%m.%Y')}

<i>Спасибо за заказ! Приятного аппетита! 😊</i>""",
                parse_mode='HTML'
            )
            logger.info(f"✅ Уведомление о начале выполнения заказа отправлено клиенту {order['user_id']}")
        except Exception as e:
            logger.error(f"❌ Не удалось отправить уведомление пользователю: {e}")
        
        # Обновляем сообщение в группе
        original_text = query.message.text
        confirmed_text = f"{original_text}\n\n✅ <b>ОПЛАТА ПОДТВЕРЖДЕНА АДМИНИСТРАТОРОМ</b>\n⏰ <i>Клиент уведомлен о начале выполнения заказа</i>\n🕐 {datetime.now().strftime('%H:%M:%S %d.%m.%Y')}"
        
        await query.edit_message_text(
            confirmed_text,
            reply_markup=get_admin_order_keyboard(order_id, 'confirmed'),
            parse_mode='HTML'
        )
        
        # Уведомление администратору в личный чат
        await send_admin_notification(context, query.from_user.id, order_id, 'confirm')
    
    elif action == 'reject':
        # Отклонение оплаты
        db.update_order_status(order_id, 'payment_rejected', 'rejected')
        
        # Уведомление клиента
        try:
            await context.bot.send_message(
                chat_id=order['user_id'],
                text=f"""❌ <b>Платеж не подтвержден</b>

🆔 ID заказа: {order_id}
💰 Сумма: {order['final_total']}{CURRENCY}
📞 Пожалуйста, свяжитесь с нами по телефону: <b>010-8361-6165</b>""",
                parse_mode='HTML'
            )
        except Exception as e:
            logger.error(f"Не удалось отправить уведомление пользователю: {e}")
        
        # Обновляем сообщение в группе
        original_text = query.message.text
        rejected_text = f"{original_text}\n\n❌ <b>ОПЛАТА ОТКЛОНЕНА АДМИНИСТРАТОРОМ</b>\n⏰ {datetime.now().strftime('%H:%M:%S %d.%m.%Y')}"
        
        await query.edit_message_text(
            rejected_text,
            reply_markup=get_admin_order_keyboard(order_id, 'rejected'),
            parse_mode='HTML'
        )
        
        # Уведомление администратору в личный чат
        await send_admin_notification(context, query.from_user.id, order_id, 'reject')

# ==================== ЗАПУСК БОТА ====================
def main():
    """Основная функция запуска бота"""
    
    # Проверка на один экземпляр
    lock_socket = check_single_instance()
    
    if not BOT_TOKEN or BOT_TOKEN == 'ВАШ_ТОКЕН_БОТА':
        logger.error("❌ Ошибка: BOT_TOKEN не установлен!")
        logger.error("💡 Установите переменную окружения BOT_TOKEN")
        if lock_socket:
            lock_socket.close()
        return
    
    # Проверяем GROUP_ID
    if not GROUP_ID or GROUP_ID == '-5083395375':
        logger.warning("⚠️ ВНИМАНИЕ: GROUP_ID не установлен или имеет значение по умолчанию!")
        logger.warning("💡 Создайте файл .env и добавьте: GROUP_ID='-ваш_ид_группы'")
    
    # Создаем приложение
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Регистрируем обработчики
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CallbackQueryHandler(handle_callback))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    
    # Запускаем бота
    logger.info("🤖 Бот запущен...")
    logger.info(f"⏰ Работаем: {WORK_TIME}")
    logger.info(f"🍺 Похмельное время: {HANGOVER_TIME}")
    logger.info(f"🚚 Доставка по {DELIVERY_AREA}: {DELIVERY_COST}{CURRENCY}")
    logger.info(f"📞 Телефон: 010-8361-6165")
    logger.info(f"👥 Группа админов: {GROUP_ID}")
    
    try:
        application.run_polling(allowed_updates=Update.ALL_TYPES)
    except KeyboardInterrupt:
        logger.info("👋 Бот завершает работу по команде пользователя")
    except Exception as e:
        logger.error(f"❌ Ошибка при работе бота: {e}")
    finally:
        if lock_socket:
            lock_socket.close()
            logger.info("🔓 Блокировка снята")

if __name__ == "__main__":
    main()