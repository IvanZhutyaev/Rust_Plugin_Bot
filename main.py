import asyncio
from io import BytesIO
import config
import requests
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext, ContextTypes


class RustPluginBot:
    def __init__(self, api_key: str):
        self.api_key = api_key.strip()
        self.api_url = "https://openrouter.ai/api/v1/chat/completions"
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "HTTP-Referer": "https://github.com/YourRepo",
            "X-Title": "RustPluginBot"
        }

        if not self.check_api_key():
            raise ValueError("API-ключ OpenRouter недействителен или не активен!")

    def check_api_key(self) -> bool:
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

    async def generate_response(self, prompt: str, is_code_request: bool = False) -> str:
        system_content = (
            "Ты опытный разработчик плагинов для игры Rust, а также хорошо понимаешь эту игру. "
            "Ты помогаешь с разработкой плагинов на C#. "
            "Отвечай подробно и профессионально."
        )

        if is_code_request:
            system_content = (
                "Ты опытный разработчик плагинов для игры Rust. "
                "Ты **генерируешь только РЕАЛЬНО рабочий C# код**, полностью готовый к использованию. "
                "Не добавляй оговорки, просто генерируй рабочий код с комментариями."
            )

        request_data = {
            "model": "mistralai/mistral-7b-instruct",
            "messages": [
                {"role": "system", "content": system_content},
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
            return f"Ошибка при генерации ответа: {str(e)}"

    async def analyze_and_modify_code(self, code: str, prompt: str) -> str:
        request_data = {
            "model": "mistralai/mistral-7b-instruct",
            "messages": [
                {"role": "system", "content": (
                    "Ты анализируешь и модифицируешь C# код для плагинов Rust. "
                    "Учитывай запрос пользователя и вноси соответствующие изменения. "
                    "Возвращай только модифицированный код без лишних объяснений."
                )},
                {"role": "user", "content": f"Исходный код:\n{code}\n\nЗапрос на изменение: {prompt}"}
            ],
            "max_tokens": 2000,
            "temperature": 0.7
        }

        try:
            response = requests.post(self.api_url, headers=self.headers, json=request_data)
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"].strip()
        except Exception as e:
            return f"Ошибка при модификации кода: {str(e)}"


class TelegramBot:
    def __init__(self, token: str, rust_bot: RustPluginBot):
        self.token = token
        self.rust_bot = rust_bot
        self.app = Application.builder().token(self.token).build()

        # Обработчики команд
        self.app.add_handler(CommandHandler("start", self.start))
        self.app.add_handler(CommandHandler("create_file", self.create_file))

        # Обработчик документов
        self.app.add_handler(MessageHandler(filters.Document.ALL, self.handle_document))

        # Обработчик текстовых сообщений
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))

    async def start(self, update: Update, context: CallbackContext) -> None:
        await update.message.reply_text(
            "Привет! Я помощник для разработки плагинов Rust на C#.\n\n"
            "Отправь описание плагина или вопрос, и я помогу.\n"
            "Используй /create_file чтобы сгенерировать файл с кодом.\n"
            "Можно отправить файл с кодом для анализа или модификации."
        )

    async def create_file(self, update: Update, context: CallbackContext) -> None:
        """Обработчик команды для создания файла с кодом"""
        if not context.args:
            await update.message.reply_text("Пожалуйста, укажи описание плагина после команды /create_file")
            return

        prompt = " ".join(context.args)
        status_msg = await update.message.reply_text("Генерируется файл плагина...")

        code = await self.rust_bot.generate_response(prompt, is_code_request=True)

        # Отправка файла
        file_obj = BytesIO(code.encode("utf-8"))
        file_obj.name = "RustPlugin.cs"
        await context.bot.send_document(update.effective_chat.id, document=file_obj)
        await status_msg.edit_text("Файл сгенерирован и отправлен!")

    async def handle_message(self, update: Update, context: CallbackContext) -> None:
        """Обработчик обычных текстовых сообщений"""
        prompt = update.message.text
        status_msg = await update.message.reply_text("Обрабатываю запрос...")

        response = await self.rust_bot.generate_response(prompt)

        await self._send_long_message(context.bot, update.effective_chat.id, response)
        await status_msg.delete()

    async def handle_document(self, update: Update, context: CallbackContext) -> None:
        """Обработчик загружаемых файлов"""
        document = update.message.document
        if not document.file_name.endswith('.cs'):
            await update.message.reply_text("Пожалуйста, отправьте файл с расширением .cs")
            return

        status_msg = await update.message.reply_text("Читаю и анализирую файл...")

        # Скачиваем файл
        file = await context.bot.get_file(document.file_id)
        file_bytes = await file.download_as_bytearray()
        file_text = file_bytes.decode('utf-8')

        # Проверяем, есть ли текст с запросом
        user_prompt = update.message.caption or "Проанализируй этот код и предложи улучшения."

        if "модифицируй" in user_prompt.lower() or "измени" in user_prompt.lower():
            modified_code = await self.rust_bot.analyze_and_modify_code(file_text, user_prompt)

            # Предлагаем выбор - текстом или файлом
            await status_msg.edit_text(
                "Код модифицирован. Как вы хотите получить результат?",
                reply_markup=self._get_file_or_text_keyboard(modified_code)
            )
        else:
            analysis = await self.rust_bot.generate_response(
                f"Проанализируй этот код плагина Rust:\n{file_text}\n\nЗапрос: {user_prompt}"
            )
            await self._send_long_message(context.bot, update.effective_chat.id, analysis)
            await status_msg.delete()

    def _get_file_or_text_keyboard(self, code: str):
        """Создает клавиатуру с выбором формата ответа"""
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup

        keyboard = [
            [InlineKeyboardButton("Текстом", callback_data=f"text_{hash(code)}")],
            [InlineKeyboardButton("Файлом", callback_data=f"file_{hash(code)}")]
        ]
        return InlineKeyboardMarkup(keyboard)

    async def _send_long_message(self, bot, chat_id, text):
        """Отправляет длинное сообщение частями"""
        chunk_size = 4000
        for i in range(0, len(text), chunk_size):
            await bot.send_message(chat_id, text[i:i + chunk_size])

    def run(self):
        self.app.run_polling()


if __name__ == "__main__":
    telegram_bot = TelegramBot(config.TELEGRAM_TOKEN, RustPluginBot(config.OPENROUTER_API_KEY))
    telegram_bot.run()