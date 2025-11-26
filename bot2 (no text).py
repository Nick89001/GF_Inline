import telebot
from telebot import types
import sqlite3
import datetime
import time
import threading
import logging
import random

# Настройка логирования с поддержкой UTF-8
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    filename='bot.log',
    filemode='a',
    encoding='utf-8'
)

# Списки тёплых фраз
COMMENT_PHRASES = [
    "Будем рады вашим пожеланиям! 💐🍷",
    "С нетерпением ждём вас! Хотите добавить дополнительные пожелания? 🌸🥂",
    "Уютный вечер начинается с деталей. Поделитесь своими пожеланиями! 🌿🍴"
]

CONSENT_PHRASES = [
    "Честность — основа вкуса и на кухне, и в отношении данных 🍷🛡",
    "Безопасность так же важна, как и вкус. Мы бережно храним ваши данные 🌷📄",
    "Ваше спокойствие — наш приоритет. Ознакомьтесь с нашей политикой 🌼🧾"
]

BOOKING_CONFIRMATION_PHRASES = [
    "{name}, Ваше бронирование подтверждено!\n"
    "Мы ждём Вас {date} в {start_time} — и уже готовим тёплую атмосферу, где вкус сочетается с заботой. "
    "Пусть этот вечер подарит вам тепло и радость! До скорой встречи! 🍽🌷",

    "Спасибо за бронь, {name}!\n"
    "Столик ждёт вас {date} в {start_time}. Мы с радостью подготовим для вас атмосферу, "
    "где каждый момент будет особенным! 🍷🌹",

    "Ваш вечер в «Глупом Французе» уже почти начался — встречаем Вас {date} в {start_time}.\n"
    "Мы создаём пространство, где можно расслабиться, насладиться и почувствовать себя "
    "по-настоящему желанным гостем.\n"
    "Пусть этот вечер подарит вам вкусные воспоминания и несравненные впечатления! ❤️🥂"
]

def get_random_warm_phrase(phrase_type):
    """Возвращает случайную тёплую фразу в зависимости от типа."""
    if phrase_type == 'comment':
        return random.choice(COMMENT_PHRASES)
    elif phrase_type == 'consent':
        return random.choice(CONSENT_PHRASES)
    elif phrase_type == 'booking':
        return random.choice(BOOKING_CONFIRMATION_PHRASES)
    return ""

# Инициализация бота
bot = telebot.TeleBot('8264428870:AAGlUN3worvwo4ee3HUbYYJAlwzHs4AsUG8')
ADMIN_CHAT_ID = 1069506191
user_state = {}



def create_table():
    conn = sqlite3.connect('booking.db', check_same_thread=False)
    cursor = conn.cursor()

    # Создаём таблицу tables с новым столбцом comment
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS tables (
        id INTEGER,
        date TEXT,
        start_time TEXT,
        end_time TEXT,
        status TEXT,
        num_of_people INTEGER,
        phone_number TEXT,
        chat_id INTEGER,
        comment TEXT,
        PRIMARY KEY (id, date, start_time)
    );
    ''')

    # Проверяем, существует ли столбец comment, и добавляем его, если отсутствует
    cursor.execute("PRAGMA table_info(tables)")
    columns = [col[1] for col in cursor.fetchall()]
    if 'comment' not in columns:
        cursor.execute('ALTER TABLE tables ADD COLUMN comment TEXT')
        logging.info("Столбец 'comment' добавлен в таблицу 'tables'")

    # Создаём остальные таблицы
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS reviews (
        booking_id INTEGER,
        chat_id INTEGER,
        review_left INTEGER DEFAULT 0,
        FOREIGN KEY (booking_id) REFERENCES tables(rowid)
    );
    ''')
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS data_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT,
        chat_id INTEGER,
        phone TEXT,
        request_type TEXT,
        result TEXT
    );
    ''')
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS consents (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT,
        chat_id INTEGER,
        phone TEXT,
        consent_type TEXT,
        result TEXT
    );
    ''')
    conn.commit()
    conn.close()
    logging.info("Таблицы 'tables', 'reviews', 'data_requests' и 'consents' созданы или обновлены")
    print("✅ Таблицы 'tables', 'reviews', 'data_requests' и 'consents' созданы или обновлены")


def log_data_request(chat_id, phone, request_type, result):
    conn = sqlite3.connect('booking.db', check_same_thread=False)
    cursor = conn.cursor()
    timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    # Записываем только chat_id, телефон и тип запроса, исключая лишние ПДн
    cursor.execute('''
        INSERT INTO data_requests (timestamp, chat_id, phone, request_type, result)
        VALUES (?, ?, ?, ?, ?)
    ''', (timestamp, chat_id, phone or "N/A", request_type, result))
    conn.commit()
    conn.close()

def get_navigation_buttons():
    """Возвращает инлайн-кнопки 'Отмена' и 'Вернуться'."""
    markup = types.InlineKeyboardMarkup()
    btn_cancel = types.InlineKeyboardButton("Отмена", callback_data="cancel")
    btn_back = types.InlineKeyboardButton("Вернуться", callback_data="back")
    markup.add(btn_cancel, btn_back)
    return markup

