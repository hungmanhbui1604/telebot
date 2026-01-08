# Telebot

A Telegram bot application.

## Running with Docker

1. Navigate to the bot directory:
   ```bash
   cd bot
   ```

2. Copy the environment file:
   ```bash
   cp .env.example .env
   ```

3. Update `.env` with your configuration

4. Start the container:
   ```bash
   docker compose up --build -d
   ```

## Local Testing

1. Create a virtual environment:
   ```bash
   python3 -m venv venv
   ```

2. Activate the virtual environment:
   ```bash
   source venv/bin/activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Run the simulator:
   ```bash
   python simulate.py
   ```