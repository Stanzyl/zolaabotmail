import os
import time
import asyncio
import logging
from pathlib import Path
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

# ===== KONFIGURASI =====
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8796308901:AAEI0f7urXaNDpX-Xh_eyKxMfT4Ol1WQ-xQ")
TEMP_DIR = Path("./temp_files")
TEMP_DIR.mkdir(exist_ok=True)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ===== FUNGSI CEK CAPTCHA + SCREENSHOT =====
async def check_captcha_and_screenshot(email: str) -> dict:
    """
    Check if Google account requires captcha/verification.
    Returns dict with status, screenshot path, and details.
    """
    screenshot_path = None
    status = "unknown"
    detail = ""
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-dev-shm-usage']
        )
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 720},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        try:
            # Buka halaman login
            await page.goto("https://accounts.google.com/", wait_until="domcontentloaded")
            await page.wait_for_timeout(1500)

            # Masukkan email
            await page.locator('input[type="email"]').fill(email)
            await page.locator('#identifierNext').click()
            
            # Tunggu sebentar agar halaman berikutnya muncul
            await page.wait_for_timeout(3000)

            # Ambil screenshot
            screenshot_path = TEMP_DIR / f"{email.replace('@','_')}_{int(time.time())}.png"
            await page.screenshot(path=str(screenshot_path))

            # Cek URL dan elemen
            url = page.url
            html = await page.content()
            html_lower = html.lower()

            if "challenge" in url or "captcha" in url or "verify" in url:
                status = "captcha"
                detail = "Captcha / Verification required"
            elif "signin" in url and "challenge" in url:
                status = "captcha"
                detail = "Captcha / Verification required"
            elif "signin" in url and "password" in url:
                # Cek apakah ada input password
                try:
                    await page.locator('input[type="password"]').wait_for(timeout=2000)
                    status = "no_captcha"
                    detail = "No captcha, direct to password page"
                except:
                    if "captcha" in html_lower or "verify" in html_lower:
                        status = "captcha"
                        detail = "Captcha / Verification required"
                    else:
                        status = "no_captcha"
                        detail = "No captcha (assumed)"
            else:
                if "captcha" in html_lower or "verify" in html_lower:
                    status = "captcha"
                    detail = "Captcha / Verification required"
                else:
                    status = "no_captcha"
                    detail = "No captcha (assumed)"

        except PlaywrightTimeoutError:
            status = "error"
            detail = "Timeout - page took too long to load"
        except Exception as e:
            status = "error"
            detail = f"Error: {str(e)[:100]}"
            logger.exception(f"Error checking {email}")
        finally:
            await browser.close()

        return {
            'email': email,
            'status': status,
            'detail': detail,
            'screenshot_path': screenshot_path
        }

# ===== PROSES SEMUA EMAIL =====
async def process_emails(emails: list) -> tuple:
    """Process all emails and return results, report path, and lists"""
    results = []
    safe_emails = []
    captcha_emails = []
    total = len(emails)
    start_time = time.time()

    for idx, email in enumerate(emails, start=1):
        email = email.strip()
        if not email:
            continue

        logger.info(f"Checking {idx}/{total}: {email}")
        result = await check_captcha_and_screenshot(email)
        
        if result['status'] == "no_captcha":
            safe_emails.append(email)
        elif result['status'] == "captcha":
            captcha_emails.append(email)
        else:
            # error/timeout, treat as captcha
            captcha_emails.append(email)
            result['status'] = "captcha"
            result['detail'] = f"Error/Timeout (treated as captcha) - {result['detail']}"

        result['index'] = idx
        result['total'] = total
        results.append(result)

        await asyncio.sleep(1.5)  # Jeda antar akun

    # Buat laporan
    report_lines = []
    report_lines.append("="*50)
    report_lines.append("          📊 CAPTCHA CHECK REPORT 📊")
    report_lines.append("="*50)
    report_lines.append("")
    report_lines.append(f"  📅 Date        : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report_lines.append(f"  📧 Total emails: {total}")
    report_lines.append(f"  ✅ No Captcha  : {len(safe_emails)}")
    report_lines.append(f"  ⚠️ Captcha     : {len(captcha_emails)}")
    report_lines.append(f"  ⏱️ Time        : {time.time() - start_time:.2f} seconds")
    report_lines.append("")
    report_lines.append("-"*50)
    report_lines.append("")

    report_lines.append("  ✅ NO CAPTCHA (DIRECT TO PASSWORD)")
    report_lines.append("  ----------------------------------")
    if safe_emails:
        for i, mail in enumerate(safe_emails, 1):
            report_lines.append(f"    {i}. {mail}")
    else:
        report_lines.append("    (none)")
    report_lines.append("")

    report_lines.append("  ⚠️ CAPTCHA / VERIFICATION REQUIRED")
    report_lines.append("  ----------------------------------")
    if captcha_emails:
        for i, mail in enumerate(captcha_emails, 1):
            report_lines.append(f"    {i}. {mail}")
    else:
        report_lines.append("    (none)")
    report_lines.append("")
    report_lines.append("="*50)
    report_lines.append(f"  Generated by TianBotGmail 🤖")
    report_lines.append("="*50)

    report_text = "\n".join(report_lines)
    report_path = TEMP_DIR / f"reports_{int(time.time())}.txt"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report_text)

    return results, report_path, safe_emails, captcha_emails

