import discord
import queue
import time
import atexit
import multiprocessing

from cgv_open_push_function import *
from cgv_open_push_global_variable import *
from cgv_open_push_movie import movie_main
from cgv_open_push_screen import screen_main

from logging.handlers import RotatingFileHandler
from discord.ext import tasks


# ==================================================
# 디스코드 봇
# ==================================================

intents = discord.Intents.default()
client = discord.Client(intents=intents)

message_queue = multiprocessing.Queue()


@client.event
async def on_ready():
    channel_id = discord_channel_id_dictionary["LOG"]
    channel = client.get_channel(channel_id)

    if channel:
        await channel.send(
            "cgv-open-push-discord-bot connected..."
        )
    else:
        print(f"LOG 채널을 찾을 수 없습니다. channel_id={channel_id}")

    # Discord 재접속 시 중복 실행 방지
    if not send_message.is_running():
        send_message.start()


@tasks.loop(seconds=1)
async def send_message():

    if not message_queue.empty():

        message = message_queue.get()

        channel_id = discord_channel_id_dictionary.get(
            message[0]
        )

        print(
            f"send_message to {message[0]} : "
            f"{message[1]}, channel_id : {channel_id}"
        )

        if channel_id:

            channel = client.get_channel(channel_id)

            if channel:
                await channel.send(message[1])

            else:
                print(
                    f"채널을 찾을 수 없습니다. "
                    f"target={message[0]}, "
                    f"channel_id={channel_id}"
                )


def run_cgv_open_push_discord_bot():
    client.run(discord_bot_token)


# ==================================================
# 프로세스 배열
# ==================================================

processes = []


# ==================================================
# 로그 저장
# 최대 5MB씩 3개 백업본 저장
# ==================================================

handlers = [
    RotatingFileHandler(
        "cgv-open-push.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8"
    )
]

logging.basicConfig(
    handlers=handlers,
    level=logging.INFO,
    format="%(asctime)s:%(levelname)s:%(message)s"
)


# ==================================================
# 종료 시 서버 종료 알림
# ==================================================

def send_stopped_message():
    try:
        message_queue.put(
            ["LOG", "cgv-open-push server stopped..."]
        )
    except Exception:
        pass


# ==================================================
# 메인 실행
# ==================================================

def main():

    # cgv_open_push_status.py 실행
    p = multiprocessing.Process(
        target=run_cgv_open_push_status
    )

    processes.append(p)
    p.start()

    time.sleep(1)


    # 서버 시작 알림
    message_queue.put(
        ["LOG", "cgv-open-push server started..."]
    )


    # ------------------------------------------------
    # 특정 영화 감시
    # 현재 movie_json_data가 비어 있으면 실행되지 않음
    # ------------------------------------------------

    for index, json_data in enumerate(movie_json_data):

        p = multiprocessing.Process(
            target=movie_main,
            args=(
                movie_url,
                movie_cookies,
                movie_headers,
                json_data,
                movie_target_name[index],
                message_queue
            )
        )

        processes.append(p)
        p.start()

        time.sleep(1)


    # ------------------------------------------------
    # 특별관 감시
    # ------------------------------------------------

    for index, json_data in enumerate(screen_json_data):

        p = multiprocessing.Process(
            target=screen_main,
            args=(
                screen_url,
                screen_cookies,
                screen_headers,
                json_data,
                screen_target_name[index],
                message_queue
            )
        )

        processes.append(p)
        p.start()

        time.sleep(1)


    # Discord 봇 실행
    run_cgv_open_push_discord_bot()


# ==================================================
# Windows multiprocessing 필수
# ==================================================

if __name__ == "__main__":

    multiprocessing.freeze_support()

    atexit.register(
        send_stopped_message
    )

    main()