import re
import time
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes


# ==========================================
# بخش اول: تحلیل‌گر داده‌های دیوار
# این کلاس مسئولیت ارتباط با وب‌سایت و استخراج قیمت‌ها را دارد
# ==========================================
class DivarAnalyzer:
    def __init__(self):
        """تنظیمات اولیه مرورگر کروم برای اجرای بدون گرافیک (Headless)"""
        self.chrome_options = Options()
        self.chrome_options.add_argument("--headless")  # عدم نمایش پنجره مرورگر
        self.chrome_options.add_argument("--no-sandbox")
        self.chrome_options.add_argument("--disable-dev-shm-usage")

    def _fa_to_en(self, text):
        """تبدیل اعداد فارسی موجود در متن قیمت به اعداد انگلیسی برای محاسبات پایتون"""
        persian_digits = '۰۱۲۳۴۵۶۷۸۹'
        english_digits = '0123456789'
        table = str.maketrans(persian_digits, english_digits)
        return text.translate(table)

    def get_average_price(self, query):
        """
        ورودی: نام محصول (مثلاً: پراید ۸۸ بدون رنگ)
        خروجی: میانگین قیمت یا کد خطا
        """
        # ۱. بررسی اعتبار ورودی کاربر (جلوگیری از ورود کلمات نامفهوم یا خیلی کوتاه)
        if len(query.strip()) < 3:
            return "ERROR_SHORT"

        # ۲. راه‌اندازی درایور مرورگر
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=self.chrome_options)

        try:
            # ۳. ساخت آدرس جستجو و بارگذاری صفحه
            url = f"https://divar.ir/s/tehran?q={query}"
            driver.get(url)
            time.sleep(5)  # زمان انتظار برای لود شدن کامل آگهی‌های داینامیک

            prices = []
            # ۴. پیدا کردن تمام کارت‌های آگهی بر اساس کلاس CSS دیوار
            post_cards = driver.find_elements(By.CLASS_NAME, "kt-post-card__description")

            if not post_cards:
                driver.quit()
                return "ERROR_NOT_FOUND"

            for card in post_cards:
                # ۵. محدود کردن بررسی به ۲۰ آگهی اول
                if len(prices) >= 20:
                    break

                text = card.text
                # ۶. فقط آگهی‌هایی که قیمت مشخص دارند (نه توافقی) را پردازش می‌کنیم
                if "تومان" in text:
                    text_en = self._fa_to_en(text)
                    # حذف هر کاراکتری که عدد نیست (مثل کاما و کلمه تومان)
                    clean_price = re.sub(r'\D', '', text_en)
                    if clean_price:
                        prices.append(int(clean_price))

            driver.quit()

            # ۷. اگر آگهی پیدا شد ولی هیچ‌کدام قیمت عددی نداشتند
            if not prices:
                return "ERROR_NO_PRICE"

            # ۸. محاسبه میانگین نهایی (تقسیم صحیح)
            return sum(prices) // len(prices)

        except Exception as e:
            print(f"Log: Scraping Error -> {e}")
            if driver: driver.quit()
            return "ERROR_SYSTEM"


# ==========================================
# بخش دوم: مدیریت ربات تلگرام
# این کلاس مسئولیت تعامل با کاربر و نمایش خروجی را دارد
# ==========================================
class DivarBot:
    def __init__(self, token):
        """راه‌اندازی ربات با توکن اختصاصی و ایجاد یک نمونه از تحلیل‌گر دیوار"""
        self.token = token
        self.analyzer = DivarAnalyzer()

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """پاسخ به دستور /start و راهنمایی کاربر"""
        await update.message.reply_text(
            "سلام! خوش آمدید. 🤖\n\n"
            "من میانگین قیمت آگهی‌های دیوار را برای شما محاسبه می‌کنم.\n"
            "لطفاً نام محصول یا خودرو را با جزئیات وارد کنید (مثلاً: آیفون ۱۳ پرو ۲۵۶ گیگ)."
        )

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """پردازش پیام‌های متنی کاربر و نمایش نتیجه نهایی"""
        user_query = update.message.text

        # اطلاع‌رسانی به کاربر برای صبور بودن (چون اسکرپینگ زمان‌بر است)
        await update.message.reply_text(f"🔍 در حال جستجو و تحلیل ۲۰ آگهی اخیر برای:\n«{user_query}»...")

        # دریافت نتیجه از کلاس اسکرپر
        result = self.analyzer.get_average_price(user_query)

        # مدیریت سناریوهای مختلف خروجی بر اساس کدهای خطا
        if result == "ERROR_SHORT":
            await update.message.reply_text("⚠️ عبارت جستجو خیلی کوتاه است. لطفاً جزئیات بیشتری بنویسید.")
        elif result == "ERROR_NOT_FOUND":
            await update.message.reply_text("❌ نتیجه‌ای در دیوار تهران پیدا نشد. لطفاً املای کلمات را چک کنید.")
        elif result == "ERROR_NO_PRICE":
            await update.message.reply_text("💡 آگهی‌ها پیدا شدند، اما قیمت مشخصی ندارند (توافقی هستند).")
        elif result == "ERROR_SYSTEM":
            await update.message.reply_text("🛠 متأسفانه مشکلی در ارتباط با دیوار پیش آمد. لحظاتی دیگر تلاش کنید.")
        else:
            # جدا کردن سه رقم سه رقم قیمت برای خوانایی بهتر
            formatted_price = "{:,}".format(result)
            await update.message.reply_text(
                f"📊 تحلیل قیمت دیوار تهران:\n\n"
                f"🔹 کالا: {user_query}\n"
                f"💰 میانگین قیمت: {formatted_price} تومان"
            )

    def run(self):
        """شروع به کار ربات (Long Polling)"""
        app = Application.builder().token(self.token).build()

        # ثبت دستورات و پیام‌ها در ربات
        app.add_handler(CommandHandler("start", self.start_command))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))

        print("Bot is running... Press Ctrl+C to stop.")
        app.run_polling()


# ==========================================
# نقطه ورود برنامه
# ==========================================
if __name__ == '__main__':
    # توکن خود را از @BotFather دریافت و اینجا جایگزین کنید
    MY_TOKEN = '8160407753:AAF5BydD1wJjB4u1SXL5jLlhvt7RYMRT_v0'

    # ساخت یک نمونه از کلاس ربات و اجرای آن
    bot = DivarBot(MY_TOKEN)
    bot.run()