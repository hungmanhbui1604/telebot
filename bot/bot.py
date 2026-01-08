import logging
import asyncio
import json
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
import os
import sys

# ==========================================
#              CONFIGURATION
# ==========================================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
try:
    # Ensure this is an integer
    AUTHORIZED_CHAT_ID = int(os.getenv("AUTHORIZED_CHAT_ID"))
except (TypeError, ValueError):
    print("❌ Error: AUTHORIZED_CHAT_ID is missing or not a number.")
    sys.exit(1)

if not TELEGRAM_TOKEN:
    print("❌ Error: TELEGRAM_TOKEN is missing.")
    sys.exit(1)

# MQTT Config
MQTT_BROKER = os.getenv("MQTT_BROKER", "mosquitto") # Default to service name in docker-compose
MQTT_PORT = int(os.getenv("MQTT_PORT", 1883))
MQTT_USERNAME = os.getenv("MQTT_USERNAME", None)
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD", None)

# Topics
TOPIC_SUB_FLAME  = "fire_alarm/esp32_01/sensor/flame"
TOPIC_SUB_GAS    = "fire_alarm/esp32_01/sensor/gas"
TOPIC_SUB_STATE  = "fire_alarm/esp32_01/sensor/state"
TOPIC_PUB_BUZZER = "fire_alarm/esp32_01/control/buzzer"
TOPIC_PUB_VALVE  = "fire_alarm/esp32_01/control/valve"

# ==========================================
#           LOGGING & GLOBALS
# ==========================================
logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Global storage
latest_flame = {}
latest_gas = {}
latest_state = {}

# We need to capture the loop to communicate between MQTT thread and Telegram
main_loop = None 
bot_app = None

# ==========================================
#           HELPER FUNCTIONS
# ==========================================
def get_main_keyboard():
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("🔔 Buzzer ON"), KeyboardButton("🔕 Buzzer OFF")],
            [KeyboardButton("🔓 Valve OPEN"), KeyboardButton("🔒 Valve CLOSE")],
            [KeyboardButton("🔄 Check Status")]
        ],
        resize_keyboard=True
    )

def format_status_message():
    f_do = latest_flame.get("DO_State", 1)
    f_val = latest_flame.get("AO_Value", "N/A")
    g_do = latest_gas.get("DO_State", 1)
    g_val = latest_gas.get("AO_Value", "N/A")
    b_state = latest_state.get("BUZZER_State", False)
    v_state = latest_state.get("VALVE_State", False)

    if f_do == 0 or g_do == 0:
        header = "🚨 <b>DANGER DETECTED</b> 🚨"
    else:
        header = "✅ <b>SYSTEM NORMAL</b>"

    msg = (
        f"{header}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🔥 <b>Flame:</b> {'⚠️ FIRE!' if f_do == 0 else 'Safe'} (Val: {f_val})\n"
        f"☣️ <b>Gas:</b> {'⚠️ LEAK!' if g_do == 0 else 'Safe'} (Val: {g_val})\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🔊 <b>Buzzer:</b> {'ON' if b_state else 'OFF'}\n"
        f"🚰 <b>Valve:</b> {'OPEN' if v_state else 'CLOSED'}\n"
        f"🕒 <i>{datetime.datetime.now().strftime('%H:%M:%S')}</i>"
    )
    return msg

# ==========================================
#           MQTT CALLBACKS
# ==========================================
def on_connect(client, userdata, flags, rc, properties=None):
    if rc == 0:
        logger.info(f"✅ MQTT Connected to {MQTT_BROKER}")
        client.subscribe([(TOPIC_SUB_FLAME, 0), (TOPIC_SUB_GAS, 0), (TOPIC_SUB_STATE, 0)])
    else:
        logger.error(f"❌ MQTT Connection Failed, rc={rc}")

def on_message(client, userdata, msg):
    global latest_flame, latest_gas, latest_state
    try:
        topic = msg.topic
        payload = msg.payload.decode("utf-8")
        data = json.loads(payload)

        if topic == TOPIC_SUB_FLAME:
            latest_flame = data
            if data.get("DO_State") == 0:
                send_async_alert("🔥 FIRE DETECTED! 🔥")

        elif topic == TOPIC_SUB_GAS:
            latest_gas = data
            if data.get("DO_State") == 0:
                send_async_alert("☣️ GAS LEAK DETECTED! ☣️")

        elif topic == TOPIC_SUB_STATE:
            latest_state = data
            
    except Exception as e:
        logger.error(f"Error processing MQTT message: {e}")

def send_async_alert(text):
    """Bridge function: MQTT Thread -> Asyncio Loop"""
    if bot_app and main_loop:
        asyncio.run_coroutine_threadsafe(
            bot_app.bot.send_message(chat_id=AUTHORIZED_CHAT_ID, text=text),
            main_loop
        )

# ==========================================
#           TELEGRAM HANDLERS
# ==========================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Security Check
    if update.effective_chat.id != AUTHORIZED_CHAT_ID:
        await update.message.reply_text("⛔ Unauthorized access.")
        return

    await update.message.reply_text(
        "👋 ESP32 Control Center Online.",
        reply_markup=get_main_keyboard()
    )

async def handle_commands(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Security Check (CRITICAL FIX)
    if update.effective_chat.id != AUTHORIZED_CHAT_ID:
        return

    text = update.message.text
    
    if text == "🔔 Buzzer ON":
        mqtt_client.publish(TOPIC_PUB_BUZZER, "ON")
        await update.message.reply_text("✅ Sent: Buzzer ON")
        
    elif text == "🔕 Buzzer OFF":
        mqtt_client.publish(TOPIC_PUB_BUZZER, "OFF")
        await update.message.reply_text("✅ Sent: Buzzer OFF")
        
    elif text == "🔓 Valve OPEN":
        mqtt_client.publish(TOPIC_PUB_VALVE, "ON")
        await update.message.reply_text("✅ Sent: Valve OPEN")
        
    elif text == "🔒 Valve CLOSE":
        mqtt_client.publish(TOPIC_PUB_VALVE, "OFF")
        await update.message.reply_text("✅ Sent: Valve CLOSE")
        
    elif text == "🔄 Check Status":
        await update.message.reply_text(format_status_message(), parse_mode="HTML")

# ==========================================
#              MAIN EXECUTION
# ==========================================
if __name__ == '__main__':
    # 1. Setup Async Loop
    try:
        main_loop = asyncio.get_event_loop()
    except RuntimeError:
        main_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(main_loop)

    # 2. Setup MQTT (Threaded)
    # Using CallbackAPIVersion.VERSION2 as you requested
    mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    mqtt_client.on_connect = on_connect
    mqtt_client.on_message = on_message
    
    if MQTT_USERNAME and MQTT_PASSWORD:
        mqtt_client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)

    try:
        # Note: In Docker, this usually connects to the service name "mosquitto"
        mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
        mqtt_client.loop_start() 
    except Exception as e:
        logger.error(f"Cannot connect to MQTT Broker: {e}")
        # We don't exit here, so the bot can still start and retry later if needed
        # But usually better to fail fast in Docker:
        sys.exit(1)

    # 3. Setup Telegram Bot
    bot_app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    bot_app.add_handler(CommandHandler('start', start))
    bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_commands))
    
    logger.info("🤖 Bot is starting polling...")
    bot_app.run_polling()