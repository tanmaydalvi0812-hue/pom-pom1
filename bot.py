import os
import logging
from datetime import datetime
from http import HTTPStatus

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ContextTypes, MessageHandler, filters
)

from config import BOT_TOKEN, ADMIN_IDS
from database import (
    init_db, add_user, create_order, approve_order, decline_order,
    get_pending_orders, get_order, get_all_orders, get_order_stats,
    get_config, set_config, get_user_count, get_all_users,
    log_action, get_recent_logs, get_log_count
)

import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


# =================== USER SECTION ===================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    add_user(user.id, user.username or "", user.first_name or "")
    log_action(user.id, "/start")

    caption = get_config("description")
    product_photo = get_config("product_photo_file_id")

    keyboard = [
        [InlineKeyboardButton("🛒 Buy Now", callback_data="buy_now")],
        [InlineKeyboardButton("📸 Proof", callback_data="proof")],
        [InlineKeyboardButton("👁 Demo", callback_data="demo")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if product_photo:
        await update.message.reply_photo(
            photo=product_photo,
            caption=caption,
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(
            text=caption,
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )


async def buy_now(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    log_action(user.id, "buy_now")

    order_id = create_order(user.id, user.username or user.first_name or "Unknown")
    upi_id = get_config("upi_id")
    price = get_config("price")
    qr_file_id = get_config("qr_file_id")

    text = (
        f"💳 *Payment Details*\n\n"
        f"💰 Amount: ₹{price}\n"
        f"🏦 UPI ID: `{upi_id}`\n\n"
        f"📌 *Order ID:* `#{order_id}`\n\n"
        f"👇 *Scan QR below or pay to UPI ID above*\n"
        f"After payment, wait for admin approval. You'll receive the link automatically."
    )

    if qr_file_id:
        await query.message.reply_photo(
            photo=qr_file_id,
            caption=text,
            parse_mode="Markdown"
        )
    else:
        await query.message.reply_text(text=text, parse_mode="Markdown")

    for admin_id in ADMIN_IDS:
        try:
            admin_text = (
                f"🆕 *New Order Received!*\n\n"
                f"👤 User: {user.mention_html()}\n"
                f"🆔 User ID: `{user.id}`\n"
                f"🔖 Order: `#{order_id}`\n"
                f"⏰ Time: {datetime.now().strftime('%d-%m-%Y %H:%M')}\n\n"
                f"➡️ Go to /admin → Pending Orders to approve or decline."
            )
            await context.bot.send_message(
                chat_id=admin_id,
                text=admin_text,
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.error(f"Failed to notify admin {admin_id}: {e}")


async def proof(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    log_action(query.from_user.id, "proof")
    text = get_config("proof_text")
    await query.message.reply_text(text, parse_mode="Markdown", disable_web_page_preview=True)


async def demo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    log_action(query.from_user.id, "demo")
    text = get_config("demo_text")
    await query.message.reply_text(text, parse_mode="Markdown", disable_web_page_preview=True)


# =================== ADMIN SECTION ===================

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id not in ADMIN_IDS:
        await update.message.reply_text("⛔ Unauthorized.")
        return

    stats = get_order_stats()
    user_count = get_user_count()
    log_count = get_log_count()

    header = (
        f"⚙️ *Admin Panel*\n\n"
        f"📊 *Bot Stats*\n"
        f"👥 Users: {user_count}\n"
        f"📦 Orders: {stats['total']} (⏳{stats['pending']}/✅{stats['approved']}/❌{stats['declined']})\n"
        f"📈 Visitors: {log_count}\n\n"
        f"👇 *Manage Below:*"
    )

    keyboard = [
        [InlineKeyboardButton("📋 Pending Orders", callback_data="admin_pending")],
        [InlineKeyboardButton("📊 All Orders", callback_data="admin_orders_all")],
        [InlineKeyboardButton("👥 User List", callback_data="admin_users")],
        [InlineKeyboardButton("📈 Activity Log", callback_data="admin_logs")],
        [InlineKeyboardButton("─────────────────")],
        [InlineKeyboardButton("🔗 Change Channel Link", callback_data="admin_edit_channel")],
        [InlineKeyboardButton("💳 Change UPI ID", callback_data="admin_edit_upi")],
        [InlineKeyboardButton("🖼 Upload QR Code", callback_data="admin_upload_qr")],
        [InlineKeyboardButton("📝 Change Description", callback_data="admin_edit_desc")],
        [InlineKeyboardButton("🖼 Upload Product Photo", callback_data="admin_upload_photo")],
        [InlineKeyboardButton("💰 Change Price", callback_data="admin_edit_price")],
        [InlineKeyboardButton("📸 Edit Proof Text", callback_data="admin_edit_proof")],
        [InlineKeyboardButton("👁 Edit Demo Text", callback_data="admin_edit_demo")],
        [InlineKeyboardButton("─────────────────")],
        [InlineKeyboardButton("📢 Broadcast Message", callback_data="admin_broadcast")],
    ]
    await update.message.reply_text(header, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")


async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    data = query.data

    if user.id not in ADMIN_IDS:
        return await query.edit_message_text("⛔ Unauthorized.")

    # ===== MANUAL APPROVE =====
    if data.startswith("ap_"):
        order_id = int(data.split("_")[1])
        approve_order(order_id)
        order = get_order(order_id)
        channel_link = get_config("channel_link")
        try:
            await context.bot.send_message(
                chat_id=order["user_id"],
                text=(
                    f"✅ *Payment Approved!*\n\n"
                    f"Your order `#{order_id}` approved ✅\n\n"
                    f"🔗 *Here is your channel link:*\n"
                    f"{channel_link}\n\n"
                    f"Thank you for your purchase! 🎉"
                ),
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.error(f"Failed to send link: {e}")
        await query.edit_message_text(f"✅ Order `#{order_id}` approved. Link sent.", parse_mode="Markdown")
        return

    # ===== MANUAL DECLINE =====
    if data.startswith("dc_"):
        order_id = int(data.split("_")[1])
        decline_order(order_id)
        order = get_order(order_id)
        try:
            await context.bot.send_message(
                chat_id=order["user_id"],
                text=(
                    f"❌ *Payment Declined*\n\n"
                    f"Your order `#{order_id}` has been declined.\n"
                    f"Contact support if you think this is an error."
                ),
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.error(f"Failed to notify user: {e}")
        await query.edit_message_text(f"❌ Order `#{order_id}` declined.", parse_mode="Markdown")
        return

    # ===== ADMIN MENU =====

    if data == "admin_pending":
        pending = get_pending_orders()
        if not pending:
            return await query.edit_message_text("✅ No pending orders.")
        for o in pending[:5]:
            text = f"🔖 *Order #{o['id']}*\n👤 {o['username'] or o['user_id']}\n⏰ {o['created_at'][:19]}"
            kb = [[
                InlineKeyboardButton("✅ Approve", callback_data=f"ap_{o['id']}"),
                InlineKeyboardButton("❌ Decline", callback_data=f"dc_{o['id']}"),
            ]]
            await query.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")
        if len(pending) > 5:
            await query.message.reply_text(f"… and {len(pending)-5} more pending.")
        await query.message.delete()
        return

    elif data == "admin_orders_all":
        orders = get_all_orders()
        if not orders:
            return await query.edit_message_text("📭 No orders yet.")
        text = "📊 *All Orders (Last 20)*\n\n"
        for o in orders[:20]:
            emojis = {"pending": "⏳", "approved": "✅", "declined": "❌"}
            text += f"{emojis.get(o['status'],'❓')} `#{o['id']}` | {o['username']} | {o['status']} | {o['created_at'][:10]}\n"
        await query.edit_message_text(text, parse_mode="Markdown")

    elif data == "admin_users":
        users = get_all_users()
        if not users:
            return await query.edit_message_text("👥 No users yet.")
        text = f"👥 *Total Users: {len(users)}*\n\n"
        for u in users[:30]:
            text += f"👤 {u['first_name'] or u['username'] or u['user_id']} | 📅 {u['joined_at'][:10]}\n"
        if len(users) > 30:
            text += f"\n... and {len(users)-30} more"
        await query.edit_message_text(text, parse_mode="Markdown")

    elif data == "admin_logs":
        logs = get_recent_logs(15)
        if not logs:
            return await query.edit_message_text("📈 No activity yet.")
        text = "📈 *Recent Activity*\n\n"
        for l in logs:
            text += f"👤 `{l['user_id']}` → {l['action']} | {l['timestamp'][:19]}\n"
        await query.edit_message_text(text, parse_mode="Markdown")

    elif data == "admin_edit_channel":
        context.user_data["admin_edit_mode"] = "channel_link"
        await query.edit_message_text("🔗 Send new channel link:", parse_mode="Markdown")
    elif data == "admin_edit_upi":
        context.user_data["admin_edit_mode"] = "upi_id"
        await query.edit_message_text("💳 Send new UPI ID:", parse_mode="Markdown")
    elif data == "admin_edit_desc":
        context.user_data["admin_edit_mode"] = "description"
        await query.edit_message_text("✏️ Send new description:", parse_mode="Markdown")
    elif data == "admin_edit_price":
        context.user_data["admin_edit_mode"] = "price"
        await query.edit_message_text("💰 Send new price (e.g. 399):", parse_mode="Markdown")
    elif data == "admin_edit_proof":
        context.user_data["admin_edit_mode"] = "proof_text"
        await query.edit_message_text("📸 Send new proof text:", parse_mode="Markdown")
    elif data == "admin_edit_demo":
        context.user_data["admin_edit_mode"] = "demo_text"
        await query.edit_message_text("👁 Send new demo text:", parse_mode="Markdown")
    elif data == "admin_upload_qr":
        context.user_data["admin_edit_mode"] = "qr_photo"
        await query.edit_message_text("🖼 Send QR code image (as photo):", parse_mode="Markdown")
    elif data == "admin_upload_photo":
        context.user_data["admin_edit_mode"] = "product_photo"
        await query.edit_message_text("🖼 Send product preview photo:", parse_mode="Markdown")
    elif data == "admin_broadcast":
        context.user_data["admin_edit_mode"] = "broadcast"
        await query.edit_message_text("📢 Send broadcast message:", parse_mode="Markdown")


# =================== ADMIN INPUT HANDLER ===================

EDIT_MODE_MAP = {
    "channel_link": "Channel link",
    "upi_id": "UPI ID",
    "description": "Description",
    "price": "Price",
    "proof_text": "Proof text",
    "demo_text": "Demo text",
}


async def handle_admin_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id not in ADMIN_IDS:
        return
    mode = context.user_data.get("admin_edit_mode")
    if not mode:
        return

    if mode in EDIT_MODE_MAP:
        set_config(mode, update.message.text)
        await update.message.reply_text(f"✅ {EDIT_MODE_MAP[mode]} updated!")
        context.user_data["admin_edit_mode"] = None
        return

    if mode == "qr_photo":
        if not update.message.photo:
            await update.message.reply_text("❌ Send a photo, not a file.")
            return
        set_config("qr_file_id", update.message.photo[-1].file_id)
        await update.message.reply_photo(photo=update.message.photo[-1].file_id, caption="✅ QR Code saved!")
        context.user_data["admin_edit_mode"] = None
        return

    if mode == "product_photo":
        if not update.message.photo:
            await update.message.reply_text("❌ Send a photo, not a file.")
            return
        set_config("product_photo_file_id", update.message.photo[-1].file_id)
        await update.message.reply_photo(photo=update.message.photo[-1].file_id, caption="✅ Product photo saved!")
        context.user_data["admin_edit_mode"] = None
        return

    if mode == "broadcast":
        await update.message.reply_text("📤 Broadcasting...")
        users = get_all_users()
        success = failed = 0
        for u in users:
            try:
                await context.bot.send_message(chat_id=u["user_id"], text=update.message.text)
                success += 1
            except:
                failed += 1
        await update.message.reply_text(f"✅ Broadcast: {success} sent, {failed} failed")
        context.user_data["admin_edit_mode"] = None
        return


# =================== WEBHOOK SETUP ===================

async def telegram_webhook(request: Request):
    """Receive incoming update from Telegram."""
    try:
        body = await request.json()
        update = Update.de_json(body, bot.application.bot)
        await bot.application.process_update(update)
        return Response(status_code=HTTPStatus.OK)
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return Response(status_code=HTTPStatus.INTERNAL_SERVER_ERROR)


async def healthz(request: Request):
    """Render health check endpoint."""
    return Response(content="Bot is running!", media_type="text/plain")


async def startup():
    """Set webhook when the app starts."""
    port = int(os.environ.get("PORT", 10000))
    external_url = os.environ.get("RENDER_EXTERNAL_URL", f"http://0.0.0.0:{port}")
    webhook_url = f"{external_url}/telegram"
    logger.info(f"Setting webhook to: {webhook_url}")
    await bot.bot.set_webhook(url=webhook_url, allowed_updates=Update.ALL_TYPES)
    logger.info("✅ Webhook set successfully!")


async def shutdown():
    """Remove webhook when shutting down."""
    logger.info("Removing webhook...")
    await bot.bot.delete_webhook()


# =================== INIT BOT ===================

logger.info("Initializing bot...")
init_db()

bot = Application.builder().token(BOT_TOKEN).build()

bot.add_handler(CommandHandler("start", start))
bot.add_handler(CommandHandler("admin", admin_panel))

bot.add_handler(CallbackQueryHandler(buy_now, pattern="^buy_now$"))
bot.add_handler(CallbackQueryHandler(proof, pattern="^proof$"))
bot.add_handler(CallbackQueryHandler(demo, pattern="^demo$"))

bot.add_handler(CallbackQueryHandler(admin_callback, pattern="^admin_"))
bot.add_handler(CallbackQueryHandler(admin_callback, pattern="^(ap_|dc_)"))

bot.add_handler(MessageHandler(
    (filters.TEXT | filters.PHOTO) & ~filters.COMMAND,
    handle_admin_input
))

logger.info("✅ Bot initialized!")


# =================== STARLETTE APP ===================

app = Starlette(
    routes=[
        Route("/telegram", telegram_webhook, methods=["POST"]),
        Route("/healthz", healthz, methods=["GET"]),
        Route("/", healthz, methods=["GET"]),
    ],
    on_startup=[startup],
    on_shutdown=[shutdown],
)


# =================== MAIN ===================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    logger.info(f"🚀 Starting server on port {port}...")
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        log_level="info",
    )