def cleanup_old_bookings():
    while True:
        conn = sqlite3.connect('booking.db', check_same_thread=False)
        cursor = conn.cursor()
        current_time = datetime.datetime.now()
        cursor.execute('''
            SELECT rowid, date, end_time, phone_number, chat_id 
            FROM tables 
            WHERE status = "confirmed"
        ''')
        bookings = cursor.fetchall()
        for booking in bookings:
            rowid, date, end_time, phone, chat_id = booking
            booking_end = datetime.datetime.strptime(f"{date} {end_time}", '%d.%m.%Y %H:%M')
            if booking_end < current_time:
                cursor.execute('DELETE FROM tables WHERE rowid = ?', (rowid,))
                cursor.execute('DELETE FROM reviews WHERE booking_id = ?', (rowid,))
                # Удаляем записи в data_requests, не связанные с согласием
                cursor.execute('''
                    DELETE FROM data_requests 
                    WHERE chat_id = ? AND phone = ? AND request_type NOT IN ('consent', 'access')
                ''', (chat_id, phone))
                cursor.execute('''
                    INSERT INTO data_requests (timestamp, chat_id, phone, request_type, result)
                    VALUES (?, ?, ?, ?, ?)
                ''', (datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'), chat_id, phone, "auto_delete", f"Бронь {date} {end_time} автоматически удалена"))
        conn.commit()
        conn.close()
        time.sleep(3600)  # Проверяем каждый час

def cleanup_old_logs():
    while True:
        conn = sqlite3.connect('booking.db', check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute('''
            DELETE FROM data_requests 
            WHERE timestamp < datetime('now', '-3 year')
        ''')
        cursor.execute('''
            DELETE FROM consents 
            WHERE timestamp < datetime('now', '-3 year')
        ''')
        conn.commit()
        conn.close()
        time.sleep(86400)  # Проверяем раз в день

@bot.message_handler(commands=['start'])
def start_command(message):
    chat_id = message.chat.id
    if chat_id not in user_state:
        user_state[chat_id] = {'welcomed': False}
    if not user_state[chat_id].get('welcomed', False):
        welcome_message = (
            "🍷 *Добро пожаловать в «Глупый Француз»!*\n\n"
            "*Глупый Француз* — ваш личный гид в мир вкусной Франции в Ростове-на-Дону! 🥂\n\n"
            "Забронировать столик за 30 секунд, заказать подарочный сертификат, провести незабываемое мероприятие или просто посмотреть меню — всё здесь.\n\n"
            "Мы говорим на языке вкуса, уюта и тёплых вечеров.\n"
            "*Честность, забота и внимание к мелочам — наш рецепт счастья.* ❤️\n\n"
            "Работаем ежедневно 8:00–23:00\n"
            "📍 ул. Козлова, 42\n"
            "☎️ +7 (951) 506-80-80"
        )
        bot.send_message(chat_id, welcome_message, reply_markup=types.ReplyKeyboardRemove(), parse_mode="Markdown")
        user_state[chat_id]['welcomed'] = True
        bot.send_message(ADMIN_CHAT_ID,
                         f"🔔 Новый подписчик: {message.from_user.id} ({message.from_user.first_name}) нажал /start")
    main_menu_inline(chat_id)


@bot.message_handler(commands=['menu'])
def menu_command(message):
    main_menu_inline(message.chat.id)

def main_menu_inline(chat_id):
    photos = ['photo_restaurant.jpg']
    try:
        media = [types.InputMediaPhoto(open(photo, 'rb')) for photo in photos]
        bot.send_media_group(chat_id, media)
    except FileNotFoundError:
        logging.error("Файл photo_restaurant.jpg не найден")
        bot.send_message(chat_id, "⚠️ Не удалось загрузить изображения ресторана.")
    markup = types.InlineKeyboardMarkup(row_width=2)
    btn1 = types.InlineKeyboardButton("Забронировать столик", callback_data="book_table")
    btn2 = types.InlineKeyboardButton("Меню", callback_data="menu")
    btn3 = types.InlineKeyboardButton("Провести мероприятие", callback_data="event_booking")
    btn4 = types.InlineKeyboardButton("Наш сайт", url="https://www.franz.chehovgroup.ru")
    btn5 = types.InlineKeyboardButton("Подарочные сертификаты", callback_data="gift_certificates")
    btn6 = types.InlineKeyboardButton("О ресторане", callback_data="about_restaurant")
    markup.add(btn1, btn2)
    markup.add(btn3, btn4)
    markup.add(btn5, btn6)
    bot.send_message(chat_id, "📌 *Выберите действие:*", reply_markup=markup, parse_mode="Markdown")




@bot.callback_query_handler(func=lambda call: call.data == "gift_certificates")
def callback_gift_certificates(call):
    bot.answer_callback_query(call.id)
    chat_id = call.message.chat.id
    markup = types.InlineKeyboardMarkup(row_width=2)
    btn1 = types.InlineKeyboardButton("Гастро-ужин", callback_data="gift_gastro")
    btn2 = types.InlineKeyboardButton("Стандартный", callback_data="gift_standard")
    btn3 = types.InlineKeyboardButton("Романтический ужин", callback_data="gift_romantic")
    btn4 = types.InlineKeyboardButton("Ужин от шеф-повара", callback_data="gift_chef")
    btn5 = types.InlineKeyboardButton("Завтрак на две персоны", callback_data="gift_breakfast")
    btn6 = types.InlineKeyboardButton("Номер в бутик-отеле", callback_data="gift_hotel")
    markup.add(btn1, btn2)
    markup.add(btn3, btn4)
    markup.add(btn5, btn6)
    bot.send_message(chat_id, "🎁 *Выберите тип подарочного сертификата:*", reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith("gift_"))
def handle_gift_selection(call):
    bot.answer_callback_query(call.id)
    chat_id = call.message.chat.id
    certificate_type = call.data.split("_")[1]
    user_state[chat_id] = {'certificate_type': certificate_type, 'step': 'gift_name', 'process': 'gift'}
    photo_pairs = {
        "gastro": ["gastro1.jpg", "gastro2.jpg"],
        "standard": ["standard1.jpg", "standard2.jpg"],
        "romantic": ["romantic1.jpg", "romantic2.jpg"],
        "chef": ["chef1.jpg", "chef2.jpg"],
        "breakfast": ["breakfast1.jpg", "breakfast2.jpg"],
        "hotel": ["hotel1.jpg", "hotel2.jpg"]
    }
    photos = photo_pairs[certificate_type]
    try:
        media = [types.InputMediaPhoto(open(photo, 'rb')) for photo in photos]
        bot.send_media_group(chat_id, media)
    except FileNotFoundError:
        logging.error(f"Файлы сертификата {certificate_type} не найдены")
        bot.send_message(chat_id, "⚠️ Не удалось загрузить изображения сертификата.")
    bot.send_message(chat_id, "*Как к Вам можно обращаться?*", reply_markup=get_navigation_buttons(), parse_mode="Markdown")
    logging.info(f"Отправлен запрос имени для gift_name, chat_id: {chat_id}")

@bot.message_handler(func=lambda message: user_state.get(message.chat.id, {}).get('step') == 'gift_name')
def get_gift_name(message):
    chat_id = message.chat.id
    user_state[chat_id]['name'] = message.text
    user_state[chat_id]['step'] = 'gift_address'
    bot.send_message(chat_id, "*Укажите адрес доставки:*", reply_markup=get_navigation_buttons(), parse_mode="Markdown")

@bot.message_handler(func=lambda message: user_state.get(message.chat.id, {}).get('step') == 'gift_address')
def get_gift_address(message):
    chat_id = message.chat.id
    user_state[chat_id]['address'] = message.text
    user_state[chat_id]['step'] = 'gift_phone'
    bot.send_message(chat_id, "*Укажите номер телефона для связи:*", reply_markup=get_navigation_buttons(), parse_mode="Markdown")

@bot.message_handler(func=lambda message: user_state.get(message.chat.id, {}).get('step') == 'gift_phone')
def get_gift_phone(message):
    chat_id = message.chat.id
    logging.info(f"get_gift_phone вызвана: chat_id={chat_id}, текст='{message.text}', состояние={user_state.get(chat_id, {})}")

    phone = message.text.strip()
    if not phone.isdigit() or len(phone) < 10:
        bot.send_message(chat_id, "*❌ Введите корректный номер телефона (только цифры, минимум 10 знаков):*",
                         reply_markup=get_navigation_buttons(), parse_mode="Markdown")
        logging.info(f"Некорректный номер телефона: {phone} для chat_id {chat_id}")
        return

    try:
        user_state[chat_id]['phone'] = phone
        user_state[chat_id]['step'] = 'consent'
        user_state[chat_id]['process'] = 'gift'
        markup = types.InlineKeyboardMarkup()
        btn_consent = types.InlineKeyboardButton("Согласен", callback_data="consent_yes")
        btn_privacy = types.InlineKeyboardButton("Политика конфиденциальности", callback_data="show_privacy")
        markup.add(btn_consent, btn_privacy)
        bot.send_message(chat_id,
                         "*Для завершения заказа сертификата подтвердите согласие на обработку персональных данных.*",
                         reply_markup=markup, parse_mode="Markdown")
        log_data_request(chat_id, phone, "consent_request", "Запрос согласия отправлен")
        logging.info(f"Запрос согласия отправлен для chat_id {chat_id} после ввода телефона {phone}")
    except Exception as e:
        logging.error(f"Ошибка в get_gift_phone для chat_id {chat_id}: {e}")
        bot.send_message(chat_id, "⚠️ Произошла ошибка. Пожалуйста, попробуйте снова.", parse_mode="Markdown")
        main_menu_inline(chat_id)

@bot.callback_query_handler(func=lambda call: call.data == "event_booking")
def callback_event_booking(call):
    bot.answer_callback_query(call.id)
    chat_id = call.message.chat.id
    if chat_id not in user_state:
        user_state[chat_id] = {}
    user_state[chat_id]['step'] = 'event_name'
    bot.send_message(chat_id, "*Как к Вам можно обращаться?*", reply_markup=get_navigation_buttons(), parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data == "book_table")
def callback_book_table(call):
    bot.answer_callback_query(call.id)
    chat_id = call.message.chat.id
    if chat_id not in user_state:
        user_state[chat_id] = {}
    user_state[chat_id]['step'] = 'name'
    bot.send_message(chat_id, "*Как к Вам можно обращаться?*", reply_markup=get_navigation_buttons(), parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data == "about_restaurant")
def about_restaurant(call):
    bot.answer_callback_query(call.id)
    info_text = (
        "📍 *Адрес:* ул. Козлова, 42, Ростов-на-Дону.\n"
        "📞 *Телефон:* +7 (951) 506-80-80.\n\n"
        "Ресторан *Глупый Француз* расположен в тихом центре Ростова-на-Дону, "
        "в 800 метрах от Комсомольской площади и проспекта Буденовский.\n\n"
        "🕒 *График работы:* ежедневно, с 8.00 до 23.00\n\n"
        "🍽 *Специальные предложения:*\n"
        "  - Комплексные завтраки (с 8.00 до 12.00)\n"
        "  - Деловые обеды (с 12.00 до 16.00)\n\n"
        "✨ Уютный интерьер и авторская кухня покоряют гостей с первого визита!\n\n"
        "❄️ *Зимние места:* 30 персон\n"
        "☀️ *Летние места:* 50 персон (включая веранду и двор с грилем)\n\n"
        "🎉 Подходит для: свадьбы, корпоративы, дни рождения, бизнес-встречи.\n\n"
        "*Глупый Француз* — часть бутик-отеля *Честный Чехов*.\n\n"
        "*Добро пожаловать!*"
    )
    markup = types.InlineKeyboardMarkup()
    btn_back = types.InlineKeyboardButton("Вернуться в меню", callback_data="back_to_main_menu")
    markup.add(btn_back)
    bot.send_message(call.message.chat.id, info_text, reply_markup=markup, parse_mode="Markdown")


@bot.callback_query_handler(func=lambda call: call.data == "menu")
def callback_menu(call):
    bot.answer_callback_query(call.id)
    chat_id = call.message.chat.id

    def send_menu_safe():
        try:
            # === ОСНОВНОЕ МЕНЮ — 9 фото одним альбомом ===
            media_main = [
                types.InputMediaPhoto(open("1.jpg", 'rb'), caption="*Основное меню*", parse_mode="Markdown")
            ]
            for i in range(2, 10):
                media_main.append(types.InputMediaPhoto(open(f"{i}.jpg", 'rb')))
            bot.send_media_group(chat_id, media_main)

            # === БАРНАЯ КАРТА — 8 фото ОДНИМ альбомом (подпись только у первого) ===
            media_bar = [
                types.InputMediaPhoto(open("10.jpg", 'rb'), caption="*Барная карта*", parse_mode="Markdown")
            ]
            for i in range(11, 18):  # 11.jpg → 17.jpg
                media_bar.append(types.InputMediaPhoto(open(f"{i}.jpg", 'rb')))
            bot.send_media_group(chat_id, media_bar)

            # === Кнопки под всем меню ===
            markup = types.InlineKeyboardMarkup()
            btn_order = types.InlineKeyboardButton("Сделать заказ", url="https://taplink.cc/glupy_franz/p/287dee/")
            btn_back = types.InlineKeyboardButton("Вернуться в меню", callback_data="back_to_main_menu")
            markup.add(btn_order, btn_back)

            bot.send_message(chat_id, "Выберите действие:", reply_markup=markup, parse_mode="Markdown")

        except FileNotFoundError as e:
            logging.error(f"Файл меню не найден: {e}")
            bot.send_message(chat_id, "Один из файлов меню отсутствует. Сообщите администратору.")
        except Exception as e:
            logging.error(f"Ошибка отправки меню: {e}")
            bot.send_message(chat_id, "Меню временно недоступно. Попробуйте позже.")


@bot.callback_query_handler(func=lambda call: call.data == "back_to_main_menu")
def callback_back_to_main_menu(call):
    bot.answer_callback_query(call.id)
    chat_id = call.message.chat.id
    user_state[chat_id] = {}  # Сбрасываем состояние
    main_menu_inline(chat_id)


@bot.message_handler(func=lambda message: user_state.get(message.chat.id, {}).get('step') == 'event_name')
def get_event_name(message):
    user_state[message.chat.id]['name'] = message.text
    user_state[message.chat.id]['step'] = 'event_type'
    bot.send_message(message.chat.id, "*У Вас праздник, День рождения или годовщина? Укажите это, пожалуйста:*",
                     reply_markup=get_navigation_buttons(), parse_mode="Markdown")

@bot.message_handler(func=lambda message: user_state.get(message.chat.id, {}).get('step') == 'event_type')
def get_event_type(message):
    user_state[message.chat.id]['event_type'] = message.text
    user_state[message.chat.id]['step'] = 'event_date'
    bot.send_message(message.chat.id, "*Укажите дату вашего события (формат ДД.ММ.ГГГГ):*",
                     reply_markup=get_navigation_buttons(), parse_mode="Markdown")

@bot.message_handler(func=lambda message: user_state.get(message.chat.id, {}).get('step') == 'event_date')
def get_event_date(message):
    try:
        date = datetime.datetime.strptime(message.text, '%d.%m.%Y').strftime('%d.%m.%Y')
        current_date = datetime.datetime.now().strftime('%d.%m.%Y')
        if datetime.datetime.strptime(date, '%d.%m.%Y') < datetime.datetime.strptime(current_date, '%d.%m.%Y'):
            bot.send_message(message.chat.id, "*❌ Нельзя выбрать прошедшую дату. Введите снова (ДД.ММ.ГГГГ):*",
                             reply_markup=get_navigation_buttons(), parse_mode="Markdown")
            return
        user_state[message.chat.id]['event_date'] = date
        user_state[message.chat.id]['step'] = 'event_time'
        bot.send_message(message.chat.id, "*Укажите время начала события (формат ЧЧ:ММ):*",
                         reply_markup=get_navigation_buttons(), parse_mode="Markdown")
    except ValueError:
        bot.send_message(message.chat.id, "*❌ Неверный формат даты. Введите снова (ДД.ММ.ГГГГ):*",
                         reply_markup=get_navigation_buttons(), parse_mode="Markdown")

@bot.message_handler(func=lambda message: user_state.get(message.chat.id, {}).get('step') == 'event_time')
def get_event_time(message):
    try:
        time = datetime.datetime.strptime(message.text, '%H:%M').strftime('%H:%M')
        user_state[message.chat.id]['event_time'] = time
        user_state[message.chat.id]['step'] = 'event_guests'
        bot.send_message(message.chat.id, "*Укажите количество гостей:*",
                         reply_markup=get_navigation_buttons(), parse_mode="Markdown")
    except ValueError:
        bot.send_message(message.chat.id, "*❌ Неверный формат времени. Введите снова (ЧЧ:ММ):*",
                         reply_markup=get_navigation_buttons(), parse_mode="Markdown")

@bot.message_handler(func=lambda message: user_state.get(message.chat.id, {}).get('step') == 'event_guests')
def get_event_guests(message):
    if message.text.isdigit():
        user_state[message.chat.id]['event_guests'] = int(message.text)
        user_state[message.chat.id]['step'] = 'event_phone'
        bot.send_message(message.chat.id, "*Укажите номер для обратной связи:*",
                         reply_markup=get_navigation_buttons(), parse_mode="Markdown")
    else:
        bot.send_message(message.chat.id, "*❌ Введите корректное число гостей:*",
                         reply_markup=get_navigation_buttons(), parse_mode="Markdown")

@bot.message_handler(func=lambda message: user_state.get(message.chat.id, {}).get('step') == 'event_phone')
def get_event_phone(message):
    chat_id = message.chat.id
    logging.info(f"get_event_phone вызвана: chat_id={chat_id}, текст='{message.text}', состояние={user_state.get(chat_id, {})}")

    phone = message.text.strip()
    if not phone.isdigit() or len(phone) < 10:
        bot.send_message(chat_id, "*❌ Введите корректный номер телефона (только цифры, минимум 10 знаков):*",
                         reply_markup=get_navigation_buttons(), parse_mode="Markdown")
        logging.info(f"Некорректный номер телефона: {phone} для chat_id {chat_id}")
        return

    try:
        user_state[chat_id]['event_phone'] = phone
        user_state[chat_id]['step'] = 'ask_comment'
        user_state[chat_id]['process'] = 'event'
        name = user_state[chat_id].get('name', 'Гость')
        bot.send_message(chat_id,
                         f"*{name}*, Вы хотите оставить пожелание/комментарий к мероприятию?",
                         reply_markup=get_comment_buttons(), parse_mode="Markdown")
        logging.info(f"Вопрос о комментарии отправлен для chat_id {chat_id} после ввода телефона {phone}")
    except Exception as e:
        logging.error(f"Ошибка в get_event_phone для chat_id {chat_id}: {e}")
        bot.send_message(chat_id, "⚠️ Произошла ошибка. Пожалуйста, попробуйте снова.", parse_mode="Markdown")
        main_menu_inline(chat_id)

def get_comment_buttons():
    """Возвращает инлайн-кнопки 'Да' и 'Нет' для комментария."""
    markup = types.InlineKeyboardMarkup()
    btn_yes = types.InlineKeyboardButton("Да", callback_data="comment_yes")
    btn_no = types.InlineKeyboardButton("Нет", callback_data="comment_no")
    markup.add(btn_yes, btn_no)
    return markup

@bot.message_handler(func=lambda message: user_state.get(message.chat.id, {}).get('step') == 'ask_comment')
def handle_ask_comment(message):
    chat_id = message.chat.id
    logging.info(f"handle_ask_comment вызвана: chat_id={chat_id}, текст='{message.text}'")

    user_state[chat_id]['comment'] = message.text
    user_state[chat_id]['step'] = 'event_meeting_time' if user_state[chat_id].get('process') == 'event' else 'consent'
    logging.info(f"Комментарий сохранён для chat_id {chat_id}: {message.text}")

    try:
        if user_state[chat_id]['step'] == 'event_meeting_time':
            name = user_state[chat_id].get('name', 'Гость')
            bot.send_message(chat_id,
                             f"*{name}, приглашаем Вас на встречу для обсуждения банкетного меню. Укажите удобное для вас время и дату для встречи и обсуждения мероприятия (в формате ДД.ММ.ГГГГ ЧЧ:ММ, например, 15.05.2025 18:00)*:",
                             reply_markup=get_navigation_buttons(), parse_mode="Markdown")
        else:
            markup = types.InlineKeyboardMarkup()
            btn_consent = types.InlineKeyboardButton("Согласен", callback_data="consent_yes")
            btn_privacy = types.InlineKeyboardButton("Политика конфиденциальности", callback_data="show_privacy")
            markup.add(btn_consent, btn_privacy)
            process = user_state[chat_id].get('process')
            phone = user_state[chat_id].get('phone') or user_state[chat_id].get('event_phone')
            if process == 'gift':
                bot.send_message(chat_id,
                                 "*Для завершения заказа сертификата подтвердите согласие на обработку персональных данных.*",
                                 reply_markup=markup, parse_mode="Markdown")
            else:
                bot.send_message(chat_id,
                                 "*Для завершения бронирования подтвердите согласие на обработку персональных данных.*",
                                 reply_markup=markup, parse_mode="Markdown")
            log_data_request(chat_id, phone, "consent_request", f"Запрос согласия отправлен для процесса {process}")
    except Exception as e:
        logging.error(f"Ошибка в handle_ask_comment для chat_id {chat_id}: {e}")
        bot.send_message(chat_id, "⚠️ Произошла ошибка. Пожалуйста, попробуйте снова.", parse_mode="Markdown")
        main_menu_inline(chat_id)

@bot.message_handler(func=lambda message: user_state.get(message.chat.id, {}).get('step') == 'name')
def get_booking_name(message):
    user_state[message.chat.id]['name'] = message.text
    user_state[message.chat.id]['step'] = None
    send_hall_map(message.chat.id)

@bot.message_handler(func=lambda message: user_state.get(message.chat.id, {}).get('step') == 'date')
def get_booking_date(message):
    try:
        date = datetime.datetime.strptime(message.text, '%d.%m.%Y').strftime('%d.%m.%Y')
        current_date = datetime.datetime.now().strftime('%d.%m.%Y')
        if datetime.datetime.strptime(date, '%d.%m.%Y') < datetime.datetime.strptime(current_date, '%d.%m.%Y'):
            bot.send_message(message.chat.id, "*❌ Нельзя забронировать столик на прошедшую дату. Введите снова (ДД.ММ.ГГГГ):*",
                             reply_markup=get_navigation_buttons(), parse_mode="Markdown")
            return
        user_state[message.chat.id]['date'] = date
        user_state[message.chat.id]['step'] = 'time'
        ask_time(message.chat.id)
    except ValueError:
        bot.send_message(message.chat.id, "*❌ Неверный формат даты. Введите снова (ДД.ММ.ГГГГ):*",
                         reply_markup=get_navigation_buttons(), parse_mode="Markdown")

@bot.message_handler(func=lambda message: user_state.get(message.chat.id, {}).get('step') == 'time')
def get_booking_time(message):
    try:
        time = datetime.datetime.strptime(message.text, '%H:%M').strftime('%H:%M')
        start_time = datetime.datetime.strptime(time, '%H:%M')
        close_time = datetime.datetime.strptime("23:00", '%H:%M')
        open_time = datetime.datetime.strptime("08:00", '%H:%M')
        latest_booking_time = datetime.datetime.strptime("22:00", '%H:%M')
        current_date = datetime.datetime.now().strftime('%d.%m.%Y')
        current_time = datetime.datetime.now().strftime('%H:%M')
        booking_date = user_state[message.chat.id]['date']
        if booking_date == current_date and time < current_time:
            bot.send_message(message.chat.id, "*❌ Нельзя забронировать столик на прошедшее время. Введите снова (ЧЧ:ММ):*",
                             reply_markup=get_navigation_buttons(), parse_mode="Markdown")
            return
        if start_time < open_time or start_time > close_time:
            bot.send_message(message.chat.id,
                             "*❌ Ресторан работает с 08:00 до 23:00. Время начала брони должно быть в этом диапазоне. Введите снова (ЧЧ:ММ):*",
                             reply_markup=get_navigation_buttons(), parse_mode="Markdown")
            ask_time(message.chat.id)
            return
        if start_time > latest_booking_time and start_time <= close_time:
            bot.send_message(message.chat.id,
                             "*❌ Извините, но заказы принимаются только до 22:00. Если вы планируете посетить ресторан и сделать заказ после 22:00, пожалуйста, свяжитесь с нами по телефону +7 (951) 506-80-80. Спасибо за понимание!*",
                             reply_markup=get_navigation_buttons(), parse_mode="Markdown")
            ask_time(message.chat.id)
            return
        user_state[message.chat.id]['time'] = time
        table_id = user_state[message.chat.id]['table']
        date = user_state[message.chat.id]['date']
        end_time_dt = start_time + datetime.timedelta(hours=3)
        if end_time_dt > close_time:
            end_time_dt = close_time
        end_time = end_time_dt.strftime('%H:%M')
        conn = sqlite3.connect('booking.db', check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT start_time, end_time FROM tables
            WHERE id = ? AND date = ? AND status = "confirmed"
        ''', (table_id, date))
        existing_bookings = cursor.fetchall()
        for booking in existing_bookings:
            existing_start_time = datetime.datetime.strptime(booking[0], '%H:%M')
            existing_end_time = datetime.datetime.strptime(booking[1], '%H:%M')
            if (start_time < existing_end_time) and (end_time_dt > existing_start_time):
                bot.send_message(message.chat.id,
                                 f"*❌ Этот столик уже забронирован с {booking[0]} до {booking[1]}. Выберите другое время или свяжитесь с нами по телефону +7 (951) 506-80-80*",
                                 reply_markup=get_navigation_buttons(), parse_mode="Markdown")
                ask_time(message.chat.id)
                conn.close()
                return
        user_state[message.chat.id]['step'] = 'people'
        ask_people(message.chat.id)
        conn.close()
    except ValueError:
        bot.send_message(message.chat.id, "*❌ Неверный формат времени. Введите снова (ЧЧ:ММ):*",
                         reply_markup=get_navigation_buttons(), parse_mode="Markdown")

@bot.message_handler(func=lambda message: user_state.get(message.chat.id, {}).get('step') == 'people')
def get_num_of_people(message):
    if message.text.isdigit():
        user_state[message.chat.id]['num_of_people'] = int(message.text)
        user_state[message.chat.id]['step'] = 'phone'
        ask_phone(message.chat.id)
    else:
        bot.send_message(message.chat.id, "*❌ Введите корректное число персон:*",
                         reply_markup=get_navigation_buttons(), parse_mode="Markdown")

@bot.message_handler(func=lambda message: user_state.get(message.chat.id, {}).get('step') == 'phone')
def get_phone_number(message):
    chat_id = message.chat.id
    logging.info(f"get_phone_number вызвана: chat_id={chat_id}, текст='{message.text}', состояние={user_state.get(chat_id, {})}")

    phone = message.text.strip()
    if not phone.isdigit() or len(phone) < 10:
        bot.send_message(chat_id, "*❌ Введите корректный номер телефона (только цифры, минимум 10 знаков):*",
                         reply_markup=get_navigation_buttons(), parse_mode="Markdown")
        logging.info(f"Некорректный номер телефона: {phone} для chat_id {chat_id}")
        return

    try:
        user_state[chat_id]['phone'] = phone
        user_state[chat_id]['step'] = 'ask_comment'
        user_state[chat_id]['process'] = 'table'
        name = user_state[chat_id].get('name', 'Гость')
        bot.send_message(chat_id,
                         f"*{name}*, Вы хотите оставить пожелание/комментарий к бронированию?",
                         reply_markup=get_comment_buttons(), parse_mode="Markdown")
        logging.info(f"Вопрос о комментарии отправлен для chat_id {chat_id} после ввода телефона {phone}")
    except Exception as e:
        logging.error(f"Ошибка в get_phone_number для chat_id {chat_id}: {e}")
        bot.send_message(chat_id, "⚠️ Произошла ошибка. Пожалуйста, попробуйте снова.", parse_mode="Markdown")
        main_menu_inline(chat_id)

@bot.message_handler(func=lambda message: user_state.get(message.chat.id, {}).get('step') == 'add_comment')
def get_comment(message):
    chat_id = message.chat.id
    user_state[chat_id]['comment'] = message.text
    user_state[chat_id]['step'] = 'event_meeting_time' if user_state[chat_id].get('process') == 'event' else 'consent'
    if user_state[chat_id]['step'] == 'event_meeting_time':
        name = user_state[chat_id].get('name', 'Гость')
        bot.send_message(chat_id,
                         f"*{name}, приглашаем Вас на встречу для обсуждения банкетного меню. Укажите удобное для вас время и дату для встречи и обсуждения мероприятия (в формате ДД.ММ.ГГГГ ЧЧ:ММ)*:",
                         reply_markup=get_navigation_buttons(), parse_mode="Markdown")
    else:
        markup = types.InlineKeyboardMarkup()
        btn_consent = types.InlineKeyboardButton("Согласен", callback_data="consent_yes")
        btn_privacy = types.InlineKeyboardButton("Политика конфиденциальности", callback_data="show_privacy")
        markup.add(btn_consent, btn_privacy)
        process = user_state[chat_id].get('process')
        phone = user_state[chat_id].get('phone') or user_state[chat_id].get('event_phone')
        try:
            if process == 'gift':
                bot.send_message(chat_id,
                                 "*Для завершения заказа сертификата подтвердите согласие на обработку персональных данных.*",
                                 reply_markup=markup, parse_mode="Markdown")
            else:
                bot.send_message(chat_id,
                                 "*Для завершения бронирования подтвердите согласие на обработку персональных данных.*",
                                 reply_markup=markup, parse_mode="Markdown")
            log_data_request(chat_id, phone, "consent_request", f"Запрос согласия отправлен для процесса {process}")
            logging.info(f"Комментарий сохранён для chat_id {chat_id}, переход к consent")
        except Exception as e:
            logging.error(f"Ошибка в get_comment для chat_id {chat_id}: {e}")
            bot.send_message(chat_id, "⚠️ Произошла ошибка. Пожалуйста, попробуйте снова.", parse_mode="Markdown")
            main_menu_inline(chat_id)

@bot.message_handler(func=lambda message: user_state.get(message.chat.id, {}).get('step') == 'event_meeting_time')
def get_event_meeting_time(message):
    chat_id = message.chat.id
    logging.info(f"get_event_meeting_time вызвана: chat_id={chat_id}, текст='{message.text}', состояние={user_state.get(chat_id, {})}")

    try:
        meeting_datetime = datetime.datetime.strptime(message.text, '%d.%m.%Y %H:%M')
        current_datetime = datetime.datetime.now()
        if meeting_datetime < current_datetime:
            bot.send_message(chat_id, "*❌ Нельзя выбрать прошедшую дату и время. Введите снова (ДД.ММ.ГГГГ ЧЧ:ММ):*",
                            reply_markup=get_navigation_buttons(), parse_mode="Markdown")
            return
        user_state[chat_id]['event_meeting_time'] = meeting_datetime.strftime('%d.%m.%Y %H:%M')
        user_state[chat_id]['step'] = 'consent'
        user_state[chat_id]['process'] = 'event'
        markup = types.InlineKeyboardMarkup()
        btn_consent = types.InlineKeyboardButton("Согласен", callback_data="consent_yes")
        btn_privacy = types.InlineKeyboardButton("Политика конфиденциальности", callback_data="show_privacy")
        markup.add(btn_consent, btn_privacy)
        phone = user_state[chat_id].get('event_phone')
        bot.send_message(chat_id,
                         "*Для завершения регистрации мероприятия подтвердите согласие на обработку персональных данных.*",
                         reply_markup=markup, parse_mode="Markdown")
        log_data_request(chat_id, phone, "consent_request", "Запрос согласия отправлен для процесса event")
        logging.info(f"Дата и время встречи сохранены для chat_id {chat_id}: {message.text}")
    except ValueError:
        bot.send_message(chat_id, "*❌ Неверный формат. Введите снова (ДД.ММ.ГГГГ ЧЧ:ММ):*",
                         reply_markup=get_navigation_buttons(), parse_mode="Markdown")
    except Exception as e:
        logging.error(f"Ошибка в get_event_meeting_time для chat_id {chat_id}: {e}")
        bot.send_message(chat_id, "⚠️ Произошла ошибка. Пожалуйста, попробуйте снова.", parse_mode="Markdown")
        main_menu_inline(chat_id)

@bot.callback_query_handler(func=lambda call: call.data in ["comment_yes", "comment_no"])
def handle_comment_choice(call):
    bot.answer_callback_query(call.id)
    chat_id = call.message.chat.id
    logging.info(f"handle_comment_choice: chat_id={chat_id}, выбор={call.data}")

    if call.data == "comment_yes":
        user_state[chat_id]['step'] = 'add_comment'
        bot.send_message(chat_id, "*Напишите Ваш комментарий:*",
                         reply_markup=get_navigation_buttons(), parse_mode="Markdown")
    elif call.data == "comment_no":
        user_state[chat_id]['comment'] = 'Нет комментария'
        user_state[chat_id]['step'] = 'event_meeting_time' if user_state[chat_id].get('process') == 'event' else 'consent'
        try:
            if user_state[chat_id]['step'] == 'event_meeting_time':
                name = user_state[chat_id].get('name', 'Гость')
                bot.send_message(chat_id,
                                 f"*{name}, приглашаем Вас на встречу для обсуждения банкетного меню. Укажите удобное для вас время и дату для встречи и обсуждения мероприятия (в формате ДД.ММ.ГГГГ ЧЧ:ММ)*:",
                                 reply_markup=get_navigation_buttons(), parse_mode="Markdown")
            else:
                markup = types.InlineKeyboardMarkup()
                btn_consent = types.InlineKeyboardButton("Согласен", callback_data="consent_yes")
                btn_privacy = types.InlineKeyboardButton("Политика конфиденциальности", callback_data="show_privacy")
                markup.add(btn_consent, btn_privacy)
                process = user_state[chat_id].get('process')
                phone = user_state[chat_id].get('phone') or user_state[chat_id].get('event_phone')
                if process == 'gift':
                    bot.send_message(chat_id,
                                     "*Для завершения заказа сертификата подтвердите согласие на обработку персональных данных.*",
                                     reply_markup=markup, parse_mode="Markdown")
                else:
                    bot.send_message(chat_id,
                                     "*Для завершения бронирования подтвердите согласие на обработку персональных данных (имя, номер телефона) в соответствии с Федеральным законом №152-ФЗ.*",
                                     reply_markup=markup, parse_mode="Markdown")
                log_data_request(chat_id, phone, "consent_request", f"Запрос согласия отправлен для процесса {process}")
        except Exception as e:
            logging.error(f"Ошибка в handle_comment_choice для chat_id {chat_id}: {e}")
            bot.send_message(chat_id, "⚠️ Произошла ошибка. Пожалуйста, попробуйте снова.", parse_mode="Markdown")
            main_menu_inline(chat_id)

@bot.callback_query_handler(func=lambda call: call.data == "show_privacy")
def show_privacy_policy(call):
    bot.answer_callback_query(call.id)
    chat_id = call.message.chat.id
    if chat_id not in user_state:
        user_state[chat_id] = {}
    user_state[chat_id]['step'] = 'privacy'
    markup = types.InlineKeyboardMarkup()
    btn_consent = types.InlineKeyboardButton("Согласен", callback_data="consent_yes")
    btn_back = types.InlineKeyboardButton("Вернуться в главное меню", callback_data="back_to_main_menu")
    markup.add(btn_consent, btn_back)
    phone = user_state[chat_id].get('phone') or user_state[chat_id].get('event_phone') or "N/A"
    bot.send_message(chat_id,
                     "*📜 Политика конфиденциальности ресторана «Глупый Француз»*\n\n"
                     "В соответствии с Федеральным законом №152-ФЗ «О персональных данных» ресторан «Глупый Француз» (оператор персональных данных: ООО «Гид-Фуд», адрес: ул. Козлова, 42, Ростов-на-Дону, Россия) информирует вас о порядке обработки персональных данных при использовании нашего Telegram-бота. Обработка осуществляется на основании вашего согласия (ст. 6, п.1, ст. 9 152-ФЗ), а также в целях исполнения договора (оказания услуги бронирования, покупки сертификата).\n\n"
                     "*📋 Какие данные мы собираем и для чего*\n\n"
                     "Мы собираем ваше имя, номер телефона, а также адрес (для заказа сертификатов), комментарии и дату/время встречи (для мероприятий) исключительно для:\n"
                     "- создания и подтверждения бронирований столиков;\n"
                     "- связи с вами для уточнения деталей брони;\n"
                     "- отправки уведомлений о бронировании и возможности оставить отзыв;\n"
                     "- организации мероприятий и доставки подарочных сертификатов.\n"
                     "Данные обрабатываются на основании вашего согласия в соответствии со ст. 6 и ст. 9 152-ФЗ.\n\n"
                     "*🔒 Как мы защищаем данные*\n\n"
                     "Ваши данные хранятся в защищённой базе данных на серверах в Российской Федерации. Мы используем шифрование и ограничиваем доступ к данным. Данные не передаются третьим лицам и не используются для иных целей, кроме указанных выше.\n\n"
                     "*🗑️ Срок хранения и удаление данных*\n\n"
                     "Ваши персональные данные (имя, адрес, комментарии) удаляются из нашей базы данных по истечению срока бронирования и завершении всех связанных с ним процессов (например, обратной связи), если отсутствуют иные законные основания для их хранения. Данные о вашем согласии на обработку и минимальные данные для идентификации (ID чата, номер телефона) хранятся до 3 лет в соответствии со сроком исковой давности для защиты от возможных претензий.\n\n"
                     "*⚖️ Ваши права*\n\n"
                     "Согласно ст. 14 152-ФЗ, вы имеете право:\n"
                     "- запросить информацию о том, какие ваши данные обрабатываются;\n"
                     "- потребовать уточнения, блокировки или удаления ваших данных, если они неполные, устаревшие или ненужные;\n"
                     "- отозвать согласие на обработку данных.\n"
                     "Для реализации этих прав свяжитесь с нами:\n"
                     "- по электронной почте: info@franz.chehovgroup.ru;\n"
                     "- через Telegram: +7 (951) 506-80-80.\n"
                     "Запрос на удаление данных будет выполнен в течение 10 рабочих дней с момента получения обращения.\n\n"
                     "*🌍 Отсутствие трансграничной передачи*\n\n"
                     "Ваши данные обрабатываются и хранятся исключительно в Российской Федерации. Трансграничная передача данных не осуществляется.\n\n"
                     "*📞 Контакты оператора*\n\n"
                     "Если у вас есть вопросы или пожелания по обработке данных, свяжитесь с нами:\n"
                     "Наименование: ООО «Гид-Фуд»\n"
                     "Адрес: ул. Козлова, 42, Ростов-на-Дону, Россия\n"
                     "ОГРН 1176196046355 от 29 сентября 2017 г.\n"
                     "ИНН/КПП 6164117129/616401001\n"
                     "Телефон: +7 (951) 506-80-80\n"
                     "Email: info@franz.chehovgroup.ru\n\n"
                     "Мы ценим ваше доверие и гарантируем соблюдение всех требований законодательства РФ при обработке ваших персональных данных.",
                     reply_markup=markup, parse_mode="Markdown")
    log_data_request(chat_id, phone, "privacy_view", "Политика конфиденциальности просмотрена")

@bot.callback_query_handler(func=lambda call: call.data == "consent_yes")
def handle_consent_yes(call):
    bot.answer_callback_query(call.id)
    chat_id = call.message.chat.id
    state = user_state.get(chat_id, {})
    process = state.get('process')
    phone = state.get('phone') or state.get('event_phone')

    try:
        # Логируем согласие в таблицу consents
        conn = sqlite3.connect('booking.db', check_same_thread=False)
        cursor = conn.cursor()
        timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute('''
            INSERT INTO consents (timestamp, chat_id, phone, consent_type, result)
            VALUES (?, ?, ?, ?, ?)
        ''', (timestamp, chat_id, phone or "N/A", process, "Согласие получено"))
        conn.commit()
        conn.close()

        if process == 'table':
            save_booking(chat_id)
            user_state[chat_id] = {'phone': phone} if phone else {}
        elif process == 'event':
            name = state.get('name', 'Не указано')
            event_type = state.get('event_type', 'Не указано')
            event_date = state.get('event_date', 'Не указано')
            event_time = state.get('event_time', 'Не указано')
            event_guests = state.get('event_guests', 'Не указано')
            comment = state.get('comment', 'Нет комментария')
            meeting_time = state.get('event_meeting_time', 'Не указано')
            bot.send_message(ADMIN_CHAT_ID,
                             f"🎉 Новый запрос на мероприятие:\n"
                             f"Имя: {name}\n"
                             f"Тип: {event_type}\n"
                             f"Дата: {event_date}\n"
                             f"Время: {event_time}\n"
                             f"Гостей: {event_guests}\n"
                             f"Телефон: {phone}\n"
                             f"Комментарий: {comment}\n"
                             f"Встреча для обсуждения меню: {meeting_time}",
                             parse_mode="Markdown")
            bot.send_message(chat_id,
                             f"*Мы рады, что Вы выбрали нас для вашего события, {name}!*\n"
                             f"*В течение дня мы свяжемся с Вами, чтобы обсудить дату, формат и детали вашего мероприятия.* 🎉❤️",
                             reply_markup=types.ReplyKeyboardRemove(), parse_mode="Markdown")
            main_menu_inline(chat_id)
            user_state[chat_id] = {'phone': phone} if phone else {}
        elif process == 'gift':
            name = state.get('name', 'Не указано')
            address = state.get('address', 'Не указано')
            certificate_type = state.get('certificate_type', 'Не указано')
            # Маппинг типов сертификатов на читаемые названия
            certificate_names = {
                'gastro': 'Гастро-ужин',
                'standard': 'Стандартный',
                'romantic': 'Романтический ужин',
                'chef': 'Ужин от шеф-повара',
                'breakfast': 'Завтрак на две персоны',
                'hotel': 'Номер в бутик-отеле'
            }
            certificate_display_name = certificate_names.get(certificate_type, certificate_type)
            bot.send_message(ADMIN_CHAT_ID,
                             f"🎁 Новый заказ сертификата:\n"
                             f"Имя: {name}\n"
                             f"Тип сертификата: {certificate_type}\n"
                             f"Адрес доставки: {address}\n"
                             f"Телефон: {phone}",
                             parse_mode="Markdown")
            bot.send_message(chat_id,
                             f"*Вы сделали великолепный выбор, приобретя подарочный сертификат «{certificate_display_name}», {name}!*\n"
                             f"*Это путешествие в мир изысканных вкусов и незабываемых впечатлений уже на пути к Вам!*\n"
                             f"*Мы доставим сертификат Вам по адресу: {address} в кратчайшие сроки.*\n"
                             f"*Мы свяжемся с Вами по номеру {phone}, чтобы уточнить время доставки.* 💖🌼",
                             reply_markup=types.ReplyKeyboardRemove(), parse_mode="Markdown")
            main_menu_inline(chat_id)
            user_state[chat_id] = {'phone': phone} if phone else {}
    except Exception as e:
        logging.error(f"Ошибка в handle_consent_yes: {e}")
        bot.send_message(chat_id, "⚠️ Произошла ошибка. Пожалуйста, попробуйте снова.", parse_mode="Markdown")
        main_menu_inline(chat_id)


@bot.callback_query_handler(func=lambda call: call.data == "cancel_process")
def cancel_process(call):
    bot.answer_callback_query(call.id)
    chat_id = call.message.chat.id
    main_menu_inline(chat_id)
    user_state[chat_id] = {}

@bot.message_handler(commands=['contact'])
def contact_command(message):
    chat_id = message.chat.id
    markup = types.InlineKeyboardMarkup()
    btn_contact = types.InlineKeyboardButton("Связаться с нами", url="https://t.me/+79515068080")
    markup.add(btn_contact)
    bot.send_message(chat_id, "📞 Вы можете написать нам в Телеграмме:", reply_markup=markup)

@bot.message_handler(commands=['my_booking'])
def my_booking_command(message):
    show_my_booking(message)

@bot.message_handler(func=lambda message: message.text == "Моя бронь")
def show_my_booking(message):
    chat_id = message.chat.id
    current_time = datetime.datetime.now()
    conn = sqlite3.connect('booking.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, date, start_time, end_time, num_of_people, phone_number, comment
        FROM tables 
        WHERE chat_id = ? AND status = "confirmed"
    ''', (chat_id,))
    bookings = cursor.fetchall()
    active_bookings = []
    for booking in bookings:
        table_id, date, start_time, end_time, num_of_people, phone_number, comment = booking
        booking_datetime_end = datetime.datetime.strptime(f"{date} {end_time}", '%d.%m.%Y %H:%M')
        if booking_datetime_end > current_time:
            active_bookings.append(booking)
    if active_bookings:
        booking_info = "📅 *Ваши активные брони:*\n\n"
        markup = types.InlineKeyboardMarkup()
        for booking in active_bookings:
            table_id, date, start_time, end_time, num_of_people, phone_number, comment = booking
            booking_info += (
                f"*Столик: {table_id}*\n"
                f"📅 Дата: {date}\n"
                f"🕒 Время: {start_time} - {end_time}\n"
                f"👥 Гостей: {num_of_people}\n"
                f"📞 Телефон: {phone_number}\n"
                f"💬 Комментарий: {comment or 'Нет комментария'}\n"
                f"---\n"
            )
            markup.add(types.InlineKeyboardButton(f"Отменить бронь {table_id} ({date} {start_time})",
                                                  callback_data=f"cancel_{table_id}_{date}_{start_time}"))
        markup.add(types.InlineKeyboardButton("Вернуться в меню", callback_data="back_to_main_menu"))
        bot.send_message(chat_id, booking_info.strip(), reply_markup=markup, parse_mode="Markdown")
        log_data_request(chat_id, "N/A", "access", "Данные о бронировании предоставлены")
    else:
        bot.send_message(chat_id, "❌ У вас нет активных бронирований.", reply_markup=types.ReplyKeyboardRemove(), parse_mode="Markdown")
        log_data_request(chat_id, "N/A", "access", "Активные бронирования не найдены")
        main_menu_inline(chat_id)
    conn.close()

@bot.message_handler(func=lambda message: user_state.get(message.chat.id, {}).get('step') == 'check_phone')
def get_phone_for_check(message):
    phone = message.text.strip()
    if not phone.isdigit() or len(phone) < 10:
        bot.send_message(message.chat.id, "*❌ Введите корректный номер телефона (только цифры, минимум 10 знаков):*",
                         reply_markup=get_navigation_buttons(), parse_mode="Markdown")
        return
    user_state[message.chat.id]['phone'] = phone
    user_state[message.chat.id]['step'] = None
    show_my_booking(message)

@bot.callback_query_handler(func=lambda call: call.data.startswith("cancel_"))
def handle_cancel_booking(call):
    bot.answer_callback_query(call.id)
    chat_id = call.message.chat.id
    parts = call.data.split("_", 3)
    if len(parts) != 4:
        bot.send_message(chat_id, "❌ Ошибка в обработке команды (неверный формат данных).",
                         reply_markup=types.ReplyKeyboardRemove(), parse_mode="Markdown")
        main_menu_inline(chat_id)  # Используем инлайн-кнопки вместо get_main_menu_reply
        return
    _, table_id, date, start_time = parts
    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton("Да", callback_data=f"confirm_cancel_{table_id}_{date}_{start_time}"),
        types.InlineKeyboardButton("Нет", callback_data="keep_booking")
    )
    bot.send_message(chat_id, "Вы действительно хотите отменить бронь?", reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith("confirm_cancel_"))
def confirm_cancel_booking(call):
    bot.answer_callback_query(call.id)
    chat_id = call.message.chat.id
    parts = call.data.split("_")
    if len(parts) < 4:
        bot.send_message(chat_id, "❌ Ошибка в обработке команды (неверный формат данных).",
                         reply_markup=types.ReplyKeyboardRemove(), parse_mode="Markdown")
        main_menu_inline(chat_id)  # Используем инлайн-кнопки
        return
    _, _, table_id, date, start_time = parts[0], parts[1], parts[2], parts[3], "_".join(parts[4:])
    try:
        table_id = int(table_id)
    except ValueError:
        bot.send_message(chat_id, "❌ Ошибка: неверный номер столика.",
                         reply_markup=types.ReplyKeyboardRemove(), parse_mode="Markdown")
        main_menu_inline(chat_id)  # Используем инлайн-кнопки
        return
    conn = sqlite3.connect('booking.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT rowid, phone_number
        FROM tables
        WHERE id = ? AND date = ? AND start_time = ? AND status = "confirmed" AND chat_id = ?
    ''', (table_id, date, start_time, chat_id))
    result = cursor.fetchone()
    if result:
        rowid, phone_number = result
        cursor.execute('DELETE FROM tables WHERE id = ? AND date = ? AND start_time = ? AND status = "confirmed"',
                       (table_id, date, start_time))
        cursor.execute('DELETE FROM reviews WHERE booking_id = ?', (rowid,))
        conn.commit()
        bot.send_message(chat_id, "❌ Бронь успешно отменена.",
                         reply_markup=types.ReplyKeyboardRemove(), parse_mode="Markdown")
        bot.send_message(ADMIN_CHAT_ID, f"❌ Бронь отменена:\nСтолик: {table_id}\nДата: {date}\nВремя: {start_time}")
        log_data_request(chat_id, phone_number or "N/A", "cancel_delete", f"Бронь {date} {start_time} удалена при отмене")
    else:
        bot.send_message(chat_id, "❌ Ошибка: бронь не найдена в базе.",
                         reply_markup=types.ReplyKeyboardRemove(), parse_mode="Markdown")
    conn.close()
    main_menu_inline(chat_id)  # Используем инлайн-кнопки

@bot.callback_query_handler(func=lambda call: call.data == "keep_booking")
def keep_booking(call):
    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id, "✅ Бронь сохранена.",
                     reply_markup=types.ReplyKeyboardRemove(), parse_mode="Markdown")
    main_menu_inline(call.message.chat.id)  # Используем инлайн-кнопки

@bot.message_handler(commands=['help'])
def help_command(message):
    chat_id = message.chat.id
    help_text = (
        "🍷 *Добро пожаловать в помощь от «Глупого Француза»!*\n\n"
        "Мы здесь, чтобы ваш визит к нам стал настоящим удовольствием. Ответим на самые популярные вопросы, чтобы всё было просто и понятно. 😊\n\n"

        "*1. Как забронировать уютный вечер в «Глупом Французе»?*\n"
        "Выберите *Забронировать столик* в главном меню, ответьте на несколько вопросов о дате, времени и количестве гостей — и ваш столик уже ждёт! Если что-то пошло не так, нажмите *Вернуться* (на шаг назад) или *Отмена* (в главное меню) и начните заново. 🍽\n\n"

        "*2. Планы изменились, как отменить бронь?*\n"
        "Ничего страшного! Введите команду */my_booking* или выберите *Моя бронь* в меню. Вы увидите свои активные брони и сможете отменить нужную, нажав *Отменить бронь*. Мы всегда готовы помочь, если возникнут вопросы! 📅\n\n"

        "*3. Хочу провести особое событие — свадьбу, день рождения или корпоратив. Как это организовать?*\n"
        "Нажмите *Провести мероприятие* в главном меню и расскажите нам о вашем событии. Мы свяжемся с вами в течение дня, чтобы обсудить меню, формат и все детали. Ваш праздник — наша забота! 🎉\n\n"

        "*4. Можно ли заранее выбрать блюда из меню?*\n"
        "Конечно! В главном меню выберите *Меню*, просмотрите наши блюда и нажмите *Сделать заказ*. В пожеланиях укажите, что это заказ к бронированию, и добавьте имя и дату визита. Мы подготовим всё к вашему приходу! 🍴\n\n"

        "*5. Хочу оставить пожелания к бронированию — например, столик у окна или особое блюдо. Как это сделать?*\n"
        "При бронировании столика через главное меню вы сможете добавить комментарий — например, «столик у окна» или «безглютеновое меню». Мы учтём ваши пожелания, чтобы вечер прошёл идеально! 💬\n\n"

        "*6. Как поделиться впечатлениями о ресторане?*\n"
        "После визита мы пришлём вам сообщение с просьбой оставить отзыв. Это займёт всего пару минут, а ваше мнение поможет нам стать ещё лучше! Если хотите поделиться впечатлениями прямо сейчас, напишите нам на +7 (951) 506-80-80 в Telegram. 🌟\n\n"

        "*7. Остались вопросы или нужна помощь?*\n"
        "Мы всегда рядом! Свяжитесь с нами по телефону +7 (951) 506-80-80, в Telegram (@+79515068080) или по почте info@franz.chehovgroup.ru. «Глупый Француз» — это место, где каждый гость чувствует себя желанным! 💖"
    )
    markup = types.InlineKeyboardMarkup()
    btn_back = types.InlineKeyboardButton("Вернуться в меню", callback_data="back_to_main_menu")
    markup.add(btn_back)
    bot.send_message(chat_id, help_text, reply_markup=markup, parse_mode="Markdown")


@bot.message_handler(commands=['book_table'])
def book_table_command(message):
    send_hall_map(message.chat.id)

def send_hall_map(chat_id):
    photos = ['зал1.jpg', 'зал2.jpg', 'веранда.jpg', 'photo_graphics.jpg']
    try:
        media = [
            types.InputMediaPhoto(open(photos[0], 'rb')),
            types.InputMediaPhoto(open(photos[1], 'rb')),
            types.InputMediaPhoto(open(photos[2], 'rb')),
            types.InputMediaPhoto(open(photos[3], 'rb'))
        ]
        bot.send_media_group(chat_id, media)
    except FileNotFoundError:
        logging.error("Файлы зала не найдены")
        bot.send_message(chat_id, "⚠️ Не удалось загрузить изображения зала.")
    markup = types.InlineKeyboardMarkup(row_width=3)
    buttons = [types.InlineKeyboardButton(f"Стол {i}", callback_data=f'table_{i}') for i in range(1, 16)]
    for i in range(0, len(buttons), 3):
        markup.row(*buttons[i:i + 3])
    bot.send_message(chat_id, "*Выберите столик:*", reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith('table_'))
def handle_table_selection(call):
    bot.answer_callback_query(call.id)
    chat_id = call.message.chat.id
    table_number = call.data.split('_')[1]
    if chat_id not in user_state:
        user_state[chat_id] = {}
    user_state[chat_id]['table'] = table_number
    user_state[chat_id]['step'] = 'date'
    bot.send_message(chat_id,
                     "*Введите дату бронирования (формат ДД.ММ.ГГГГ) либо нажмите на кнопку:*",
                     reply_markup=get_date_buttons(), parse_mode="Markdown")

def ask_date(chat_id):
    bot.send_message(chat_id,
                     "*Введите дату бронирования (формат ДД.ММ.ГГГГ) либо нажмите на кнопку:*",
                     reply_markup=get_date_buttons(), parse_mode="Markdown")

def ask_time(chat_id):
    bot.send_message(chat_id,
                     "*Введите время бронирования (формат ЧЧ:ММ) либо нажмите на кнопку:*",
                     reply_markup=get_time_buttons(), parse_mode="Markdown")

def ask_people(chat_id):
    bot.send_message(chat_id, "*Введите количество персон:*",
                     reply_markup=get_navigation_buttons(), parse_mode="Markdown")

def ask_phone(chat_id):
    bot.send_message(chat_id, "*Введите ваш номер телефона:*",
                     reply_markup=get_navigation_buttons(), parse_mode="Markdown")


def get_date_buttons():
    markup = types.InlineKeyboardMarkup(row_width=2)
    btn_cancel = types.InlineKeyboardButton("Отмена", callback_data="cancel")
    btn_back = types.InlineKeyboardButton("Вернуться", callback_data="back")
    markup.row(btn_cancel, btn_back)

    today = datetime.datetime.now().date()  # Только дата, без времени
    weekdays = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]

    for i in range(7):
        current_date = today + datetime.timedelta(days=i)
        day_name = weekdays[current_date.weekday()]
        date_str = current_date.strftime('%d.%m.%Y')

        # Формируем текст: "Ср 09.11", "Чт 10.11" и т.д.
        display_text = f"{day_name} {current_date.strftime('%d.%m')}"

        btn = types.InlineKeyboardButton(display_text, callback_data=f"date_{date_str}")
        markup.row(btn)

    return markup


def get_time_buttons():
    markup = types.InlineKeyboardMarkup(row_width=3)
    btn_cancel = types.InlineKeyboardButton("Отмена", callback_data="cancel")
    btn_back = types.InlineKeyboardButton("Вернуться", callback_data="back")
    markup.row(btn_cancel, btn_back)

    start = datetime.datetime.strptime("08:00", "%H:%M")
    end = datetime.datetime.strptime("22:00", "%H:%M")
    current = start
    row = []
    while current <= end:
        time_str = current.strftime("%H:%M")
        btn = types.InlineKeyboardButton(time_str, callback_data=f"time_{time_str}")
        row.append(btn)
        if len(row) == 3:
            markup.row(*row)
            row = []
        current += datetime.timedelta(minutes=30)
    if row:
        markup.row(*row)

    return markup


@bot.callback_query_handler(func=lambda call: call.data.startswith('date_'))
def handle_date_button(call):
    bot.answer_callback_query(call.id)
    chat_id = call.message.chat.id
    date_str = call.data.split('_', 1)[1]

    # Проверяем, что дата не в прошлом
    selected_date = datetime.datetime.strptime(date_str, '%d.%m.%Y')
    if selected_date.date() < datetime.datetime.now().date():
        bot.send_message(chat_id, "*❌ Нельзя выбрать прошедшую дату.*", parse_mode="Markdown")
        return

    user_state[chat_id]['date'] = date_str
    user_state[chat_id]['step'] = 'time'

    bot.send_message(chat_id,
                     "*Введите время бронирования (формат ЧЧ:ММ) либо нажмите на кнопку:*",
                     reply_markup=get_time_buttons(), parse_mode="Markdown")


@bot.callback_query_handler(func=lambda call: call.data.startswith('time_'))
def handle_time_button(call):
    bot.answer_callback_query(call.id)
    chat_id = call.message.chat.id
    time_str = call.data.split('_', 1)[1]

    # Здесь вся твоя старая валидация времени (повторяем из get_booking_time)
    try:
        start_time = datetime.datetime.strptime(time_str, '%H:%M')
        close_time = datetime.datetime.strptime("23:00", '%H:%M')
        open_time = datetime.datetime.strptime("08:00", '%H:%M')
        latest_booking_time = datetime.datetime.strptime("22:00", '%H:%M')
        current_date = datetime.datetime.now().strftime('%d.%m.%Y')
        current_time = datetime.datetime.now().strftime('%H:%M')
        booking_date = user_state[chat_id]['date']

        if booking_date == current_date and time_str < current_time:
            bot.send_message(chat_id, "*❌ Нельзя забронировать на прошедшее время.*", reply_markup=get_time_buttons(),
                             parse_mode="Markdown")
            return

        if start_time < open_time or start_time > close_time:
            bot.send_message(chat_id, "*❌ Ресторан работает с 08:00 до 23:00.*", reply_markup=get_time_buttons(),
                             parse_mode="Markdown")
            return

        if start_time > latest_booking_time:
            bot.send_message(chat_id,
                             "*❌ Заказы принимаются только до 22:00. После — только по телефону +7 (951) 506-80-80.*",
                             reply_markup=get_time_buttons(), parse_mode="Markdown")
            return

        # Проверка пересечения с другими бронями
        table_id = user_state[chat_id]['table']
        date = user_state[chat_id]['date']
        end_time_dt = start_time + datetime.timedelta(hours=3)
        if end_time_dt > close_time:
            end_time_dt = close_time
        end_time = end_time_dt.strftime('%H:%M')

        conn = sqlite3.connect('booking.db', check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT start_time, end_time FROM tables
            WHERE id = ? AND date = ? AND status = "confirmed"
        ''', (table_id, date))
        existing_bookings = cursor.fetchall()
        conn.close()

        for booking in existing_bookings:
            existing_start = datetime.datetime.strptime(booking[0], '%H:%M')
            existing_end = datetime.datetime.strptime(booking[1], '%H:%M')
            if start_time < existing_end and end_time_dt > existing_start:
                bot.send_message(chat_id,
                                 f"*❌ Столик занят с {booking[0]} до {booking[1]}. Выберите другое время.*",
                                 reply_markup=get_time_buttons(), parse_mode="Markdown")
                return

        user_state[chat_id]['time'] = time_str
        user_state[chat_id]['step'] = 'people'
        ask_people(chat_id)

    except Exception as e:
        logging.error(f"Ошибка в handle_time_button: {e}")
        bot.send_message(chat_id, "*❌ Ошибка времени. Попробуйте ещё раз.*", reply_markup=get_time_buttons(),
                         parse_mode="Markdown")

def save_booking(chat_id):
    conn = sqlite3.connect('booking.db', check_same_thread=False)
    cursor = conn.cursor()
    data = user_state.get(chat_id, {})
    table_id = data.get('table')
    date = data.get('date')
    start_time = data.get('time')
    num_of_people = data.get('num_of_people')
    phone_number = data.get('phone')
    name = data.get('name')
    comment = data.get('comment', 'Нет комментария')
    start_time_dt = datetime.datetime.strptime(start_time, '%H:%M')
    end_time_dt = start_time_dt + datetime.timedelta(hours=3)
    close_time = datetime.datetime.strptime("23:00", '%H:%M')
    if end_time_dt > close_time:
        end_time_dt = close_time
    end_time = end_time_dt.strftime('%H:%M')
    cursor.execute('''
        SELECT start_time, end_time FROM tables 
        WHERE id = ? AND date = ? AND status = "confirmed"
    ''', (table_id, date))
    existing_bookings = cursor.fetchall()
    for booking in existing_bookings:
        existing_start_time = datetime.datetime.strptime(booking[0], '%H:%M')
        existing_end_time = datetime.datetime.strptime(booking[1], '%H:%M')
        if (start_time_dt < existing_end_time) and (end_time_dt > existing_start_time):
            bot.send_message(chat_id,
                             f"*❌ Этот столик уже забронирован с {booking[0]} до {booking[1]}. Выберите другое время или свяжитесь с нами по телефону +7 (951) 506-80-80*",
                             parse_mode="Markdown")
            ask_time(chat_id)
            conn.close()
            return
    cursor.execute('''
        INSERT INTO tables (id, date, start_time, end_time, status, num_of_people, phone_number, chat_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (int(table_id), date, start_time, end_time, 'confirmed', num_of_people, phone_number, chat_id))
    conn.commit()
    booking_id = cursor.lastrowid
    cursor.execute('INSERT INTO reviews (booking_id, chat_id) VALUES (?, ?)', (booking_id, chat_id))
    conn.commit()
    markup = types.InlineKeyboardMarkup()
    btn_back = types.InlineKeyboardButton("Вернуться в меню", callback_data="back_to_main_menu")
    markup.add(btn_back)
    # Формируем сообщение о бронировании с использованием случайной фразы и полной информации
    confirmation_message = get_random_warm_phrase('booking').format(name=name, date=date, start_time=start_time)
    booking_details = (
        f"📅 Дата: {date}\n"
        f"🕒 Время: {start_time} - {end_time}\n"
        f"👥 Гостей: {num_of_people}\n"
        f"📞 Телефон: {phone_number}\n"
        f"💬 Комментарий: {comment}"
    )
    bot.send_message(chat_id, f"*{confirmation_message}*\n\n*{booking_details}*",
                     reply_markup=markup, parse_mode="Markdown")
    # Отправляем временное сообщение с часами для удаления текстовой клавиатуры
    try:
        temp_message = bot.send_message(chat_id, "⌛", reply_markup=types.ReplyKeyboardRemove(), parse_mode="Markdown")
        threading.Timer(0.11, lambda: bot.delete_message(chat_id, temp_message.message_id)).start()
    except Exception as e:
        logging.error(f"Ошибка при удалении временного сообщения в save_booking: {e}")
    bot.send_message(ADMIN_CHAT_ID, f"✅ Новое бронирование:\n"
                                    f"Имя гостя: {name}\n"
                                    f"Столик: {table_id}\n"
                                    f"Дата: {date}\n"
                                    f"Время: {start_time} - {end_time}\n"
                                    f"Гостей: {num_of_people}\n"
                                    f"Телефон: {phone_number}\n"
                                    f"💬 Комментарий: {comment}",
                     parse_mode="Markdown")
    conn.close()
    schedule_review_notifications(chat_id, booking_id, name, date, start_time)

def send_review_request(chat_id, name, booking_id, delay):
    try:
        markup = types.InlineKeyboardMarkup()
        btn_review = types.InlineKeyboardButton("Оставить отзыв",
                                               url="https://yandex.ru/maps/org/glupy_frantsuz/81763928384/reviews/?add-review=true&ll=39.690509%2C47.233435&z=13")
        btn_back = types.InlineKeyboardButton("Вернуться в меню", callback_data="back_to_main_menu")
        markup.add(btn_review, btn_back)
        bot.send_message(chat_id,
                         f"Здравствуйте, {name}! Надеюсь, вам нравится у нас в Глупом Французе! 🍷 Не хотите поделиться впечатлениями? Это занимает пару минут. Ваш отзыв очень важен для нас!",
                         reply_markup=markup, parse_mode="Markdown")
    except Exception as e:
        logging.error(f"Ошибка в send_review_request для chat_id {chat_id}: {e}")

def send_second_review_request(chat_id, name, booking_id, delay):
    try:
        conn = sqlite3.connect('booking.db', check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute('SELECT review_left FROM reviews WHERE booking_id = ?', (booking_id,))
        review_status = cursor.fetchone()
        if review_status and review_status[0] == 0:
            markup = types.InlineKeyboardMarkup()
            btn_review = types.InlineKeyboardButton("Оставить отзыв",
                                                   url="https://yandex.ru/maps/org/glupy_frantsuz/81763928384/reviews/?add-review=true&ll=39.690509%2C47.233435&z=13")
            btn_back = types.InlineKeyboardButton("Вернуться в меню", callback_data="back_to_main_menu")
            markup.add(btn_back)
            bot.send_message(chat_id,
                             f"Привет, {name}! Как прошёл Ваш визит в \"Глупый Француз\"? Нам важно узнать Ваше мнение — это помогает нам становиться лучше!",
                             reply_markup=markup, parse_mode="Markdown")
        conn.close()
    except Exception as e:
        logging.error(f"Ошибка в send_second_review_request для chat_id {chat_id}: {e}")
        conn.close()

def schedule_review_notifications(chat_id, booking_id, name, date, start_time):
    try:
        booking_dt = datetime.datetime.strptime(f"{date} {start_time}", '%d.%m.%Y %H:%M')
        first_notification = booking_dt + datetime.timedelta(hours=1.5)
        second_notification = booking_dt + datetime.timedelta(hours=4)
        delay_first = (first_notification - datetime.datetime.now()).total_seconds()
        if delay_first > 0:
            threading.Timer(delay_first, send_review_request, args=(chat_id, name, booking_id, delay_first)).start()
        delay_second = (second_notification - datetime.datetime.now()).total_seconds()
        if delay_second > 0:
            second_notification_time = second_notification.time()
            if second_notification_time > datetime.time(22, 0):
                next_day = second_notification + datetime.timedelta(days=1)
                second_notification = datetime.datetime.combine(next_day.date(), datetime.time(11, 0))
                delay_second = (second_notification - datetime.datetime.now()).total_seconds()
            threading.Timer(delay_second, send_second_review_request, args=(chat_id, name, booking_id, delay_second)).start()
    except Exception as e:
        logging.error(f"Ошибка в schedule_review_notifications: {e}")

@bot.callback_query_handler(func=lambda call: call.data.startswith("review_"))
def handle_review_submission(call):
    bot.answer_callback_query(call.id)
    booking_id = int(call.data.split("_")[1])
    conn = sqlite3.connect('booking.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('UPDATE reviews SET review_left = 1 WHERE booking_id = ?', (booking_id,))
    conn.commit()
    conn.close()
    bot.send_message(call.message.chat.id, "Спасибо за ваш отзыв!", parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data in ["cancel", "back"])
def handle_cancel_or_back(call):
    bot.answer_callback_query(call.id)
    chat_id = call.message.chat.id
    state = user_state.get(chat_id, {})
    phone = state.get('phone') or state.get('event_phone')
    logging.info(f"handle_cancel_or_back вызвана: chat_id={chat_id}, callback_data='{call.data}', step={state.get('step')}, process={state.get('process')}")

    if call.data == "cancel":
        logging.info(f"Отмена процесса для chat_id {chat_id}")
        main_menu_inline(chat_id)
        user_state[chat_id] = {'phone': phone} if phone else {}
        return

    elif call.data == "back":
        step = state.get('step')
        process = state.get('process')
        if step == 'event_name':
            main_menu_inline(chat_id)
            user_state[chat_id] = {'phone': phone} if phone else {}
        elif step == 'name':
            main_menu_inline(chat_id)
            user_state[chat_id] = {'phone': phone} if phone else {}
        elif step == 'event_type':
            user_state[chat_id]['step'] = 'event_name'
            bot.send_message(chat_id, "*Как к Вам можно обращаться?*",
                             reply_markup=get_navigation_buttons(), parse_mode="Markdown")
        elif step == 'event_date':
            user_state[chat_id]['step'] = 'event_type'
            bot.send_message(chat_id, "*У Вас праздник, День рождения или годовщина? Укажите это, пожалуйста:*",
                             reply_markup=get_navigation_buttons(), parse_mode="Markdown")
        elif step == 'event_time':
            user_state[chat_id]['step'] = 'event_date'
            bot.send_message(chat_id, "*Укажите дату вашего события (формат ДД.ММ.ГГГГ):*",
                             reply_markup=get_navigation_buttons(), parse_mode="Markdown")
        elif step == 'event_guests':
            user_state[chat_id]['step'] = 'event_time'
            bot.send_message(chat_id, "*Укажите время начала события (формат ЧЧ:ММ):*",
                             reply_markup=get_navigation_buttons(), parse_mode="Markdown")
        elif step == 'event_phone':
            user_state[chat_id]['step'] = 'event_guests'
            bot.send_message(chat_id, "*Укажите количество гостей:*",
                             reply_markup=get_navigation_buttons(), parse_mode="Markdown")
        elif step == 'event_meeting_time':
            user_state[chat_id]['step'] = 'ask_comment'
            name = user_state[chat_id].get('name', 'Гость')
            bot.send_message(chat_id,
                             f"*{name}*, Вы хотите оставить пожелание/комментарий к мероприятию?",
                             reply_markup=get_comment_buttons(), parse_mode="Markdown")
        elif step == 'date':
            user_state[chat_id]['step'] = None
            send_hall_map(chat_id)
        elif step == 'time':
            user_state[chat_id]['step'] = 'date'
            ask_date(chat_id)
        elif step == 'people':
            user_state[chat_id]['step'] = 'time'
            ask_time(chat_id)
        elif step == 'phone':
            user_state[chat_id]['step'] = 'people'
            ask_people(chat_id)
        elif step == 'check_phone':
            bot.send_message(chat_id, "❌ Проверка брони отменена.",
                             reply_markup=types.ReplyKeyboardRemove(), parse_mode="Markdown")
            main_menu_inline(chat_id)
            user_state[chat_id] = {'phone': phone} if phone else {}
        elif step == 'gift_name':
            markup = types.InlineKeyboardMarkup(row_width=2)
            btn1 = types.InlineKeyboardButton("Гастро-ужин", callback_data="gift_gastro")
            btn2 = types.InlineKeyboardButton("Стандартный", callback_data="gift_standard")
            btn3 = types.InlineKeyboardButton("Романтический ужин", callback_data="gift_romantic")
            btn4 = types.InlineKeyboardButton("Ужин от шеф-повара", callback_data="gift_chef")
            btn5 = types.InlineKeyboardButton("Завтрак на две персоны", callback_data="gift_breakfast")
            btn6 = types.InlineKeyboardButton("Номер в бутик-отеле", callback_data="gift_hotel")
            markup.add(btn1, btn2)
            markup.add(btn3, btn4)
            markup.add(btn5, btn6)
            bot.send_message(chat_id, "🎁 *Выберите тип подарочного сертификата:*",
                             reply_markup=markup, parse_mode="Markdown")
            user_state[chat_id] = {'phone': phone} if phone else {}
        elif step == 'gift_address':
            user_state[chat_id]['step'] = 'gift_name'
            bot.send_message(chat_id, "*Как к Вам можно обращаться?*",
                             reply_markup=get_navigation_buttons(), parse_mode="Markdown")
        elif step == 'gift_phone':
            user_state[chat_id]['step'] = 'gift_address'
            bot.send_message(chat_id, "*Укажите адрес доставки:*",
                             reply_markup=get_navigation_buttons(), parse_mode="Markdown")
        elif step == 'add_comment':
            if process == 'event':
                user_state[chat_id]['step'] = 'event_phone'
                bot.send_message(chat_id, "*Укажите номер для обратной связи:*",
                                 reply_markup=get_navigation_buttons(), parse_mode="Markdown")
            elif process == 'table':
                user_state[chat_id]['step'] = 'phone'
                bot.send_message(chat_id, "*Введите ваш номер телефона:*",
                                 reply_markup=get_navigation_buttons(), parse_mode="Markdown")
            elif process == 'gift':
                user_state[chat_id]['step'] = 'gift_phone'
                bot.send_message(chat_id, "*Укажите номер телефона для связи:*",
                                 reply_markup=get_navigation_buttons(), parse_mode="Markdown")
        else:
            main_menu_inline(chat_id)
            user_state[chat_id] = {'phone': phone} if phone else {}

create_table()
threading.Thread(target=cleanup_old_bookings, daemon=True).start()
threading.Thread(target=cleanup_old_logs, daemon=True).start()

# === НЕУБИВАЕМЫЙ POLLING С АВТО-ПЕРЕЗАПУСКОМ ===
import traceback

if __name__ == '__main__':
    logging.info("Бот запущен. Начинаем polling с авто-перезапуском...")
    while True:
        try:
            bot.polling(
                none_stop=True,          # Не останавливаться при ошибках в handlers
                interval=0,              # Мгновенный опрос
                timeout=60,              # Таймаут на long_poll
                long_polling_timeout=60, # Таймаут на чтение
                allowed_updates=None     # Все обновления
            )
        except Exception as e:
            logging.error(f"КРИТИЧЕСКАЯ ОШИБКА POLLING: {e}\n{traceback.format_exc()}")
            bot.send_message(ADMIN_CHAT_ID, f"🚨 Бот упал! Ошибка:\n{e}\nПерезапуск через 5 сек...")
            time.sleep(5)  # Пауза перед рестартом
            logging.info("Перезапуск polling...")

            continue  # Снова в цикл
