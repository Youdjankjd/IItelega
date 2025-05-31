
import os
import asyncio
import logging
from datetime import datetime, timezone
from telethon import TelegramClient, events
import requests

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Проверка обязательных переменных окружения
required_vars = [
    'TARGET_USER_ID',
    'DEEPSEEK_API_KEY'
]

missing_vars = [var for var in required_vars if not os.getenv(var)]
if missing_vars:
    logger.critical(f"Отсутствуют обязательные переменные окружения: {', '.join(missing_vars)}")
    exit(1)

# Используем предоставленные API ID и API HASH
API_ID = 28426067
API_HASH = 'aa1a85494ff6c9ac01ce3193de534731'
TARGET_USER_ID = int(os.getenv('6505085514'))
DEEPSEEK_API_KEY = os.getenv('sk-937024120cb941ac8b1fbf0178b7e8f2')

# DeepSeek API конфигурация
DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"

# Инициализация клиента Telegram
client = TelegramClient(
    'telegram_assistant_session',
    API_ID,
    API_HASH
)

# Ограничение длины запросов
MAX_INPUT_LENGTH = 2000
MAX_RESPONSE_TOKENS = 2000

async def get_deepseek_response(text):
    """Получение ответа от DeepSeek API с улучшенной обработкой"""
    if len(text) > MAX_INPUT_LENGTH:
        logger.warning(f"Превышена длина запроса: {len(text)} символов")
        return "⚠️ Запрос слишком длинный. Максимальная длина - 2000 символов."

    try:
        headers = {
            "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": "deepseek-chat",
            "messages": [{"role": "user", "content": text}],
            "temperature": 0.7,
            "max_tokens": MAX_RESPONSE_TOKENS,
            "top_p": 0.9,
            "frequency_penalty": 0.2,
            "presence_penalty": 0.2
        }
        
        response = requests.post(
            DEEPSEEK_API_URL,
            json=payload,
            headers=headers,
            timeout=30
        )
        
        if response.status_code != 200:
            logger.error(f"DeepSeek API error: {response.status_code} - {response.text[:200]}")
            return f"⚠️ Ошибка API ({response.status_code})"
        
        data = response.json()
        
        if not data.get("choices") or not isinstance(data["choices"], list):
            logger.error(f"Некорректный ответ DeepSeek: {data}")
            return "⚠️ Ошибка формата ответа"
        
        return data["choices"][0]["message"]["content"]
    
    except requests.exceptions.Timeout:
        logger.error("Таймаут запроса к DeepSeek API")
        return "⌛ Превышено время ожидания ответа"
    except requests.exceptions.RequestException as e:
        logger.error(f"Ошибка сети: {str(e)}")
        return "⚠️ Проблемы с подключением к сервису"
    except Exception as e:
        logger.error(f"Неизвестная ошибка DeepSeek API: {str(e)}", exc_info=True)
        return "⚠️ Внутренняя ошибка сервиса"

async def send_hourly_report():
    """Улучшенная отправка ежечасных отчетов"""
    logger.info("Служба отправки отчетов запущена")
    
    while True:
        try:
            if not client.is_connected():
                logger.warning("Клиент не подключен, ожидание соединения...")
                await asyncio.sleep(30)
                continue
            
            time_str = datetime.now(timezone.utc).strftime('%H:%M %d.%m.%Y')
            report_request = (
                f"Сгенерируй краткий технический отчет о работе системы. "
                f"Текущее время: {time_str}. "
                "Отчет должен содержать 3-5 пунктов о состоянии системы."
            )
            
            ai_report = await get_deepseek_response(report_request)

            if ai_report.startswith(("⚠️", "⌛")):
                logger.error(f"Ошибка генерации отчета: {ai_report}")
                await asyncio.sleep(300)
                continue
                
            message = f"📊 Отчет за {time_str} (UTC):\n\n{ai_report}"
            
            while message:
                chunk = message[:4096]
                message = message[4096:]
                await client.send_message(
                    TARGET_USER_ID,
                    chunk,
                    silent=True,
                    link_preview=False
                )
            
            logger.info(f"Отчет отправлен пользователю {TARGET_USER_ID}")
            
        except Exception as e:
            logger.error(f"Ошибка в отправке отчета: {str(e)}", exc_info=True)
        
        await asyncio.sleep(3600)

@client.on(events.NewMessage(incoming=True, func=lambda e: e.is_private))
async def private_message_handler(event):
    if event.sender_id != TARGET_USER_ID:
        logger.warning(f"Попытка доступа от неавторизованного пользователя: {event.sender_id}")
        return
        
    try:
        logger.info(f"Новое сообщение от {event.sender_id}")
        await event.client.send_read_acknowledge(event.chat_id)
        
        async with event.client.action(event.chat_id, 'typing'):
            response = await asyncio.wait_for(
                get_deepseek_response(event.text),
                timeout=30
            )
        
        reply = f"🤖 {response}" if not response.startswith("⚠️") else response
        while reply:
            chunk = reply[:4096]
            reply = reply[4096:]
            await event.reply(chunk, link_preview=False)
        
        logger.info(f"Ответ отправлен {event.sender_id}")
        
    except asyncio.TimeoutError:
        logger.warning(f"Таймаут обработки сообщения от {event.sender_id}")
        await event.reply("⌛ Превышено время обработки запроса, попробуйте позже")
    except Exception as e:
        logger.error(f"Ошибка обработки сообщения: {str(e)}", exc_info=True)
        await event.reply("⚠️ Произошла внутренняя ошибка при обработке запроса")

async def main():
    try:
        await client.start()
        me = await client.get_me()
        logger.info(f"✅ Аккаунт подключен: @{me.username} (ID: {me.id})")
        
        await client.send_message(
            TARGET_USER_ID, 
            '🤖 Бот успешно запущен!\n'
            f'Версия: 2.0\n'
            f'Время запуска: {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S %Z")}'
        )
        
        asyncio.create_task(send_hourly_report())
        await client.run_until_disconnected()
        
    except Exception as e:
        logger.critical(f"Критическая ошибка: {str(e)}", exc_info=True)
    finally:
        logger.info("Бот остановлен")
        try:
            await client.disconnect()
        except:
            pass

if __name__ == '__main__':
    asyncio.run(main())