# ===== HANDLER TELEGRAM =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 *Hello! I'm TianBotGmail* 🤖\n\n"
        "I can check which Google accounts require captcha/verification during login.\n\n"
        "📌 *How to use:*\n"
        "1️⃣ Send a `.txt` file with one email per line\n"
        "2️⃣ *Reply* to that file with `/check_captcha`\n\n"
        "📊 I will send a screenshot and status for each email, and a final report file.\n\n"
        "🚀 *Let's go!*",
        parse_mode="Markdown"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📌 *Command:* `/check_captcha`\n\n"
        "Reply to a `.txt` file containing emails.\n\n"
        "📤 *Example:*\n"
        "1. Send file `emails.txt`\n"
        "2. Reply with `/check_captcha`\n"
        "3. Receive screenshots + status per email\n"
        "4. Receive final report file\n\n"
        "⚡ *Fast and accurate!*",
        parse_mode="Markdown"
    )

async def check_captcha(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    logger.info(f"User {user.id} ({user.username}) used /check_captcha")

    reply = update.message.reply_to_message
    if not reply or not reply.document:
        await update.message.reply_text(
            "❌ Please *reply* to a `.txt` file that contains the email list.",
            parse_mode="Markdown"
        )
        return

    # Download file
    document = reply.document
    file = await context.bot.get_file(document.file_id)
    file_path = TEMP_DIR / f"emails_{user.id}_{int(time.time())}.txt"
    await file.download_to_drive(file_path)

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            emails = [line.strip() for line in f if line.strip()]
    except Exception as e:
        await update.message.reply_text(f"❌ Failed to read file: {e}")
        return
    finally:
        file_path.unlink(missing_ok=True)

    if not emails:
        await update.message.reply_text("❌ The file is empty.")
        return

    progress_msg = await update.message.reply_text(
        f"⏳ *Checking {len(emails)} emails...* Please wait.\n"
        f"🔄 Progress: 0/{len(emails)}",
        parse_mode="Markdown"
    )

    # Process emails
    results, report_path, safe_emails, captcha_emails = await process_emails(emails)

    # Send results per account with screenshot
    for idx, res in enumerate(results, start=1):
        email = res['email']
        status = res['status']
        detail = res['detail']
        screenshot_path = res['screenshot_path']

        if status == "no_captcha":
            emoji = "✅"
            status_text = "No Captcha → Direct to password page"
        elif status == "captcha":
            emoji = "⚠️"
            status_text = "Captcha Required → Verification needed"
        else:
            emoji = "❓"
            status_text = f"Unknown/Error: {detail}"

        caption = f"{emoji} *Account {idx}/{len(emails)}*\n📧 `{email}`\n📋 {status_text}"

        # Send screenshot if exists
        if screenshot_path and screenshot_path.exists():
            with open(screenshot_path, "rb") as photo:
                await update.message.reply_photo(photo, caption=caption, parse_mode="Markdown")
            screenshot_path.unlink(missing_ok=True)
        else:
            await update.message.reply_text(caption, parse_mode="Markdown")

        # Update progress
        if idx % 5 == 0 or idx == len(emails):
            await progress_msg.edit_text(
                f"⏳ *Checking {len(emails)} emails...*\n"
                f"🔄 Progress: {idx}/{len(emails)}",
                parse_mode="Markdown"
            )

    # Send final report file
    with open(report_path, "rb") as f:
        await update.message.reply_document(
            document=f,
            filename=f"reports_{int(time.time())}.txt",
            caption="📊 *Full Report Attached!*\n\n"
                    f"✅ No Captcha: {len(safe_emails)}\n"
                    f"⚠️ Captcha: {len(captcha_emails)}\n\n"
                    "📄 Check attachment for complete lists.",
            parse_mode="Markdown"
        )
    report_path.unlink(missing_ok=True)

    await progress_msg.delete()
    await update.message.reply_text("✅ *All done!* 🎉\nThank you for using TianBotGmail.", parse_mode="Markdown")

# ===== MAIN =====
def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("check_captcha", check_captcha))

    print("🚀 TianBotGmail (Captcha Checker) is running...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
