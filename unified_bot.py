# unified_bot.py
import json
import re
import logging
import asyncio
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler
import config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Состояния для ConversationHandler
SELECTING_STORY, SELECTING_SERIES = range(2)

# Функции для работы с данными
def load_data():
    try:
        with open('guides_data.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return {"guides_data.json": {}}

def save_data(data):
    with open('guides_data.json', 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

# Обработчик сообщений из канала (админская часть)
async def handle_channel_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.channel_post or not update.channel_post.photo:
        return

    if str(update.channel_post.chat.id) != str(config.CHANNEL_ID):
        return

    caption = update.channel_post.caption or ""
    hashtags = re.findall(r'#(\w+)', caption)

    if len(hashtags) < 2:
        await update.channel_post.reply_text("Нужны два хештега: #История #Серия")
        return

    story_name, series_name = hashtags[0], hashtags[1]
    file_id = update.channel_post.photo[-1].file_id

    data = load_data()
    
    if story_name not in data['guides_data.json']:
        data['guides_data.json'][story_name] = {"series": {}}
    
    if series_name not in data['guides_data.json'][story_name]['series']:
        data['guides_data.json'][story_name]['series'][series_name] = {"photos": []}
    
    data['guides_data.json'][story_name]['series'][series_name]["photos"].append(file_id)
    save_data(data)

    await update.channel_post.reply_text(
        f"✅ Фото добавлено в гайд!\n"
        f"🎮 Гайд: {story_name}\n"
        f"📖 Серия: {series_name}\n"
        f"📸 Фото: {len(data['guides_data.json'][story_name]['series'][series_name]['photos'])}"
    )

# Обработчик текстовых сообщений из канала (рассылка)
async def handle_channel_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.channel_post or not update.channel_post.text:
        return
    
    if str(update.channel_post.chat.id) != str(config.CHANNEL_ID):
        return
    
    # Пересылаем сообщение из канала всем пользователям
    try:
        with open('user_data.json', 'r', encoding='utf-8') as f:
            user_data = json.load(f)
    except FileNotFoundError:
        return  # Если нет пользователей, ничего не делаем
    
    message_text = update.channel_post.text
    
    for user_id in user_data.get('users', []):
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=message_text
            )
            await asyncio.sleep(0.1)  # Небольшая задержка
        except:
            continue  # Пропускаем если ошибка

# Функция для создания клавиатуры с кнопками в 2 колонки
def create_two_column_keyboard(items):
    keyboard = []
    row = []
    
    for i, item in enumerate(items):
        row.append(KeyboardButton(item))
        # Каждые 2 кнопки создаем новый ряд
        if (i + 1) % 2 == 0:
            keyboard.append(row)
            row = []
    
    # Добавляем оставшиеся кнопки
    if row:
        keyboard.append(row)
    
    return keyboard

# Обработчики для пользователей (паблик часть)
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Проверяем что это сообщение от пользователя, а не из канала
    if update.channel_post:
        return
    
    data = load_data()
    
    if not data['guides_data.json']:
        await update.message.reply_text('📭 Пока нет гайдов!', reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END
    
    # Создаем клавиатуру с историями (по две кнопки в ряду)
    story_names = list(data['guides_data.json'].keys())
    keyboard = create_two_column_keyboard(story_names)
    
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)
    await update.message.reply_text(
        '🎮 Выбери в меню:',
        reply_markup=reply_markup
    )
    return SELECTING_STORY

async def handle_story_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Проверяем что это сообщение от пользователя
    if update.channel_post:
        return SELECTING_STORY
    
    story_name = update.message.text
    data = load_data()
    
    if story_name not in data['guides_data.json']:
        await update.message.reply_text("❌ Действие не распознано")
        return SELECTING_STORY
    
    context.user_data['selected_story'] = story_name
    story_data = data['guides_data.json'][story_name]
    
    # Создаем клавиатуру с сериями (по две кнопки в ряду)
    series_buttons = []
    for series_name in story_data['series']:
        photo_count = len(story_data['series'][series_name]['photos'])
        series_buttons.append(f"{series_name} ({photo_count} фото)")
    
    keyboard = create_two_column_keyboard(series_buttons)
    keyboard.append([KeyboardButton("← Назад в меню")])
    
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)
    await update.message.reply_text(
        f"📖 Гайд: {story_name}\nВыбери в меню:",
        reply_markup=reply_markup
    )
    return SELECTING_SERIES

async def handle_series_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Проверяем что это сообщение от пользователя
    if update.channel_post:
        return SELECTING_SERIES
    
    series_text = update.message.text
    data = load_data()
    
    if series_text == "← Назад в меню":
        # Возвращаемся к выбору истории
        story_names = list(data['guides_data.json'].keys())
        keyboard = create_two_column_keyboard(story_names)
        
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)
        await update.message.reply_text(
            '🎮 Выбери в меню:',
            reply_markup=reply_markup
        )
        return SELECTING_STORY
    
    # Извлекаем название серии из текста кнопки
    series_name = series_text.split(' (')[0]  # Убираем " (X фото)"
    story_name = context.user_data.get('selected_story')
    
    if not story_name:
        await update.message.reply_text("❌ Ошибка: история не выбрана")
        return SELECTING_STORY
    
    if (story_name not in data['guides_data.json'] or 
        series_name not in data['guides_data.json'][story_name]['series']):
        await update.message.reply_text("❌ Серия не найдена")
        return SELECTING_SERIES
    
    photos = data['guides_data.json'][story_name]['series'][series_name]['photos']
    
    # Отправляем все фото
    for i, file_id in enumerate(photos, 1):
        await update.message.reply_photo(
            photo=file_id,
            caption=f"🎮 Гайд: {story_name}\n📖 №: {series_name}\n📸 страница: {i}/{len(photos)}"
        )
    
    # После отправки фото остаемся в том же меню
    story_data = data['guides_data.json'][story_name]
    series_buttons = []
    for series in story_data['series']:
        photo_count = len(story_data['series'][series]['photos'])
        series_buttons.append(f"{series} ({photo_count} фото)")
    
    keyboard = create_two_column_keyboard(series_buttons)
    keyboard.append([KeyboardButton("← Назад к историям")])
    
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)
    return SELECTING_SERIES

def main():
    application = Application.builder().token(config.ADMIN_BOT_TOKEN).build()
    
    # Обработчик для фото из канала
    application.add_handler(MessageHandler(
        filters.ChatType.CHANNEL & filters.PHOTO, 
        handle_channel_post
    ))

    # Обработчик для текста из канала
    application.add_handler(MessageHandler(
        filters.ChatType.CHANNEL & filters.TEXT,
        handle_channel_text
    ))
    
    # Обработчики для пользователей (паблик) с ConversationHandler
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            SELECTING_STORY: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_story_selection)
            ],
            SELECTING_SERIES: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_series_selection)
            ],
        },
        fallbacks=[],
    )
    
    application.add_handler(conv_handler)
    
    print("Бот запущен! Слушает канал и отвечае пользователям!")
    application.run_polling()

if __name__ == '__main__':
    main()