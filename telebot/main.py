import logging
import asyncio
import html
import datetime
import paho.mqtt.client as mqtt
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, 
    ContextTypes, 
    CommandHandler, 
    MessageHandler,
    filters
)

# ==========================================
#              CONFIGURATION
# ==========================================
TELEGRAM_TOKEN = "" # Your Telegram Bot Token
AUTHORIZED_CHAT_ID = 123456789 # Your Telegram Chat ID

MQTT_BROKER = "" # Your MQTT Broker Address
MQTT_PORT = 1883
MQTT_USERNAME = ""
MQTT_PASSWORD = ""

TOPIC_SUBSCRIBE = "fire_system/status"
TOPIC_PUBLISH = "fire_system/command"

# ==========================================
#           LOGGING & GLOBAL VARS
# ==========================================
logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

bot_app = None
main_loop = None 

# Flag to check if user is waiting for status update
is_waiting_for_status = False

# ==========================================
#           MESSAGE PARSING & FORMAT
# ==========================================
def parse_and_format(payload_str, force_show=False):
    """
    Parse string: 'x1 x2 x3'
    x1: Fire Status (0: Normal, 1: Warning, 2: Alarm)
    x2: Valve State (0: Closed, 1: Open)
    x3: Siren State (0: Off, 1: On)
    """
    try:
        parts = payload_str.split()
        if len(parts) < 3:
            return None
            
        x1, x2, x3 = parts[0], parts[1], parts[2]
        
        # --- 1. CHECK x1 (FIRE STATUS) ---
        if x1 == '0':
            # Normal state: Only show if requested manually
            if not force_show:
                logger.info("Status Normal (x1=0). Ignored (Not a manual check).")
                return None
            
            header = "✅ <b>SYSTEM NORMAL</b>"
            status_text = "🛡 Area is safe. No hazards detected."
            
        elif x1 == '1':
            header = "⚠️ <b>WARNING</b>"
            status_text = "🟡 Level 1: Smoke/Heat detected. Check immediately!"
        elif x1 == '2':
            header = "🔥 <b>EMERGENCY ALARM</b> 🔥"
            status_text = "🔴 Level 2: FIRE DETECTED! ACTIVATE RESPONSE!"
        else:
            header = "❓ <b>UNKNOWN SIGNAL</b>"
            status_text = f"Status Code: {x1}"

        # --- 2. CHECK x2 (WATER VALVE) ---
        if x2 == '1':
            relay_state = "🚰 Water Valve: <b>OPEN</b> (Spraying)"
        else:
            relay_state = "🔒 Water Valve: <b>CLOSED</b>"

        # --- 3. CHECK x3 (SIREN) ---
        if x3 == '0':
            siren_state = "🔇 Siren: <b>SILENT</b>"
        else:
            siren_state = "🔊 Siren: <b>BLARING</b>"

        # --- BUILD MESSAGE ---
        msg = (
            f"{header}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"{status_text}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"{relay_state}\n"
            f"{siren_state}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🕒 <i>{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</i>\n"
            f"📡 Raw data: <code>{payload_str}</code>"
        )
        return msg

    except Exception as e:
        logger.error(f"Error parsing data: {e}")
        return None

# ==========================================
#           MQTT FUNCTIONS
# ==========================================
def on_connect(client, userdata, flags, rc, properties=None):
    if rc == 0:
        logger.info("✅ Connected to MQTT Broker!")
        client.subscribe(TOPIC_SUBSCRIBE)
    else:
        logger.error(f"❌ Failed to connect to MQTT, return code {rc}")

def on_message(client, userdata, msg):
    global is_waiting_for_status
    
    try:
        payload_str = msg.payload.decode().strip()
        logger.info(f"📨 Received: {payload_str}")
        
        should_force = is_waiting_for_status
        
        text_msg = parse_and_format(payload_str, force_show=should_force)
        
        if text_msg and main_loop and main_loop.is_running():
            if is_waiting_for_status:
                is_waiting_for_status = False 
                
            asyncio.run_coroutine_threadsafe(
                bot_app.bot.send_message(
                    chat_id=AUTHORIZED_CHAT_ID,
                    text=text_msg,
                    parse_mode="HTML"
                ),
                main_loop
            )
            
    except Exception as e:
        logger.error(f"Error forwarding message: {e}")

# ==========================================
#           KEYBOARD LAYOUT
# ==========================================
def get_fire_keyboard():
    keyboard = [
        [KeyboardButton("🚰 Toggle Valve"), KeyboardButton("🔔 Toggle Siren")],
        [KeyboardButton("🔄 Check Status")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, is_persistent=True)

# ==========================================
#       TELEGRAM HANDLERS
# ==========================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🚒 <b>FIRE ALARM MONITORING SYSTEM</b>\n"
        "Mode: <i>Alert on anomaly only</i>",
        parse_mode="HTML",
        reply_markup=get_fire_keyboard()
    )

async def handle_commands(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global is_waiting_for_status
    
    text = update.message.text
    user_id = update.effective_user.id

    if AUTHORIZED_CHAT_ID and user_id != AUTHORIZED_CHAT_ID:
        return

    # --- COMMAND LOGIC ---
    if text == "🚰 Toggle Valve": 
        # Send "1 0": Toggle Valve (1), Keep Siren (0)
        mqtt_client.publish(TOPIC_PUBLISH, "1 0")
        await update.message.reply_text("✅ Command sent: Toggle Water Valve (1 0)")
        
    elif text == "🔔 Toggle Siren":
        # Send "0 1": Keep Valve (0), Toggle Siren (1)
        mqtt_client.publish(TOPIC_PUBLISH, "0 1")
        await update.message.reply_text("✅ Command sent: Toggle Siren (0 1)")
        
    elif text == "🔄 Check Status":
        is_waiting_for_status = True
        # Send "CHECK_STATUS" to request data update
        mqtt_client.publish(TOPIC_PUBLISH, "CHECK_STATUS")
        await update.message.reply_text("⏳ Fetching latest data from device...")

# ==========================================
#              MAIN EXECUTION
# ==========================================
if __name__ == '__main__':
    try:
        main_loop = asyncio.get_event_loop()
    except RuntimeError:
        main_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(main_loop)

    mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    mqtt_client.on_connect = on_connect
    mqtt_client.on_message = on_message
    if MQTT_USERNAME and MQTT_PASSWORD:
        mqtt_client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
    
    try:
        mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
        mqtt_client.loop_start()
    except Exception as e:
        logger.error(f"MQTT Error: {e}")
        exit(1)

    bot_app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    bot_app.add_handler(CommandHandler('start', start))
    bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_commands))
    
    logger.info("🔥 Fire Alarm Bot is running...")
    bot_app.run_polling(allowed_updates=Update.ALL_TYPES)