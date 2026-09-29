import asyncio
from telegram_bot import fetch_api_data

async def main():
    ins_code = "46348559193224090" # Fmli
    try:
        df = await fetch_api_data(ins_code)
        print("Fetched", len(df))
    except Exception as e:
        print("Error:", repr(e))

asyncio.run(main())
