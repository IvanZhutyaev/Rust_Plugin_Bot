import asyncio
from io import BytesIO
import config
import requests
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext


class RustPluginBot:
    def __init__(self, api_key: str):
        self.api_key = api_key.strip()  # убираем лишние пробелы
        self.api_url = "https://openrouter.ai/api/v1/chat/completions"
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "HTTP-Referer": "https://github.com/YourRepo",
            "X-Title": "RustPluginBot"
        }

        # Проверка ключа сразу при запуске
        if not self.check_api_key():
            raise ValueError("API-ключ OpenRouter недействителен или не активен!")

    def check_api_key(self) -> bool:
        """Проверяет валидность API-ключа на OpenRouter."""
        try:
            response = requests.get("https://openrouter.ai/api/v1/models", headers=self.headers)
            if response.status_code == 200:
                print("API-ключ валиден ✅")
                return True
            elif response.status_code == 401:
                print("Ошибка 401: Неверный или неактивный API-ключ ❌")
                return False
            else:
                print(f"Ошибка при проверке ключа: {response.status_code} - {response.text}")
                return False
        except Exception as e:
            print(f"Не удалось проверить ключ: {str(e)}")
            return False

    async def generate_code(self, prompt: str) -> str:
        request_data = {
            "model": "mistralai/mistral-7b-instruct",
            "messages": [
                {"role": "system", "content": (
                    "Ты квалифицированный разработчик плагинов для игры Rust. "
                    "Создавай рабочий C# плагин для игры Rust с полной функциональностью, "
                    "готовым к использованию кодом, без лишних пояснений."
                )},
                {"role": "user", "content": prompt}
            ],
            "max_tokens": 2000,
            "temperature": 0.7
        }

        try:
            response = requests.post(self.api_url, headers=self.headers, json=request_data)
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"].strip()
        except requests.HTTPError as http_err:
            if response.status_code == 401:
                return "Ошибка 401: Неавторизованный запрос. Проверьте API-ключ OpenRouter!"
            return f"HTTP ошибка: {http_err} - {response.text}"
        except Exception as e:
            return f"Ошибка при генерации кода: {str(e)}"

    async def generate_explanation(self, code: str) -> str:
        request_data = {
            "model": "mistralai/mistral-7b-instruct",
            "messages": [
                {"role": "system", "content": (
                    "Ты объясняешь C# код для плагинов игры Rust подробно и понятно."
                )},
                {"role": "user", "content": f"Объясни этот код:\n{code}"}
            ],
            "max_tokens": 1500,
            "temperature": 0.7
        }

        try:
            response = requests.post(self.api_url, headers=self.headers, json=request_data)
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"].strip()
        except requests.HTTPError as http_err:
            if response.status_code == 401:
                return "Ошибка 401: Неавторизованный запрос. Проверьте API-ключ OpenRouter!"
            return f"HTTP ошибка: {http_err} - {response.text}"
        except Exception as e:
            return f"Ошибка при генерации объяснения: {str(e)}"


class TelegramBot:
    def __init__(self, token: str, rust_bot: RustPluginBot):
        self.token = token
        self.rust_bot = rust_bot
        self.app = Application.builder().token(self.token).build()
        self.app.add_handler(CommandHandler("start", self.start))
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))

    async def start(self, update: Update, context: CallbackContext) -> None:
        await update.message.reply_text(
            "Привет! Отправь описание плагина для Rust, и я сгенерирую рабочий C# код с подробным объяснением."
        )

    async def handle_message(self, update: Update, context: CallbackContext) -> None:
        chat_id = update.effective_chat.id
        prompt = update.message.text

        # Генерация кода с прогрессом
        status_msg = await update.message.reply_text("Генерируется файл плагина (~20 секунд)...")
        await asyncio.sleep(10)  # пример прогресса
        await status_msg.edit_text("Генерируется файл плагина (~10 секунд осталось)...")
        code = await self.rust_bot.generate_code(prompt)
        await status_msg.edit_text("Файл готов! Отправляю...")

        # Отправка C# файла
        file_obj = BytesIO(code.encode("utf-8"))
        file_obj.name = "RustPlugin.cs"
        await context.bot.send_document(chat_id, document=file_obj)

        # Генерация объяснения с прогрессом
        status_msg = await update.message.reply_text("Генерируется объяснение (~15 секунд)...")
        await asyncio.sleep(7)
        await status_msg.edit_text("Генерируется объяснение (~8 секунд осталось)...")
        explanation = await self.rust_bot.generate_explanation(code)
        await status_msg.edit_text("Объяснение готово!")

        async def send_long_message(bot, chat_id, text):
            chunk_size = 4000
            for i in range(0, len(text), chunk_size):
                await bot.send_message(chat_id, text[i:i + chunk_size])

        await send_long_message(context.bot, chat_id, explanation)

    def run(self):
        self.app.run_polling()


if __name__ == "__main__":
    telegram_bot = TelegramBot(config.TELEGRAM_TOKEN, RustPluginBot(config.OPENROUTER_API_KEY))
    telegram_bot.run()
